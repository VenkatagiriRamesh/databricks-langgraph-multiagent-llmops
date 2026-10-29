"""LLM-as-judge scorers through the injected LLM (ADR-001: built-in MLflow judges were empty)."""
import json
import re
from dataclasses import dataclass

from insurance_automation.contracts import AgentOutput
from insurance_automation.evaluation.types import GoldenItem
from insurance_automation.llm.base import LLM

_FORMAT = (
    'Answer with JSON only: {"score": <0, 0.25, 0.5, 0.75 or 1>, "rationale": "<one sentence>"}.'
)
_GROUNDEDNESS = (
    'You grade whether an insurance assistant answer is supported by the evidence it cites. '
    'Score 1 when every claim is supported, 0 when it invents facts. ' + _FORMAT
)
_CORRECTNESS = (
    'You grade whether an insurance assistant answer agrees with the reference answer. '
    'Score 1 when it is fully correct, 0 when it is wrong or contradicts the reference. ' + _FORMAT
)


@dataclass
class JudgeScore:
    score: float
    rationale: str


def _parse(text: str) -> JudgeScore:
    match = re.search(r'\{.*?\}', text, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
        score = min(1.0, max(0.0, float(data['score'])))
        return JudgeScore(score, str(data.get('rationale', '')))
    except (ValueError, KeyError, TypeError):
        return JudgeScore(0.0, 'unparseable judge output')


def _ask(llm: LLM, system: str, node: str, item: GoldenItem, output: AgentOutput) -> JudgeScore:
    prompt = (
        f'Question: {item.question}\nReference answer: {item.reference_answer}\n'
        f'Answer: {output.answer}\nCitations: {output.citations}\nRetrieved: {output.hit_ids}'
    )
    return _parse(llm.invoke(prompt, system=system, node=node).text)


def judge_groundedness(llm: LLM, item: GoldenItem, output: AgentOutput) -> JudgeScore:
    return _ask(llm, _GROUNDEDNESS, 'judge_groundedness', item, output)


def judge_correctness(llm: LLM, item: GoldenItem, output: AgentOutput) -> JudgeScore:
    return _ask(llm, _CORRECTNESS, 'judge_correctness', item, output)
