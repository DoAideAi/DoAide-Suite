"""Bound streamed request bodies and share rate counters across API processes."""
import hashlib
import os
import time
from starlette.responses import JSONResponse
from .db import database


class RequestBoundary:
    def __init__(self,app,path=None):self.app,self.path=app,path

    async def __call__(self,scope,receive,send):
        if scope['type']!='http' or not scope['path'].startswith('/api/'):
            await self.app(scope,receive,send);return
        path=scope['path'];headers=dict(scope.get('headers',[]))
        limit=10_600_000 if path.endswith(('/files','/report','/recordings','/start')) else 512_000
        client=(scope.get('client') or ('unknown',))[0]
        # Ignore forwarded headers: only the trusted ASGI client address keys limits.
        public=path.startswith(('/api/portal/','/api/contractor/','/api/webhooks/'))
        budget=int(os.environ.get('DOAIDE_PUBLIC_REQUESTS_PER_MINUTE' if public else 'DOAIDE_API_REQUESTS_PER_MINUTE','120' if public else '600'))
        window=int(time.time())//60;bucket=hashlib.sha256((str(client)+(':public' if public else ':api')).encode()).hexdigest()
        with database(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM request_limits WHERE window<?',(window-2,))
            db.execute('INSERT INTO request_limits VALUES (?,?,1) ON CONFLICT(bucket) DO UPDATE SET count=CASE WHEN window=excluded.window THEN count+1 ELSE 1 END,window=excluded.window',(bucket,window))
            count=db.execute('SELECT count FROM request_limits WHERE bucket=?',(bucket,)).fetchone()[0]
        if count>max(1,budget):
            await JSONResponse({'detail':'Request limit reached. Try again shortly.'},429,headers={'Retry-After':str(60-int(time.time())%60)})(scope,receive,send);return
        if scope['method'] in ('POST','PUT','PATCH','DELETE'):
            try:declared=int(headers.get(b'content-length',b'0'))
            except ValueError:declared=limit+1
            if declared>limit:
                await JSONResponse({'detail':'Request is too large'},413)(scope,receive,send);return
        if scope['method'] not in ('POST','PUT','PATCH','DELETE'):
            await self.app(scope,receive,send);return
        # Bound and buffer before routing so a parser cannot swallow a size error.
        chunks=[];received=0
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            chunk=message.get('body',b'');received+=len(chunk)
            if received>limit:
                await JSONResponse({'detail':'Request is too large'},413)(scope,receive,send);return
            chunks.append(chunk)
            if not message.get('more_body',False):break
        body=b''.join(chunks);replayed=False
        async def bounded_receive():
            nonlocal replayed
            if not replayed:
                replayed=True
                return {'type':'http.request','body':body,'more_body':False}
            return await receive()
        await self.app(scope,bounded_receive,send)
