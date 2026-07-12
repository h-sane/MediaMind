"""End-to-end smoke test against real media supplied by the project owner.

Exercises the full HTTP pipeline (register library -> dedupe scan -> real
face scan -> rescan stability -> stale-row pruning -> organize preview /
execute / undo) against a real folder of photos and videos, using the real
InsightFace provider (already downloaded to ~/.insightface on this dev
machine from earlier prototype work).

This is a manual/local-only smoke test, not part of the standard suite: it
is skipped entirely when the real media folder or the InsightFace model
files are not present (fresh clone, CI, another contributor's machine).

Runs against a COPY of the real folder under pytest's tmp_path — never the
original. Organize/undo and duplicate-trash are real filesystem mutations;
running them against a throwaway copy is what makes that safe to do
unattended (see session 08 handoff for the reasoning).
"""

from __future__ import annotations

import contextlib
import shutil
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mediamind.api.app import create_app
from mediamind.config import library_data_dir
from mediamind.core.hashing import hash_file
from mediamind.core.scanner import scan_folder
from mediamind.providers.catalog import CATALOG
from mediamind.providers.manager import ProviderManager
from mediamind.store.db import library_db_path, open_db

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_MEDIA_DIR = REPO_ROOT / "test"
INSIGHTFACE_ROOT = Path.home() / ".insightface"
BUFFALO_L_DIR = INSIGHTFACE_ROOT / "models" / "buffalo_l"
PROVIDER_ID = "insightface-buffalo-l"

# Excluded outright: filename indicates adult content, not personal-photo
# test material -- never staged, never run through any pipeline.
EXCLUDE_NAMES = {
    "印度网红女神_Anjali_屏幕前的高贵女神_私底下却是别人操腻了的母狗_Anjali_印度_网红_女神_AnjaliArora.mp4",
}

# Real InsightFace detection on CPU costs ~1s/image and ~15-20s/video
# (DEFAULT_VIDEO_FRAMES=15 sampled frames each). The folder has ~130 videos;
# processing all of them would take ~40 minutes. Sample a subset spread
# across the sorted name list for content diversity while keeping a full
# scan to a few minutes.
MAX_VIDEOS = 10

JOB_TIMEOUT_S = 1800  # hard cap per scan job; fail loudly instead of hanging

pytestmark = pytest.mark.real_media

insightface = pytest.importorskip("insightface")

if not REAL_MEDIA_DIR.is_dir():
    pytest.skip(f"real media folder not found at {REAL_MEDIA_DIR}", allow_module_level=True)
