from pathlib import Path
from app.db import Session,Document,CalculationRecord,FactRecord
from sqlalchemy import select,func


def test_health_and_static_frontend(client):
    assert client.get("/health").json()["status"]=="ok"
    r=client.get("/")
    assert r.status_code==200 and "Fund Intelligence" in r.text
    assert client.get("/static/app.js").status_code==200
    assert r.headers["X-Request-ID"]
    assert client.get("/docs").status_code==200
    assert "Content-Security-Policy" not in client.get("/docs").headers
    assert client.get("/openapi.json").json()["info"]["title"]=="Fund Evidence API"


def test_api_metrics_and_page_evidence(client,report):
    root=f"/documents/{report['id']}"
    assert client.get(root).json()["page_count"]==50
    assert client.get(root+"/status").json()["status"]=="completed"
    facts=client.get(root+"/metrics?metric=nav&period=2025&classification=historical").json()
    assert len(facts)==1 and facts[0]["value"]=="192.9"
    assert client.get(root+"/pages/9").json()["number"]==9
    image=client.get(root+"/pages/9/image")
    assert image.status_code==200 and image.headers["Content-Type"]=="image/png"
    assert client.get(root+"/pages/0").status_code==404
    assert client.get(root+"/pages/51/image").status_code==404
    assert client.get("/documents/nonexistent").status_code==404


def test_query_and_persisted_calculation(client,report):
    r=client.post("/chat/query",json={"document_id":report["id"],"question":"Compare the 2025 return with the benchmark"})
    assert r.status_code==200,r.text
    assert r.json()["calculation"]["result"]=="2.20"
    with Session() as s:assert s.scalar(select(func.count()).select_from(CalculationRecord))>0
    assert client.post("/chat/query",json={"document_id":report["id"],"question":" "}).status_code==422
    assert client.post("/chat/query",json={"document_id":report["id"],"question":"x"*2001}).status_code==422


def test_duplicate_upload_is_idempotent(client,report,report_path):
    with Session() as s:before=s.scalar(select(func.count()).select_from(FactRecord))
    r=client.post("/documents/upload",files={"file":("report.pdf",report_path.read_bytes(),"application/pdf")})
    assert r.status_code==202 and r.json()["duplicate"] is True
    assert r.json()["id"]==report["id"]
    with Session() as s:assert before==s.scalar(select(func.count()).select_from(FactRecord))


def test_new_upload_processes_and_keeps_documents_isolated(client,report,report_path):
    content=report_path.read_bytes()+b"\n% independent upload test\n"
    r=client.post("/documents/upload",files={"file":("second-report.pdf",content,"application/pdf")})
    assert r.status_code==202 and not r.json()["duplicate"]
    doc_id=r.json()["id"]
    assert doc_id!=report["id"]
    result=client.get(f"/documents/{doc_id}").json()
    assert result["status"]=="completed" and result["fact_count"]==346
    assert len(client.get(f"/documents/{report['id']}/metrics").json())==346
    assert all(f["source"]["document_id"]==doc_id for f in client.get(f"/documents/{doc_id}/metrics").json())


def test_bad_uploads(client):
    assert client.post("/documents/upload",files={"file":("notes.txt",b"hello","text/plain")}).status_code==415
    assert client.post("/documents/upload",files={"file":("fake.pdf",b"not a pdf","application/pdf")}).status_code==422
    assert client.post("/documents/upload",files={"file":("corrupt.pdf",b"%PDF-1.7\nno valid objects","application/pdf")}).status_code==422


def test_review_state_is_persistent_without_changing_facts(client,report):
    root=f"/documents/{report['id']}"
    issue=client.get(root+"/validation").json()[0]
    facts_before=client.get(root+"/metrics").json()
    assert client.patch(root+"/validation/"+issue["id"],json={"status":"reviewed"}).status_code==200
    assert client.get(root+"/validation").json()[0]["status"]=="reviewed"
    assert client.get(root+"/metrics").json()==facts_before
    assert client.patch(root+"/validation/"+issue["id"],json={"status":"open"}).status_code==200


def test_export_contains_evidence_and_original_units(client,report):
    r=client.get(f"/documents/{report['id']}/export")
    assert "attachment" in r.headers["Content-Disposition"]
    assert r.json()["document"]["checksum"]
    assert len(r.json()["pages"])==50
    assert r.json()["facts"][0]["raw_text"]
