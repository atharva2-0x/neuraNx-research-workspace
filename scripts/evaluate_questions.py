"""Fixed source-verified interview evaluation; no network or LLM grading."""
import os
# Reproducible and free by default. Opt in explicitly to evaluate configured providers.
if "--live" not in __import__("sys").argv:
    os.environ["ENABLE_LLM"]="false"
    os.environ["ENABLE_EMBEDDINGS"]="false"
import json
from pathlib import Path
from sqlalchemy import select
from app.db import initialize,Session,Document
from app.answering import answer_question
from app.retrieval import retrieve
from app.evaluation import evidence_metrics, answer_accuracy

CASES=[
    ("2025 lookup","What was the reported NAV and return for 2025?","structured",[9],["192.9","15.6"]),
    ("Ranking","Which year had the highest annual return?","structured",[5],["2021","18.0"]),
    ("Benchmark arithmetic","Compare the 2025 performance with the benchmark","structured",[9],["2.20"]),
    ("Forecast","What are the forecast NAV and AUM for 2030?","structured",[40],["390.3","57,800"]),
    ("Portfolio","Which sector has the largest allocation?","structured",[26],["Technology","43"]),
    ("Assumptions","What assumptions are used in the forecast?","semantic",[36,37,38,39,40],["Earnings growth","Innovation"]),
    ("Cross-section conflict","Does the 2025 annual NAV agree with the quarterly section?","hybrid",[9,16,19,22,25],["192.9","194.7","192.5","194.0","195.5"]),
    ("NAV reconciliation","Does the 2021 NAV movement agree with the reported return?","hybrid",[4,5],["12.00","18.0"]),
    ("Compounding","Compound 3.1%, 5.2%, 4.7%, and 2.8%","structured",[],["16.74"]),
    ("Ambiguous quarter","Compare Q2 fund and benchmark returns","clarification",[],["Which year"]),
    ("Glossary","What is NAV?","semantic",[49],["Net Asset Value"]),
    ("Recent summary","summarise me data for last 2 years","structured",[8,9],["2024","2025","192.9"]),
    ("Quarterly formatting","can you dig me deeper in quarterly performance for 2023","structured",[14,17,20,23],["| Quarter |","2.3%","3.9%"]),
    ("Unsupported year","What is the NAV in 2040?","unsupported",[],["not present"]),
]


def main():
    initialize()
    with Session() as session:
        docs=session.scalars(select(Document).where(Document.status=="completed")).all()
        doc=next((d for d in docs if d.payload.get("title")=="ABC Company Fund"),None)
        if not doc:raise SystemExit("Ingest the supplied ABC Company Fund PDF first")
        results=[]
        for name,question,route,pages,tokens in CASES:
            a=answer_question(doc.payload,question,doc.id)
            actual_pages=sorted({s["page"] for s in a["sources"]})
            evidence=evidence_metrics(actual_pages,pages)
            accuracy=answer_accuracy(a["answer"],tokens)
            passed=a["query_type"]==route and actual_pages==pages and accuracy==1
            # Retrieval is measured separately from final citation selection.
            retrieved=retrieve(question,doc.payload["chunks"],limit=4)
            retrieval=evidence_metrics([p["page"] for p in retrieved],pages) if pages else None
            results.append({"evidence_precision":evidence["precision"],"evidence_recall":evidence["recall"],"answer_accuracy":accuracy,"keyword_retrieval_at_4":retrieval,"name":name,"question":question,"passed":passed,"expected_route":route,"actual_route":a["query_type"],"expected_pages":pages,"actual_pages":actual_pages,"answer":a["answer"],"warnings":a["warnings"],"latency_ms":a["latency_ms"]})
    output={"passed":sum(r["passed"] for r in results),"total":len(results),"cases":results}
    output["metrics"]={
        "citation_precision":sum(r["evidence_precision"] for r in results)/len(results),
        "citation_recall":sum(r["evidence_recall"] for r in results)/len(results),
        "answer_accuracy":sum(r["answer_accuracy"] for r in results)/len(results),
        "keyword_precision_at_4":sum(r["keyword_retrieval_at_4"]["precision"] for r in results if r["keyword_retrieval_at_4"] is not None)/sum(r["keyword_retrieval_at_4"] is not None for r in results),
        "keyword_recall_at_4":sum(r["keyword_retrieval_at_4"]["recall"] for r in results if r["keyword_retrieval_at_4"] is not None)/sum(r["keyword_retrieval_at_4"] is not None for r in results),
    }
    Path("output").mkdir(exist_ok=True)
    Path("output/evaluation.json").write_text(json.dumps(output,indent=2))
    print(json.dumps(output["metrics"],indent=2))
    for r in results:print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['name']}")
    print(f"{output['passed']}/{output['total']} passed · output/evaluation.json")
    if output["passed"]!=output["total"]:raise SystemExit(1)


if __name__=="__main__":main()
