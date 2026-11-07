from decimal import Decimal
import copy
import pytest
from app.calculations import percentage_change,compound,difference
from app.extraction import normalize,numeric
from app.validation import validate
from app.retrieval import retrieve


def test_decimal_difference_has_no_float_drift():
    assert difference("15.6","13.4")==Decimal("2.2")


def test_compounding_is_not_summation():
    assert compound(["3.1","5.2","4.7","2.8"])==Decimal("16.738524939200")


def test_percentage_change_and_zero_guard():
    assert percentage_change("100","112")==12
    with pytest.raises(ValueError):percentage_change(0,112)
    with pytest.raises(ValueError):compound([])


@pytest.mark.parametrize("token,expected",[("57,800",Decimal("57800")),("15.8*",Decimal("15.8")),("−1.3%",Decimal("-1.3"))])
def test_source_token_normalization(token,expected):
    assert numeric(token)==expected


@pytest.mark.parametrize("token",["unknown","NaN","₹15","1e3","12 crore"])
def test_ambiguous_values_are_not_guessed(token):
    with pytest.raises(ValueError):numeric(token)


def table_page(n,year,nav,ret):
    return {"number":n,"section":f"Annual Performance Review — {year}","text":"annual data","warnings":[],"chart_observations":[],
            "tables":[{"id":f"p{n}-t1","rows":[["Year","Year-end NAV (n)","Annual return (%)","Benchmark (%)","Fund minus benchmark (pp)"],[str(year),str(nav),str(ret),"10.5","1.5"]],"bbox":[0,0,100,100],"cells":[[],[[1,2,3,4]]*5]}]}


def test_extraction_keeps_tokens_units_and_geometry():
    facts,_,warnings=normalize([table_page(7,2025,"192.9","15.6")])
    nav=next(f for f in facts if f["metric"]=="nav")
    excess=next(f for f in facts if f["metric"]=="excess_return")
    assert nav["raw_text"]=="192.9"
    assert nav["source"]["page"]==7
    assert nav["source"]["bbox"]==[1,2,3,4]
    assert nav["unit"]=="NAV units (currency unresolved)"
    assert excess["unit"]=="percentage points"
    assert not warnings


def test_validation_flags_mismatch_without_mutation():
    pages=[table_page(4,2020,100,12),table_page(5,2021,112,18)]
    facts,_,_=normalize(pages)
    before=copy.deepcopy(facts)
    issues=validate(facts,pages)
    mismatch=next(i for i in issues if i["rule"]=="nav_return_mismatch")
    assert Decimal(mismatch["details"]["computed"])==12
    assert mismatch["details"]["reported"]=="18"
    assert mismatch["pages"]==[4,5]
    assert facts==before


def test_keyword_retrieval_carries_real_provenance():
    chunks=[{"id":"a","page":48,"section":"Risks and Limitations","content":"Risks include liquidity and currency exposure."},
            {"id":"b","page":4,"section":"Annual performance","content":"2020 NAV 100."}]
    found=retrieve("What are the liquidity risks?",chunks)
    assert found[0]["page"]==48
    assert found[0]["id"]=="a"
    assert retrieve("quantum astrophysics",chunks)==[]
