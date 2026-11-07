import pytest
from app.answering import answer_question
from app.evaluation import evidence_metrics, answer_accuracy


def test_evaluation_penalizes_irrelevant_and_missing_pages():
    assert evidence_metrics([1, 1, 2], [2, 3]) == {"precision": .5, "recall": .5}
    assert evidence_metrics([], []) == {"precision": 1, "recall": 1}
    assert evidence_metrics([1], []) == {"precision": 0, "recall": 0}
    assert evidence_metrics([], [1]) == {"precision": 0, "recall": 0}
    assert answer_accuracy("NAV is 192.9", ["192.9", "15.6"]) == .5
    with pytest.raises(ValueError): answer_accuracy("", [])


def test_relative_summary_and_quarterly_tables(report):
    a=answer_question(report["payload"], "summarise me data for last 2 years", report["id"])
    assert a["query_type"] == "structured"
    assert {s["page"] for s in a["sources"]} == {8,9}
    assert "2024, 2025" in a["answer"] and "| Year |" in a["answer"]
    assert "192.9" in a["answer"] and "2030" not in a["answer"]
    a=answer_question(report["payload"], "dig deeper in quarterly performance for 2023", report["id"])
    assert "| Quarter |" in a["answer"]
    assert a["answer"].count("| 2023-Q") == 16
    assert len(a["calculations"]) == 16
    assert {s["page"] for s in a["sources"]} == {14,17,20,23}


def test_relative_years_use_uploaded_report_not_fixed_dates(report):
    import copy
    payload=copy.deepcopy(report["payload"])
    for fact in payload["facts"]:
        if fact["period"] in {"2024", "2025"}:fact["period"]=str(int(fact["period"])-10)
    a=answer_question(payload,"summary for the last two years",report["id"])
    assert "2022, 2023" in a["answer"]


def test_semantic_paraphrase_without_keyword_overlap_uses_model(monkeypatch):
    from app import provider
    payload={"facts":[],"issues":[],"synthetic":False,"pages":[{"number":7}],"chunks":[],
             "_semantic_passages":[{"id":"c7","page":7,"section":"Strategy","content":"Diversified holdings reduce concentration exposure."}]}
    monkeypatch.setattr(provider,"enabled",lambda name:name=="ENABLE_LLM")
    monkeypatch.setattr(provider,"compose",lambda q,p:provider.ComposedAnswer(answer="Diversification reduces concentration risk.",citation_pages=[7]))
    a=answer_question(payload,"Why avoid putting eggs in one basket?","test")
    assert a["composer"]=="llm"
    assert [s["page"] for s in a["sources"]]==[7]


def test_finance_questions_are_not_blocked_by_topic_keywords(report,monkeypatch):
    from app import provider
    monkeypatch.setattr(provider,"enabled",lambda name:name=="ENABLE_LLM")
    monkeypatch.setattr(provider,"compose",lambda q,p:provider.ComposedAnswer(answer="Review the documented liquidity risks before making a decision.",citation_pages=[p[0]["page"]]))
    a=answer_question(report["payload"],"Explain the liquidity risks before I buy",report["id"])
    assert a["composer"]=="llm" and a["sources"]
