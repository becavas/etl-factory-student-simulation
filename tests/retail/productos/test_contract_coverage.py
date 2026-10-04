import re
from pathlib import Path

from tests.retail.productos.test_bronze import (
    COVERED_GUARANTEES as BRONZE_GUARANTEES,
)
from tests.retail.productos.test_silver import (
    COVERED_GUARANTEES as SILVER_GUARANTEES,
)

README = (
    Path(__file__).parents[3] / "domains" / "retail" / "capabilities" / "productos" / "README.md"
)


def documented_guarantees() -> list[str]:
    text = README.read_text(encoding="utf-8")
    start = text.index("<!-- guarantees:start -->")
    end = text.index("<!-- guarantees:end -->")
    return re.findall(r"`(PRO-[A-Z]{2}-[0-9]{3})`", text[start:end])


def test_every_documented_guarantee_has_declared_test_coverage():
    documented = documented_guarantees()
    assert len(documented) == len(set(documented)), "duplicate guarantee IDs"
    assert len(documented) == 10
    assert set(documented) == BRONZE_GUARANTEES | SILVER_GUARANTEES | {"PRO-PK-001"}
