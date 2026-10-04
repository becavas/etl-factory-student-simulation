"""Runtime constants for the ventas_netas_diarias semantic contract."""

from decimal import Decimal

METRIC_ID = "ventas_netas_diarias"
METRIC_VERSION = "1.0.0"
REPORTING_CURRENCY = "PEN"
ABSOLUTE_TOLERANCE = Decimal("0.01")
MAX_HOURS_AFTER_FACT_SUCCESS = 4
OUTPUT_GRAIN = ("fecha_pedido", "canal", "moneda")


class SemanticContractError(ValueError):
    """Raised when data cannot satisfy the published metric contract."""
