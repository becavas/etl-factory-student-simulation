import pytest

from enterprise_fabric.shared.identifiers import require_safe_value


@pytest.mark.parametrize("value", ["training_001", "RUN-17", "a"])
def test_accepts_safe_values(value):
    assert require_safe_value(value, "value") == value


@pytest.mark.parametrize("value", ["", "a b", "x' OR 1=1", "a" * 65])
def test_rejects_unsafe_values(value):
    with pytest.raises(ValueError):
        require_safe_value(value, "value")
