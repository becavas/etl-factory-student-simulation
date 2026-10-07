"""Build locally or verify the single prebuilt wheel supplied by CI/CD."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

DIST = Path("dist")
PATTERN = "enterprise_fabric-*.whl"


class ArtifactError(ValueError):
    """The release artifact is missing, ambiguous, or has the wrong digest."""


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def one_wheel() -> Path:
    wheels = sorted(DIST.glob(PATTERN))
    if len(wheels) != 1:
        raise ArtifactError(f"expected one {PATTERN}; found {len(wheels)}")
    return wheels[0]


def prepare(*, use_prebuilt: bool, expected_sha256: str | None) -> Path:
    DIST.mkdir(exist_ok=True)
    if not use_prebuilt:
        for wheel in DIST.glob(PATTERN):
            wheel.unlink()
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel"],
            check=True,
        )
    wheel = one_wheel()
    actual = digest(wheel)
    if use_prebuilt:
        if not expected_sha256 or len(expected_sha256) != 64:
            raise ArtifactError("EF_EXPECTED_WHEEL_SHA256 must be a SHA-256")
        if actual != expected_sha256.lower():
            raise ArtifactError(
                f"wheel checksum mismatch: expected={expected_sha256} actual={actual}"
            )
    print(f"{actual}  {wheel.as_posix()}")
    return wheel


def main() -> int:
    try:
        prepare(
            use_prebuilt=os.environ.get("EF_USE_PREBUILT_WHEEL") == "true",
            expected_sha256=os.environ.get("EF_EXPECTED_WHEEL_SHA256"),
        )
    except (ArtifactError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
