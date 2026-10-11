import pytest
from scripts.write_promotion_record import build_promotion


def environment(target, sha="a" * 40, checksum="c" * 64):
    return {
        "status": "SUCCESS",
        "repository": "org/repo",
        "git_sha": sha,
        "artifact": {"sha256": checksum},
        "bundles": [{"root": "domains/retail/orchestration", "target": target}],
        "workflow_run_id": "10",
        "workflow_run_attempt": "1",
        "target": target,
    }


def test_same_release_and_successful_smoke_are_promotable():
    result = build_promotion(
        environment("dev"),
        environment("certi"),
        environment("prod"),
        {"result_state": "SUCCESS", "run_id": 99},
    )
    assert result["status"] == "PROMOTED"
    assert result["artifact_sha256"] == "c" * 64


def test_different_artifact_blocks_promotion():
    prod = environment("prod", checksum="d" * 64)
    with pytest.raises(ValueError, match="different artifacts"):
        build_promotion(
            environment("dev"),
            environment("certi"),
            prod,
            {"result_state": "SUCCESS"},
        )


def test_failed_certi_smoke_blocks_promotion():
    with pytest.raises(ValueError, match="smoke"):
        build_promotion(
            environment("dev"),
            environment("certi"),
            environment("prod"),
            {"result_state": "FAILED"},
        )


def test_different_repository_blocks_promotion():
    prod = environment("prod")
    prod["repository"] = "other/repo"
    with pytest.raises(ValueError, match="repositories"):
        build_promotion(
            environment("dev"),
            environment("certi"),
            prod,
            {"result_state": "SUCCESS"},
        )


def test_record_target_must_match_environment():
    with pytest.raises(ValueError, match="target"):
        build_promotion(
            environment("dev"),
            environment("prod"),
            environment("certi"),
            {"result_state": "SUCCESS"},
        )
