"""Driver Neo4j lazily initialized; only read-only parameterized queries."""
from functools import lru_cache
import os


@lru_cache(maxsize=1)
def get_driver():
    from neo4j import GraphDatabase

    username = os.getenv("NEO4J_USERNAME", "")
    password = os.getenv("NEO4J_PASSWORD", "")
    auth = (username, password) if username else None
    return GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://iyp:7687"),
        auth=auth,
        connection_timeout=10.0,
        max_connection_pool_size=20,
    )


def read(statement: str, **parameters) -> list[dict]:
    from neo4j import Query, READ_ACCESS

    timeout = max(1, min(120, int(os.getenv("QUERY_TIMEOUT_SECONDS", "20"))))
    with get_driver().session(
        database=os.getenv("NEO4J_DATABASE", "neo4j"),
        default_access_mode=READ_ACCESS,
    ) as session:
        result = session.run(Query(statement, timeout=timeout), parameters)
        return [r.data() for r in result]
