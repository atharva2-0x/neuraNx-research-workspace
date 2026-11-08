import pytest
from app import provider
from app.answering import answer_question


def mock_answer(monkeypatch,answer):
    monkeypatch.setattr(provider,'_compose_anthropic',lambda *a,**k:answer)


def test_derived_numbers_are_verified_not_whitelisted(monkeypatch):
    passages=[{'page':30,'content':'India 45%; North America 25%'}]
    answer=provider.ComposedAnswer(answer='20 percentage points',citation_pages=[30],calculations=[
        provider.DerivedCalculation(operation='subtract',inputs=['45','25'],result='20')])
    mock_answer(monkeypatch,answer)
    assert provider.compose('Difference?',passages).answer.startswith('20')
    answer.calculations[0].result='21'
    with pytest.raises(ValueError,match='mismatch'):provider.compose('Difference?',passages)
    answer.calculations=[]
    with pytest.raises(ValueError,match='absent'):provider.compose('Difference?',passages)


def test_unicode_ranges_and_question_scope_do_not_fail_validation(monkeypatch):
    answer=provider.ComposedAnswer(answer='Pages 14–25.',citation_pages=[3])
    mock_answer(monkeypatch,answer)
    provider.compose('Which pages?', [{'page':3,'content':'Quarter-wise performance: 14–25'}])
    answer.answer='Between 2020 and 2025, 2022 has +4.6 percentage points.'
    answer.citation_pages=[6]
    provider.compose('Between 2020 and 2025?', [{'page':6,'content':'2022 outperformance +4.6'}])


def test_model_decides_clarification_and_sees_table_headers(report,monkeypatch):
    monkeypatch.setenv('ENABLE_LLM','true')
    monkeypatch.setenv('ANTHROPIC_API_KEY','fake-test-key')
    def compose(question,passages):
        assert any('5 columns. Exact headers: Year' in p['content'] and 'Assumption' in p['content'] for p in passages)
        return provider.ComposedAnswer(answer='There are five headers, including Assumption.',citation_pages=[36])
    monkeypatch.setattr(provider,'compose',compose)
    a=answer_question(report['payload'],'Which four projection headers?',report['id'])
    assert a['composer']=='llm' and a['query_type']!='clarification'
    monkeypatch.setattr(provider,'compose',lambda *a:provider.ComposedAnswer(answer='Which year?',citation_pages=[],ambiguity=True))
    a=answer_question(report['payload'],'Compare Q2 returns',report['id'])
    assert a['query_type']=='clarification' and a['llm']['used']


def test_provider_failure_does_not_establish_ambiguity(report,monkeypatch):
    monkeypatch.setenv('ENABLE_LLM','true')
    monkeypatch.setenv('ANTHROPIC_API_KEY','fake-test-key')
    def fail(*a):raise TimeoutError()
    monkeypatch.setattr(provider,'compose',fail)
    a=answer_question(report['payload'],'Compare Q2 returns',report['id'])
    assert a['query_type']!='clarification' and a['llm']['state']=='failed'
