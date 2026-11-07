import hashlib
import json
import logging
import time
from decimal import Decimal
from pathlib import Path
from sqlalchemy import delete, select
from app.db import DATA_DIR, Session, Document, FactRecord, ChunkRecord, ValidationRecord
from app.extraction import extract_pdf, normalize, summarize
from app.validation import validate
from app.retrieval import chunks_from_pages

logger = logging.getLogger("fund.ingestion")


def pdf_path(document_id):
    return DATA_DIR / "input" / f"{document_id}.pdf"


def register(content, filename):
    checksum = hashlib.sha256(content).hexdigest()
    document_id = checksum[:24]
    with Session() as session:
        existing = session.scalar(select(Document).where(Document.checksum==checksum))
        if existing:
            return existing.id, True
        path = pdf_path(document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        session.add(Document(id=document_id, filename=Path(filename).name[:255], checksum=checksum, payload={}))
        session.commit()
    return document_id, False


def update(document_id, **kwargs):
    with Session() as session:
        doc = session.get(Document,document_id)
        for k,v in kwargs.items():
            setattr(doc,k,v)
        session.commit()


def run_pipeline(document_id):
    try:
        update(document_id,status="processing",stage="Extracting page text, tables, and geometry",progress=5,error=None)
        stages = []
        started = time.perf_counter()
        pages = extract_pdf(pdf_path(document_id),lambda done,total:update(document_id,progress=5+int(done/total*45),page_count=total))
        stages.append({"name":"Extract source evidence","description":f"{len(pages)} pages · native text, table cells, and chart-axis geometry preserved","duration_ms":int((time.perf_counter()-started)*1000)})
        update(document_id,stage="Normalizing facts and retaining source units",progress=55)
        started = time.perf_counter()
        facts, assumptions, extraction_warnings = normalize(pages)
        with Session() as session:
            filename=session.get(Document,document_id).filename
        for fact in facts:
            fact["source"]["document_id"]=document_id
            fact["source"]["filename"]=filename
        stages.append({"name":"Normalize facts","description":f"{len(facts)} typed observations · raw tokens, units, periods, and coordinates retained","duration_ms":int((time.perf_counter()-started)*1000)})
        update(document_id,stage="Checking financial consistency",progress=70)
        started = time.perf_counter()
        issues = validate(facts,pages)
        stages.append({"name":"Validate without changing source values","description":f"{len(issues)} findings · reconciliation, compounding, repeated versions, and extraction quality","duration_ms":int((time.perf_counter()-started)*1000)})
        update(document_id,stage="Indexing page-level evidence",progress=85)
        started = time.perf_counter()
        chunks = chunks_from_pages(pages)
        title = " ".join(word if len(word)<=3 and word.isupper() else word.capitalize() for word in pages[0]["section"].split())
        payload = {"title":title,"synthetic":any("fictional" in p["text"].lower() or "synthetic" in p["text"].lower() for p in pages[:3]),
                   "pages":pages,"facts":facts,"assumptions":assumptions,"issues":issues,"chunks":chunks,
                   "extraction_warnings":extraction_warnings,**summarize(facts),
                   "nav_unit":"NAV units · Currency glyph unresolved",
                   "extraction":{"stages":stages,"retrieval_description":"Offline retrieval uses a BM25 keyword index; optional provider embeddings can enable semantic ranking.",
                                  "ocr_description":"Native chart labels and vector axes are inspected directly. Low-text pages use Tesseract when installed; otherwise they are flagged for review."}}
        stages.append({"name":"Index narrative evidence","description":f"{len(chunks)} page-aware passages · keyword retrieval ready","duration_ms":int((time.perf_counter()-started)*1000)})
        # Facts, chunks, issues and completed state are committed atomically.
        started = time.perf_counter()
        with Session() as session:
            doc = session.get(Document,document_id)
            for model in [FactRecord,ChunkRecord,ValidationRecord]:
                session.execute(delete(model).where(model.document_id==document_id))
            session.add_all([FactRecord(document_id=document_id,id=f["id"],metric=f["metric"],period=f["period"],
                                       value=Decimal(f["value"]),unit=f["unit"],classification=f["classification"],data=f) for f in facts])
            session.add_all([ChunkRecord(document_id=document_id,id=c["id"],page=c["page"],section=c["section"],content=c["content"]) for c in chunks])
            session.add_all([ValidationRecord(document_id=document_id,id=i["id"],rule=i["rule"],severity=i["severity"],status=i["status"],data=i) for i in issues])
            stages.append({"name":"Save the evidence register","description":"Original PDF, raw page records, typed facts, and findings saved locally","duration_ms":int((time.perf_counter()-started)*1000)})
            doc.payload=payload;doc.page_count=len(pages);doc.status="completed";doc.stage="Ready";doc.progress=100
            session.commit()
        out=DATA_DIR/"processed"/document_id
        out.mkdir(parents=True,exist_ok=True)
        (out/"extraction.json").write_text(json.dumps(payload,indent=2))
        logger.info("ingestion_completed",extra={"document_id":document_id,"page_count":len(pages),"fact_count":len(facts),"issue_count":len(issues)})
    except Exception as exc:
        logger.exception("ingestion_failed",extra={"document_id":document_id})
        update(document_id,status="failed",stage="Extraction failed",error=f"{type(exc).__name__}: {str(exc)[:500]}")
