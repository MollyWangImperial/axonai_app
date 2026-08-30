from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_results_page_uses_backend_snapshot_decision_and_excludes_no_issue_sentinel():
    source = (ROOT / "frontend" / "app" / "results.tsx").read_text(encoding="utf-8")

    assert "data?.movement_snapshot_decision || assessment?.movement_snapshot_decision" in source
    assert 'issue.code !== "NO_ISSUES"' in source
    assert "snapshotDecision.presentation.title" in source
    assert "snapshotDecision.anatomy_marker.visible" in source


def test_assessment_result_requests_are_authenticated():
    source = (ROOT / "frontend" / "src" / "api.ts").read_text(encoding="utf-8")

    assert "authedFetch(`/api/assessment/${id}`)" in source
    assert "authedFetch(`/api/assessment/${id}/patient-summary`)" in source
