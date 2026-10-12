from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/publish-release.yml")


def workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_release_is_manual_and_serialized():
    document = workflow()
    assert set(document[True]) == {"workflow_dispatch"}
    assert document["concurrency"]["cancel-in-progress"] is False
    inputs = document[True]["workflow_dispatch"]["inputs"]
    assert set(inputs) == {
        "release_tag",
        "bundle_root",
        "release_title",
        "release_sha",
        "promotion_run_id",
        "promotion_run_attempt",
    }


def test_only_protected_publish_job_can_write_contents():
    jobs = workflow()["jobs"]
    assert jobs["verify-release"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    assert jobs["publish-release"]["environment"] == "prod"
    assert jobs["publish-release"]["permissions"]["contents"] == "write"
    assert "id-token" not in jobs["publish-release"]["permissions"]


def test_exact_promotion_run_and_attempt_are_downloaded():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "inputs.promotion_run_id" in text
    assert "inputs.promotion_run_attempt" in text
    assert "inputs.bundle_root" in text
    assert "inputs.release_title" in text
    assert text.count("scripts/verify_release_publication.py") == 2
    assert "secrets." not in text
    assert "git push --force" not in text
    assert 'test "$tag_sha" = "$RELEASE_SHA"' in text
