"""Tests for entrypoints in retail capabilities: pedidos, clientes, productos.

Verifies strict CLI argument parsing (allow_abbrev=False, parse_args):
- Accepts known parameters with optional snapshot_mode and aggregate_mode omitted.
- Accepts known parameters with snapshot_mode and aggregate_mode (FULL / INCREMENTAL).
- Modes do not alter upstream ETL calls.
- Rejects unknown arguments before Spark or ETL execution.
- Rejects abbreviated arguments before Spark or ETL execution.
- Rejects invalid mode values before Spark or ETL execution.
- Preserves capability-specific arguments like --fail_after_pedidos.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from enterprise_fabric.retail.clientes import entrypoints as clientes_ep
from enterprise_fabric.retail.pedidos import entrypoints as pedidos_ep
from enterprise_fabric.retail.productos import entrypoints as productos_ep


@dataclass
class DummyResult:
    status: str = "SUCCESS"


@pytest.fixture
def mock_spark():
    spark = MagicMock()
    with patch("pyspark.sql.SparkSession.getActiveSession", return_value=spark):
        yield spark


# ---------------------------------------------------------------------------
# PEDIDOS BRONZE
# ---------------------------------------------------------------------------


def test_pedidos_bronze_accepts_known_parameters_omitting_modes(mock_spark):
    with patch(
        "enterprise_fabric.retail.pedidos.entrypoints.ingest_bronze", return_value=DummyResult()
    ) as mock_etl:
        pedidos_ep.run_bronze(
            [
                "--catalog",
                "test_cat",
                "--source_volume_path",
                "/Volumes/test",
                "--batch_id",
                "b1",
                "--run_id",
                "r1",
            ]
        )
        mock_etl.assert_called_once_with(
            spark=mock_spark,
            catalog="test_cat",
            source_volume_path="/Volumes/test",
            batch_id="b1",
            run_id="r1",
            fail_after_pedidos=False,
        )


def test_pedidos_bronze_accepts_modes_without_altering_etl_call(mock_spark):
    with patch(
        "enterprise_fabric.retail.pedidos.entrypoints.ingest_bronze", return_value=DummyResult()
    ) as mock_etl:
        pedidos_ep.run_bronze(
            [
                "--catalog",
                "test_cat",
                "--source_volume_path",
                "/Volumes/test",
                "--batch_id",
                "b1",
                "--run_id",
                "r1",
                "--snapshot_mode",
                "FULL",
                "--aggregate_mode",
                "INCREMENTAL",
                "--fail_after_pedidos",
                "true",
            ]
        )
        mock_etl.assert_called_once_with(
            spark=mock_spark,
            catalog="test_cat",
            source_volume_path="/Volumes/test",
            batch_id="b1",
            run_id="r1",
            fail_after_pedidos=True,
        )


@pytest.mark.parametrize(
    "bad_argv",
    [
        [
            "--catalog",
            "c",
            "--source_volume_path",
            "v",
            "--batch_id",
            "b",
            "--run_id",
            "r",
            "--unexpected_flag",
            "bad",
        ],
        ["--cat", "c", "--source_volume_path", "v", "--batch_id", "b", "--run_id", "r"],
        [
            "--catalog",
            "c",
            "--source_volume_path",
            "v",
            "--batch_id",
            "b",
            "--run_id",
            "r",
            "--snapshot_mode",
            "INVALID",
        ],
        [
            "--catalog",
            "c",
            "--source_volume_path",
            "v",
            "--batch_id",
            "b",
            "--run_id",
            "r",
            "--aggregate_mode",
            "BAD",
        ],
    ],
)
def test_pedidos_bronze_rejects_invalid_before_etl(bad_argv):
    with patch("enterprise_fabric.retail.pedidos.entrypoints.ingest_bronze") as mock_etl:
        with pytest.raises(SystemExit) as exc:
            pedidos_ep.run_bronze(bad_argv)
        assert exc.value.code == 2
        mock_etl.assert_not_called()


# ---------------------------------------------------------------------------
# PEDIDOS SILVER
# ---------------------------------------------------------------------------


def test_pedidos_silver_accepts_known_parameters_omitting_modes(mock_spark):
    with patch(
        "enterprise_fabric.retail.pedidos.entrypoints.publish_silver", return_value=DummyResult()
    ) as mock_etl:
        pedidos_ep.run_silver(
            [
                "--catalog",
                "test_cat",
                "--batch_id",
                "b1",
                "--quality_run_id",
                "q1",
            ]
        )
        mock_etl.assert_called_once_with(
            spark=mock_spark,
            catalog="test_cat",
            batch_id="b1",
            quality_run_id="q1",
        )


def test_pedidos_silver_accepts_modes_and_fail_after_pedidos(mock_spark):
    with patch(
        "enterprise_fabric.retail.pedidos.entrypoints.publish_silver", return_value=DummyResult()
    ) as mock_etl:
        pedidos_ep.run_silver(
            [
                "--catalog",
                "test_cat",
                "--batch_id",
                "b1",
                "--quality_run_id",
                "q1",
                "--fail_after_pedidos",
                "false",
                "--snapshot_mode",
                "INCREMENTAL",
                "--aggregate_mode",
                "FULL",
            ]
        )
        mock_etl.assert_called_once_with(
            spark=mock_spark,
            catalog="test_cat",
            batch_id="b1",
            quality_run_id="q1",
        )


@pytest.mark.parametrize(
    "bad_argv",
    [
        [
            "--catalog",
            "c",
            "--batch_id",
            "b",
            "--quality_run_id",
            "q",
            "--unexpected_flag",
            "bad",
        ],
        ["--cat", "c", "--batch_id", "b", "--quality_run_id", "q"],
        [
            "--catalog",
            "c",
            "--batch_id",
            "b",
            "--quality_run_id",
            "q",
            "--snapshot_mode",
            "BAD",
        ],
        [
            "--catalog",
            "c",
            "--batch_id",
            "b",
            "--quality_run_id",
            "q",
            "--aggregate_mode",
            "INVALID",
        ],
    ],
)
def test_pedidos_silver_rejects_invalid_before_etl(bad_argv):
    with patch("enterprise_fabric.retail.pedidos.entrypoints.publish_silver") as mock_etl:
        with pytest.raises(SystemExit) as exc:
            pedidos_ep.run_silver(bad_argv)
        assert exc.value.code == 2
        mock_etl.assert_not_called()


# ---------------------------------------------------------------------------
# CLIENTES BRONZE
# ---------------------------------------------------------------------------


def test_clientes_bronze_accepts_known_parameters_omitting_modes(mock_spark):
    with patch(
        "enterprise_fabric.retail.clientes.entrypoints.ingest_bronze", return_value=DummyResult()
    ) as mock_etl:
        clientes_ep.run_bronze(
            [
                "--catalog",
                "test_cat",
                "--source_volume_path",
                "/Volumes/test",
                "--batch_id",
                "b1",
                "--run_id",
                "r1",
            ]
        )
        mock_etl.assert_called_once_with(mock_spark, "test_cat", "/Volumes/test", "b1", "r1")


def test_clientes_bronze_accepts_modes_without_altering_etl_call(mock_spark):
    with patch(
        "enterprise_fabric.retail.clientes.entrypoints.ingest_bronze", return_value=DummyResult()
    ) as mock_etl:
        clientes_ep.run_bronze(
            [
                "--catalog",
                "test_cat",
                "--source_volume_path",
                "/Volumes/test",
                "--batch_id",
                "b1",
                "--run_id",
                "r1",
                "--snapshot_mode",
                "FULL",
                "--aggregate_mode",
                "INCREMENTAL",
            ]
        )
        mock_etl.assert_called_once_with(mock_spark, "test_cat", "/Volumes/test", "b1", "r1")


@pytest.mark.parametrize(
    "bad_argv",
    [
        [
            "--catalog",
            "c",
            "--source_volume_path",
            "v",
            "--batch_id",
            "b",
            "--run_id",
            "r",
            "--unexpected",
            "bad",
        ],
        ["--cat", "c", "--source_volume_path", "v", "--batch_id", "b", "--run_id", "r"],
        [
            "--catalog",
            "c",
            "--source_volume_path",
            "v",
            "--batch_id",
            "b",
            "--run_id",
            "r",
            "--snapshot_mode",
            "BAD",
        ],
        [
            "--catalog",
            "c",
            "--source_volume_path",
            "v",
            "--batch_id",
            "b",
            "--run_id",
            "r",
            "--aggregate_mode",
            "BAD",
        ],
    ],
)
def test_clientes_bronze_rejects_invalid_before_etl(bad_argv):
    with patch("enterprise_fabric.retail.clientes.entrypoints.ingest_bronze") as mock_etl:
        with pytest.raises(SystemExit) as exc:
            clientes_ep.run_bronze(bad_argv)
        assert exc.value.code == 2
        mock_etl.assert_not_called()


# ---------------------------------------------------------------------------
# CLIENTES SILVER
# ---------------------------------------------------------------------------


def test_clientes_silver_accepts_known_parameters_omitting_modes(mock_spark):
    with patch(
        "enterprise_fabric.retail.clientes.entrypoints.publish_silver", return_value=DummyResult()
    ) as mock_etl:
        clientes_ep.run_silver(
            [
                "--catalog",
                "test_cat",
                "--batch_id",
                "b1",
                "--quality_run_id",
                "q1",
            ]
        )
        mock_etl.assert_called_once_with(mock_spark, "test_cat", "b1", "q1")


def test_clientes_silver_accepts_modes_without_altering_etl_call(mock_spark):
    with patch(
        "enterprise_fabric.retail.clientes.entrypoints.publish_silver", return_value=DummyResult()
    ) as mock_etl:
        clientes_ep.run_silver(
            [
                "--catalog",
                "test_cat",
                "--batch_id",
                "b1",
                "--quality_run_id",
                "q1",
                "--snapshot_mode",
                "INCREMENTAL",
                "--aggregate_mode",
                "FULL",
            ]
        )
        mock_etl.assert_called_once_with(mock_spark, "test_cat", "b1", "q1")


@pytest.mark.parametrize(
    "bad_argv",
    [
        ["--catalog", "c", "--batch_id", "b", "--quality_run_id", "q", "--extra", "bad"],
        ["--cat", "c", "--batch_id", "b", "--quality_run_id", "q"],
        [
            "--catalog",
            "c",
            "--batch_id",
            "b",
            "--quality_run_id",
            "q",
            "--snapshot_mode",
            "INVALID",
        ],
        [
            "--catalog",
            "c",
            "--batch_id",
            "b",
            "--quality_run_id",
            "q",
            "--aggregate_mode",
            "INVALID",
        ],
    ],
)
def test_clientes_silver_rejects_invalid_before_etl(bad_argv):
    with patch("enterprise_fabric.retail.clientes.entrypoints.publish_silver") as mock_etl:
        with pytest.raises(SystemExit) as exc:
            clientes_ep.run_silver(bad_argv)
        assert exc.value.code == 2
        mock_etl.assert_not_called()


# ---------------------------------------------------------------------------
# PRODUCTOS BRONZE
# ---------------------------------------------------------------------------


def test_productos_bronze_accepts_known_parameters_omitting_modes(mock_spark):
    with patch(
        "enterprise_fabric.retail.productos.entrypoints.ingest_bronze", return_value=DummyResult()
    ) as mock_etl:
        productos_ep.run_bronze(
            [
                "--catalog",
                "test_cat",
                "--source_volume_path",
                "/Volumes/test",
                "--batch_id",
                "b1",
                "--run_id",
                "r1",
            ]
        )
        mock_etl.assert_called_once_with(mock_spark, "test_cat", "/Volumes/test", "b1", "r1")


def test_productos_bronze_accepts_modes_without_altering_etl_call(mock_spark):
    with patch(
        "enterprise_fabric.retail.productos.entrypoints.ingest_bronze", return_value=DummyResult()
    ) as mock_etl:
        productos_ep.run_bronze(
            [
                "--catalog",
                "test_cat",
                "--source_volume_path",
                "/Volumes/test",
                "--batch_id",
                "b1",
                "--run_id",
                "r1",
                "--snapshot_mode",
                "FULL",
                "--aggregate_mode",
                "FULL",
            ]
        )
        mock_etl.assert_called_once_with(mock_spark, "test_cat", "/Volumes/test", "b1", "r1")


@pytest.mark.parametrize(
    "bad_argv",
    [
        [
            "--catalog",
            "c",
            "--source_volume_path",
            "v",
            "--batch_id",
            "b",
            "--run_id",
            "r",
            "--extra",
            "bad",
        ],
        ["--cat", "c", "--source_volume_path", "v", "--batch_id", "b", "--run_id", "r"],
        [
            "--catalog",
            "c",
            "--source_volume_path",
            "v",
            "--batch_id",
            "b",
            "--run_id",
            "r",
            "--snapshot_mode",
            "INVALID",
        ],
        [
            "--catalog",
            "c",
            "--source_volume_path",
            "v",
            "--batch_id",
            "b",
            "--run_id",
            "r",
            "--aggregate_mode",
            "INVALID",
        ],
    ],
)
def test_productos_bronze_rejects_invalid_before_etl(bad_argv):
    with patch("enterprise_fabric.retail.productos.entrypoints.ingest_bronze") as mock_etl:
        with pytest.raises(SystemExit) as exc:
            productos_ep.run_bronze(bad_argv)
        assert exc.value.code == 2
        mock_etl.assert_not_called()


# ---------------------------------------------------------------------------
# PRODUCTOS SILVER
# ---------------------------------------------------------------------------


def test_productos_silver_accepts_known_parameters_omitting_modes(mock_spark):
    with patch(
        "enterprise_fabric.retail.productos.entrypoints.publish_silver", return_value=DummyResult()
    ) as mock_etl:
        productos_ep.run_silver(
            [
                "--catalog",
                "test_cat",
                "--batch_id",
                "b1",
                "--quality_run_id",
                "q1",
            ]
        )
        mock_etl.assert_called_once_with(mock_spark, "test_cat", "b1", "q1")


def test_productos_silver_accepts_modes_without_altering_etl_call(mock_spark):
    with patch(
        "enterprise_fabric.retail.productos.entrypoints.publish_silver", return_value=DummyResult()
    ) as mock_etl:
        productos_ep.run_silver(
            [
                "--catalog",
                "test_cat",
                "--batch_id",
                "b1",
                "--quality_run_id",
                "q1",
                "--snapshot_mode",
                "INCREMENTAL",
                "--aggregate_mode",
                "INCREMENTAL",
            ]
        )
        mock_etl.assert_called_once_with(mock_spark, "test_cat", "b1", "q1")


@pytest.mark.parametrize(
    "bad_argv",
    [
        ["--catalog", "c", "--batch_id", "b", "--quality_run_id", "q", "--extra", "bad"],
        ["--cat", "c", "--batch_id", "b", "--quality_run_id", "q"],
        [
            "--catalog",
            "c",
            "--batch_id",
            "b",
            "--quality_run_id",
            "q",
            "--snapshot_mode",
            "BAD",
        ],
        [
            "--catalog",
            "c",
            "--batch_id",
            "b",
            "--quality_run_id",
            "q",
            "--aggregate_mode",
            "BAD",
        ],
    ],
)
def test_productos_silver_rejects_invalid_before_etl(bad_argv):
    with patch("enterprise_fabric.retail.productos.entrypoints.publish_silver") as mock_etl:
        with pytest.raises(SystemExit) as exc:
            productos_ep.run_silver(bad_argv)
        assert exc.value.code == 2
        mock_etl.assert_not_called()