if not BUFFALO_L_DIR.is_dir():
    pytest.skip(f"InsightFace buffalo_l model not found at {BUFFALO_L_DIR}", allow_module_level=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _conn(lib_dir: Path):
    c = open_db(library_db_path(library_data_dir(lib_dir)))
    try:
        yield c
    finally:
        c.close()


def _content_hashes(root: Path) -> list[str]:
    """Sorted multiset of content hashes for every real file under root.

    Path-independent by design: used to prove file *content* survives a
    move+undo round trip even though paths change.
    """
    return sorted(hash_file(sf.path) for sf in scan_folder(root))


def _wait_for_job(client: TestClient, lib_id: str, job_id: str, timeout: float) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        res = client.get(f"/v1/libraries/{lib_id}/scans/{job_id}")
        assert res.status_code == 200
        job = res.json()
        if job["state"] in ("succeeded", "failed", "cancelled"):
            return job
        time.sleep(0.5)
    pytest.fail(f"job {job_id} did not reach a terminal state within {timeout}s")


def _stage_library(tmp_path: Path) -> Path:
    lib_dir = tmp_path / "library"
    all_videos = sorted(
        p.name for p in REAL_MEDIA_DIR.iterdir()
        if p.suffix.lower() == ".mp4" and p.name not in EXCLUDE_NAMES
    )
    keep_videos = set(all_videos[:: max(1, len(all_videos) // MAX_VIDEOS)][:MAX_VIDEOS])
    skip_videos = {n for n in all_videos if n not in keep_videos}

    def _ignore(_dir: str, names: list[str]) -> set[str]:
        return {n for n in names if n in EXCLUDE_NAMES or n in skip_videos}

    shutil.copytree(REAL_MEDIA_DIR, lib_dir, ignore=_ignore)

    # Deliberately corrupt file: valid-looking extension, garbage bytes.
    # Exercises decode-failure handling end to end (unreadable_files count,
    # files.decoded_ok, and organize routing to People/_unsorted).
    (lib_dir / "zzz_corrupt.jpg").write_bytes(b"not a real jpeg" * 100)
    return lib_dir


@pytest.fixture
def real_provider_manager():
    """ProviderManager using the real ~/.insightface cache.

    buffalo_l is already downloaded there (from earlier prototype work).
    insightface_pack entries resolve to InsightFace's own cache root by
    default, and is_installed() checks the real .onnx files — so the pack
    counts as installed with no marker and no download.
    """
    pm = ProviderManager(INSIGHTFACE_ROOT, catalog=CATALOG)
    assert pm.is_installed(PROVIDER_ID), "buffalo_l files present but not detected"
    return pm


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, real_provider_manager: ProviderManager):
    monkeypatch.setenv("MEDIAMIND_DATA_DIR", str(tmp_path / "appdata"))
    with TestClient(create_app(provider_manager=real_provider_manager)) as c:
        yield c


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------

def test_full_pipeline_against_real_media(client: TestClient, tmp_path: Path):
    lib_dir = _stage_library(tmp_path)
    total_files_before = sum(1 for _ in scan_folder(lib_dir))
    print(f"\n[stage] {total_files_before} files staged from real media")

    res = client.post("/v1/libraries", json={"path": str(lib_dir)})
    assert res.status_code == 201
    lib_id = res.json()["id"]

    # ============================================================
    # 1. Dedupe scan: run, review, dry-run, real trash (real send2trash)
    # ============================================================
    res = client.post(f"/v1/libraries/{lib_id}/scans", json={"type": "dedupe"})
    assert res.status_code == 202
    job = _wait_for_job(client, lib_id, res.json()["id"], timeout=300)
    assert job["state"] == "succeeded", job.get("error")
    dedupe_summary = job["result"]
    assert dedupe_summary["files"] <= total_files_before
    print(f"[dedupe] groups={dedupe_summary['groups']} files={dedupe_summary['files']} "
          f"reclaimable_bytes={dedupe_summary['reclaimable_bytes']}")

    dup = client.get(f"/v1/libraries/{lib_id}/duplicates")
    assert dup.status_code == 200
    groups = dup.json()["groups"]

    trashed_paths: list[Path] = []
    group = next((g for g in groups if any(f["suggested_keep"] for f in g["files"])), None)
    if group is not None:
        trash_ids = [f["id"] for f in group["files"] if not f["suggested_keep"]]
        if trash_ids:
            res = client.post(
                f"/v1/libraries/{lib_id}/duplicates/resolutions",
                json={"resolutions": [{"file_id": fid, "action": "trash"} for fid in trash_ids]},
            )
            assert res.status_code == 200

            # Safety guard: stale expected_trash_count is rejected.
            res = client.post(
                f"/v1/libraries/{lib_id}/duplicates/execute",
                json={"dry_run": True, "expected_trash_count": len(trash_ids) + 1},
            )
            assert res.status_code == 409

            paths = [lib_dir / f["path"] for f in group["files"] if not f["suggested_keep"]]

            # Dry run changes nothing on disk.
            res = client.post(
                f"/v1/libraries/{lib_id}/duplicates/execute",
                json={"dry_run": True, "expected_trash_count": len(trash_ids)},
            )
            assert res.status_code == 200 and res.json()["dry_run"] is True
            for p in paths:
                assert p.exists()

            # Real trash -> files leave their original location (recycle bin, recoverable).
            res = client.post(
                f"/v1/libraries/{lib_id}/duplicates/execute",
                json={"dry_run": False, "expected_trash_count": len(trash_ids)},
            )
            assert res.status_code == 200
            report = res.json()
            assert report["ok"] is True
            for p in paths:
                assert not p.exists()
            trashed_paths = paths
            print(f"[dedupe] trashed {len(trash_ids)} file(s) via send2trash")
    else:
        print("[dedupe] no group had a suggested keeper in this sample — skipping trash exercise")

    # ============================================================
    # 2. Face scan (real InsightFace) -- first run
    # ============================================================
    res = client.post(
        f"/v1/libraries/{lib_id}/scans",
        json={"type": "faces", "provider_id": PROVIDER_ID},
    )
    assert res.status_code == 202
    job1 = _wait_for_job(client, lib_id, res.json()["id"], timeout=JOB_TIMEOUT_S)
    assert job1["state"] == "succeeded", job1.get("error")
    s1 = job1["result"]
    print(f"[faces#1] files={s1['files']} faces={s1['faces']} people={s1['people']} "
          f"no_face={s1['no_face_files']} unreadable={s1['unreadable_files']}")

    assert s1["unreadable_files"] >= 1, "injected corrupt file was not flagged unreadable"

    with _conn(lib_dir) as conn:
        row = conn.execute(
            "SELECT decoded_ok FROM files WHERE path = ?", ("zzz_corrupt.jpg",)
        ).fetchone()
        assert row is not None, "corrupt file was never registered in files table"
        assert row["decoded_ok"] == 0

    persons_res = client.get(f"/v1/libraries/{lib_id}/persons")
    assert persons_res.status_code == 200
    persons_body = persons_res.json()
    print(f"[faces#1] persons clustered={len(persons_body['persons'])} "
          f"unassigned={persons_body['unassigned_faces']} "
          f"multi_person_files={persons_body['multi_person_count']}")

    # Conservation invariant: every detected face is either assigned to a
    # person or counted as unassigned -- nothing can vanish in between.
    assigned_total = sum(p["face_count"] for p in persons_body["persons"])
    assert assigned_total + persons_body["unassigned_faces"] == s1["faces"]

    # ============================================================
    # 3. Delete one file with faces, then rescan: stale-row pruning (fix 13)
    #    combined with a general rescan-stability check.
    # ============================================================
    with _conn(lib_dir) as conn:
        row = conn.execute(
            """
            SELECT fi.id, fi.path, COUNT(*) AS n
            FROM files fi JOIN faces f ON f.file_id = fi.id
            GROUP BY fi.id ORDER BY fi.id LIMIT 1
            """
        ).fetchone()

    victim_faces = 0
    if row is not None:
        victim_path = lib_dir / row["path"]
        with _conn(lib_dir) as conn:
            victim_faces = conn.execute(
                "SELECT COUNT(*) FROM faces WHERE file_id = ?", (row["id"],)
            ).fetchone()[0]
        victim_path.unlink()
        print(f"[faces#2] deleted {row['path']} externally ({victim_faces} face row(s) expected pruned)")

    res = client.post(
        f"/v1/libraries/{lib_id}/scans",
        json={"type": "faces", "provider_id": PROVIDER_ID},
    )
    assert res.status_code == 202
    job2 = _wait_for_job(client, lib_id, res.json()["id"], timeout=JOB_TIMEOUT_S)
    assert job2["state"] == "succeeded", job2.get("error")
    s2 = job2["result"]
    print(f"[faces#2] files={s2['files']} faces={s2['faces']} people={s2['people']}")

    if row is not None:
        assert s2["faces"] == s1["faces"] - victim_faces, (
            "face count did not drop by exactly the deleted file's rows -- "
            "stale-row pruning (or rescan stability) regression"
        )
        with _conn(lib_dir) as conn:
            remaining = conn.execute(
                "SELECT COUNT(*) FROM faces WHERE file_id = ?", (row["id"],)
            ).fetchone()[0]
        assert remaining == 0, "stale faces for an externally-deleted file were not pruned"
    else:
        assert s2["faces"] == s1["faces"], "face count drifted on an unchanged rescan"

    # ============================================================
    # 4. Organize: preview -> execute -> re-preview (no churn) -> undo
    # ============================================================
    preview = client.post(f"/v1/libraries/{lib_id}/organize/preview")
    assert preview.status_code == 200
    plan = preview.json()
    print(f"[organize] planned={plan['planned']} by_person={plan['by_person']}")
    assert plan["planned"] > 0, "organize plan is empty -- expected at least the corrupt file"

    hashes_before = _content_hashes(lib_dir)
    expected_planned = plan["planned"]

    res = client.post(
        f"/v1/libraries/{lib_id}/organize/execute",
        json={"dry_run": False, "expected_planned": expected_planned},
    )
    assert res.status_code == 200
    report = res.json()
    assert report["ok"] is True
    assert report["handled"] == expected_planned

    hashes_after_organize = _content_hashes(lib_dir)
    assert hashes_after_organize == hashes_before, "file content changed during organize (copy-then-delete violated)"

    unsorted_path = lib_dir / "People" / "_unsorted" / "zzz_corrupt.jpg"
    assert unsorted_path.exists(), (
        "undecodable file did not route to People/_unsorted -- "
        "violates the 'everything routes somewhere' safety invariant"
    )

    with _conn(lib_dir) as conn:
        db_row = conn.execute(
            "SELECT path FROM files WHERE path LIKE '%zzz_corrupt.jpg'"
        ).fetchone()
    assert db_row["path"] == "People/_unsorted/zzz_corrupt.jpg", "files.path not updated after organize execute"

    # Re-running organize immediately must plan nothing further (skip-in-place, fix 3).
    preview2 = client.post(f"/v1/libraries/{lib_id}/organize/preview")
    assert preview2.status_code == 200
    assert preview2.json()["planned"] == 0, "re-running organize planned more moves -- churn regression"

    # With nothing left to plan, execute must refuse rather than silently no-op.
    res = client.post(
        f"/v1/libraries/{lib_id}/organize/execute",
        json={"dry_run": False, "expected_planned": expected_planned},
    )
    assert res.status_code == 422

    # Undo restores everything, byte-for-byte.
    res = client.post(f"/v1/libraries/{lib_id}/organize/undo")
    assert res.status_code == 200
    undo_report = res.json()
    assert undo_report["ok"] is True
    assert undo_report["handled"] == expected_planned

    hashes_after_undo = _content_hashes(lib_dir)
    assert hashes_after_undo == hashes_before, "undo did not fully restore original file content"
    assert (lib_dir / "zzz_corrupt.jpg").exists(), "corrupt file not restored to its original path by undo"

    with _conn(lib_dir) as conn:
        db_row = conn.execute(
            "SELECT path FROM files WHERE path = 'zzz_corrupt.jpg'"
        ).fetchone()
    assert db_row is not None, "files.path not restored after undo"

    # A second undo has nothing left to reverse.
    res = client.post(f"/v1/libraries/{lib_id}/organize/undo")
    assert res.status_code == 404

    audit = client.get(f"/v1/libraries/{lib_id}/organize/audit")
    assert audit.status_code == 200
    kinds = {a["kind"] for a in audit.json()}
    assert {"organize-by-person", "undo"} <= kinds

    print("[organize] execute -> re-preview(empty) -> undo round-trip OK, byte content preserved throughout")
    print(f"[summary] {total_files_before} staged files, {len(trashed_paths)} trashed as duplicates, "
          f"{s1['people']} person cluster(s), {expected_planned} file(s) organized and undone cleanly")
