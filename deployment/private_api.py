"""OCI API with capability-isolated browser workspaces and durable PDF ingestion."""
import hashlib
import json
import os
import re
import secrets
import threading
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import pdfplumber
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from app.answering import answer_question
from app.extraction import extract_pdf, normalize, summarize
from app.validation import validate
from app.retrieval import chunks_from_pages

ROOT=Path(__file__).resolve().parents[1]
SEED=json.loads((ROOT/'evidence.json').read_text())
STORE=ROOT/'private-data'
STORE.mkdir(mode=0o700,exist_ok=True)
LOCK=threading.BoundedSemaphore(2)
app=FastAPI()

def workspace(request):
    token=request.headers.get('x-workspace','')
    if not re.fullmatch(r'[a-f0-9]{64}',token):raise HTTPException(401,'Open the application to start your private browser workspace')
    folder=STORE/hashlib.sha256(token.encode()).hexdigest()
    folder.mkdir(mode=0o700,exist_ok=True)
    return folder

def save(path,data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data),encoding='utf-8');temp.replace(path)

def load(request,doc_id):
    if doc_id==SEED['metadata']['id']:return SEED,ROOT/'sample-report.pdf'
    if not re.fullmatch(r'[a-f0-9]{24}',doc_id):raise HTTPException(404,'Report not found')
    folder=workspace(request);path=folder/(doc_id+'.json')
    if not path.exists():raise HTTPException(404,'Report not found in this browser workspace')
    return json.loads(path.read_text()),folder/(doc_id+'.pdf')

def process(path,record):
    with LOCK:
        try:
            meta=record['metadata'];meta.update(status='processing',stage='Extracting pages and tables',progress=10)
            save(path,record)
            pages=extract_pdf(path.with_suffix('.pdf'))
            facts,assumptions,warnings=normalize(pages)
            for f in facts:f['source'].update(document_id=meta['id'],filename=meta['filename'])
            issues=validate(facts,pages)
            title=pages[0]['section'][:160]
            synthetic=any('fictional' in p['text'].lower() or 'synthetic' in p['text'].lower() for p in pages[:3])
            payload={'title':title,'pages':pages,'facts':facts,'issues':issues,'assumptions':assumptions,'chunks':chunks_from_pages(pages),'synthetic':synthetic,**summarize(facts),'nav_unit':'NAV units · See source for currency','extraction_warnings':warnings,'extraction':{'stages':[{'name':'Extract and preserve evidence','description':'Original PDF, text, table cells, and coordinates retained','duration_ms':0},{'name':'Normalize and validate','description':'Source facts preserved independently of calculated findings','duration_ms':0}],'retrieval_description':'BM25 keyword retrieval over this report’s page-aware passages.','ocr_description':'Low-text pages are flagged when OCR is unavailable.'}}
            meta.update(status='completed',stage='Ready',progress=100,page_count=len(pages),fact_count=len(facts),issue_count=len(issues),table_count=sum(len(p['tables']) for p in pages),synthetic=synthetic)
            record['payload']=payload;save(path,record)
        except Exception as exc:
            record['metadata'].update(status='failed',stage='Extraction failed',error=str(exc)[:300]);save(path,record)

