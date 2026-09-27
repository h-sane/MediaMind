# People folders and auto-filing (s100 plan)

Hussain's ask (2026-09-27):
1. Counts in Who's who for **files**, not faces: how many files the folder has, how many are sorted, and how many aren't.
2. Per person, a **primary folder** (their physical location), and a button to **move every picture and video of that person** there.
3. The **watchdog**, for folders he enables, files new pictures of known people into their primary folder by itself.
4. **Group pictures** (two or more known people in one file) are the only case that asks him. The options are: one person's folder, a **new group folder** (e.g. `AESPA/OT4`), or leave it where it is. A file is never duplicated.

## What already exists (reused, not rebuilt)
- `store/global_people.py`: a global person per identity with an absolute `primary_location`, links to per-library persons, and a move history (`global_move_actions`) for undo.
- `core/global_people.py`: `execute_move_plan` runs a safe cross-library move (copy-then-delete through `core/safety.execute`, a manifest, plan-hash guards) plus undo. `list_move_suggestions`.
- `core/ingest_worker.py` plus `api/app.py::_sort_by_named_examples`: new files in watched libraries are already sorted against every named person.
- The old per-library `persons.primary_folder_path` and the sidebar "Consolidate" flow are left alone. That flow only accepts library-relative paths, so it can't reach another group's folder.

## Decisions
- **One person = one name, everywhere.** The primary folder lives on the global person. A named local person is linked to the global person *of the same name* (created if missing). This is the same rule teaching already uses to pool examples. The earlier "always ask before linking" rule was about face-similarity suggestions; a name the user typed is explicit intent.
- **The primary folder is absolute** and can be in another library or drive (Yuna's folder is in ITZY, not AESPA).
- **Group rules are keyed by the set of names in the picture** (`group_rules` in the global db): `{karina, winter, giselle, ningning} → D:\…\AESPA\OT4`. A rule answers every current and future picture of exactly that set, including in the watchdog. A one-off choice (without "always") moves just that file.
- **What counts as a group picture:** a file with 2+ named people where at least one of them has a primary folder. Leave-it-here is stored as a rule with `dest = NULL` for that set, so it's never asked again.
- **Moves inside one library keep the index:** the `files.path` row is updated, so faces and names survive. A move to another library drops the source row, and the destination library's watcher or rescan picks the file up (as `execute_move_plan` does).
- **Auto-filing is opt-in per watched folder** (`settings.auto_file_library_ids`), set on the Watched folders page. Turning it on is the informed consent that safety rule 6 requires. Only confident matches are filed: auto-attached faces, never pending ones. Every run goes through the same safe move with a manifest, so undo works. Each run is a job (`auto-file`), so the Status centre shows it.

## Phases (all in s100)
1. Backend `core/placement.py` + routes in `api/routes/teach.py`:
   - `GET teach/stats?under=` returns `{total, sorted, unsorted, no_faces}`. Unsorted means the file has faces but nobody named; no_faces means no face was found.
   - `teach/people` adds `primary_location`.
   - `PUT teach/people/{id}/primary-location {path}` links to or creates the global person by name and sets it.
   - `GET teach/people/{id}/move-plan` returns `{moves:[…], groups:[…], primary_location}` across every library the name is in.
   - `POST teach/people/{id}/move {expected_count, expected_plan_hash}` runs as a job.
   - `GET teach/groups` lists this library's group pictures waiting for a choice.
   - `POST teach/groups/place {file_id, choice: person|new|stay, person, folder_name, remember}`.
2. Watchdog: `auto_file(...)` after the ingest sort for opted-in libraries. Also `GET/PUT /libraries/{id}/auto-file`.
3. Frontend Who's who:
   - a counts line under the title;
   - a person bar when a person is selected: the Belongs switch, the folder with Choose…, and Move N files there with a confirm dialog and status;
   - a "Group pictures" pane item with per-file choices (person folders, New group folder… with "always for these people", Leave here).
4. Frontend Watched folders: a per-folder "File new pictures into people's folders" toggle.

## Not in this round
- Re-attaching faces for files moved into a *different* library: the destination rescans.
- A dedicated toast for auto-filing, beyond the Status centre card and the Group pictures count.

## Follow-up (s102, 2026-09-27): progress, no double copies, answered groups, ignored faces
Hussain's first live run: choosing Karina's folder and opening Move files each sat on a spinner for 1 to 2 minutes, and the move itself showed no real progress.

**Why it was slow.**
- `placement._under` called `Path.resolve()` on every file. On the network vault that is one round-trip per picture: 22 s for `teach/groups` on AESPA, and most of the time spent building the move plan.
- It now resolves each library root and each destination folder once (`_real`, cached), then compares the paths as strings.

**Progress everywhere a person waits.**
- `POST teach/people/{id}/move-plan` is the plan as a job. Phase `checking` counts the scanned folders read (the detail is the folder's name), then phase `comparing` counts the files checked against the destination. The GET route stays for compatibility.
- The move job reports the same two phases, then `moving` with the name of the file being moved.
- `POST teach/apply-job` is Sort as a job: `checking` for each other folder's examples read, then `sorting`.
- Who's who shows one activity card in the message slot: the title, counts, a real progress bar, the current file or folder, the elapsed time, and Cancel for the plan and the move.
  - It only appears after 400 ms, so quick actions don't flash it.
  - The page reload names the parts still loading.
- Jobs the page is following stay off the bottom strip until the user leaves the page. The strip now has a title for every job type and never shows a raw code.
- Duplicate removal uses the existing `execute-job`, so the strip counts deletions.

**No second copies.** `already_there()`:
- A file whose identical copy is already somewhere under the destination is not moved. The check lists the folder once and hashes only files of the same size.
- The plan reports `already_there`, and the Move dialog says so.
- The file stays where it is. Removing copies is the duplicate finder's job, never an automatic delete.
- Files already inside the destination were already left out.

**Answered group pictures stay answered.**
- `group_settled` (global db, keyed by content hash) records every group picture the user placed or left, with or without "remember".
- `classify(settled=…)` skips them, so they are never asked about or moved again, whoever's folder is filled next.

**Ignored faces don't count.**
- `_named_files` drops a person from a file when the user said No, or Ignore, to that person in that file's content (`rejected_matches`), unless they also named that person there.
- So Karina's video with Winter ignored in the background is Karina's alone, not a group picture. This is the same rule the review queue uses to settle a file for a person.
