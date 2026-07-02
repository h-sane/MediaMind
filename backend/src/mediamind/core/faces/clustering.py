"""Unsupervised person clustering (ported from V0).

DBSCAN over cosine distance, one global pass across all embeddings — photos
and video frames cluster together, so a person in a clip and in a photo get
the same label. DBSCAN (not k-means) because the number of people is unknown
and singleton/outlier faces must become noise (-1), never be forced into a
group.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from mediamind.core.faces.engine import MediaFaces

DEFAULT_EPS = 0.5  # V0 default; higher merges more, lower splits more
DEFAULT_MIN_SAMPLES = 2
NOISE_LABEL = -1


@dataclass
class ClusterResult:
    labels: np.ndarray  # one label per embedding, -1 = noise
    media_people: dict[int, set[int]] = field(default_factory=dict)  # media idx -> labels
    n_people: int = 0


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


def cluster_media_faces(
    media_faces: list[MediaFaces],
    eps: float = DEFAULT_EPS,
    min_samples: int = DEFAULT_MIN_SAMPLES,
) -> ClusterResult:
    """One global DBSCAN pass over every embedding from every file."""
    embeddings: list[np.ndarray] = []
    owner: list[int] = []  # media index per embedding
    for idx, mf in enumerate(media_faces):
        for emb in mf.embeddings:
            embeddings.append(emb)
            owner.append(idx)

    labels = cluster_embeddings(embeddings, eps=eps, min_samples=min_samples)

    result = ClusterResult(labels=labels)
    for label, media_idx in zip(labels, owner):
        result.media_people.setdefault(media_idx, set()).add(int(label))
    result.n_people = len({l for l in labels if l != NOISE_LABEL})
    return result