@app.api_route('/{path:path}',methods=['GET','POST','PATCH'])
async def route(path:str,request:Request,tasks:BackgroundTasks):
    url=request.url.path
    if url=='/health':return {'status':'ok','mode':'OCI private browser workspaces','oci_connected':True,'uploads_enabled':True}
    if url=='/documents' and request.method=='GET':
        folder=workspace(request)
        return [json.loads(p.read_text())['metadata'] for p in sorted(folder.glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)]+[SEED['metadata']]
    if url=='/documents/upload' and request.method=='POST':
        folder=workspace(request)
        if len(list(folder.glob('*.json')))>=10:raise HTTPException(409,'This workspace has reached its 10-report limit')
        if sum(p.stat().st_size for p in STORE.rglob('*') if p.is_file())>1024**3:raise HTTPException(503,'Upload storage is currently full')
        if int(request.headers.get('content-length','0'))>4*1024**2:raise HTTPException(413,'Hosted PDFs must be smaller than 4 MB')
        form=await request.form();file=form.get('file')
        if not file or not getattr(file,'filename','').lower().endswith('.pdf'):raise HTTPException(415,'Choose a PDF file')
        content=await file.read(4*1024**2+1)
        if len(content)>4*1024**2:raise HTTPException(413,'Hosted PDFs must be smaller than 4 MB')
        if not content.startswith(b'%PDF-'):raise HTTPException(422,'The file is not a valid PDF')
        try:
            with pdfplumber.open(BytesIO(content)) as pdf:
                if not 1<=len(pdf.pages)<=200:raise ValueError()
        except Exception:raise HTTPException(422,'The PDF is damaged, encrypted, or exceeds 200 pages')
        digest=hashlib.sha256(content).hexdigest();doc_id=digest[:24];target=folder/(doc_id+'.json')
        if target.exists():return {**json.loads(target.read_text())['metadata'],'duplicate':True}
        (folder/(doc_id+'.pdf')).write_bytes(content)
        meta={'id':doc_id,'filename':Path(file.filename).name[:255],'checksum':digest,'status':'queued','stage':'Queued','progress':0,'page_count':0,'uploaded_at':datetime.now(timezone.utc).isoformat(),'error':None,'pipeline_version':'1.1.0','fact_count':0,'issue_count':0,'table_count':0,'synthetic':False}
        save(target,{'metadata':meta,'payload':{}});tasks.add_task(process,target,{'metadata':meta,'payload':{}})
        return {**meta,'duplicate':False}
    if url=='/chat/query' and request.method=='POST':
        body=await request.json();record,_=load(request,body.get('document_id',''));question=body.get('question','')
        if not isinstance(question,str) or not 2<=len(question.strip())<=2000:raise HTTPException(422,'Enter a question between 2 and 2000 characters')
        if record['metadata']['status']!='completed':raise HTTPException(409,'The report is still processing')
        return answer_question(record['payload'],question,record['metadata']['id'])
    match=re.fullmatch(r'/documents/([a-f0-9]{24})(.*)',url)
    if not match:raise HTTPException(404,'Not found')
    doc_id,suffix=match.groups();record,original=load(request,doc_id);meta=record['metadata'];p=record['payload']
    if suffix in {'','/status'}:return meta
    if meta['status']!='completed':raise HTTPException(409,'The report has not finished processing')
    if suffix=='/overview':return {'document':meta,**{k:p[k] for k in ['title','facts','issues','annual','forecast','allocations','nav_unit','extraction']},'pages':[{**{k:x[k] for k in ['number','section','char_count','method','warnings']},'table_count':len(x['tables'])} for x in p['pages']]}
    if suffix.startswith('/validation/') and request.method=='PATCH':
        if doc_id==SEED['metadata']['id']:raise HTTPException(409,'The shared sample is read-only. Upload your own PDF to save review decisions.')
        body=await request.json();status=body.get('status')
        if status not in {'open','reviewed'}:raise HTTPException(422,'Choose open or reviewed')
        issue=next((i for i in p['issues'] if i['id']==suffix.split('/')[-1]),None)
        if not issue:raise HTTPException(404,'Finding not found')
        issue['status']=status;save(workspace(request)/(doc_id+'.json'),record)
        return issue
    if suffix=='/validation':return p['issues']
    if suffix=='/metrics':return p['facts']
    if suffix=='/file':return FileResponse(original,media_type='application/pdf',filename=meta['filename'],content_disposition_type='inline')
    if suffix=='/export':return JSONResponse({'document':meta,**p})
    m=re.fullmatch(r'/pages/(\d+)(/image)?',suffix)
    if m:
        number=int(m[1])
        if not 1<=number<=meta['page_count']:raise HTTPException(404,'Page not found')
        if m[2]:
            cache=original.parent/(doc_id+'-pages');cache.mkdir(exist_ok=True)
            image=cache/(str(number)+'.png')
            if not image.exists():
                with pdfplumber.open(original) as pdf:pdf.pages[number-1].to_image(resolution=100).save(image)
            return FileResponse(image,media_type='image/png',headers={'Cache-Control':'private, no-store'})
        return p['pages'][number-1]
    raise HTTPException(404,'Not found')
