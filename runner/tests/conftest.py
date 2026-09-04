"""Nothing renders a manifest before load_images() has run, so the tests fill
cell.IMAGES the same way a lab day does: from the two fixtures, with the
documentation account id 123456789012 as the registry."""

import json

import pytest

import cell


@pytest.fixture(autouse=True)
def own_images():
    registry = json.loads(cell.FIXTURE_ECR.read_text())["registry"]["value"]
    tag = json.loads(cell.FIXTURE_IMAGES.read_text())["tag"]
    before = dict(cell.IMAGES)
    cell.IMAGES.update(registry=registry, tag=tag)
    yield cell.IMAGES
    cell.IMAGES.clear()
    cell.IMAGES.update(before)
