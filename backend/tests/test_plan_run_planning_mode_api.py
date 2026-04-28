"""HTTP contract: POST /api/plan/run planning_mode query validation."""
from __future__ import annotations


def test_post_plan_run_invalid_planning_mode_returns_422(client, admin_headers) -> None:
    """Invalid planning_mode is rejected by FastAPI enum validation."""
    r = client.post(
        "/api/plan/run",
        params={"scenario_name": "mode-test-invalid", "planning_mode": "not_a_mode"},
        headers=admin_headers,
    )
    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
