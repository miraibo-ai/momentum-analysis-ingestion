"""Ingestion package for momentum-ops.

Orchestration is handled by Prefect flows defined in ``flows.py``.
The legacy ``scheduler.py`` (APScheduler) is retained for reference but
is no longer the active entry point.
"""