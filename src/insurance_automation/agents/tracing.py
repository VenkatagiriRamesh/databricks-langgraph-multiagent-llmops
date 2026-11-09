from collections.abc import Callable

import mlflow
from langgraph.errors import GraphInterrupt

_enabled = False

SPAN_FIELDS = ('question', 'route', 'tools_called', 'citations', 'hit_ids', 'sql', 'sql_error',
               'critic_verdict', 'critic_reason', 'retries', 'draft', 'approval_status',
               'required_authority')
MAX_SPAN_STR = 2000
PROMPT_NODES = ('supervisor', 'sql_analyst', 'writer', 'critic')


def _clip(value):
    if isinstance(value, str):
        return value[:MAX_SPAN_STR]
    if isinstance(value, (list, tuple)):
        return [_clip(v) for v in value][:50]
    return value


def span_view(mapping) -> dict:
    """Whitelisted, truncated copy of a state/result dict for span inputs and outputs."""
    if not isinstance(mapping, dict):
        return {}
    return {k: _clip(mapping[k]) for k in SPAN_FIELDS if k in mapping}


def enable_tracing() -> None:
    global _enabled
    if _enabled:
        return
    try:
        mlflow.langchain.autolog()
    except Exception:  # noqa: BLE001, S110 - manual node spans are the contract
        pass
    _enabled = True


def _tokens(ledger) -> tuple[int, int]:
    total = getattr(ledger, 'total_tokens', None)
    if callable(total):
        return total()
    records = getattr(ledger, 'records', [])
    return (sum(r.tokens_in for _, r in records), sum(r.tokens_out for _, r in records))


def traced_node(name: str, fn: Callable[[dict], dict], ledger,
                prompts=None) -> Callable[[dict], dict]:
    """Run `fn` inside a span named `name` carrying the ledger's token delta for that node."""

    def wrapper(state):
        in0, out0 = _tokens(ledger)
        paused = None
        result = None
        with mlflow.start_span(name=name, span_type='CHAIN') as span:
            span.set_attribute('node', name)
            span.set_inputs(span_view(state))
            if prompts is not None and name in PROMPT_NODES:
                try:
                    version = getattr(prompts, 'version', None)
                    span.set_attribute('prompt_version', (version(name) if version else None)
                                       or prompts.source(name))
                except Exception:  # noqa: BLE001 - metadata must never fail a node
                    pass
            try:
                result = fn(state)
                span.set_outputs(span_view(result))
            except GraphInterrupt as exc:  # human-approval pause: control flow, not a failure
                paused = exc
            finally:
                in1, out1 = _tokens(ledger)
                span.set_attribute('tokens_in', in1 - in0)
                span.set_attribute('tokens_out', out1 - out0)
        if paused is not None:
            raise paused
        return result

    wrapper.__name__ = name
    return wrapper
