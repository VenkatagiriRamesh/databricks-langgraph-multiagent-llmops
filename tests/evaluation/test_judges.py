from insurance_automation.contracts import AgentOutput
from insurance_automation.evaluation.judges import judge_correctness, judge_groundedness
from insurance_automation.evaluation.types import GoldenItem
from tests.conftest import FakeLLM

ITEM = GoldenItem(
    id='a', question='q', expected_route='policy', expected_tools=[], reference_answer='ref',
    reference_sql=None, reference_rows=None, must_cite=False, expected_citations=[],
    safety_case=False,
)
OUT = AgentOutput(answer='ans', route='policy', citations=['K1'])


def test_clean_json():
    s = judge_groundedness(FakeLLM(default='{"score": 0.75, "rationale": "fine"}'), ITEM, OUT)
    assert s.score == 0.75 and s.rationale == 'fine'


def test_json_wrapped_in_prose_and_clamped():
    llm = FakeLLM(default='Sure! {"score": 3, "rationale": "x"} hope that helps')
    assert judge_correctness(llm, ITEM, OUT).score == 1.0


def test_garbage():
    s = judge_correctness(FakeLLM(default='no idea'), ITEM, OUT)
    assert s.score == 0.0 and s.rationale == 'unparseable judge output'
