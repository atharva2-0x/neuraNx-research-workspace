import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Literal
import pdfplumber
from fastapi import FastAPI, UploadFile, File, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import select, text
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from app.db import DATA_DIR, Session, Document, FactRecord, ValidationRecord, QueryLog, CalculationRecord, engine, initialize, metadata
from app.pipeline import register, run_pipeline, pdf_path
from app.models import Query
from app.answering import answer_question

ROOT=Path(__file__).resolve().parent.parent
logger=logging.getLogger("fund.api")
logging.basicConfig(level=logging.INFO,format="%(asctime)s %(name)s %(levelname)s %(message)s")
MAX_UPLOAD=int(os.getenv("MAX_UPLOAD_MB","25"))*1024*1024


@asynccontextmanager
async def lifespan(app):
    initialize()
    with Session() as session:
        for doc in session.scalars(select(Document).where(Document.status.in_(["queued","processing"]))):
            doc.status="failed";doc.stage="Interrupted";doc.error="The process stopped before extraction completed. Retry this document to resume from its original PDF."
        session.commit()
    # A local source in data/input bootstraps the interview demo. No fixture facts.
    if os.getenv("AUTO_INGEST","true").lower()=="true":
        for path in (DATA_DIR/"input").glob("*.pdf"):
            doc_id,duplicate=register(path.read_bytes(),path.name)
            if not duplicate:run_pipeline(doc_id)
    yield


app=FastAPI(title="Fund Evidence API",version="1.0.0",description="Evidence-preserving financial PDF intelligence. All demo fund data is synthetic.",lifespan=lifespan)


@app.middleware("http")
async def tracing(request:Request,call_next):
    request_id=uuid.uuid4().hex[:16]
    started=time.perf_counter()
    response=await call_next(request)
    response.headers["X-Request-ID"]=request_id
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["Referrer-Policy"]="same-origin"
    response.headers["X-Frame-Options"]="DENY"
    if request.url.path not in {"/docs","/redoc","/docs/oauth2-redirect"}:
        response.headers["Content-Security-Policy"]="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    if not request.url.path.startswith("/static"):
        logger.info(json.dumps({"event":"request","request_id":request_id,"method":request.method,"path":request.url.path,"status":response.status_code,"latency_ms":int((time.perf_counter()-started)*1000)}))
    return response


def get_document(document_id,ready=False):
    with Session() as session:
        doc=session.get(Document,document_id)
        if not doc:raise HTTPException(404,"Document not found")
        if ready and doc.status!="completed":raise HTTPException(409,"This document has not finished processing")
        return doc


@app.get("/health")
def health():
    with engine.connect() as connection:connection.execute(text("SELECT 1"))
    return {"status":"ok","database":engine.dialect.name,"pipeline_version":"1.0.0"}


@app.get("/documents")
def documents():
    with Session() as session:
        return [metadata(d) for d in session.scalars(select(Document).order_by(Document.uploaded_at.desc()))]


@app.post("/documents/upload",status_code=202)
async def upload(background_tasks:BackgroundTasks,file:UploadFile=File(...)):
    if file.content_type not in {"application/pdf","application/octet-stream"} or not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(415,"Please upload a PDF file")
    content=bytearray()
    while chunk:=await file.read(1024*1024):
        content.extend(chunk)
        if len(content)>MAX_UPLOAD:raise HTTPException(413,f"PDF must be smaller than {MAX_UPLOAD//1024//1024} MB")
    await file.close()
    if not content.startswith(b"%PDF-"):raise HTTPException(422,"The file is not a valid PDF")
    try:
        with pdfplumber.open(BytesIO(content)) as pdf:
            if not 1<=len(pdf.pages)<=200:raise ValueError("PDF must contain between 1 and 200 pages")
    except Exception as exc:
        raise HTTPException(422,"The PDF is damaged, encrypted, or exceeds the 200-page limit") from exc
    doc_id,duplicate=register(bytes(content),file.filename)
    if not duplicate:background_tasks.add_task(run_pipeline,doc_id)
    return {**metadata(get_document(doc_id)),"duplicate":duplicate}


@app.get("/documents/{document_id}")
def document(document_id:str):
    return metadata(get_document(document_id))


@app.get("/documents/{document_id}/status")
def status(document_id:str):
    return metadata(get_document(document_id))


