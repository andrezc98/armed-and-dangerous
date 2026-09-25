"""Nothing renders a manifest before load_images() has run, so the tests fill
cell.IMAGES the same way a lab day does: from the two fixtures, with the
documentation account id 123456789012 as the registry."""

import json
import subprocess

import pytest

import cell
import config

# Commands that reach the cluster, AWS or state. Tests must never run them for
# real: on 2026-09-25 a test whose mocks missed a new code path applied two
# YCSB Jobs to the live lab cluster (they stayed Pending and were deleted).
_LIVE = ("kubectl", "aws", "helm", "terraform")


def _local_only(cmd):
    """kubectl kustomize and --dry-run=client never leave the laptop."""
    return (cmd[0] not in _LIVE or cmd[:2] == ["kubectl", "kustomize"]
            or "--dry-run=client" in cmd)


class _Guarded:
    def __getattr__(self, name):
        return getattr(subprocess, name)

    def run(self, cmd, *a, **k):
        if not _local_only(cmd):
            raise AssertionError(f"test tried to run a live command: {' '.join(cmd)}")
        return subprocess.run(cmd, *a, **k)

    def Popen(self, cmd, *a, **k):
        if not _local_only(cmd):
            raise AssertionError(f"test tried to start a live command: {' '.join(cmd)}")
        return subprocess.Popen(cmd, *a, **k)


@pytest.fixture(autouse=True)
def no_live_commands(monkeypatch):
    monkeypatch.setattr(config, "subprocess", _Guarded())


@pytest.fixture(autouse=True)
def own_images():
    registry = json.loads(cell.FIXTURE_ECR.read_text())["registry"]["value"]
    images = json.loads(cell.FIXTURE_IMAGES.read_text())["images"]
    tags = {name: images[name]["tag"] for name in cell.OWN_IMAGES}
    before = dict(cell.IMAGES)
    cell.IMAGES.update(registry=registry, tags=tags)
    yield cell.IMAGES
    cell.IMAGES.clear()
    cell.IMAGES.update(before)
