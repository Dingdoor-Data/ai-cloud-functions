from __future__ import annotations
import os
from typing import Any, Dict, Optional, Sequence
from functools import lru_cache

from google.cloud import bigquery
from google.api_core.retry import Retry

# ---- Client factory (lazy + cached) -----------------------------------------
@lru_cache(maxsize=1)
def get_bq_client(project_id: Optional[str] = None) -> bigquery.Client:
    """
    Creates a cached BigQuery client. Auth comes from env / ADC.
    """
    project = project_id or os.getenv("GOOGLE_CLOUD_PROJECT", 'knock24-inc')
    return bigquery.Client(project=project)

# ---- Parameter handling ------------------------------------------------------
_TYPE_MAP = {
    str: "STRING",
    int: "INT64",
    float: "FLOAT64",
    bool: "BOOL",
}

def _to_query_parameters(params: Dict[str, Any]) -> Sequence[bigquery.ScalarQueryParameter]:
    qp: list[bigquery.ScalarQueryParameter] = []
    for name, value in params.items():
        # Derive BQ type from Python type (basic cases)
        py_t = type(value)
        bq_type = _TYPE_MAP.get(py_t, "STRING")
        qp.append(bigquery.ScalarQueryParameter(name, bq_type, value))
    return qp

# ---- Query helpers -----------------------------------------------------------
def fetch_all(
    sql: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    project_id: Optional[str] = None,
    timeout: float = 30.0,
    retry: Retry | int | None = None,
) -> list[Dict[str, Any]]:
    """
    Runs a parameterized query and returns all rows as dicts.
    """
    client = get_bq_client(project_id)
    job_config = bigquery.QueryJobConfig()
    if params:
        job_config.query_parameters = _to_query_parameters(params)

    job = client.query(sql, job_config=job_config, retry=retry)
    result = job.result(timeout=timeout)
    rows: list[Dict[str, Any]] = [dict(row) for row in result]
    return rows

def fetch_one(
    sql: str,
    params: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Optional[Dict[str, Any]]:
    """
    Like fetch_all but returns the first row or None.
    """
    rows = fetch_all(sql, params, **kwargs)
    return rows[0] if rows else None
