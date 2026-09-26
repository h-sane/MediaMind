"""Classify faces against user-named example faces (teach-who's-who).

Replaces DBSCAN for libraries where the user has named examples. Open-set:
a face goes to a person only if it clearly matches that person's examples AND
beats the runner-up by a margin; lookalikes (same-group members) and
background strangers fall to pending review or unknown instead of being
silently glued onto someone. See docs/PEOPLE_TEACHING_DESIGN.md §3.2.

Examples may come from any library (people are recognised everywhere), so the
caller passes them in as plain arrays keyed by a person key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable

import numpy as np

# Calibration knobs — measured on the kpop library, not fixed laws.
AUTO_SIM = 0.45
SUGGEST_SIM = 0.32
MARGIN = 0.08
TOP_K = 3

AUTO = "auto"
PENDING = "pending"
UNKNOWN = "unknown"


@dataclass(frozen=True)
class Verdict:
    person: Hashable | None   # best candidate (None only when there are no examples)
    score: float
    runner_up: float
    decision: str             # AUTO | PENDING | UNKNOWN


def _unit(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    return x / np.maximum(np.linalg.norm(x, axis=-1, keepdims=True), 1e-12)


def person_scores(faces: np.ndarray, examples: dict[Hashable, np.ndarray], top_k: int = TOP_K) -> tuple[list, np.ndarray]:
    """Score every face against every person: mean of the top-k similarities
    to that person's examples (nearest examples, not a centroid — a centroid
    of stage and selfie shots looks like neither). Returns (keys, [n_faces, n_people])."""
    keys = [k for k, e in examples.items() if len(e)]
    F = _unit(faces)
    out = np.empty((len(F), len(keys)), dtype=np.float32)
    for j, k in enumerate(keys):
        sims = F @ _unit(examples[k]).T
        k_eff = min(top_k, sims.shape[1])
        out[:, j] = np.sort(sims, axis=1)[:, -k_eff:].mean(axis=1)
    return keys, out


def classify(
    faces: np.ndarray,
    examples: dict[Hashable, np.ndarray],
    *,
    auto_sim: float = AUTO_SIM,
    suggest_sim: float = SUGGEST_SIM,
    margin: float = MARGIN,
    top_k: int = TOP_K,
) -> list[Verdict]:
    faces = np.asarray(faces, dtype=np.float32).reshape(-1, faces.shape[-1] if len(faces) else 1)
    keys, S = person_scores(faces, examples, top_k) if len(faces) else ([], None)
    if not keys:
        return [Verdict(None, 0.0, 0.0, UNKNOWN) for _ in range(len(faces))]
    order = np.argsort(S, axis=1)
    verdicts = []
    for i in range(len(faces)):
        best = order[i, -1]
        s1 = float(S[i, best])
        s2 = float(S[i, order[i, -2]]) if len(keys) > 1 else -1.0
        if s1 >= auto_sim and s1 - s2 >= margin:
            d = AUTO
        elif s1 >= suggest_sim:
            d = PENDING
        else:
            d = UNKNOWN
        verdicts.append(Verdict(keys[best], s1, s2, d))
    return verdicts


if __name__ == "__main__":
    rng = np.random.default_rng(0)
    a, b = _unit(rng.normal(size=512)), _unit(rng.normal(size=512))
    look = _unit(a + b * 0.9)  # halfway between a and b: a lookalike

    def near(c, n):
        return _unit(c + rng.normal(scale=0.03, size=(n, 512)))

    ex = {"A": near(a, 5), "B": near(b, 5)}
    v = classify(np.vstack([near(a, 1), near(b, 1), look[None], _unit(rng.normal(size=(1, 512)))]), ex)
    assert (v[0].person, v[0].decision) == ("A", AUTO)
    assert (v[1].person, v[1].decision) == ("B", AUTO)
    assert v[2].decision == PENDING, v[2]      # lookalike is asked about, never auto-assigned
    assert v[3].decision == UNKNOWN, v[3]      # stranger is not glued onto anyone
    assert classify(near(a, 2), {})[0].decision == UNKNOWN
    print("classify self-check ok")
