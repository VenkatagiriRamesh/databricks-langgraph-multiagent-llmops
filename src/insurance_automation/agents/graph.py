import time
from contextlib import nullcontext
from dataclasses import dataclass
from functools import partial
from typing import Literal

import mlflow
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from insurance_automation.agents import nodes
from insurance_automation.agents.approval import approval_gate
from insurance_automation.agents.nodes import ESCALATION_ANSWER, NodeContext
from insurance_automation.agents.state import ClaimsState
from insurance_automation.agents.tracing import traced_node
from insurance_automation.contracts import AgentOutput

MAX_RETRIES = 2
FIRST_NODE = {
    'analytics': 'sql_analyst', 'policy': 'policy_rag', 'risk': 'risk_scorer',
    'claim_decision': 'coverage_checker', 'refuse': 'refuse',
}

__all__ = ['ESCALATION_ANSWER', 'GraphResult', 'build_graph', 'invoke', 'resume']


@dataclass
class GraphResult:
    status: Literal['done', 'pending_approval']
    output: AgentOutput
    interrupt_payload: dict | None = None


def _after_critic(state: ClaimsState) -> str:
    if state['critic_verdict'] == 'pass':
        return 'approval_gate'
    return 'writer' if state.get('retries', 0) < MAX_RETRIES else 'escalate'


def build_graph(ctx: NodeContext, checkpointer=None, tracing: bool = True):
    g = StateGraph(ClaimsState)

    def add(name, fn):
        g.add_node(name, traced_node(name, fn, ctx.ledger) if tracing else fn)

    for name in ('supervisor', 'refuse', 'sql_analyst', 'policy_rag', 'coverage_checker',
                 'fraud_screener', 'risk_scorer', 'writer', 'critic', 'escalate'):
        add(name, partial(getattr(nodes, name), ctx=ctx))
    add('approval_gate', approval_gate)
    g.add_edge(START, 'supervisor')
    g.add_conditional_edges('supervisor', lambda s: FIRST_NODE[s['route']], list(FIRST_NODE.values()))
    g.add_edge('sql_analyst', 'writer')
    g.add_edge('policy_rag', 'writer')
    g.add_edge('risk_scorer', 'writer')
    g.add_conditional_edges('coverage_checker', nodes.after_coverage, ['fraud_screener', 'writer'])
    g.add_edge('fraud_screener', 'risk_scorer')
    g.add_edge('writer', 'critic')
    g.add_conditional_edges('critic', _after_critic, ['approval_gate', 'writer', 'escalate'])
    for end in ('refuse', 'escalate', 'approval_gate'):
        g.add_edge(end, END)
    graph = g.compile(checkpointer=checkpointer or MemorySaver())
    graph.tracing = tracing
    graph.ledger = ctx.ledger  # read by invoke/resume to measure cost
    return graph


def _root(name: str, graph):
    return mlflow.start_span(name=name, span_type='AGENT') if graph.tracing else nullcontext()


def _initial(question: str) -> ClaimsState:
    return {
        'question': question, 'route': 'refuse', 'claim_id': None, 'claim': None, 'sql': None,
        'rows': [], 'refusal_reason': None, 'hits': [], 'coverage': None, 'fraud': None,
        'risk': None, 'authority': None, 'draft': '', 'critic_verdict': '', 'critic_reason': '',
        'retries': 0, 'approval_status': '', 'answer': '', 'citations': [], 'evidence_ids': [],
        'tools_called': [], 'notes_flagged': False,
    }


def _ledger_total(ctx_ledger) -> float:
    total = getattr(ctx_ledger, 'total_usd', None)
    return float(total()) if callable(total) else 0.0


def _result(graph, config: dict, started: float, cost_before: float, ledger) -> GraphResult:
    snapshot = graph.get_state(config)
    state = snapshot.values
    interrupts = [i for task in snapshot.tasks for i in task.interrupts]
    pending = bool(snapshot.next)
    fraud = state.get('fraud')
    output = AgentOutput(
        answer=state.get('answer') or state.get('draft', ''),
        route=state.get('route', 'refuse'),
        tools_called=list(state.get('tools_called', [])),
        citations=list(state.get('citations', [])),
        hit_ids=list(state.get('evidence_ids', [])),
        sql=state.get('sql'),
        rows=list(state.get('rows', [])),
        cost_usd=_ledger_total(ledger) - cost_before,
        latency_s=time.perf_counter() - started,
        approval_status='pending' if pending else (state.get('approval_status') or 'not_required'),
        required_authority=state.get('authority'),
        fraud_referred=fraud['refer_to_siu'] if fraud else None,
    )
    return GraphResult(
        'pending_approval' if pending else 'done', output,
        interrupts[0].value if interrupts else None,
    )


def invoke(graph, question: str, thread_id: str) -> GraphResult:
    config = {'configurable': {'thread_id': thread_id}}
    ledger = graph.ledger
    started, before = time.perf_counter(), _ledger_total(ledger)
    with _root('invoke', graph):
        graph.invoke(_initial(question), config)
    return _result(graph, config, started, before, ledger)


def resume(graph, thread_id: str, decision: str, edit_text: str = '') -> GraphResult:
    config = {'configurable': {'thread_id': thread_id}}
    snapshot = graph.get_state(config)
    if not snapshot.values:
        raise ValueError(f'unknown thread id: {thread_id}')
    if not snapshot.next:
        raise ValueError(f'thread {thread_id} has no pending approval')
    ledger = graph.ledger
    started, before = time.perf_counter(), _ledger_total(ledger)
    with _root('resume', graph):
        graph.invoke(Command(resume={'decision': decision, 'edit_text': edit_text}), config)
    return _result(graph, config, started, before, ledger)
