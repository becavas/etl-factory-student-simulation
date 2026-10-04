import re
from pathlib import Path

from tests.retail.clientes.test_bronze import (
    COVERED_GUARANTEES as BRONZE_GUARANTEES,
)
from tests.retail.clientes.test_silver import (
    COVERED_GUARANTEES as SILVER_GUARANTEES,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
README = REPO_ROOT / "domains/retail/capabilities/clientes/README.md"


def documented_guarantees() -> list[str]:
    text = README.read_text(encoding="utf-8")
    start = text.index("<!-- guarantees:start -->")
    end = text.index("<!-- guarantees:end -->")
    return re.findall(r"`(CLI-[0-9]{3})`", text[start:end])


def test_every_documented_guarantee_has_declared_test_coverage():
    documented = documented_guarantees()
    assert len(documented) == len(set(documented)), "duplicate guarantee IDs"
    assert set(documented) == BRONZE_GUARANTEES | SILVER_GUARANTEES
