"""Unsupervised person clustering (ported from V0).

DBSCAN over cosine distance, one global pass across all embeddings — photos
and video frames cluster together, so a person in a clip and in a photo get
the same label. DBSCAN (not k-means) because the number of people is unknown
and singleton/outlier faces must become noise (-1), never be forced into a
group.
"""

from __future__ import annotations

import numpy as np

DEFAULT_EPS = 0.5  # V0 default; higher merges more, lower splits more
DEFAULT_MIN_SAMPLES = 2
NOISE_LABEL = -1


def cluster_embeddings(
    embeddings: list[np.ndarray],
    eps: float = DEFAULT_EPS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> np.ndarray:
    """Run DBSCAN on a flat list of embeddings; return one label per embedding."""
    if not embeddings:
        return np.empty(0, dtype=int)
    from sklearn.cluster import DBSCAN
    X = np.asarray(embeddings, dtype=np.float32)
    return DBSCAN(eps=eps, min_samples=min_samples, metric="cosine", n_jobs=-1).fit_predict(X)
