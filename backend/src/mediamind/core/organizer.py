"""Routing and organize-plan building (V0 `targets_for_media`, evolved).

The V0 invariant holds: EVERY file routes somewhere. Undecodable files and
ungroupable faces go to visible holding folders, never nowhere. What changed
from V0 (per PRD Feature 3): media with multiple people is NOT copied into
every person's folder — it is flagged for user review and gets exactly one
final destination.
"""

from __future__ import annotations

from dataclasses import dataclass

from mediamind.core.faces.clustering import NOISE_LABEL

FOLDER_NO_FACE = "_no_face"
FOLDER_UNSORTED = "_unsorted"
FOLDER_OTHERS = "_others"
PERSON_PREFIX = "Person_"


def person_folder_name(label: int) -> str:
    return f"{PERSON_PREFIX}{label + 1:03d}"


@dataclass(frozen=True)
class Route:
    """Where one media file belongs after a face scan."""

    folder: str | None  # single destination, or None when review is required
    person_labels: tuple[int, ...]  # real (non-noise) cluster labels found
    needs_review: bool  # multiple people -> user picks the final home


def route_media(decoded_ok: bool, people: set[int] | None) -> Route:
    """Pure routing decision for one file (V0 rules + review for multi-person).

    - not decoded            -> _unsorted
    - decoded, zero faces    -> _no_face
    - exactly one person     -> that person's folder
    - several people         -> needs_review (user chooses; no duplicate copies)
    - only noise faces       -> _unsorted
    """
    if not decoded_ok:
        return Route(FOLDER_UNSORTED, (), False)
    if not people:
        return Route(FOLDER_NO_FACE, (), False)
    real = tuple(sorted(l for l in people if l != NOISE_LABEL))
    if not real:
        return Route(FOLDER_UNSORTED, (), False)
    if len(real) == 1:
        return Route(person_folder_name(real[0]), real, False)
    return Route(None, real, True)
