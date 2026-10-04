"""Tests for canonical deterministic keys and unique assertion."""

import pytest
from pyspark.sql import functions as F

from enterprise_fabric.retail.ventas.keys import (
    assert_unique,
    canonical_key,
    payload_hash,
)


def test_canonical_json_avoids_delimiter_ambiguity(spark):
    rows = spark.createDataFrame(
        [(1, "A|B", "C"), (2, "A", "B|C")],
        ["position", "left", "right"],
    )
    result = (
        rows.select(
            "position",
            canonical_key("test_key", ["left", "right"]).alias("key"),
        )
        .orderBy("position")
        .collect()
    )
    assert len(result[0].key) == 64
    assert result[0].key != result[1].key


def test_same_payload_produces_same_key(spark):
    rows = spark.range(2).select(
        F.lit("PED-1").alias("pedido_id"),
        F.lit("ITEM-1").alias("item_id"),
    )
    assert (
        rows.select(canonical_key("fact_ventas", ["pedido_id", "item_id"]).alias("key"))
        .distinct()
        .count()
        == 1
    )


def test_different_namespaces_produce_different_keys(spark):
    rows = spark.createDataFrame([("VAL-1",)], ["val"])
    key1 = rows.select(canonical_key("namespace_a", ["val"]).alias("k")).first().k
    key2 = rows.select(canonical_key("namespace_b", ["val"]).alias("k")).first().k
    assert key1 != key2


def test_field_order_changes_key(spark):
    rows = spark.createDataFrame([("A", "B")], ["f1", "f2"])
    k_ab = rows.select(canonical_key("test", ["f1", "f2"]).alias("k")).first().k
    k_ba = rows.select(canonical_key("test", ["f2", "f1"]).alias("k")).first().k
    assert k_ab != k_ba


def test_payload_hash_uses_payload_namespace(spark):
    rows = spark.createDataFrame([("A",)], ["val"])
    p_hash = rows.select(payload_hash("entity", ["val"]).alias("h")).first().h
    c_key = rows.select(canonical_key("payload_entity", ["val"]).alias("h")).first().h
    assert p_hash == c_key


def test_canonical_key_empty_columns_raises():
    with pytest.raises(ValueError, match="columns must not be empty"):
        canonical_key("ns", [])


def test_assert_unique_raises_on_duplicates(spark):
    dups = spark.createDataFrame([("ID1", 1), ("ID1", 2)], ["id", "val"])
    with pytest.raises(ValueError, match="test_label has duplicate MERGE keys"):
        assert_unique(dups, ["id"], "test_label")


def test_assert_unique_passes_on_unique(spark):
    unique = spark.createDataFrame([("ID1", 1), ("ID2", 2)], ["id", "val"])
    assert_unique(unique, ["id"], "test_label")


def test_assert_unique_empty_keys_raises(spark):
    df = spark.createDataFrame([(1,)], ["val"])
    with pytest.raises(ValueError, match="keys must not be empty"):
        assert_unique(df, [], "test_label")
