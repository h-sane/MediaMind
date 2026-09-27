"""People folders: file counts, a primary folder per person, moving a person's files there,
group pictures, and auto-filing new pictures from opted-in watched folders.

A person is a *name*, everywhere: the same rule teaching uses to pool examples. The primary
folder is kept on the global person(s) of that name (store/global_people.py) as an absolute
path, so it can be in another library or drive. A picture with two or more named people can
only go one place; that choice is a group rule keyed by the set of names (`group_rules`), or
the picture waits for the user. Moves go through core/safety.execute (copy-then-delete, a
manifest), are recorded for undo, and keep the index row when the file stays in its library.
See docs/PEOPLE_FOLDERS_AUTOFILE_PLAN.md.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

from mediamind.config import global_moves_dir
from mediamind.core.faces.teach import name_key
from mediamind.core.hashing import hash_file, is_sampled, sampled_hash
from mediamind.core.organize_plan import safe_folder_name
from mediamind.core.safety import FileOp, execute as safety_execute
from mediamind.store import global_people as gp_store
from mediamind.store.db import open_library_db

logger = logging.getLogger(__name__)

MEDIA_KINDS = ("image", "video")


# --- counts ---------------------------------------------------------------------------------

def file_stats(conn: sqlite3.Connection, under: str | None = None) -> dict:
    """Pictures and videos in this library (or under one of its folders): sorted (someone in it
    is named), unsorted (it has faces, nobody named yet) and no faces (none were found)."""
    prefix = under.strip("/").replace("\\", "/") + "/" if under and under.strip("/") else None
    rows = conn.execute(
        """
        SELECT fi.path,
               EXISTS(SELECT 1 FROM faces f JOIN persons p ON p.id = f.person_id
                      WHERE f.file_id = fi.id AND p.name IS NOT NULL) AS named,
               EXISTS(SELECT 1 FROM faces f WHERE f.file_id = fi.id) AS has_faces
        FROM files fi WHERE fi.kind IN ('image', 'video')
        """
    ).fetchall()
    total = sorted_ = unsorted = 0
    for r in rows:
        if prefix and not r["path"].replace("\\", "/").startswith(prefix):
            continue
        total += 1
        if r["named"]:
            sorted_ += 1
        elif r["has_faces"]:
            unsorted += 1
    return {"total": total, "sorted": sorted_, "unsorted": unsorted, "no_faces": total - sorted_ - unsorted}


def no_face_files(conn: sqlite3.Connection, under: str | None = None) -> list[dict]:
    """The pictures and videos in which the scan found no face (the "no faces" count), so the
    user can look at them and keep, move or delete each one."""
    prefix = under.strip("/").replace("\\", "/") + "/" if under and under.strip("/") else None
    rows = conn.execute(
        """
        SELECT fi.id, fi.path, fi.kind, fi.size FROM files fi
        WHERE fi.kind IN ('image', 'video') AND NOT EXISTS (SELECT 1 FROM faces f WHERE f.file_id = fi.id)
        ORDER BY fi.path COLLATE NOCASE
        """
    ).fetchall()
    return [{"file_id": r["id"], "path": r["path"], "kind": r["kind"], "size": r["size"]}
            for r in rows if not prefix or r["path"].replace("\\", "/").startswith(prefix)]


# --- primary folders (by name) --------------------------------------------------------------

def primary_folders(gp_conn: sqlite3.Connection) -> dict[str, str]:
    """name key -> primary folder, for every name that has one."""
    out: dict[str, str] = {}
    for g in gp_store.list_global_persons(gp_conn):
        if g.primary_location:
            out.setdefault(name_key(g.name), g.primary_location)
    return out


def set_primary_folder(gp_conn: sqlite3.Connection, library_id: str, local_person_id: int, name: str,
                       provider_id: str, path: str | None) -> str | None:
    """Set (or clear) the primary folder of everyone called `name`. `path` must be an existing
    folder; it is stored resolved. Links this library's person to the global person of that name,
    creating it if needed."""
    if path is not None:
        p = Path(path).expanduser()
        if not p.is_dir():
            raise ValueError("Pick a folder that exists.")
        path = str(p.resolve())
    key = name_key(name)
    same = [g for g in gp_store.list_global_persons(gp_conn) if name_key(g.name) == key]
    gid = gp_store.global_for_local(gp_conn, library_id, local_person_id)
    if gid is None:
        gid = same[0].id if same else gp_store.create_global_person(gp_conn, " ".join(name.split()))
        gp_store.link(gp_conn, gid, library_id, local_person_id, provider_id)
    for g in {gid, *(g.id for g in same)}:
        gp_store.set_primary_location(gp_conn, g, path)
    return path


# --- group rules ----------------------------------------------------------------------------

def group_key(names: set[str]) -> str:
    return "|".join(sorted(names))


@dataclass(frozen=True)
class GroupRule:
    dest: str | None  # None: leave these pictures where they are


def settled_groups(gp_conn: sqlite3.Connection) -> set[str]:
    return {r["content_hash"] for r in gp_conn.execute("SELECT content_hash FROM group_settled")}


def settle_groups(gp_conn: sqlite3.Connection, files: list[NamedFile]) -> None:
    gp_conn.executemany("INSERT OR IGNORE INTO group_settled (content_hash, created_at) VALUES (?, ?)",
                        [(f.content_hash, time.time()) for f in files if f.content_hash])
    gp_conn.commit()


def group_rules(gp_conn: sqlite3.Connection) -> dict[str, GroupRule]:
    return {r["key"]: GroupRule(r["dest"]) for r in gp_conn.execute("SELECT key, dest FROM group_rules")}


def set_group_rule(gp_conn: sqlite3.Connection, names: list[str], dest: str | None) -> None:
    gp_conn.execute(
        "INSERT INTO group_rules (key, names, dest, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET dest = excluded.dest, names = excluded.names",
        (group_key({name_key(n) for n in names}), ", ".join(sorted(names, key=str.casefold)), dest, time.time()))
    gp_conn.commit()


def existing_group_folders(parent: Path, depth: int = 2, limit: int = 300) -> list[str]:
    """Folders that already exist under `parent` (two levels down), so a group picture can go
    into one made earlier (AESPA\\OT4) instead of only a new one. Hidden and system folders
    (".mediamind", "$RECYCLE.BIN") are left out."""
    out: list[str] = []
    level = [str(parent)]
    for _ in range(depth):
        below: list[str] = []
        for folder in level:
            try:
                with os.scandir(folder) as it:
                    for e in it:
                        if e.name.startswith((".", "$")) or not e.is_dir(follow_symlinks=False):
                            continue
                        below.append(e.path)
            except OSError:
                continue
        out.extend(below)
        if len(out) >= limit:
            break
        level = below
    return sorted(out[:limit], key=str.casefold)


def default_group_parent(primaries: list[str], file_abs: Path) -> Path:
    """Where a new group folder goes: beside the people's own folders (AESPA\\KARINA and
    AESPA\\WINTER give AESPA), else next to the picture."""
    parents = [str(Path(p).parent) for p in primaries]
    if parents:
        try:
            return Path(os.path.commonpath(parents))
        except ValueError:  # different drives
            return Path(parents[0])
    return file_abs.parent


# --- who is in which file -------------------------------------------------------------------

@dataclass(frozen=True)
class NamedFile:
    library_id: str
    library_root: Path
    file_id: int
    path: str            # library-relative
    names: dict[str, str]  # name key -> display name
    size: int = 0
    content_hash: str | None = None
    kind: str = "image"

    @property
    def abs_path(self) -> Path:
        return self.library_root / self.path


def _named_files(conn: sqlite3.Connection, library_id: str, root: Path, file_ids: list[int] | None = None) -> list[NamedFile]:
    # A person the user said No to (or whose face they ignored) in this file doesn't count in
    # it, even if other frames of them were attached by themselves, unless the user also named
    # them in it. The same rule the review uses to settle a file for a person.
    sql = """SELECT fi.id, fi.path, fi.size, fi.content_hash, fi.kind, p.name FROM files fi
             JOIN faces f ON f.file_id = fi.id JOIN persons p ON p.id = f.person_id
             WHERE p.name IS NOT NULL
               AND NOT (EXISTS (SELECT 1 FROM rejected_matches rm
                                WHERE rm.content_hash = fi.content_hash AND rm.person_id = p.id)
                        AND NOT EXISTS (SELECT 1 FROM face_assignments fa
                                        WHERE fa.content_hash = fi.content_hash AND fa.person_id = p.id
                                          AND fa.source = 'user'))"""
    params: tuple = ()
    if file_ids is not None:
        if not file_ids:
            return []
        sql += " AND fi.id IN (%s)" % ",".join("?" * len(file_ids))
        params = tuple(file_ids)
    by_file: dict[int, NamedFile] = {}
    for r in conn.execute(sql, params):
        nf = by_file.setdefault(r["id"], NamedFile(library_id, root, r["id"], r["path"], {}, r["size"] or 0, r["content_hash"], r["kind"]))
        nf.names.setdefault(name_key(r["name"]), " ".join(r["name"].split()))
    return list(by_file.values())


@lru_cache(maxsize=4096)
def _real(folder: str) -> str:
    """A folder resolved once (mapped drive -> UNC, symlinks), normalised for comparing.
    Resolving every file instead cost a network round-trip per picture on a NAS."""
    try:
        folder = str(Path(folder).resolve())
    except OSError:
        pass
    return os.path.normcase(os.path.normpath(folder))


def _under(f: NamedFile, folder: str | None) -> bool:
    # ponytail: roots and folders are resolved once per process; a drive remapped while the
    # engine runs keeps its old resolution until restart.
    if not folder:
        return False
    path = os.path.normcase(os.path.normpath(os.path.join(_real(str(f.library_root)), f.path)))
    d = _real(folder)
    return path == d or path.startswith(d.rstrip(os.sep) + os.sep)


@dataclass(frozen=True)
class Placement:
    file: NamedFile
    dest: str


@dataclass(frozen=True)
class GroupQuestion:
    file: NamedFile
    primaries: dict[str, str]  # name key -> primary folder, for the people who have one
    new_folder_parent: Path


def classify(files: list[NamedFile], primaries: dict[str, str], rules: dict[str, GroupRule],
             *, only_name: str | None = None, settled: set[str] | frozenset[str] = frozenset(),
             ) -> tuple[list[Placement], list[GroupQuestion]]:
    """Where each file goes. One named person: their primary folder. Two or more: the group's
    rule, else a question — asked only when someone in it has a primary folder. Files already
    in their destination (or in any of their people's folders, for a question) are left out,
    and so are group pictures the user already placed (`settled` content hashes)."""
    moves: list[Placement] = []
    questions: list[GroupQuestion] = []
    for f in files:
        if only_name is not None and only_name not in f.names:
            continue
        if len(f.names) > 1 and f.content_hash in settled:
            continue
        if len(f.names) == 1:
            dest = primaries.get(next(iter(f.names)))
            if dest and not _under(f, dest):
                moves.append(Placement(f, dest))
            continue
        rule = rules.get(group_key(set(f.names)))
        if rule is not None:
            if rule.dest and not _under(f, rule.dest):
                moves.append(Placement(f, rule.dest))
            continue
        mine = {k: primaries[k] for k in f.names if k in primaries}
        if mine and not any(_under(f, d) for d in mine.values()):
            questions.append(GroupQuestion(f, mine, default_group_parent(list(mine.values()), f.abs_path)))
    return moves, questions


Progress = Callable[[int, int, str], None]  # (done, total, what is being looked at)


def _library_files(registry, name: str | None = None, on_progress: Progress | None = None) -> list[NamedFile]:
    """Named files across every reachable library (only those with `name`, when given)."""
    key = name_key(name) if name else None

    def load(lib) -> list[NamedFile]:
        try:
            conn = open_library_db(Path(lib.path))
        except Exception:  # offline drive, locked vault: skipped, never blocks
            return []
        try:
            if key is not None:
                names = [r["name"] for r in conn.execute("SELECT DISTINCT name FROM persons WHERE name IS NOT NULL")]
                if not any(name_key(n) == key for n in names):
                    return []
            return _named_files(conn, lib.id, Path(lib.path))
        except sqlite3.Error:
            return []
        finally:
            conn.close()

    libs = registry.list()
    found: dict[int, list[NamedFile]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(load, lib): i for i, lib in enumerate(libs)}
        for n, fut in enumerate(as_completed(futures), 1):
            i = futures[fut]
            found[i] = fut.result()
            if on_progress is not None:
                on_progress(n, len(libs), libs[i].name)
    return [f for i in sorted(found) for f in found[i]]


def _dedupe_nested(files: list[NamedFile]) -> list[NamedFile]:
    """A folder registered inside another (AESPA inside KPOP) indexes the same file twice;
    keep one row per real path, the one from the deepest library."""
    best: dict[str, NamedFile] = {}
    for f in files:
        k = os.path.normcase(str(f.abs_path))
        if k not in best or len(str(f.library_root)) > len(str(best[k].library_root)):
            best[k] = f
    return list(best.values())


def person_plan(gp_conn: sqlite3.Connection, registry, name: str,
                on_progress: Progress | None = None) -> tuple[list[Placement], list[GroupQuestion]]:
    files = _dedupe_nested(_library_files(registry, name, on_progress))
    return classify(files, primary_folders(gp_conn), group_rules(gp_conn), only_name=name_key(name),
                    settled=settled_groups(gp_conn))


def library_questions(gp_conn: sqlite3.Connection, conn: sqlite3.Connection, library_id: str, root: Path) -> list[GroupQuestion]:
    _, questions = classify(_named_files(conn, library_id, root), primary_folders(gp_conn), group_rules(gp_conn),
                            settled=settled_groups(gp_conn))
    return questions


# --- already in the destination -----------------------------------------------------------

def _sizes_under(folder: str) -> dict[int, list[str]]:
    """size -> files anywhere under `folder`, from one listing per folder (on Windows the size
    comes with the listing, so no file is opened)."""
    out: dict[int, list[str]] = {}
    stack = [folder]
    while stack:
        try:
            with os.scandir(stack.pop()) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(e.path)
                        elif e.is_file():
                            out.setdefault(e.stat().st_size, []).append(e.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return out


def _same_content(path: str, f: NamedFile) -> bool:
    try:
        if f.content_hash and is_sampled(f.content_hash):
            return sampled_hash(Path(path), f.size) == f.content_hash
        return hash_file(Path(path)) == (f.content_hash or hash_file(f.abs_path))
    except OSError:
        return False


def already_there(moves: list[Placement], on_progress: Progress | None = None,
                  ) -> tuple[list[Placement], list[Placement]]:
    """Split off the moves whose identical file (same size, same content) is already somewhere
    in the destination folder: moving them would only make a second copy there. They stay where
    they are; removing copies is the duplicate finder's job. Only same-size files are read."""
    by_dest: dict[str, list[Placement]] = {}
    for m in moves:
        by_dest.setdefault(m.dest, []).append(m)
    keep: list[Placement] = []
    there: list[Placement] = []
    done = 0
    for dest, ms in by_dest.items():
        sizes = _sizes_under(dest)
        for m in ms:
            done += 1
            if on_progress is not None:
                on_progress(done, len(moves), Path(m.file.path).name)
            same = m.file.size > 0 and any(_same_content(p, m.file) for p in sizes.get(m.file.size, ()))
            (there if same else keep).append(m)
    return keep, there


# --- moving ---------------------------------------------------------------------------------

def plan_hash(moves: list[Placement]) -> str:
    import hashlib

    h = hashlib.sha256()
    for lib, fid, dest in sorted((m.file.library_id, m.file.file_id, m.dest) for m in moves):
        h.update(f"{lib}\0{fid}\0{dest}\n".encode("utf-8"))
    return h.hexdigest()


def execute_moves(
    gp_conn: sqlite3.Connection,
    registry,
    moves: list[Placement],
    *,
    label: str,
    on_progress: Callable[[int, int], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict:
    """Move the files (copy-then-delete, manifest), then fix the index: a file that stayed inside
    its library keeps its row (and faces) at the new path; one that left drops the row, and the
    library it arrived in indexes it itself. Recorded as one undoable move.

    Cancelled part-way, it puts back what it already moved (the same copy-then-delete, with its
    own manifest), removes the folders it created if they are empty again, and leaves the index
    as it was: a cancel never leaves a half-done move behind. A file that can't go back (its old
    place taken, the drive gone) stays where it arrived, indexed there, and is reported."""
    ops = [FileOp(source=m.file.abs_path, dest_folder=Path(m.dest), mode="move") for m in moves]
    created: list[str] = []  # every folder this makes, parents first, to remove again on a cancel
    for d in sorted({m.dest for m in moves}):
        missing = []
        p = Path(d)
        while not p.exists() and p.parent != p:
            missing.append(str(p))
            p = p.parent
        created += [x for x in reversed(missing) if x not in created]
    for m in moves:
        Path(m.dest).mkdir(parents=True, exist_ok=True)
    manifest_path = global_moves_dir() / "manifests" / f"{time.strftime('%Y%m%d-%H%M%S')}_{label}.csv"
    report = safety_execute(ops, manifest_path=manifest_path, on_progress=on_progress, should_cancel=should_cancel)

    by_source = {os.path.normcase(str(m.file.abs_path)): m for m in moves}
    arrived = {os.path.normcase(e.source): e.destination for e in report.entries if e.action == "moved"}
    cancelled = should_cancel is not None and should_cancel()
    arrived_count = len(arrived)
    rolled_back = 0
    rollback_errors: list[str] = []
    if cancelled and arrived:
        back_ops = [FileOp(source=Path(dest), dest_folder=Path(src).parent, mode="move") for src, dest in
                    ((by_source[k].file.abs_path, d) for k, d in arrived.items() if k in by_source)]
        back = safety_execute(back_ops, manifest_path=manifest_path.with_name(manifest_path.stem + "_cancelled.csv"))
        returned = {os.path.normcase(e.source): e.destination for e in back.entries if e.action == "moved"}
        rollback_errors = [e.error for e in back.entries if e.action == "error"][:5]
        for k, dest in list(arrived.items()):
            home = returned.get(os.path.normcase(dest))
            if home is None:
                continue
            rolled_back += 1
            if os.path.normcase(home) == k:
                del arrived[k]  # back exactly where it was: its index row never changed
            else:
                arrived[k] = home  # back in its folder under another name (its old one was taken)
        for d in reversed(created):
            try:
                Path(d).rmdir()  # only succeeds when empty again
            except OSError:
                pass

    updates: dict[str, list[tuple[str | None, int]]] = {}
    for k, dest in arrived.items():
        m = by_source.get(k)
        if m is None:
            continue
        try:
            rel = Path(dest).resolve().relative_to(m.file.library_root.resolve()).as_posix()
        except ValueError:
            rel = None
        updates.setdefault(m.file.library_id, []).append((rel, m.file.file_id))
    roots = {m.file.library_id: m.file.library_root for m in moves}
    for library_id, rows in updates.items():
        try:
            conn = open_library_db(roots[library_id])
        except Exception:
            continue
        try:
            for rel, fid in rows:
                if rel is None:
                    conn.execute("DELETE FROM files WHERE id = ?", (fid,))
                else:
                    conn.execute("UPDATE files SET path = ? WHERE id = ?", (rel, fid))
            conn.commit()
        finally:
            conn.close()

    moved = arrived_count - rolled_back
    if moved:
        gp_store.record_move_action(
            gp_conn, 0, dest_folder=", ".join(sorted({m.dest for m in moves})), file_count=len(moves),
            dry_run=False, manifest_path=str(manifest_path), ok_count=moved, error_count=len(report.errors))
    return {
        "planned": len(moves), "moved": moved, "cancelled": cancelled, "rolled_back": rolled_back,
        "errors": ([e.error for e in report.entries if e.action == "error"] + rollback_errors)[:5],
    }


# --- watched folders ------------------------------------------------------------------------

def auto_file_enabled(gp_conn: sqlite3.Connection, library_id: str) -> bool:
    return gp_conn.execute("SELECT 1 FROM auto_file_libraries WHERE library_id = ?", (library_id,)).fetchone() is not None


def set_auto_file(gp_conn: sqlite3.Connection, library_id: str, on: bool) -> None:
    if on:
        gp_conn.execute("INSERT OR IGNORE INTO auto_file_libraries (library_id) VALUES (?)", (library_id,))
    else:
        gp_conn.execute("DELETE FROM auto_file_libraries WHERE library_id = ?", (library_id,))
    gp_conn.commit()


def auto_file_moves(gp_conn: sqlite3.Connection, conn: sqlite3.Connection, library_id: str, root: Path,
                    paths: list[str]) -> list[Placement]:
    """What to file from a batch of new or changed paths in a watched folder. Only faces the sort
    attached with confidence carry a name here (pending ones don't), and group pictures without a
    rule wait for the user."""
    rels = []
    for p in paths:
        try:
            rels.append(Path(p).resolve().relative_to(root.resolve()).as_posix())
        except (OSError, ValueError):
            continue
    if not rels:
        return []
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM files WHERE path IN (%s)" % ",".join("?" * len(rels)), tuple(rels))]
    moves, _ = classify(_named_files(conn, library_id, root, ids), primary_folders(gp_conn), group_rules(gp_conn),
                        settled=settled_groups(gp_conn))
    return already_there(moves)[0]


if __name__ == "__main__":
    root = Path("C:/lib")
    f = lambda i, *names: NamedFile("L", root, i, f"x/{i}.jpg", {name_key(n): n for n in names})
    prim = {"karina": "C:/lib/KARINA", "winter": "C:/lib/WINTER"}
    moves, qs = classify([f(1, "Karina"), f(2, "Karina", "Winter"), f(3, "Yuna"), f(4, "Winter", "Yuna")], prim, {})
    assert [(m.file.file_id, m.dest) for m in moves] == [(1, "C:/lib/KARINA")]   # Yuna has no folder
    assert [q.file.file_id for q in qs] == [2, 4]                                 # group pictures ask
    assert qs[0].new_folder_parent == Path("C:/lib")
    moves, qs = classify([f(2, "Karina", "Winter")], prim, {group_key({"karina", "winter"}): GroupRule("C:/lib/OT2")})
    assert [(m.file.file_id, m.dest) for m in moves] == [(2, "C:/lib/OT2")] and not qs
    _, qs = classify([f(2, "Karina", "Winter")], prim, {group_key({"karina", "winter"}): GroupRule(None)})
    assert not qs                                                                # "leave it here" is remembered
    assert _under(f(9, "Karina"), "C:/lib/x") and _under(f(9, "Karina"), "c:/LIB/x/")
    assert not _under(f(9, "Karina"), "C:/lib/x2") and not _under(f(9, "Karina"), None)
    g = NamedFile("L", root, 2, "x/2.jpg", {"karina": "Karina", "winter": "Winter"}, 5, "h2")
    assert classify([g], prim, {}, settled={"h2"}) == ([], [])                  # already placed once

    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        src, dest = Path(tmp, "src"), Path(tmp, "KARINA")
        (dest / "sub").mkdir(parents=True)
        src.mkdir()
        (src / "a.jpg").write_bytes(b"same")
        (src / "b.jpg").write_bytes(b"diff")
        (dest / "sub" / "a copy.jpg").write_bytes(b"same")
        (dest / "c.jpg").write_bytes(b"othr")                                     # same size, other bytes
        mk = lambda n: Placement(NamedFile("L", src, 1, n, {"karina": "Karina"}, 4, hash_file(src / n)), str(dest))
        keep, there = already_there([mk("a.jpg"), mk("b.jpg")])
        assert [m.file.path for m in there] == ["a.jpg"] and [m.file.path for m in keep] == ["b.jpg"]
    print("placement self-check ok")
