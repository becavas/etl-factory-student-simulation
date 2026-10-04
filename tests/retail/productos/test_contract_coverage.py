from pathlib import Path

README = (
    Path(__file__).parents[3] / "domains" / "retail" / "capabilities" / "productos" / "README.md"
)

EXPECTED_GUARANTEES = {
    "PRO-BR-001",
    "PRO-BR-002",
    "PRO-BR-003",
    "PRO-SI-001",
    "PRO-SI-002",
    "PRO-SI-003",
    "PRO-SI-004",
    "PRO-SI-005",
    "PRO-SI-006",
    "PRO-PK-001",
}


def test_readme_documents_all_required_guarantees():
    assert README.is_file(), f"Missing README: {README}"
    text = README.read_text(encoding="utf-8")
    missing = [gid for gid in EXPECTED_GUARANTEES if gid not in text]
    assert not missing, f"README does not document guarantees: {missing}"
