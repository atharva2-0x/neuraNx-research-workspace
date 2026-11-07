"""LLM invocation and honest status across answer routes and API boundaries."""
import copy
import pytest
from app import provider
from app.answering import answer_question
from app.models import Query


@pytest.mark.parametrize('question,expected,pages', [
    ('What was the fictional year-end Net Asset Value (NAV) of the ABC Company Fund in 2025?', ['192.9'], {9}),
    ("In which historical year did the fund's annual return underperform its benchmark, and what were those figures?", ['2023','10.3','11.6','-1.30'], {7}),
    ('According to the Expense Breakdown, what percentage is allocated to Management fees?', ['45%'], {28}),
    ("What does the acronym CAGR stand for according to the report's Glossary and Data Dictionary?", ['Compound Annual Growth Rate'], {49}),
    ('Which risk category is allocated 12% in the fictional Risk Profile distribution?', ['Liquidity 12%'], {27}),
    ('Which investor category holds a 15% allocation in the illustrative Investor Mix?', ['Pension 15%'], {29}),
])
def test_intent_and_llm_composition(report,monkeypatch,question,expected,pages):
    monkeypatch.setenv('ENABLE_LLM','false')
    offline=answer_question(report['payload'],question,report['id'])
    assert all(token in offline['answer'] for token in expected)
    assert {s['page'] for s in offline['sources']}==pages
    calls=[]
    def compose(q,passages):
        calls.append((q,passages))
        return provider.ComposedAnswer(answer=offline['answer'],citation_pages=sorted(pages))
    monkeypatch.setenv('ENABLE_LLM','true')
    monkeypatch.setenv('ANTHROPIC_API_KEY','test-key-not-used')
    monkeypatch.setattr(provider,'compose',compose)
    response=answer_question(report['payload'],question,report['id'])
    assert len(calls)==1
    assert response['composer']=='llm'
    assert response['llm']['attempted'] and response['llm']['used']
    assert all(str(p) in str(calls[0][1]) for p in pages)


def test_missing_key_and_provider_failure_are_explicit(report,monkeypatch):
    monkeypatch.setenv('ENABLE_LLM','true')
    monkeypatch.delenv('ANTHROPIC_API_KEY',raising=False)
    q='What was the NAV for 2025?'
    a=answer_question(report['payload'],q,report['id'])
    assert a['llm']['state']=='missing_key' and not a['llm']['attempted']
    monkeypatch.setenv('ANTHROPIC_API_KEY','test-key-not-used')
    def fail(*args):raise TimeoutError('unavailable')
    monkeypatch.setattr(provider,'compose',fail)
    a=answer_question(report['payload'],q,report['id'])
    assert a['llm']['state']=='failed' and a['llm']['attempted'] and not a['llm']['used']
    assert a['composer']=='deterministic' and '192.9' in a['answer']


def test_explicit_cagr_calculation_keeps_deterministic_workings(report):
    answer=answer_question(report['payload'],'What is the CAGR from 2020 to 2025?',report['id'])
    assert answer['calculation']['result']=='14.04'
    assert {s['page'] for s in answer['sources']}=={4,9}


def test_request_credentials_enable_llm_without_mutating_document(report,monkeypatch):
    monkeypatch.setenv('ENABLE_LLM','false')
    payload=copy.deepcopy(report['payload'])
    credentials={'provider':'openai','api_key':'test-request-key-123456789'}
    def compose(q,passages,credentials=None):
        assert credentials=={'provider':'openai','api_key':'test-request-key-123456789'}
        return provider.ComposedAnswer(answer='NAV 192.9',citation_pages=[9])
    monkeypatch.setattr(provider,'compose',compose)
    a=answer_question({**payload,'_llm_credentials':credentials},'NAV for 2025?',report['id'])
    assert a['composer']=='llm' and a['llm']['provider']=='openai'
    assert '_llm_credentials' not in payload and 'api_key' not in a['llm']
    query=Query(document_id=report['id'],question='NAV for 2025?',**credentials)
    assert credentials['api_key'] not in repr(query)
    assert query.credentials()==credentials
    with pytest.raises(ValueError):Query(document_id='test',question='test',provider='openai')


def test_provider_preserves_all_cited_pages_and_table_values(monkeypatch):
    passages=[{'page':i,'content':('source text '*200)+'Management 45%'} for i in range(1,7)]
    def compose(q,p,key):
        assert len(p)==6 and all('45%' in row['content'] for row in p)
        return provider.ComposedAnswer(answer='Management 45%',citation_pages=[6])
    monkeypatch.setattr(provider,'_compose_openai',compose)
    result=provider.compose('Management?',passages,{'provider':'openai','api_key':'test'})
    assert result.citation_pages==[6]


def test_local_api_forwards_browser_key_and_reports_health(client,report,monkeypatch):
    monkeypatch.setenv('ENABLE_LLM','false')
    def compose(q,passages,credentials=None):
        assert credentials=={'provider':'anthropic','api_key':'test-browser-key-123456789'}
        return provider.ComposedAnswer(answer='192.9',citation_pages=[9])
    monkeypatch.setattr(provider,'compose',compose)
    response=client.post('/chat/query',json={'document_id':report['id'],'question':'NAV for 2025?',
        'provider':'anthropic','api_key':'test-browser-key-123456789'})
    assert response.status_code==200 and response.json()['llm']['used']
    assert 'test-browser-key' not in response.text
    assert 'llm' in client.get('/health').json()


def test_vercel_api_forwards_request_credentials(monkeypatch):
    from fastapi.testclient import TestClient
    from deployment.vercel_api import app,meta
    monkeypatch.setenv('ENABLE_LLM','false')
    def compose(q,passages,credentials=None):
        assert credentials['provider']=='anthropic'
        return provider.ComposedAnswer(answer='192.9',citation_pages=[9])
    monkeypatch.setattr(provider,'compose',compose)
    with TestClient(app) as client:
        assert client.get('/health').json()['llm']['enabled'] is False
        r=client.post('/chat/query',json={'document_id':meta['id'],'question':'NAV for 2025?',
            'provider':'anthropic','api_key':'test-browser-key-123456789'})
        assert r.status_code==200 and r.json()['llm']['used']


@pytest.mark.parametrize('request_key',[None,'request-test-key'])
def test_anthropic_transport_works_without_optional_sdk(monkeypatch,request_key):
    import builtins
    import httpx
    monkeypatch.setenv('ANTHROPIC_API_KEY','server-test-key')
    original_import=builtins.__import__
    def no_sdk(name,*args,**kwargs):
        if name=='anthropic':raise ModuleNotFoundError('SDK intentionally absent')
        return original_import(name,*args,**kwargs)
    monkeypatch.setattr(builtins,'__import__',no_sdk)
    def post(client,url,**kwargs):
        assert url=='https://api.anthropic.com/v1/messages'
        assert kwargs['headers']['x-api-key']==(request_key or 'server-test-key')
        return httpx.Response(200,request=httpx.Request('POST',url),json={
            'stop_reason':'end_turn','content':[{'type':'text','text':'{"answer":"NAV 192.9","citation_pages":[9]}'}]})
    monkeypatch.setattr(httpx.Client,'post',post)
    answer=provider._compose_anthropic('NAV?', [{'page':9,'content':'NAV 192.9'}],api_key=request_key)
    assert answer.answer=='NAV 192.9'
