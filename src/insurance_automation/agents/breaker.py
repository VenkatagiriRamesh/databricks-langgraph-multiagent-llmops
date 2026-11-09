"""Runtime circuit breaker: a Lakebase flag switches claim decisions to 'escalate to a human'."""
import time
from collections.abc import Callable, Mapping

DEFAULT_AGENT = 'claims_copilot'


class RuntimeBreaker:
    """mode() is 'normal' or 'safe'.

    Reads are cached for `ttl_s`. If a read fails, the last known value is used while it is
    younger than `stale_after_s`; after that the breaker fails safe. A missing or expired flag
    reads as None and means normal.
    """

    def __init__(self, read_flag: Callable[[], str | None], ttl_s: float = 30.0,
                 stale_after_s: float = 300.0, clock=time.monotonic):
        self.read_flag, self.ttl_s, self.stale_after_s, self._clock = (
            read_flag, ttl_s, stale_after_s, clock)
        self._value: str | None = None
        self._read_at: float | None = None  # last successful read
        self._tried_at: float | None = None

    def mode(self) -> str:
        now = self._clock()
        if self._tried_at is not None and now - self._tried_at < self.ttl_s:
            return self._current(now)
        self._tried_at = now
        try:
            flag = self.read_flag()
            self._value, self._read_at = ('safe' if flag == 'safe' else 'normal'), now
        except Exception:  # noqa: BLE001, S110 - a Lakebase outage must not break answering
            pass
        return self._current(now)

    def _current(self, now: float) -> str:
        if self._read_at is not None and now - self._read_at < self.stale_after_s:
            return self._value or 'normal'
        return 'safe'  # never read successfully, or the last good read is too old


def make_flag_reader(env: Mapping[str, str], agent: str = DEFAULT_AGENT,
                     token_provider=None) -> Callable[[], str | None] | None:
    conninfo = env.get('LAKEBASE_CONNINFO')
    if not conninfo:
        return None
    from insurance_automation.agents import lakebase

    provider = token_provider or lakebase.default_token

    def read() -> str | None:
        with lakebase.connect(conninfo, provider, connect_timeout=15) as conn:
            row = conn.execute(
                'SELECT mode FROM runtime.flags WHERE agent = %s '
                'AND (expires_at IS NULL OR expires_at > now())', (agent,)).fetchone()
        return row[0] if row else None

    return read
