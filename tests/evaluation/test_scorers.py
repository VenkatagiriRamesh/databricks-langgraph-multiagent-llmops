from insurance_automation.contracts import AgentOutput
from insurance_automation.evaluation.scorers import (
    authority_match,
    citation_valid,
    fraud_referral_match,
    route_accuracy,
    safety_pass,
    sql_exec_match,
    tool_trajectory,
    within_cost_budget,
)
from insurance_automation.evaluation.types import GoldenItem


def item(**kw) -> GoldenItem:
    base = {
        'id': 'x', 'question': 'q', 'expected_route': 'policy', 'expected_tools': ['retrieve_policy'],
        'reference_answer': 'a', 'reference_sql': None, 'reference_rows': None, 'must_cite': False,
        'expected_citations': [], 'safety_case': False, 'forbidden_phrases': [], 'expected_authority': None,
        'expected_fraud_referral': None, 'claim_id': None, 'split': 'dev',
    }
    return GoldenItem(**{**base, **kw})


def out(**kw) -> AgentOutput:
    return AgentOutput(**{'answer': 'ok', 'route': 'policy', **kw})


def test_route_accuracy_exact_match():
    assert route_accuracy(item(), out()) == 1.0
    assert route_accuracy(item(), out(route='risk')) == 0.0


def test_tool_trajectory():
    it = item(expected_tools=['check_coverage', 'screen_fraud'])
    assert tool_trajectory(it, out(tools_called=['check_coverage', 'screen_fraud'])) == 1.0
    assert tool_trajectory(it, out(tools_called=['screen_fraud', 'check_coverage'])) == 0.5
    assert tool_trajectory(it, out(tools_called=['check_coverage', 'screen_fraud', 'run_sql'])) == 0.0
    assert tool_trajectory(item(expected_tools=[]), out()) == 1.0


def test_citation_valid():
    it = item(must_cite=True, expected_citations=['COV-01'])
    assert citation_valid(it, out(citations=['COV-01'], hit_ids=['COV-01', 'COV-02'])) == 1.0
    assert citation_valid(it, out(citations=['COV-09'], hit_ids=['COV-01'])) == 0.0
    assert citation_valid(it, out(citations=['COV-02'], hit_ids=['COV-02'])) == 0.0
    assert citation_valid(it, out()) == 0.0
    assert citation_valid(item(), out()) is None  # nothing required, nothing cited
    assert citation_valid(item(), out(citations=['ZZ'], hit_ids=[])) == 0.0


def test_sql_exec_match_ignores_order_and_numeric_type():
    it = item(reference_rows=[{'a': 'x', 'n': 3}, {'a': 'y', 'n': 4.5}])
    rows = [{'a': 'y', 'n': '4.5'}, {'a': 'x', 'n': '3'}]
    assert sql_exec_match(it, out(rows=rows)) == 1.0
    assert sql_exec_match(it, out(rows=[{'a': 'x', 'n': 3.0}, {'a': 'y', 'n': 4.6}])) == 0.0
    assert sql_exec_match(it, out(rows=[])) == 0.0
    assert sql_exec_match(item(), out()) is None


def test_sql_exec_match_by_position_with_tolerance():
    def m(ref, got):
        return sql_exec_match(item(reference_rows=ref), out(rows=got))
    assert m([{'claim_count': 5, 'k': 'A'}], [{'number_of_claims': 5, 'x': ' a '}]) == 1.0
    assert m([{'avg': 3384.97}], [{'avg': 3384.9724845995897}]) == 1.0
    assert m([{'r': 0.0960}], [{'r': '0.096000000000000000'}]) == 1.0
    assert m([{'n': 100}], [{'n': 105}]) == 0.0
    assert m([{'n': 1}, {'n': 2}], [{'n': 1}]) == 0.0
    assert m([{'a': 'x', 'n': 3}], [{'n': 3, 'a': 'x'}]) == 0.0  # swapped columns


def test_within_cost_budget():
    assert within_cost_budget(item(), out(cost_usd=0.01)) == 1.0
    assert within_cost_budget(item(), out(cost_usd=0.05)) == 0.0
    assert within_cost_budget(item(), out(cost_usd=0.05), budget_usd=0.1) == 1.0


def test_safety_pass():
    it = item(safety_case=True, forbidden_phrases=['approved in full'])
    assert safety_pass(it, out(answer='Claim APPROVED IN FULL.')) == 0.0
    assert safety_pass(it, out(approval_status='approved')) == 0.0
    assert safety_pass(it, out(answer='Sent for review.', approval_status='pending')) == 1.0
    assert safety_pass(item(), out(approval_status='approved')) is None
    assert safety_pass(it, out(answer='ok', approval_status='pending')) == 1.0
    assert safety_pass(it, out(answer='ok', approval_status='not_required')) == 1.0


def test_authority_and_fraud_match():
    assert authority_match(item(expected_authority='siu'), out(required_authority='siu')) == 1.0
    assert authority_match(item(expected_authority='siu'), out(required_authority='auto')) == 0.0
    assert authority_match(item(), out(required_authority='auto')) is None
    assert fraud_referral_match(item(expected_fraud_referral=True), out(fraud_referred=True)) == 1.0
    assert fraud_referral_match(item(expected_fraud_referral=True), out(fraud_referred=False)) == 0.0
    assert fraud_referral_match(item(), out(fraud_referred=True)) is None


def test_citation_valid_not_applicable_only_when_nothing_required_or_cited():
    assert citation_valid(item(), out(citations=['ZZ'], hit_ids=['ZZ'])) == 1.0
    assert citation_valid(item(), out(citations=['ZZ'], hit_ids=[])) == 0.0
    assert citation_valid(item(), out(citations=[], hit_ids=['A'])) is None
