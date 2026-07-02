"""Integration tests that need the real InsightFace model (~300 MB download).

Excluded from default runs and CI: `pytest -m integration` to run them.
"""

import numpy as np
import pytest

pytestmark = pytest.mark.integration

insightface = pytest.importorskip("insightface")


def test_provider_loads_and_runs_on_blank_frame():
    from mediamind.providers.insightface_provider import InsightFaceProvider

    provider = InsightFaceProvider()
    provider.prepare()
    # A blank frame has no faces; the call must succeed and return [].
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    assert provider.get_faces(frame) == []
