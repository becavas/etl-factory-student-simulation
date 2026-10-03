from datetime import UTC, datetime

import pytest

from enterprise_fabric.retail.pedidos.silver import evaluate_silver


def _metadata(batch_id: str = "test_batch") -> dict[str, object]:
    return {
        "_source_system": "pedidos_source",
        "_source_file_path": "/Volumes/test/input.csv",
        "_source_file_modification_time": datetime(2026, 1, 1, tzinfo=UTC),
        "_ingestion_batch_id": batch_id,
        "_ingestion_run_id": "bronze-run-1",
        "_ingested_at_utc": datetime(2026, 1, 1, tzinfo=UTC),
        "_record_hash": "a" * 64,
    }


def _pedido(**overrides: object) -> dict[str, object]:
    row = {
        "pedido_id": "PED-001",
        "cliente_id": "CLI-001",
        "fecha_pedido": "2026-01-01",
        "fecha_actualizacion": "2026-01-01T10:00:00Z",
        "canal": " web ",
        "moneda": " pen ",
        "monto_total": "100.00",
        "estado": " creado ",
        **_metadata(),
    }
    row.update(overrides)
    return row


def _item(**overrides: object) -> dict[str, object]:
    row = {
        "pedido_id": "PED-001",
        "item_id": "ITEM-001",
        "producto_id": "PROD-001",
        "cantidad": "2",
        "precio_unitario": "50.00",
        "importe_linea": "100.00",
        "fecha_actualizacion": "2026-01-01T10:00:00Z",
        **_metadata(),
    }
    row.update(overrides)
    return row


def _evaluate(spark, pedidos, items):
    return evaluate_silver(
        spark,
        spark.createDataFrame(pedidos),
        spark.createDataFrame(items),
        "test_batch",
        "quality-run-1",
    )


def _metric(evaluation, rule_id: str) -> int:
    return evaluation.metrics.where(f"rule_id = '{rule_id}'").first()["failed_records"]


def test_types_and_normalizes_valid_rows(spark):
    evaluation = _evaluate(spark, [_pedido()], [_item()])
    pedido = evaluation.pedidos_curated.first()
    assert pedido["canal"] == "WEB"
    assert pedido["moneda"] == "PEN"
    assert str(pedido["monto_total"]) == "100.00"
    assert evaluation.fail_count == 0
    assert evaluation.quarantine.count() == 0


def test_measures_duplicate_and_keeps_most_recent_source_record(spark):
    older = _pedido(_record_hash="a" * 64)
    newer = _pedido(
        fecha_actualizacion="2026-01-01T11:00:00Z",
        estado=" entregado ",
        _record_hash="b" * 64,
    )
    evaluation = _evaluate(spark, [older, newer], [_item()])
    assert _metric(evaluation, "pedido_duplicate") == 1
    assert evaluation.pedidos_curated.first()["estado"] == "ENTREGADO"


def test_blank_required_id_fails_and_is_quarantined(spark):
    evaluation = _evaluate(spark, [_pedido(pedido_id="  ")], [_item()])
    assert _metric(evaluation, "pedido_id_required") == 1
    assert evaluation.fail_count == 1
    assert evaluation.quarantine.where("entity = 'pedidos'").count() == 1


def test_orphan_item_is_quarantined_without_failing_batch(spark):
    evaluation = _evaluate(
        spark,
        [_pedido()],
        [_item(pedido_id="PED-NOT-FOUND")],
    )
    assert _metric(evaluation, "item_pedido_orphan") == 1
    assert evaluation.fail_count == 0
    assert evaluation.items_curated.count() == 0
    assert evaluation.quarantine.where("entity = 'pedido_items'").count() == 1


def test_invalid_numeric_value_is_explicitly_quarantined(spark):
    evaluation = _evaluate(spark, [_pedido(monto_total="not-a-number")], [_item()])
    assert _metric(evaluation, "pedido_amount_valid") == 1
    assert evaluation.fail_count == 0
    assert evaluation.pedidos_curated.count() == 0


