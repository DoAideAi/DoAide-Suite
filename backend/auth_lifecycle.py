"""One-use email verification and recovery; opaque tokens, throttled requests and session revocation."""
import json
import os
import secrets
import time
from urllib.parse import urlencode
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from .db import database,password_hash,token_hash
from .operations import now,uid,dump


def verification_required():return os.environ.get('DOAIDE_REQUIRE_VERIFIED_EMAIL','false')=='true'


def queue_auth(db,user,purpose):
    token=secrets.token_urlsafe(32);lifetime=3600 if purpose=='reset' else 86400
    # A newer email replaces outstanding tokens for this purpose.
    db.execute('UPDATE auth_tokens SET used_at=? WHERE user_id=? AND purpose=? AND used_at IS NULL',(now(),user['id'],purpose))
    db.execute('INSERT INTO auth_tokens VALUES (?,?,?,?,NULL)',(token_hash(token),user['id'],purpose,int(time.time())+lifetime))
    url=os.environ.get('DOAIDE_PUBLIC_URL','http://127.0.0.1:8012').rstrip('/')+'/?'+urlencode({'auth':purpose,'token':token})
    identifier=uid();data={'recipient':user['email'],'subject':'Reset your DoAide password' if purpose=='reset' else 'Verify your DoAide email','message':('Reset your password' if purpose=='reset' else 'Verify your email')+' using this one-use link:\n\n'+url+f'\n\nThis link expires in {lifetime//3600} hour(s).','expires_at':int(time.time())+lifetime,'token_hash':token_hash(token)}
    db.execute('INSERT INTO jobs(id,workspace_id,record_id,kind,dedupe_key,data,due_at,created_at,updated_at) VALUES (?,?,NULL,?,?,?,?,?,?)',(identifier,user['id'],'auth-email','auth:'+identifier,dump(data),now(),now(),now()))
    return identifier


class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class EmailRequest(Strict):email:str=Field(min_length=5,max_length=254)
class TokenRequest(Strict):token:str=Field(min_length=32,max_length=200)
class ResetRequest(TokenRequest):password:str=Field(min_length=12,max_length=256)


def install_auth_lifecycle(app,path,rate_limit):
    @app.get('/api/auth/options')
    def options():return {'verification_required':verification_required()}

    def request_link(body,request,purpose):
        rate_limit(request)
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE');user=db.execute('SELECT id,email FROM users WHERE email=?',(body.email.strip().lower(),)).fetchone()
            if user:
                verified=db.execute('SELECT email_verified_at FROM user_flags WHERE user_id=?',(user['id'],)).fetchone()
                if purpose!='verify' or not verified or not verified['email_verified_at']:queue_auth(db,dict(user),purpose)
        return {'message':'If this account is eligible, a one-use link is queued for the configured email service.'}

    @app.post('/api/auth/request-verification')
    def request_verification(body:EmailRequest,request:Request):return request_link(body,request,'verify')

    @app.post('/api/auth/request-reset')
    def request_reset(body:EmailRequest,request:Request):return request_link(body,request,'reset')

    def consume(db,token,purpose):
        row=db.execute('SELECT * FROM auth_tokens WHERE token_hash=? AND purpose=? AND expires_at>? AND used_at IS NULL',(token_hash(token),purpose,int(time.time()))).fetchone()
        if not row:raise HTTPException(422,'This link is invalid, expired or already used. Request a new one.')
        db.execute('UPDATE auth_tokens SET used_at=? WHERE token_hash=?',(now(),token_hash(token)))
        return row['user_id']

    @app.post('/api/auth/verify')
    def verify(body:TokenRequest,request:Request):
        rate_limit(request)
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE');user_id=consume(db,body.token,'verify')
            db.execute('INSERT INTO user_flags VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET email_verified_at=excluded.email_verified_at',(user_id,now()))
        return {'message':'Email verified. You can sign in.'}

    @app.post('/api/auth/reset')
    def reset(body:ResetRequest,request:Request):
        rate_limit(request)
        hashed=password_hash(body.password)
        with database(path) as db:
            db.execute('BEGIN IMMEDIATE');user_id=consume(db,body.token,'reset')
            db.execute('UPDATE users SET password_hash=? WHERE id=?',(hashed,user_id))
            db.execute('DELETE FROM sessions WHERE user_id=?',(user_id,))
            db.execute('UPDATE auth_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL',(now(),user_id))
        return {'message':'Password updated and previous sessions revoked. Sign in with your new password.'}
