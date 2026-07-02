"""End-to-end face pipeline, model-free: scan -> extract -> cluster -> route.

FakeColorProvider makes solid-color fixtures act like people: red media is
one person, blue another, black frames have no face.
"""

from pathlib import Path

from mediamind.core.faces.clustering import cluster_media_faces
from mediamind.core.faces.engine import extract_faces
from mediamind.core.organizer import (
    FOLDER_NO_FACE,
    FOLDER_UNSORTED,
    person_folder_name,
    route_media,
)
from mediamind.core.scanner import scan_folder
from mediamind.providers.fake import FakeColorProvider


def run_pipeline(library: Path):
    files = [f for f in scan_folder(library) if f.is_media]
    media_faces = extract_faces(files, FakeColorProvider(), min_face_size=10)
    clusters = cluster_media_faces(media_faces)
    return files, media_faces, clusters


def test_two_people_found(media_library: Path):
    _, _, clusters = run_pipeline(media_library)
    assert clusters.n_people == 2  # red and blue


def test_photos_and_gif_of_same_person_share_a_cluster(media_library: Path):
    files, _, clusters = run_pipeline(media_library)
    label_sets = {}
    for idx, f in enumerate(files):
        if f.path.name in ("red1.jpg", "red2.png", "red3.jpg", "red.gif"):
            label_sets[f.path.name] = clusters.media_people.get(idx)
    values = list(label_sets.values())
    assert all(v == values[0] and v is not None for v in values)


def test_routing_covers_every_file(media_library: Path):
    """V0 invariant: everything routes somewhere (or explicitly to review)."""
    files, media_faces, clusters = run_pipeline(media_library)
    for idx, mf in enumerate(media_faces):
        route = route_media(mf.decoded_ok, clusters.media_people.get(idx))
        assert route.needs_review or route.folder is not None


def test_routing_rules(media_library: Path):
    files, media_faces, clusters = run_pipeline(media_library)
    by_name = {mf.file.path.name: idx for idx, mf in enumerate(media_faces)}

    corrupt = route_media(
        media_faces[by_name["corrupt.jpg"]].decoded_ok,
        clusters.media_people.get(by_name["corrupt.jpg"]),
    )
    assert corrupt.folder == FOLDER_UNSORTED  # undecodable -> visible holding area

    black = route_media(
        media_faces[by_name["black.jpg"]].decoded_ok,
        clusters.media_people.get(by_name["black.jpg"]),
    )
    assert black.folder == FOLDER_NO_FACE  # decoded, zero faces

    red = route_media(
        media_faces[by_name["red1.jpg"]].decoded_ok,
        clusters.media_people.get(by_name["red1.jpg"]),
    )
    assert red.folder is not None and red.folder.startswith("Person_")
    assert not red.needs_review  # single person -> direct route


def test_multi_person_media_needs_review():
    """PRD Feature 3: several people -> user review, no auto-copies."""
    route = route_media(True, {0, 1, 2})
    assert route.needs_review
    assert route.folder is None
    assert route.person_labels == (0, 1, 2)


def test_noise_only_faces_go_to_unsorted():
    route = route_media(True, {-1})
    assert route.folder == FOLDER_UNSORTED


def test_person_folder_naming():
    assert person_folder_name(0) == "Person_001"
    assert person_folder_name(41) == "Person_042"


def test_fault_isolation_on_corrupt_file(media_library: Path):
    files = [f for f in scan_folder(media_library) if f.is_media]
    media_faces = extract_faces(files, FakeColorProvider(), min_face_size=10)
    corrupt = next(mf for mf in media_faces if mf.file.path.name == "corrupt.jpg")
    assert corrupt.decoded_ok is False
    assert corrupt.embeddings == []
    # ...and the rest of the batch still processed fine
    assert sum(1 for mf in media_faces if mf.embeddings) >= 5
