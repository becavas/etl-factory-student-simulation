import pytest
from scripts.verify_release_publication import PublicationError, verify


def promotion():
    return {
        "status": "PROMOTED",
        "repository": "org/repo",
        "git_sha": "a" * 40,
        "artifact_sha256": "c" * 64,
        "bundle_scope": [
            "domains/retail/capabilities/ventas",
            "domains/retail/orchestration",
        ],
        "certi_smoke": {"result_state": "SUCCESS"},
        "environments": {
            name: {
                "target": name,
                "workflow_run_id": "10",
                "workflow_run_attempt": "1",
            }
            for name in ("dev", "certi", "prod")
        },
    }


def valid_inputs(**overrides):
    values = {
        "repository": "org/repo",
        "release_sha": "a" * 40,
        "release_tag": "retail/ventas/v1.0.0",
        "bundle_root": "domains/retail/capabilities/ventas",
        "release_title": "Ventas: primera versión operable",
    }
    values.update(overrides)
    return values


def test_promoted_release_is_publishable():
    result = verify(promotion(), **valid_inputs())
    assert result["wheel_sha256"] == "c" * 64
    assert result["bundle_root"] == "domains/retail/capabilities/ventas"


@pytest.mark.parametrize(
    "tag",
    ["v1.0.0", "retail/ventas/1.0.0", "retail/ventas/v01.0.0", "latest"],
)
def test_non_namespaced_semver_tag_is_rejected(tag):
    with pytest.raises(PublicationError, match="domain"):
        verify(promotion(), **valid_inputs(release_tag=tag))


def test_namespace_must_match_bundle_root():
    with pytest.raises(PublicationError, match="namespace"):
        verify(
            promotion(),
            **valid_inputs(release_tag="retail/pedidos/v1.0.0"),
        )


def test_bundle_root_must_belong_to_promoted_scope():
    with pytest.raises(PublicationError, match="absent"):
        verify(
            promotion(),
            **valid_inputs(
                release_tag="retail/clientes/v1.0.0",
                bundle_root="domains/retail/capabilities/clientes",
            ),
        )


def test_unpromoted_or_cross_repository_record_is_rejected():
    record = promotion()
    record["repository"] = "other/repo"
    with pytest.raises(PublicationError, match="repository"):
        verify(record, **valid_inputs())


def test_failed_certi_smoke_is_rejected():
    record = promotion()
    record["certi_smoke"]["result_state"] = "FAILED"
    with pytest.raises(PublicationError, match="smoke"):
        verify(record, **valid_inputs())


def test_missing_run_attempt_is_rejected():
    record = promotion()
    del record["environments"]["prod"]["workflow_run_attempt"]
    with pytest.raises(PublicationError, match="attempt"):
        verify(record, **valid_inputs())


def test_release_title_is_required_and_bounded():
    with pytest.raises(PublicationError, match="descriptive"):
        verify(promotion(), **valid_inputs(release_title=""))