@pytest.mark.parametrize(
    ("override", "rule_id", "expected_fail_count"),
    [
        (
            {"fecha_actualizacion": "not-a-timestamp"},
            "pedido_updated_at_valid",
            1,
        ),
        ({"cliente_id": "  "}, "cliente_id_required", 0),
        ({"fecha_pedido": "not-a-date"}, "pedido_date_valid", 0),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_remaining_pedido_rules(spark, override, rule_id, expected_fail_count):
    evaluation = _evaluate(spark, [_pedido(**override)], [_item()])
    assert _metric(evaluation, rule_id) == 1
    assert evaluation.fail_count == expected_fail_count
    assert evaluation.quarantine.where("entity = 'pedidos'").count() == 1


@pytest.mark.parametrize(
    ("override", "rule_id", "expected_fail_count"),
    [
        ({"item_id": "  "}, "item_id_required", 1),
        ({"pedido_id": "  "}, "item_pedido_id_required", 1),
        (
            {"fecha_actualizacion": "not-a-timestamp"},
            "item_updated_at_valid",
            1,
        ),
        ({"producto_id": "  "}, "item_product_required", 0),
        ({"cantidad": "0"}, "item_quantity_valid", 0),
        ({"precio_unitario": "-1.00"}, "item_price_valid", 0),
        ({"importe_linea": "-1.00"}, "item_amount_valid", 0),
    ],
    ids=lambda value: value if isinstance(value, str) else None,
)
def test_each_item_value_rule(spark, override, rule_id, expected_fail_count):
    evaluation = _evaluate(spark, [_pedido()], [_item(**override)])
    assert _metric(evaluation, rule_id) == 1
    assert evaluation.fail_count == expected_fail_count
    assert evaluation.quarantine.where("entity = 'pedido_items'").count() == 1


def test_measures_item_duplicate_before_deduplication(spark):
    newer = _item(
        fecha_actualizacion="2026-01-01T11:00:00Z",
        cantidad="3",
        _record_hash="b" * 64,
    )
    evaluation = _evaluate(spark, [_pedido()], [_item(), newer])
    assert _metric(evaluation, "item_duplicate") == 1
    assert evaluation.items_curated.first()["cantidad"] == 3


@pytest.mark.parametrize(
    ("flag", "expected_val"),
    [
        ("--fail_after_pedidos=true", True),
        ("--fail_after_pedidos=false", False),
    ],
)
def test_silver_parser_accepts_common_fail_after_pedidos(flag, expected_val):
    from enterprise_fabric.retail.pedidos.entrypoints import build_silver_parser

    parser = build_silver_parser()
    args = parser.parse_args(
        [
            "--catalog",
            "retail_sbx_a001",
            "--batch_id",
            "training_001",
            "--quality_run_id",
            "run_001",
            flag,
        ]
    )
    assert args.catalog == "retail_sbx_a001"
    assert args.batch_id == "training_001"
    assert args.quality_run_id == "run_001"
    assert args.fail_after_pedidos is expected_val


def test_silver_parser_default_fail_after_pedidos():
    from enterprise_fabric.retail.pedidos.entrypoints import build_silver_parser

    parser = build_silver_parser()
    args = parser.parse_args(
        [
            "--catalog",
            "retail_sbx_a001",
            "--batch_id",
            "training_001",
            "--quality_run_id",
            "run_001",
        ]
    )
    assert args.fail_after_pedidos is False


def test_silver_parser_rejects_unknown_arguments():
    from enterprise_fabric.retail.pedidos.entrypoints import build_silver_parser

    parser = build_silver_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "--catalog",
                "retail_sbx_a001",
                "--batch_id",
                "training_001",
                "--quality_run_id",
                "run_001",
                "--unexpected_flag",
                "bad",
            ]
        )
    assert exc_info.value.code == 2


def test_silver_parser_rejects_invalid_boolean():
    from enterprise_fabric.retail.pedidos.entrypoints import build_silver_parser

    parser = build_silver_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "--catalog",
                "retail_sbx_a001",
                "--batch_id",
                "training_001",
                "--quality_run_id",
                "run_001",
                "--fail_after_pedidos=not_a_bool",
            ]
        )
    assert exc_info.value.code == 2


def test_silver_parser_rejects_abbreviated_arguments():
    from enterprise_fabric.retail.pedidos.entrypoints import build_silver_parser

    parser = build_silver_parser()
    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(
            [
                "--cat",
                "retail_sbx_a001",
                "--batch_id",
                "training_001",
                "--quality_run_id",
                "run_001",
            ]
        )
    assert exc_info.value.code == 2
