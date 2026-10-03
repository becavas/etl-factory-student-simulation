from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml
from tools.bundle_generator.generator import (
    REPO_ROOT,
    SpecError,
    compare_output,
    load_yaml,
    output_path_for,
    render_spec,
    validate_spec,
)

PEDIDOS_SPEC = REPO_ROOT / "domains/retail/capabilities/pedidos/specs/jobs.yml"
GOLDEN_DIR = REPO_ROOT / "tests/tools/bundle_generator/golden"


def _generated_jobs() -> dict:
    return yaml.safe_load(render_spec(PEDIDOS_SPEC))["resources"]["jobs"]


def _golden_jobs() -> dict:
    jobs = {}
    for path in sorted(GOLDEN_DIR.glob("*.yml")):
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        jobs.update(document["resources"]["jobs"])
    return jobs


def test_generated_jobs_match_native_golden_field_by_field():
    assert _generated_jobs() == _golden_jobs()


def test_render_is_byte_deterministic():
    assert render_spec(PEDIDOS_SPEC) == render_spec(PEDIDOS_SPEC)


def test_checked_in_output_matches_spec():
    rendered = render_spec(PEDIDOS_SPEC)
    matches, details = compare_output(output_path_for(PEDIDOS_SPEC), rendered)
    assert matches, details


def test_output_location_is_constrained_to_repo_domains(tmp_path: Path):
    external_spec = tmp_path / "capability/specs/jobs.yml"
    with pytest.raises(SpecError, match="spec must live under"):
        output_path_for(external_spec)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda spec: spec.update({"unknown": True}), "Additional properties"),
        (lambda spec: spec.update({"spec_version": 2}), "1 was expected"),
        (
            lambda spec: spec["jobs"][0]["tasks"][0].update({"timeout_seconds": "1800"}),
            "is not of type 'integer'",
        ),
    ],
)
def test_schema_rejects_unknown_version_and_invalid_type(mutation, message):
    spec = copy.deepcopy(load_yaml(PEDIDOS_SPEC))
    mutation(spec)
    with pytest.raises(SpecError, match=message):
        validate_spec(spec, PEDIDOS_SPEC)


def test_unknown_task_dependency_fails_with_context():
    spec = copy.deepcopy(load_yaml(PEDIDOS_SPEC))
    spec["jobs"][1]["tasks"][1]["depends_on"] = ["missing_task"]
    with pytest.raises(SpecError, match="depends on unknown task 'missing_task'"):
        validate_spec(spec, PEDIDOS_SPEC)


def test_dependency_cycle_is_rejected():
    spec = copy.deepcopy(load_yaml(PEDIDOS_SPEC))
    spec["jobs"][1]["tasks"][0]["depends_on"] = ["publish_pedidos_silver"]
    with pytest.raises(SpecError, match="dependency cycle"):
        validate_spec(spec, PEDIDOS_SPEC)


def test_manual_generated_edit_produces_drift_diff(tmp_path: Path):
    output = tmp_path / "jobs.generated.yml"
    output.write_text("manual: edit\n", encoding="utf-8")
    matches, details = compare_output(output, render_spec(PEDIDOS_SPEC))
    assert not matches
    assert "expected-from-spec" in details


def test_duplicate_yaml_key_is_rejected(tmp_path: Path):
    spec_path = tmp_path / "jobs.yml"
    spec_path.write_text("spec_version: 1\nspec_version: 1\n", encoding="utf-8")
    with pytest.raises(SpecError, match="duplicate YAML key 'spec_version'"):
        load_yaml(spec_path)
