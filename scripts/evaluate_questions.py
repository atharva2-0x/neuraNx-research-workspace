"""Fixed source-verified interview evaluation; no network or LLM grading."""
import json
from pathlib import Path
from sqlalchemy import select
from app.db import initialize,Session,Document
from app.answering import answer_question

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
            passed=a["query_type"]==route and actual_pages==pages and all(t in a["answer"] for t in tokens)
            results.append({"name":name,"question":question,"passed":passed,"expected_route":route,"actual_route":a["query_type"],"expected_pages":pages,"actual_pages":actual_pages,"answer":a["answer"],"warnings":a["warnings"],"latency_ms":a["latency_ms"]})
    output={"passed":sum(r["passed"] for r in results),"total":len(results),"cases":results}
    Path("output").mkdir(exist_ok=True)
    Path("output/evaluation.json").write_text(json.dumps(output,indent=2))
    for r in results:print(f"{'PASS' if r['passed'] else 'FAIL'}  {r['name']}")
    print(f"{output['passed']}/{output['total']} passed · output/evaluation.json")
    if output["passed"]!=output["total"]:raise SystemExit(1)


if __name__=="__main__":main()
