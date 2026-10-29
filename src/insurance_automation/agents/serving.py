import re
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from datetime import UTC, datetime

from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import (
    ResponsesAgentRequest,
    ResponsesAgentResponse,
    ResponsesAgentStreamEvent,
)

from insurance_automation.agents import graph as agent_graph
from insurance_automation.agents.approval_log import ApprovalLog, ApprovalRecord
from insurance_automation.agents.nodes import NodeContext

DECIDE = re.compile(r'^\s*(approve|reject)\s+(\S+)\s*$', re.IGNORECASE)
MAX_RESOLVED_REMEMBERED = 1000
EDIT = re.compile(r'^\s*edit\s+(\S+):\s*(.+?)\s*$', re.IGNORECASE | re.DOTALL)


def _last_user_text(request: ResponsesAgentRequest) -> str:
    for item in reversed(request.input):
        if getattr(item, 'role', None) != 'user':
            continue
        content = item.content
        if isinstance(content, str):
            return content
        return ' '.join(getattr(p, 'text', '') or '' for p in content)
    return ''


def _decision_line(answer: str) -> str:
    """The final deterministic 'Decision: ...' line, or the whole answer if it has none."""
    for line in reversed(answer.splitlines()):
        if line.startswith('Decision:'):
            return line
    return answer


class ClaimsResponsesAgent(ResponsesAgent):
    """Two-call approval: the first call returns a run id, a follow-up grammar message resumes it.

    Pending runs live in this process only (no Lakebase on Free Edition, see ADR 001); every
    decision is also appended to the approval log.
    """

    def __init__(self, ctx_factory: Callable[[], NodeContext], approval_log: ApprovalLog,
                 checkpointer=None):
        self.ctx_factory, self.approval_log, self.checkpointer = ctx_factory, approval_log, checkpointer
        self._graph = None
        # Pending/resolved state is per process: a replay reaching another replica answers
        # 'Unknown run id', which is the honest answer there (no shared store on Free Edition).
        self._lock = threading.Lock()
        self._pending: dict[str, dict] = {}
        self._resolved: OrderedDict[str, None] = OrderedDict()

    def _remember_resolved(self, run_id: str) -> None:
        """Caller holds no lock requirement beyond _lock use in _resolve; bounded history."""
        self._resolved[run_id] = None
        while len(self._resolved) > MAX_RESOLVED_REMEMBERED:
            self._resolved.popitem(last=False)

    @property
    def graph(self):
        if self._graph is None:
            self._graph = agent_graph.build_graph(self.ctx_factory(), self.checkpointer)
        return self._graph

    def _ask(self, text: str) -> str:
        run_id = str(uuid.uuid4())
        res = agent_graph.invoke(self.graph, text, thread_id=run_id)
        if res.status != 'pending_approval':
            self._audit_auto(run_id, res)
            return res.output.answer
        payload = res.interrupt_payload or {}
        role = payload.get('required_authority') or res.output.required_authority
        with self._lock:
            self._pending[run_id] = payload
        return (
            f'Proposed decision for claim {payload.get("claim_id")}: '
            f'{payload.get("proposed_decision")} (payable {payload.get("payable_amount")}).\n'
            f'Approval required from: {role}.\n{res.output.answer}\n'
            f'Run id: {run_id}\n'
            f'Reply `approve {run_id}`, `reject {run_id}` or `edit {run_id}: <text>` '
            f'as an authorised {role}.'
        )

    def _audit_auto(self, run_id: str, res) -> None:
        if res.output.route != 'claim_decision' or res.output.required_authority != 'auto':
            return
        line = _decision_line(res.output.answer)
        if not line.startswith('Decision: AUTO-'):
            return
        state = self.graph.get_state({'configurable': {'thread_id': run_id}}).values
        coverage = state.get('coverage') or {}
        self.approval_log.append(ApprovalRecord(
            run_id, state.get('claim_id'), 'auto', 'auto', datetime.now(UTC).isoformat(),
            float(coverage.get('payable_amount') or 0.0), '',
            'auto_settle' if line.startswith('Decision: AUTO-SETTLED') else 'auto_deny', line,
        ))

    def _resolve(self, run_id: str, decision: str, edit_text: str = '') -> str:
        with self._lock:  # claim the run so a concurrent or replayed approval cannot also win
            if run_id in self._resolved:
                return f'Run id {run_id} was already resolved. No action taken.'
            payload = self._pending.pop(run_id, None)
            if payload is None:
                return f'Unknown run id {run_id}. No action taken.'
            self._remember_resolved(run_id)
        try:
            res = agent_graph.resume(self.graph, run_id, decision, edit_text)
        except Exception as exc:
            with self._lock:  # the run did not complete: put it back so it can be retried
                self._resolved.pop(run_id, None)
                self._pending[run_id] = payload
            if isinstance(exc, ValueError):
                return f'Cannot resume run id {run_id}: {exc}'
            raise
        self.approval_log.append(ApprovalRecord(
            run_id, payload.get('claim_id'), payload.get('required_authority'), decision,
            datetime.now(UTC).isoformat(), float(payload.get('payable_amount') or 0.0),
            edit_text, payload.get('proposed_decision') or '', _decision_line(res.output.answer),
        ))
        return res.output.answer

    def _reply(self, text: str) -> str:
        if m := DECIDE.match(text):
            return self._resolve(m.group(2), m.group(1).lower())
        if m := EDIT.match(text):
            return self._resolve(m.group(1), 'edit', m.group(2))
        return self._ask(text)

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        text = self._reply(_last_user_text(request))
        return ResponsesAgentResponse(
            output=[self.create_text_output_item(text, id=str(uuid.uuid4()))])

    def predict_stream(self, request: ResponsesAgentRequest):
        response = self.predict(request)
        yield ResponsesAgentStreamEvent(type='response.output_item.done', item=response.output[0])
