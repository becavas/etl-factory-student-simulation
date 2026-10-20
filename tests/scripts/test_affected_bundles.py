import io
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from scripts.affected_bundles import (
    REPO_ROOT,
    affected_bundles,
    bundle_declares_target,
    discover_bundles,
    main,
)

CLIENTES = "domains/retail/capabilities/clientes"
PEDIDOS = "domains/retail/capabilities/pedidos"
PRODUCTOS = "domains/retail/capabilities/productos"
VENTAS = "domains/retail/capabilities/ventas"
ORCHESTRATION = "domains/retail/orchestration"
EXISTING_DEV_BUNDLES = sorted([CLIENTES, PEDIDOS, PRODUCTOS, VENTAS, ORCHESTRATION])


def all_known_bundles() -> list[str]:
    return sorted(discover_bundles().values())


def all_dev_bundles() -> list[str]:
    return sorted(b for b in discover_bundles().values() if bundle_declares_target(b, "dev"))


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
    # Untargeted discovery returns all discovered bundles in the repository dynamically
    assert affected_bundles([".github/workflows/pull-request.yml"]) == all_known_bundles()
    for root in EXISTING_DEV_BUNDLES:
        assert root in affected_bundles([".github/workflows/pull-request.yml"])

    # Target dev returns only bundles declaring dev
    assert (
        affected_bundles([".github/workflows/pull-request.yml"], target="dev") == all_dev_bundles()
    )
    for root in EXISTING_DEV_BUNDLES:
        assert root in affected_bundles([".github/workflows/pull-request.yml"], target="dev")


def test_shared_release_delivery_controls_select_all_bundles():
    expected_all = all_known_bundles()
    expected_dev = all_dev_bundles()
    for path in (
        ".github/workflows/promote-release.yml",
        ".github/workflows/publish-release.yml",
        "scripts/verify_release_candidate.py",
        "scripts/verify_release_publication.py",
        "scripts/write_promotion_record.py",
    ):
        assert affected_bundles([path]) == expected_all
        assert affected_bundles([path], target="dev") == expected_dev


def test_shared_generator_change_selects_every_capability():
    assert affected_bundles(["tools/bundle_generator/generator.py"]) == all_known_bundles()
    assert (
        affected_bundles(["tools/bundle_generator/generator.py"], target="dev") == all_dev_bundles()
    )


def test_shared_code_change_selects_every_capability():
    assert affected_bundles(["src/enterprise_fabric/shared/spark.py"]) == all_known_bundles()
    assert (
        affected_bundles(["src/enterprise_fabric/shared/spark.py"], target="dev")
        == all_dev_bundles()
    )


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
    for root in EXISTING_DEV_BUNDLES:
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
        == all_dev_bundles()
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


def test_onboarding_sandbox_only_root_growth_and_isolation(synthetic_repo: Path):
    """Verifies that adding a new sandbox-only root grows discovery without breaking DEV scope."""
    std_root = "domains/retail/capabilities/standard"
    orch_root = "domains/retail/orchestration"
    sbx_root = "domains/retail/capabilities/sandbox_only"

    # Onboard an additional synthetic sandbox-only capability
    onboarded_cap = synthetic_repo / "domains" / "retail" / "capabilities" / "onboarded_sandbox"
    onboarded_cap.mkdir(parents=True)
    with open(onboarded_cap / "databricks.yml", "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "bundle": {"name": "retail_onboarded_sandbox"},
                "targets": {
                    "sandbox": {"mode": "development", "default": True},
                },
            },
            f,
        )
    onboarded_root = "domains/retail/capabilities/onboarded_sandbox"

    # 1. Inventory discovery dynamically includes the new root (count = 4)
    all_discovered = sorted(discover_bundles(repo_root=synthetic_repo).values())
    assert all_discovered == sorted([std_root, orch_root, sbx_root, onboarded_root])

    # 2. Untargeted shared change discovers all 4 roots (no global list editing needed)
    assert (
        affected_bundles(
            [".github/workflows/pull-request.yml"], target=None, repo_root=synthetic_repo
        )
        == all_discovered
    )

    # 3. Direct change to onboarded root is discovered untargeted
    assert affected_bundles(
        [f"{onboarded_root}/specs/jobs.yml"], target=None, repo_root=synthetic_repo
    ) == [onboarded_root]

    # 4. Direct change to onboarded root is strictly excluded from DEV
    assert (
        affected_bundles(
            [f"{onboarded_root}/specs/jobs.yml"], target="dev", repo_root=synthetic_repo
        )
        == []
    )

    # 5. Shared change targeting DEV selects ONLY dev-enabled roots
    # (excludes both sandbox-only roots)
    assert affected_bundles(
        [".github/CODEOWNERS"], target="dev", repo_root=synthetic_repo
    ) == sorted([std_root, orch_root])

    # 6. DEV capabilities retain expected behavior
    assert affected_bundles(
        [f"{std_root}/specs/jobs.yml"], target="dev", repo_root=synthetic_repo
    ) == [std_root]


def test_onboarding_sandbox_root_in_actual_repo_inventory(tmp_path: Path):
    """Verifies adding a sandbox-only capability to a replica of the real repo
    preserves existing DEV roots.
    """
    repo_copy = tmp_path / "repo_copy"
    repo_copy.mkdir()

    # Replicate actual domains directory and scripts
    shutil.copytree(REPO_ROOT / "domains", repo_copy / "domains")
    shutil.copytree(REPO_ROOT / "scripts", repo_copy / "scripts")

    # Add a synthetic sandbox-only capability to the actual domain
    synthetic_sbx = repo_copy / "domains" / "retail" / "capabilities" / "synthetic_sandbox"
    synthetic_sbx.mkdir(parents=True)
    with open(synthetic_sbx / "databricks.yml", "w", encoding="utf-8") as f:
        yaml.dump(
            {
                "bundle": {"name": "retail_synthetic_sandbox"},
                "targets": {
                    "sandbox": {"mode": "development", "default": True},
                },
            },
            f,
        )
    synthetic_sbx_root = "domains/retail/capabilities/synthetic_sandbox"

    # Untargeted discovery returns all 6 bundles
    all_discovered = sorted(discover_bundles(repo_root=repo_copy).values())
    assert len(all_discovered) == 6
    assert synthetic_sbx_root in all_discovered
    for root in EXISTING_DEV_BUNDLES:
        assert root in all_discovered

    # Shared change without target discovers all 6 bundles
    assert (
        affected_bundles([".github/CODEOWNERS"], target=None, repo_root=repo_copy) == all_discovered
    )

    # Shared change targeting DEV returns exactly the 5 existing DEV roots
    assert (
        affected_bundles([".github/CODEOWNERS"], target="dev", repo_root=repo_copy)
        == EXISTING_DEV_BUNDLES
    )

    # Direct change in synthetic sandbox root is excluded from DEV
    assert (
        affected_bundles([f"{synthetic_sbx_root}/source.py"], target="dev", repo_root=repo_copy)
        == []
    )


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