@app.post("/documents/{document_id}/retry",status_code=202)
def retry(document_id:str,background_tasks:BackgroundTasks):
    doc=get_document(document_id)
    if doc.status!="failed":raise HTTPException(409,"Only failed ingestion jobs can be retried")
    with Session() as session:
        doc=session.get(Document,document_id);doc.status="queued";doc.progress=0;doc.error=None;session.commit()
    background_tasks.add_task(run_pipeline,document_id)
    return {"id":document_id,"status":"queued"}


@app.get("/documents/{document_id}/overview")
def overview(document_id:str):
    doc=get_document(document_id,True);p=doc.payload
    return {"document":metadata(doc),**{k:p[k] for k in ["title","facts","issues","annual","forecast","allocations","nav_unit","extraction"]},
            "pages":[{"number":x["number"],"section":x["section"],"char_count":x["char_count"],"method":x["method"],"warnings":x["warnings"],"table_count":len(x["tables"])} for x in p["pages"]]}


@app.get("/documents/{document_id}/metrics")
def metrics(document_id:str,metric:str|None=None,period:str|None=None,classification:str|None=None):
    get_document(document_id,True)
    with Session() as session:
        statement=select(FactRecord).where(FactRecord.document_id==document_id)
        if metric:statement=statement.where(FactRecord.metric==metric)
        if period:statement=statement.where(FactRecord.period==period)
        if classification:statement=statement.where(FactRecord.classification==classification)
        return [f.data for f in session.scalars(statement)]


@app.get("/documents/{document_id}/validation")
def validation(document_id:str):
    return get_document(document_id,True).payload["issues"]


class Review(BaseModel):
    status:Literal["open","reviewed"]


@app.patch("/documents/{document_id}/validation/{issue_id}")
def review(document_id:str,issue_id:str,body:Review):
    get_document(document_id,True)
    with Session() as session:
        record=session.get(ValidationRecord,(document_id,issue_id))
        if not record:raise HTTPException(404,"Finding not found")
        doc=session.get(Document,document_id)
        payload={**doc.payload,"issues":[{**i,"status":body.status} if i["id"]==issue_id else i for i in doc.payload["issues"]]}
        doc.payload=payload;record.status=body.status;record.data={**record.data,"status":body.status};session.commit()
    return {"id":issue_id,"status":body.status}


@app.get("/documents/{document_id}/pages/{page_number}")
def page(document_id:str,page_number:int):
    doc=get_document(document_id,True)
    if not 1<=page_number<=doc.page_count:raise HTTPException(404,"Page not found")
    return doc.payload["pages"][page_number-1]


@app.get("/documents/{document_id}/pages/{page_number}/image")
def image(document_id:str,page_number:int):
    doc=get_document(document_id,True)
    if not 1<=page_number<=doc.page_count:raise HTTPException(404,"Page not found")
    cache=DATA_DIR/"processed"/document_id/"pages";cache.mkdir(parents=True,exist_ok=True)
    output=cache/f"{page_number}.png"
    if not output.exists():
        with pdfplumber.open(pdf_path(document_id)) as pdf:pdf.pages[page_number-1].to_image(resolution=125).save(output)
    return FileResponse(output,media_type="image/png",headers={"Cache-Control":"private, max-age=86400"})


@app.get("/documents/{document_id}/file")
def file(document_id:str):
    doc=get_document(document_id)
    return FileResponse(pdf_path(document_id),media_type="application/pdf",filename=doc.filename,content_disposition_type="inline")


@app.get("/documents/{document_id}/export")
def export(document_id:str):
    doc=get_document(document_id,True)
    return JSONResponse({"document":metadata(doc),**doc.payload},headers={"Content-Disposition":f'attachment; filename="evidence-{document_id}.json"'})


@app.post("/chat/query")
def query(body:Query):
    doc=get_document(body.document_id,True)
    if not body.question.strip():raise HTTPException(422,"Please enter a question")
    response=answer_question(doc.payload,body.question.strip(),body.document_id)
    with Session() as session:
        session.add(QueryLog(document_id=body.document_id,route=response["query_type"],latency_ms=response["latency_ms"],source_pages=[s["page"] for s in response["sources"]]))
        session.add_all([CalculationRecord(document_id=body.document_id,data=c) for c in response["calculations"]])
        session.commit()
    return response


app.mount("/static",StaticFiles(directory=ROOT/"ui"),name="static")


@app.get("/",include_in_schema=False)
def home():
    return FileResponse(ROOT/"ui/index.html")
