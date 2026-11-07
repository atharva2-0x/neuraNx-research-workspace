"""Run with python -m app.ingest path/to/report.pdf."""
import argparse
import json
from pathlib import Path
from app.db import initialize,Session,Document,metadata
from app.pipeline import register,run_pipeline


def main():
    parser=argparse.ArgumentParser(description="Ingest a PDF with page-level evidence")
    parser.add_argument("pdf",type=Path)
    parser.add_argument("--reprocess",action="store_true")
    args=parser.parse_args()
    initialize()
    document_id,duplicate=register(args.pdf.read_bytes(),args.pdf.name)
    if not duplicate or args.reprocess:run_pipeline(document_id)
    with Session() as session:
        doc=session.get(Document,document_id)
        print(json.dumps(metadata(doc),indent=2))
        if doc.status!="completed":raise SystemExit(1)


if __name__=="__main__":main()
