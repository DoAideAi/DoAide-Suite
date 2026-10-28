import json
import secrets
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .catalog import CATALOG, PRODUCTS
from .db import database, initialize, password_hash, password_matches, token_hash
from .domain import DomainError, calculate
from .migrations import ensure_workspace, record_access, permit, invalidate
from .auth_lifecycle import install_auth_lifecycle, queue_auth, verification_required

ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Credentials(StrictModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=12, max_length=256)


class RecordInput(StrictModel):
    title: str = Field(min_length=1, max_length=160)
    payload: dict
    version: int | None = Field(default=None, ge=1)


class StatusInput(StrictModel):
    status: str
    version: int = Field(ge=1)


def create_app(db_path=None):
    @asynccontextmanager
    async def lifespan(app):
        initialize(db_path)
        from .logging_config import install_private_access_logging
        install_private_access_logging()
        yield

    app = FastAPI(title="DoAide Suite", version="0.5.0", lifespan=lifespan)
    from .security import RequestBoundary
    app.add_middleware(RequestBoundary,path=db_path)

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        # Browser mutations must originate from this app or the local Vite editor.
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            allowed = {str(request.base_url).rstrip("/"), "http://127.0.0.1:5173", "http://localhost:5173"}
            if origin and origin not in allowed:
                return JSONResponse({"detail": "Cross-origin mutation rejected"}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": "Cross-site mutation rejected"}, status_code=403)
            limit = 10_600_000 if request.url.path.endswith(('/files','/report')) else 512_000
            if request.headers.get("content-length", "0").isdigit() and int(request.headers.get("content-length", "0")) > limit:
                return JSONResponse({"detail": "Request is too large"}, status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        response.headers['Permissions-Policy']='camera=(self), microphone=(self), geolocation=()'
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    def current_user(request: Request):
        token = request.cookies.get("doaide_session", "")
        with database(db_path) as db:
            user = db.execute("SELECT users.id, users.email FROM users JOIN sessions ON sessions.user_id = users.id WHERE sessions.token_hash = ? AND sessions.expires_at > ?", (token_hash(token), int(time.time()))).fetchone()
            if not user:
                raise HTTPException(401, "Sign in to your workspace")
            verified=db.execute('SELECT email_verified_at FROM user_flags WHERE user_id=?',(user['id'],)).fetchone()
            if verification_required() and (not verified or not verified['email_verified_at']):
                raise HTTPException(403,'Verify your email before accessing this workspace')
            workspace_id = request.headers.get('X-Workspace-ID') or request.cookies.get('doaide_workspace') or user['id']
            membership = db.execute('SELECT role FROM memberships WHERE workspace_id=? AND user_id=?', (workspace_id, user['id'])).fetchone()
            if not membership:
                raise HTTPException(403, 'Workspace membership is required')
            access=db.execute('SELECT fees_mode FROM member_access WHERE workspace_id=? AND user_id=?',(workspace_id,user['id'])).fetchone()
        return {**dict(user), 'workspace_id': workspace_id, 'role': membership['role'], 'fees_access':access[0] if access and membership['role']!='owner' else 'financial'}

    def rate_limit(request):
        ip = request.client.host if request.client else "unknown"
        timestamp = int(time.time())
        with database(db_path) as db:
            db.execute("DELETE FROM auth_attempts WHERE at < ?", (timestamp - 600,))
            count = db.execute("SELECT count(*) FROM auth_attempts WHERE ip = ?", (ip,)).fetchone()[0]
            if count >= 20:
                raise HTTPException(429, "Too many attempts. Try again in ten minutes.")
            db.execute("INSERT INTO auth_attempts VALUES (?, ?)", (ip, timestamp))

    def session(user, request, response):
        token = secrets.token_urlsafe(32)
        with database(db_path) as db:
            db.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
            db.execute("INSERT INTO sessions VALUES (?, ?, ?)", (token_hash(token), user["id"], int(time.time()) + 43200))
        response.set_cookie("doaide_session", token, max_age=43200, httponly=True, samesite="strict", secure=request.url.scheme == "https")
        response.delete_cookie('doaide_workspace')
        return {"id": user["id"], "email": user["email"]}

    @app.get("/api/health")
    def health():
        with database(db_path) as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok", "stage": "local-development", "products": len(PRODUCTS)}

    @app.post("/api/auth/register", status_code=201)
    def register(credentials: Credentials, request: Request, response: Response):
        rate_limit(request)
        email = credentials.email.strip().lower()
        if "@" not in email or " " in email or email.startswith("@") or email.endswith("@"):
            raise HTTPException(422, "Enter a valid email address")
        user = {"id": str(uuid4()), "email": email}
        try:
            with database(db_path) as db:
                db.execute("INSERT INTO users VALUES (?, ?, ?, ?)", (user["id"], email, password_hash(credentials.password), now()))
                ensure_workspace(db, {**user, 'created_at': now()})
                if verification_required():queue_auth(db,user,'verify')
        except sqlite3.IntegrityError:
            raise HTTPException(409, "This email already has a local account")
        if verification_required():return {**user,'verification_required':True,'message':'Account created. Use the verification link from the configured email service, then sign in.'}
        return session(user, request, response)

    @app.post("/api/auth/login")
    def login(credentials: Credentials, request: Request, response: Response):
        rate_limit(request)
        with database(db_path) as db:
            user = db.execute("SELECT * FROM users WHERE email = ?", (credentials.email.strip().lower(),)).fetchone()
        if not user or not password_matches(credentials.password, user["password_hash"]):
            raise HTTPException(401, "Email or password is incorrect")
        if verification_required():
            with database(db_path) as db:
                verified=db.execute('SELECT email_verified_at FROM user_flags WHERE user_id=?',(user['id'],)).fetchone()
                if not verified or not verified['email_verified_at']:raise HTTPException(403,'Verify your email first. You can request a new verification link below.')
        return session(user, request, response)

    @app.get("/api/auth/me")
    def me(user=Depends(current_user)):
        return user

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response):
        with database(db_path) as db:
            db.execute("DELETE FROM sessions WHERE token_hash = ?", (token_hash(request.cookies.get("doaide_session", "")),))
        response.delete_cookie("doaide_session")
        return {"ok": True}

    @app.get("/api/products")
    def products(user=Depends(current_user)):
        return PRODUCTS

    @app.get("/api/products/{slug}/scope")
    def product_scope(slug: str, user=Depends(current_user)):
        require_product(slug)
        path = ROOT / "docs" / "scopes" / f"{slug}.md"
        if not path.is_file():
            raise HTTPException(503, "Scope document is not installed")
        return {"markdown": path.read_text()}

    def require_product(slug):
        if slug not in CATALOG:
            raise HTTPException(404, "Product not found")

    def owned_record(db, record_id, user):
        return record_access(db, record_id, user)

    def serialize(row, with_result=True):
        result = {k: v for k, v in dict(row).items() if k != "user_id"}
        result["payload"] = json.loads(result["payload"])
        if with_result:
            _, result["result"] = calculate(result["product"], result["payload"])
        return result

    def audit(db, record, action, actor):
        db.execute("INSERT INTO audit_events(record_id, user_id, action, version, snapshot, created_at) VALUES (?, ?, ?, ?, ?, ?)", (record["id"], actor['id'], action, record["version"], json.dumps(serialize(record, False)), now()))

    @app.get("/api/records")
    def list_records(product: str | None = None, offset: int = 0, limit: int = 500, user=Depends(current_user)):
        if offset < 0 or not 1 <= limit <= 500:
            raise HTTPException(422, 'Invalid pagination')
        with database(db_path) as db:
            restriction=" AND r.product!='fees'" if user.get('fees_access')=='academic' else ''
            if product:
                require_product(product)
                records = db.execute("SELECT r.* FROM records r JOIN record_workspaces w ON w.record_id=r.id WHERE w.workspace_id=? AND r.product=?"+restriction+" ORDER BY r.updated_at DESC,r.id LIMIT ? OFFSET ?", (user['workspace_id'], product, limit, offset)).fetchall()
            else:
                records = db.execute("SELECT r.* FROM records r JOIN record_workspaces w ON w.record_id=r.id WHERE w.workspace_id=?"+restriction+" ORDER BY r.updated_at DESC,r.id LIMIT ? OFFSET ?", (user['workspace_id'], limit, offset)).fetchall()
        return [serialize(row, False) for row in records]

    @app.post("/api/products/{slug}/preview")
    def preview(slug: str, payload: dict, user=Depends(current_user)):
        require_product(slug)
        return calculate(slug, payload)[1]

    @app.post("/api/products/{slug}/records", status_code=201)
    def create_record(slug: str, body: RecordInput, user=Depends(current_user)):
        permit(user, 'owner', 'operator', 'reviewer')
        require_product(slug)
        if not body.title.strip():
            raise HTTPException(422, "Record title is required")
        if slug=='fees' and user.get('fees_access')=='academic':raise HTTPException(403,'Financial access is required to create fee agreements')
        payload, result = calculate(slug, body.payload)
        record = {"id": str(uuid4()), "user_id": user["id"], "product": slug, "title": body.title.strip(), "payload": json.dumps(payload), "status": "draft", "version": 1, "created_at": now(), "updated_at": now()}
        with database(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            from .commercial import admit
            admit(db, user['workspace_id'], 'records', product=slug)
            db.execute("INSERT INTO records VALUES (:id, :user_id, :product, :title, :payload, :status, :version, :created_at, :updated_at)", record)
            db.execute('INSERT INTO record_workspaces VALUES (?,?)', (record['id'], user['workspace_id']))
            audit(db, record, "created", user)
        return serialize(record)

    @app.get("/api/records/{record_id}")
    def get_record(record_id: str, user=Depends(current_user)):
        with database(db_path) as db:
            return serialize(owned_record(db, record_id, user))

    @app.put("/api/records/{record_id}")
    def update_record(record_id: str, body: RecordInput, user=Depends(current_user)):
        permit(user, 'owner', 'operator', 'reviewer')
        if not body.title.strip():
            raise HTTPException(422, "Record title is required")
        with database(db_path) as db:
            db.execute('BEGIN IMMEDIATE')
            record = owned_record(db, record_id, user)
            from .operations import editable_record
            editable_record(db, record)
            if record["status"] == "archived":
                raise HTTPException(409, "Restore an archived record to draft before editing")
            if body.version != record["version"]:
                raise HTTPException(409, "This record changed in another window. Reload it before saving.")
            payload, _ = calculate(record["product"], body.payload)
            record.update(title=body.title.strip(), payload=json.dumps(payload), status="draft", version=record["version"] + 1, updated_at=now())
            changed = db.execute("UPDATE records SET title=:title, payload=:payload, status=:status, version=:version, updated_at=:updated_at WHERE id=:id AND user_id=:user_id AND version=:previous", {**record, "previous": body.version}).rowcount
            if not changed:
                raise HTTPException(409, "Concurrent update; reload before saving")
            audit(db, record, "updated", user)
            invalidate(db, record_id)
            if record['product']=='renew':
                from .renewals import refresh
                refresh(db,record,user)
        return serialize(record)

    @app.post("/api/records/{record_id}/status")
    def change_status(record_id: str, body: StatusInput, user=Depends(current_user)):
        permit(user, 'owner', 'reviewer')
        allowed = {"draft": {"reviewed", "archived"}, "reviewed": {"draft", "archived"}, "archived": {"draft"}}
        with database(db_path) as db:
            record = owned_record(db, record_id, user)
            if body.version != record["version"]:
                raise HTTPException(409, "This record changed; reload before updating its status")
            if body.status not in allowed[record["status"]]:
                raise HTTPException(409, "Invalid status transition")
            if body.status == "reviewed":
                _, result = calculate(record["product"], json.loads(record["payload"]))
                if result["blockers"]:
                    raise HTTPException(422, "Resolve review checks first: " + " ".join(result["blockers"]))
            record.update(status=body.status, version=record["version"] + 1, updated_at=now())
            changed = db.execute("UPDATE records SET status=:status, version=:version, updated_at=:updated_at WHERE id=:id AND user_id=:user_id AND version=:previous", {**record, "previous": body.version}).rowcount
            if not changed:
                raise HTTPException(409, "Concurrent update; reload before changing status")
            if body.status=='archived':
                from .operations import get_state,items
                state=get_state(db,record_id)
                if state['data'].get('authority_pending') or any(i['data'].get('_scheduler_reference') and i['data'].get('_status') not in ('completed','verified','booking-cancelled','booking-no_show','booking-missing') for i in items(db,record_id,'visit')):
                    raise HTTPException(409,'Resolve connected stock commands and close Scheduler appointments before archiving')
                operational=db.execute('SELECT stage FROM operations WHERE record_id=?',(record_id,)).fetchone()
                if operational and operational['stage'] in ('reserved','materials-reserved'):
                    raise HTTPException(409,'Release stock reservations before archiving this record')
            audit(db, record, body.status, user)
        return serialize(record)

    @app.get("/api/records/{record_id}/audit")
    def get_audit(record_id: str, user=Depends(current_user)):
        with database(db_path) as db:
            owned_record(db, record_id, user)
            rows = db.execute("SELECT action, version, snapshot, created_at FROM audit_events WHERE record_id = ? ORDER BY id DESC", (record_id,)).fetchall()
        return [{**dict(row), "snapshot": json.loads(row["snapshot"])} for row in rows]

    @app.get("/api/records/{record_id}/export")
    def export(record_id: str, user=Depends(current_user)):
        with database(db_path) as db:
            record = serialize(owned_record(db, record_id, user))
        return JSONResponse({"exported_at": now(), "stage": "internal-draft", "record": record}, headers={"Content-Disposition": f'attachment; filename="doaide-{record["product"]}-{record_id}.json"'})

    from .operations_api import install_operations
    install_operations(app, db_path, current_user)
    from .billing import install_billing
    install_billing(app, db_path, current_user)
    from .reports import install_reports
    install_reports(app, db_path, current_user)
    from .inventory import install_inventory
    install_inventory(app, db_path, current_user)
    from .diagnostics import install_diagnostics
    install_diagnostics(app, db_path, current_user)
    from .access import install_access
    install_access(app,db_path,current_user)
    from .recordings import install_recordings
    install_recordings(app,db_path,current_user)
    from .whatsapp import install_whatsapp
    install_whatsapp(app,db_path)
    install_auth_lifecycle(app, db_path, rate_limit)

    dist = ROOT / "frontend" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")

    return app


app = create_app()
