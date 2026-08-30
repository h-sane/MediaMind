"""Write-ahead journal + auto-resume (ADR-0005).

Covers the three properties that matter: a finished batch leaves no journal, an
interrupted batch's leftover is resumed (moving only the still-present source),
and journaling never disturbs a normal move when unconfigured.
"""

from pathlib import Path

from mediamind.core import journal
from mediamind.core.safety import FileOp, execute


def _mk(path: Path, content: str = "data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _configure(tmp_path: Path) -> Path:
    jdir = tmp_path / "journals"
    jdir.mkdir()
    journal.configure(jdir)
    return jdir


def test_clean_run_leaves_no_journal(tmp_path: Path):
    jdir = _configure(tmp_path)
    try:
        src = _mk(tmp_path / "src" / "a.jpg")
        report = execute([FileOp(src, tmp_path / "out")])
        assert report.ok
        assert list(jdir.glob("*.json")) == []  # deleted on normal return
    finally:
        journal.configure(None)


def test_interrupted_batch_is_resumed(tmp_path: Path):
    jdir = _configure(tmp_path)
    try:
        # Simulate a crash mid-batch: one file already moved before the crash
        # (source gone, in `out`), one still pending (source present). The
        # journal names both, as it would have at batch start.
        done_dest = _mk(tmp_path / "out" / "done.jpg")  # "already moved" copy
        pending_src = _mk(tmp_path / "src" / "pending.jpg")
        gone_src = tmp_path / "src" / "done.jpg"  # unlinked by the crash

        payload_ops = [
            FileOp(gone_src, tmp_path / "out"),
            FileOp(pending_src, tmp_path / "out"),
        ]
        jpath = journal.begin(payload_ops)
        assert jpath is not None and jpath.exists()

        resumed = journal.resume_pending()

        assert resumed == 1
        assert list(jdir.glob("*.json")) == []          # journal cleared
        assert (tmp_path / "out" / "pending.jpg").exists()  # pending finished
        assert not pending_src.exists()                  # source removed (moved)
        assert done_dest.exists()                        # already-done left alone
    finally:
        journal.configure(None)


def test_unconfigured_is_a_no_op(tmp_path: Path):
    journal.configure(None)
    src = _mk(tmp_path / "src" / "a.jpg")
    assert journal.begin([FileOp(src, tmp_path / "out")]) is None
    assert journal.resume_pending() == 0
    # Move still works with journaling off.
    assert execute([FileOp(src, tmp_path / "out")]).ok
