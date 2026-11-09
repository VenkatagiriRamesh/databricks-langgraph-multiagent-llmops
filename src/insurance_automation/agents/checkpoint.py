"""Durable LangGraph checkpoints on Lakebase, so pending approvals survive a redeploy."""
from collections.abc import Mapping

from langgraph.checkpoint.memory import MemorySaver


def make_checkpointer(env: Mapping[str, str], token_provider=None):
    """PostgresSaver when LAKEBASE_CONNINFO is set, otherwise the in-process MemorySaver."""
    conninfo = env.get('LAKEBASE_CONNINFO')
    if not conninfo:
        return MemorySaver()
    from langgraph.checkpoint.postgres import PostgresSaver
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    from insurance_automation.agents import lakebase

    provider = token_provider or lakebase.default_token

    class TokenConnection(lakebase.psycopg.Connection):
        @classmethod
        def connect(cls, conninfo='', **kwargs):
            return lakebase.connect(
                conninfo, provider,
                connector=lambda ci, **kw: lakebase.psycopg.Connection.connect.__func__(cls, ci, **kw),
                **kwargs)

    pool = ConnectionPool(conninfo, connection_class=TokenConnection, min_size=0, max_size=4,
                          kwargs={'autocommit': True, 'row_factory': dict_row}, open=True)
    saver = PostgresSaver(pool)
    saver.setup()
    return saver
