import os
import tempfile
from pathlib import Path
import pytest

_testdir=tempfile.TemporaryDirectory(prefix="fund-evidence-tests-")
os.environ["DATA_DIR"]=_testdir.name
os.environ["DATABASE_URL"]=f"sqlite:///{_testdir.name}/test.db"
os.environ["AUTO_INGEST"]="false"
os.environ["ENABLE_LLM"]="false"
os.environ["ENABLE_EMBEDDINGS"]="false"


@pytest.fixture(scope="session")
def report_path():
    path=Path(__file__).resolve().parents[1]/"data/input/ABC_Company_Fund_Performance_Report_50_Pages.pdf"
    if not path.exists():pytest.skip("Place the supplied ABC Company Fund PDF in data/input to run source-document integration checks")
    return path


@pytest.fixture(scope="session")
def report(report_path):
    from app.db import initialize,Session,Document
    from app.pipeline import register,run_pipeline
    initialize()
    doc_id,_=register(report_path.read_bytes(),report_path.name)
    run_pipeline(doc_id)
    with Session() as session:
        doc=session.get(Document,doc_id)
        assert doc.status=="completed",doc.error
        return {"id":doc_id,"payload":doc.payload}


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
