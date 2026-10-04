"""Behavioral tests for aggregate formula, multi-currency rejection, and validations."""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from enterprise_fabric.retail.ventas.aggregate import (
    assert_reconciled,
    assert_unique_grain,
    build_daily_aggregate,
    require_aggregate_mode,
    require_fact_contract,
)
from enterprise_fabric.retail.ventas.semantic import SemanticContractError


def fact_frame(spark, rows):
    return spark.createDataFrame(
        rows,
        """
        fecha_pedido date,
        canal string,
        moneda string,
        importe_linea decimal(18,2),
        cantidad int,
        is_cancelled boolean,
        _last_change_batch_id string,
        _updated_at_utc timestamp
        """,
    )


def test_formula_excludes_cancelled_lines_and_reconciles(spark):
    now = datetime(2026, 8, 14, tzinfo=UTC)
    scope = fact_frame(
        spark,
        [
            (date(2026, 8, 13), "WEB", "PEN", Decimal("100.00"), 2, False, "b1", now),
            (date(2026, 8, 13), "WEB", "PEN", Decimal("25.50"), 1, False, "b1", now),
            (date(2026, 8, 13), "WEB", "PEN", Decimal("80.00"), 1, True, "b1", now),
        ],
    )

    aggregate = build_daily_aggregate(scope)
    row = aggregate.select("ventas_netas", "lineas_incluidas", "unidades_vendidas").first()

    assert row.ventas_netas == Decimal("125.50")
    assert row.lineas_incluidas == 2
    assert row.unidades_vendidas == 3
    assert_unique_grain(aggregate)
    assert_reconciled(scope, aggregate)


def test_rejects_second_eligible_currency(spark):
    now = datetime(2026, 8, 14, tzinfo=UTC)
    scope = fact_frame(
        spark,
        [
            (date(2026, 8, 13), "WEB", "PEN", Decimal("100.00"), 1, False, "b1", now),
            (date(2026, 8, 13), "WEB", "USD", Decimal("20.00"), 1, False, "b1", now),
        ],
    )

    with pytest.raises(SemanticContractError, match="only supports PEN"):
        build_daily_aggregate(scope)


def test_cancelled_currency_does_not_trigger_currency_error(spark):
    now = datetime(2026, 8, 14, tzinfo=UTC)
    # A cancelled line in USD should not fail the active currency check
    scope = fact_frame(
        spark,
        [
            (date(2026, 8, 13), "WEB", "PEN", Decimal("100.00"), 1, False, "b1", now),
            (date(2026, 8, 13), "WEB", "USD", Decimal("20.00"), 1, True, "b1", now),
        ],
    )
    aggregate = build_daily_aggregate(scope)
    assert aggregate.count() == 1


def test_required_null_value_raises_semantic_contract_error(spark):
    now = datetime(2026, 8, 14, tzinfo=UTC)
    scope = fact_frame(
        spark,
        [
            (None, "WEB", "PEN", Decimal("100.00"), 1, False, "b1", now),
        ],
    )
    with pytest.raises(SemanticContractError, match="required null values"):
        build_daily_aggregate(scope)


def test_two_channels_produce_two_rows_in_grain(spark):
    now = datetime(2026, 8, 14, tzinfo=UTC)
    scope = fact_frame(
        spark,
        [
            (date(2026, 8, 13), "WEB", "PEN", Decimal("100.00"), 1, False, "b1", now),
            (date(2026, 8, 13), "TIENDA", "PEN", Decimal("50.00"), 2, False, "b1", now),
        ],
    )
    aggregate = build_daily_aggregate(scope)
    assert aggregate.count() == 2
    assert_unique_grain(aggregate)
    assert_reconciled(scope, aggregate)


def test_assert_reconciled_accepts_one_cent_and_rejects_two_cents(spark):
    now = datetime(2026, 8, 14, tzinfo=UTC)
    scope = fact_frame(
        spark,
        [(date(2026, 8, 13), "WEB", "PEN", Decimal("100.00"), 1, False, "b1", now)],
    )
    # Match within 0.01
    agg_ok = spark.createDataFrame(
        [
            (
                date(2026, 8, 13),
                "WEB",
                "PEN",
                Decimal("100.01"),
                1,
                1,
                "id",
                "v1",
                now,
                now,
            )
        ],
        """fecha_pedido date, canal string, moneda string, ventas_netas decimal(28,2),
        lineas_incluidas long, unidades_vendidas long, _metric_id string, _metric_version string,
        _source_max_updated_at_utc timestamp, _published_at_utc timestamp""",
    )
    assert_reconciled(scope, agg_ok)

    # Mismatch of 0.02
    agg_bad = spark.createDataFrame(
        [
            (
                date(2026, 8, 13),
                "WEB",
                "PEN",
                Decimal("100.02"),
                1,
                1,
                "id",
                "v1",
                now,
                now,
            )
        ],
        """fecha_pedido date, canal string, moneda string, ventas_netas decimal(28,2),
        lineas_incluidas long, unidades_vendidas long, _metric_id string, _metric_version string,
        _source_max_updated_at_utc timestamp, _published_at_utc timestamp""",
    )
    with pytest.raises(SemanticContractError, match="metric reconciliation exceeded 0.01 PEN"):
        assert_reconciled(scope, agg_bad)


def test_require_aggregate_mode():
    assert require_aggregate_mode("full") == "FULL"
    assert require_aggregate_mode("INCREMENTAL") == "INCREMENTAL"
    with pytest.raises(SemanticContractError, match="must be FULL or INCREMENTAL"):
        require_aggregate_mode("UNKNOWN")


def test_require_fact_contract_missing_columns(spark):
    df = spark.createDataFrame([(1,)], ["fecha_pedido"])
    with pytest.raises(SemanticContractError, match="fact_ventas missing columns"):
        require_fact_contract(df)
