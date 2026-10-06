import pytest
from scripts.require_unique_job import JobLookupError, require_unique_job


def test_returns_the_only_exact_case_insensitive_match():
    payload = {
        "jobs": [
            {"job_id": 11, "settings": {"name": "[dev de] retail-pedidos-e2e"}},
            {"job_id": 12, "settings": {"name": "another-job"}},
        ]
    }
    assert require_unique_job(payload, "[DEV DE] RETAIL-PEDIDOS-E2E") == 11


def test_missing_job_has_actionable_error():
    with pytest.raises(JobLookupError, match="found 0"):
        require_unique_job({"jobs": []}, "missing-job")


def test_duplicate_job_lists_conflicting_ids():
    payload = [
        {"job_id": 31, "settings": {"name": "duplicate-job"}},
        {"job_id": 32, "settings": {"name": "duplicate-job"}},
    ]
    with pytest.raises(JobLookupError, match=r"job_ids=\[31, 32\]"):
        require_unique_job(payload, "duplicate-job")


def test_rejects_unknown_output_shape():
    with pytest.raises(JobLookupError, match="jobs list output"):
        require_unique_job({"items": []}, "job")
