"""Read-only interview API. Persistent uploads belong to the OCI backend."""
import json
import secrets
import re
from pathlib import Path
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import JSONResponse, Response, FileResponse
from app.answering import answer_question
data=json.loads((Path(__file__).resolve().parents[1]/'evidence.json').read_text())
meta=data['metadata'];payload=data['payload']
app=FastAPI()

@app.api_route('/{path:path}',methods=['GET','POST','PATCH'])
async def route(path:str,request:Request):
    url=request.query_params.get("route",request.url.path)
    root=Path(__file__).resolve().parents[1]
    if url=='/':
        html=(root/'ui/index.html').read_text().replace('Local, private workspace','Private browser workspace').replace('Local workspace','Private browser workspace').replace('Up to 25 MB','Up to 4 MB').replace('<body>','<body data-hosted="vercel">')
        return Response(html,media_type='text/html')
    if url in {'/static/app.js','/static/style.css','/static/favicon.svg'}:
        target=root/'ui'/url.split('/')[-1]
        if url.endswith('.js'):return Response(target.read_text().replace('25*1024*1024','4*1024*1024').replace('smaller than 25 MB','smaller than 4 MB'),media_type='application/javascript')
        return FileResponse(target)
    if url in {'/deck.html','/interview-preparation.html'}:return FileResponse(root/'docs'/url[1:])
    if request.method=='POST':
        if url.endswith('/upload'):raise HTTPException(409,'Uploads require the persistent OCI backend, which is not connected yet')
        body=await request.json();question=body.get('question','')
        if body.get('document_id')!=meta['id']:raise HTTPException(404,'Document not found')
        if not isinstance(question,str) or not 2<=len(question.strip())<=2000:raise HTTPException(422,'Enter a question between 2 and 2000 characters')
        request_payload=payload
        vendor=body.get('provider');api_key=body.get('api_key')
        if vendor or api_key:
            if vendor not in {'openai','anthropic'} or not isinstance(api_key,str) or not 20<=len(api_key)<=300:
                raise HTTPException(422,'Connect a valid OpenAI or Anthropic key first')
            # Never retain a browser-supplied API key on the module-level sample payload.
            request_payload={**payload,'_llm_credentials':{'provider':vendor,'api_key':api_key}}
        return answer_question(request_payload,question,meta['id'])
    if request.method=='PATCH':raise HTTPException(409,'Persistent review requires the OCI backend')
    if url=='/health':return {'status':'ok','mode':'Vercel sample with per-request AI keys','oci_connected':False,'uploads_enabled':False}
    if url=='/documents':return [meta]
    if not url.startswith('/documents/'+meta['id']):raise HTTPException(404,'Not found')
    suffix=url.split(meta['id'],1)[1]
    if suffix in {'','/status'}:return meta
    if suffix=='/overview':
        return {'document':meta,**{k:payload[k] for k in ['title','facts','issues','annual','forecast','allocations','nav_unit','extraction']},'pages':[{**{k:p[k] for k in ['number','section','char_count','method','warnings']},'table_count':len(p['tables'])} for p in payload['pages']]}
    if suffix=='/validation':return payload['issues']
    if suffix=='/metrics':return [f for f in payload['facts'] if all(f.get(k)==v for k,v in request.query_params.items() if k in {'metric','period','classification'})]
    if suffix=='/export':return JSONResponse({'document':meta,**payload},headers={'Content-Disposition':'attachment; filename="sample-evidence.json"'})
    if suffix=='/file':
        sample=root/'public'/'sample-report.pdf'
        if sample.exists():return FileResponse(sample,media_type='application/pdf',filename=meta.get('filename','sample-report.pdf'),content_disposition_type='inline')
        raise HTTPException(404,'Sample PDF not available')
    if suffix.startswith('/pages/'):
        try:n=int(suffix.split('/')[2])
        except ValueError:raise HTTPException(404,'Not found')
        if not 1<=n<=len(payload['pages']):raise HTTPException(404,'Not found')
        if suffix.endswith('/image'):
            image=root/'public'/'pages'/f'{n}.png'
            if image.exists():return FileResponse(image,media_type='image/png',headers={'Cache-Control':'public, max-age=86400'})
            raise HTTPException(404,'Page image not available')
        return payload['pages'][n-1]
    raise HTTPException(404,'Not found')
