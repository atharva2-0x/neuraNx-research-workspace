"""Read-only interview API. Persistent uploads belong to the OCI backend."""
import json
import os
import secrets
import re
import httpx
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import JSONResponse, Response
from app.answering import answer_question
data=json.loads((Path(__file__).resolve().parents[1]/'evidence.json').read_text())
meta=data['metadata'];payload=data['payload']
app=FastAPI()
backend_file=Path(__file__).resolve().parents[1]/'backend.json'
BACKEND_ORIGIN=os.getenv('BACKEND_ORIGIN') or (json.loads(backend_file.read_text())['origin'] if backend_file.exists() else '')

@app.api_route('/{path:path}',methods=['GET','POST','PATCH'])
async def route(path:str,request:Request):
    url=request.query_params.get("route",request.url.path)
    if BACKEND_ORIGIN:
        token=request.cookies.get('fund_workspace','')
        if not re.fullmatch(r'[a-f0-9]{64}',token):token=secrets.token_hex(32)
        async with httpx.AsyncClient(timeout=55) as client:
            response=await client.request(request.method,BACKEND_ORIGIN+url,params={k:v for k,v in request.query_params.items() if k!='route'},content=await request.body(),headers={'Content-Type':request.headers.get('content-type','application/json'),'X-Workspace':token})
        result=Response(response.content,status_code=response.status_code,headers={'Content-Type':response.headers.get('content-type','application/json'),'X-Backend':'OCI','Cache-Control':'private, no-store'})
        result.set_cookie('fund_workspace',token,max_age=60*60*24*30,httponly=True,secure=True,samesite='lax')
        return result
    if request.method=='POST':
        if url.endswith('/upload'):raise HTTPException(409,'Uploads require the persistent OCI backend, which is not connected yet')
        body=await request.json();question=body.get('question','')
        if body.get('document_id')!=meta['id']:raise HTTPException(404,'Document not found')
        if not isinstance(question,str) or not 2<=len(question.strip())<=2000:raise HTTPException(422,'Enter a question between 2 and 2000 characters')
        return answer_question(payload,question,meta['id'])
    if request.method=='PATCH':raise HTTPException(409,'Persistent review requires the OCI backend')
    if url=='/health':return {'status':'ok','mode':'read-only Vercel demo','oci_connected':False}
    if url=='/documents':return [meta]
    if not url.startswith('/documents/'+meta['id']):raise HTTPException(404,'Not found')
    suffix=url.split(meta['id'],1)[1]
    if suffix in {'','/status'}:return meta
    if suffix=='/overview':
        return {'document':meta,**{k:payload[k] for k in ['title','facts','issues','annual','forecast','allocations','nav_unit','extraction']},'pages':[{**{k:p[k] for k in ['number','section','char_count','method','warnings']},'table_count':len(p['tables'])} for p in payload['pages']]}
    if suffix=='/validation':return payload['issues']
    if suffix=='/metrics':return [f for f in payload['facts'] if all(f.get(k)==v for k,v in request.query_params.items() if k in {'metric','period','classification'})]
    if suffix=='/export':return JSONResponse({'document':meta,**payload},headers={'Content-Disposition':'attachment; filename="sample-evidence.json"'})
    if suffix.startswith('/pages/'):
        try:n=int(suffix.split('/')[2])
        except ValueError:raise HTTPException(404,'Not found')
        if not 1<=n<=len(payload['pages']):raise HTTPException(404,'Not found')
        return payload['pages'][n-1]
    raise HTTPException(404,'Not found')
