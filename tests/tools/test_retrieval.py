from insurance_automation.data.generate import generate_policy_docs
from insurance_automation.tools.retrieval import retrieve_policy

DOCS = generate_policy_docs()


def test_retrieve_ranks_relevant_doc_first_for_reporting_deadline():
    hits = retrieve_policy('how late can a claim be reported, reporting deadline', DOCS, k=3)
    assert hits[0].doc_id == 'RPT-01'


def test_retrieve_ranks_cosmetic_exclusion_first():
    hits = retrieve_policy('is cosmetic surgery covered', DOCS, k=3)
    assert hits[0].doc_id == 'EXC-01'


def test_retrieve_respects_k_and_orders_by_score():
    hits = retrieve_policy('claim authority limit approval', DOCS, k=2)
    assert len(hits) <= 2
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_retrieve_returns_empty_when_no_overlap():
    assert retrieve_policy('zzzz qqqq xxxx', DOCS, k=3) == []


def test_retrieve_empty_query_returns_empty():
    assert retrieve_policy('   ', DOCS, k=3) == []


def test_retrieve_snippet_is_bounded():
    hits = retrieve_policy('inpatient hospital', DOCS, k=1)
    assert 0 < len(hits[0].snippet) <= 240
