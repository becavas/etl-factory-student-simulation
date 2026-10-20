import io
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from scripts.affected_bundles import (
    REPO_ROOT,
    affected_bundles,
    bundle_declares_target,
    main,
)

CLIENTES = "domains/retail/capabilities/clientes"
PEDIDOS = "domains/retail/capabilities/pedidos"
PRODUCTOS = "domains/retail/capabilities/productos"
VENTAS = "domains/retail/capabilities/ventas"
ORCHESTRATION = "domains/retail/orchestration"
ALL_BUNDLES = sorted([CLIENTES, PEDIDOS, PRODUCTOS, VENTAS, ORCHESTRATION])


def test_clientes_only_change_selects_only_clientes():
    assert affected_bundles(["src/enterprise_fabric/retail/clientes/silver.py"]) == [CLIENTES]


def test_pedidos_only_change_selects_only_pedidos():
    assert affected_bundles(["domains/retail/capabilities/pedidos/specs/jobs.yml"]) == [PEDIDOS]


def test_productos_only_change_selects_only_productos():
    assert affected_bundles(["src/enterprise_fabric/retail/productos/silver.py"]) == [PRODUCTOS]


def test_ventas_only_change_selects_only_ventas():
    assert affected_bundles(["src/enterprise_fabric/retail/ventas/fact.py"]) == [VENTAS]


def test_orchestration_change_selects_only_orchestration():
    assert affected_bundles(["domains/retail/orchestration/resources/domain-workflow.yml"]) == [
        ORCHESTRATION
    ]


def test_shared_change_selects_capabilities_and_orchestration():
    assert affected_bundles([".github/workflows/pull-request.yml"]) == ALL_BUNDLES


def test_shared_release_delivery_controls_select_all_bundles():
    for path in (
        ".github/workflows/promote-release.yml",
        ".github/workflows/publish-release.yml",
        "scripts/verify_release_candidate.py",
        "scripts/verify_release_publication.py",
        "scripts/write_promotion_record.py",
    ):
        assert affected_bundles([path]) == ALL_BUNDLES


def test_shared_generator_change_selects_every_capability():
    assert affected_bundles(["tools/bundle_generator/generator.py"]) == ALL_BUNDLES


def test_shared_code_change_selects_every_capability():
    assert affected_bundles(["src/enterprise_fabric/shared/spark.py"]) == ALL_BUNDLES


def test_docs_only_change_selects_no_capability():
    assert affected_bundles(["docs/architecture/overview.md"]) == []


def test_removed_bundle_does_not_disappear_silently():
    with pytest.raises(ValueError, match="sin Bundle actual"):
        affected_bundles(["domains/retail/capabilities/retirada/databricks.yml"])


def test_removed_orchestration_bundle_does_not_disappear_silently():
    with pytest.raises(ValueError, match="sin Bundle actual"):
        affected_bundles(["domains/retail_other/orchestration/databricks.yml"])


# --- Phase 15 §11.1 CD Target Isolation and Synthetic Fixtures ---


def test_target_dev_preserves_existing_dev_roots():
    for root in (CLIENTES, PEDIDOS, PRODUCTOS, VENTAS, ORCHESTRATION):
        assert bundle_declares_target(root, "dev") is True

    assert affected_bundles(
        ["src/enterprise_fabric/retail/pedidos/silver.py"],
        target="dev",
    ) == [PEDIDOS]
    assert (
        affected_bundles(
            [".github/CODEOWNERS"],
            target="dev",
        )
        == ALL_BUNDLES
    )


@pytest.fixture
def synthetic_repo(tmp_path: Path) -> Path:
    """Fixture creating a synthetic repository with sandbox-only and dev-enabled bundles."""
    repo = tmp_path / "repo"
    repo.mkdir()

    # Bundle 1: Standard capability with sandbox and dev
    std_cap = repo / "domains" / "retail" / "capabilities" / "standard"
    std_cap.mkdir(parents=True)
    with open(std_cap / "databricks.yml", "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "bundle": {"name": "retail_standard"},
                "targets": {
                    "sandbox": {"mode": "development", "default": True},
                    "dev": {"mode": "production"},
                },
            },
            f,
        )

    # Bundle 2: Sandbox-only capability (declares only sandbox)
    sbx_cap = repo / "domains" / "retail" / "capabilities" / "sandbox_only"
    sbx_cap.mkdir(parents=True)
    with open(sbx_cap / "databricks.yml", "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "bundle": {"name": "retail_sandbox_only"},
                "targets": {
                    "sandbox": {"mode": "development", "default": True},
                },
            },
            f,
        )

    # Bundle 3: Orchestration with sandbox and dev
    orch = repo / "domains" / "retail" / "orchestration"
    orch.mkdir(parents=True)
    with open(orch / "databricks.yml", "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "bundle": {"name": "retail_orchestration"},
                "targets": {
                    "sandbox": {"mode": "development", "default": True},
                    "dev": {"mode": "production"},
                },
            },
            f,
        )

    return repo


def test_synthetic_sandbox_only_direct_change_excluded_from_dev(synthetic_repo: Path):
    sbx_root = "domains/retail/capabilities/sandbox_only"
    change = ["domains/retail/capabilities/sandbox_only/specs/jobs.yml"]

    # When targeting dev, sandbox-only capability must NOT be selected
    assert affected_bundles(change, target="dev", repo_root=synthetic_repo) == []

    # When target is sandbox or omitted, it IS selected
    assert affected_bundles(change, target="sandbox", repo_root=synthetic_repo) == [sbx_root]
    assert affected_bundles(change, target=None, repo_root=synthetic_repo) == [sbx_root]


def test_synthetic_shared_change_excludes_sandbox_only_from_dev(synthetic_repo: Path):
    std_root = "domains/retail/capabilities/standard"
    orch_root = "domains/retail/orchestration"
    sbx_root = "domains/retail/capabilities/sandbox_only"
    shared_change = [".github/CODEOWNERS"]

    # General discovery / untargeted CI selects all 3
    assert affected_bundles(shared_change, target=None, repo_root=synthetic_repo) == sorted(
        [std_root, orch_root, sbx_root]
    )

    # CD targeting dev selects ONLY roots declaring dev (excludes sandbox_only)
    assert affected_bundles(shared_change, target="dev", repo_root=synthetic_repo) == sorted(
        [std_root, orch_root]
    )


def test_synthetic_dev_bundle_direct_change_selected_for_dev(synthetic_repo: Path):
    std_root = "domains/retail/capabilities/standard"
    change = ["domains/retail/capabilities/standard/specs/jobs.yml"]
    assert affected_bundles(change, target="dev", repo_root=synthetic_repo) == [std_root]


def test_cli_execution_with_target_dev(monkeypatch, capsys):
    input_paths = "src/enterprise_fabric/retail/pedidos/silver.py\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(input_paths))

    exit_code = main(["--target", "dev"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == PEDIDOS


def test_cli_subprocess_execution():
    script_path = REPO_ROOT / "scripts" / "affected_bundles.py"
    input_paths = "src/enterprise_fabric/retail/clientes/silver.py\n"
    result = subprocess.run(
        [sys.executable, str(script_path), "--target", "dev"],
        input=input_paths,
        text=True,
        capture_output=True,
        cwd=str(REPO_ROOT),
        check=True,
    )
    assert result.stdout.strip() == CLIENTES
