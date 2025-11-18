from __future__ import annotations
import os
from functools import lru_cache
from typing import Any, Dict, Optional, Sequence, List
from google.cloud import bigquery
from google.api_core.retry import Retry

@lru_cache(maxsize=1)
def get_client(project_id: Optional[str] = None) -> bigquery.Client:
    return bigquery.Client(project=project_id or os.getenv("GOOGLE_CLOUD_PROJECT"))

_TYPE_MAP = {str: "STRING", int: "INT64", float: "FLOAT64", bool: "BOOL"}

def _to_params(params: Optional[Dict[str, Any]]) -> Sequence[bigquery.ScalarQueryParameter]:
    if not params:
        return []
    return [bigquery.ScalarQueryParameter(k, _TYPE_MAP.get(type(v), "STRING"), v)
            for k, v in params.items()]

def fetch_all(sql: str, params: Optional[Dict[str, Any]] = None, *,
              project_id: Optional[str] = None, timeout: float = 30.0,
              retry: Retry | int | None = None) -> List[Dict[str, Any]]:
    job = get_client(project_id).query(
        sql, job_config=bigquery.QueryJobConfig(query_parameters=_to_params(params)),
        retry=retry
    )
    return [dict(r) for r in job.result(timeout=timeout)]

def fetch_one(sql: str, params: Optional[Dict[str, Any]] = None, **kw: Any) -> Optional[Dict[str, Any]]:
    rows = fetch_all(sql, params, **kw)
    return rows[0] if rows else None

