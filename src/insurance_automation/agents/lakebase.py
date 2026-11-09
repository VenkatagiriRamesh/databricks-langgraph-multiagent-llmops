"""Shared Lakebase connection helper: every new connection gets a fresh OAuth token."""
import time
from collections.abc import Callable

import psycopg

BACKOFF_S = (2, 4, 8, 16)  # covers the scale-to-zero cold start


def default_token() -> str:
    from databricks.sdk import WorkspaceClient

    return WorkspaceClient().config.authenticate()['Authorization'].removeprefix('Bearer ')


def connect(conninfo: str, token_provider: Callable[[], str] = default_token, *,
            connector=psycopg.Connection.connect, sleep=time.sleep, **kwargs):
    last = None
    for attempt in range(len(BACKOFF_S) + 1):
        try:
            return connector(conninfo, password=token_provider(), **kwargs)
        except psycopg.OperationalError as exc:
            last = exc
            if attempt < len(BACKOFF_S):
                sleep(BACKOFF_S[attempt])
    raise last
