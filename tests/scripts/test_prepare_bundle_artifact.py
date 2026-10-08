import hashlib

import pytest

from scripts import prepare_bundle_artifact as artifact


def test_prebuilt_wheel_with_expected_checksum_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(artifact, "DIST", tmp_path)
    wheel = tmp_path / "enterprise_fabric-0.1.0-py3-none-any.whl"
    wheel.write_bytes(b"immutable-wheel")
    expected = hashlib.sha256(b"immutable-wheel").hexdigest()
    assert artifact.prepare(use_prebuilt=True, expected_sha256=expected) == wheel


def test_checksum_mismatch_blocks_deployment(tmp_path, monkeypatch):
    monkeypatch.setattr(artifact, "DIST", tmp_path)
    (tmp_path / "enterprise_fabric-0.1.0-py3-none-any.whl").write_bytes(b"changed")
    with pytest.raises(artifact.ArtifactError, match="checksum mismatch"):
        artifact.prepare(use_prebuilt=True, expected_sha256="0" * 64)


def test_multiple_wheels_are_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(artifact, "DIST", tmp_path)
    (tmp_path / "enterprise_fabric-a.whl").write_bytes(b"a")
    (tmp_path / "enterprise_fabric-b.whl").write_bytes(b"b")
    with pytest.raises(artifact.ArtifactError, match="found 2"):
        artifact.prepare(use_prebuilt=True, expected_sha256="0" * 64)
