from collections.abc import Callable

import mlflow
from langgraph.errors import GraphInterrupt

_enabled = False


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


def traced_node(name: str, fn: Callable[[dict], dict], ledger) -> Callable[[dict], dict]:
    """Run `fn` inside a span named `name` carrying the ledger's token delta for that node."""

    def wrapper(state):
        in0, out0 = _tokens(ledger)
        paused = None
        result = None
        with mlflow.start_span(name=name, span_type='CHAIN') as span:
            span.set_attribute('node', name)
            try:
                result = fn(state)
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
