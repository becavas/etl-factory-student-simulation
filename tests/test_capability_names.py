import os
import pytest

from enterprise_fabric.capability_names import normalize_capability_name


@pytest.mark.parametrize(
    ("raw_name", "expected"),
    [
        ("Pedidos", "pedidos"),
        ("ventas-mart", "ventas_mart"),
        ("  Clientes VIP  ", "clientes_vip"),
    ],
)
def test_normalize_capability_name(raw_name: str, expected: str) -> None:
    assert normalize_capability_name(raw_name) == expected


@pytest.mark.parametrize("raw_name", ["", "123_pedidos", "ventas/mart"])
def test_normalize_capability_name_rejects_invalid_values(raw_name: str) -> None:
    with pytest.raises(ValueError, match="Invalid capability name"):
        normalize_capability_name(raw_name)
