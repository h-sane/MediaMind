# Teach MediaMind who's who — design (s96, not built)

Status: proposal, agreed direction pending Hussain's review. Nothing here is implemented.

## 1. Why the kpop scan came out wrong (measured, not guessed)

Read-only analysis of the finished kpop library (`insightface-buffalo-l`, 2704 faces, 1022 files):

- The biggest "person" holds **1988 faces from 900 files**. Inside it, the **median pairwise similarity is 0.25** (10th pct 0.10, 90th 0.47). With buffalo_l, 0.25 is the level of *different* people, not the same person. The 900-file person is several members glued together.
- Cause: `core/faces/clustering.py` runs **DBSCAN, eps 0.42, min_samples 2**. DBSCAN links A to B to C to D: a chain of faces that are each close to the next joins people who look nothing alike end to end. Same-group idols (similar styling, makeup, lighting) give it many bridges. The rest of the 96 "people" are fragments and bystanders.
- A better unsupervised algorithm helps a little but does not solve it. Average-linkage clustering at several thresholds still gives two giant groups (430 to 834 faces) plus hundreds of small ones. These faces are simply close together for this model (the catalog itself notes every model here is weakest on East Asian faces).

**Conclusion:** Hussain's instinct is right. A few labelled examples per person, then classifying against them, will beat any zero-shot clustering here. The expensive part (detecting and embedding faces, 75 min) is already cached in `faces.embedding`. Re-sorting with labels is pure numpy and takes seconds, so **no rescan is needed after teaching**.

## 2. Key design change: teach *after* the scan, not before

The idea as first described was: before scanning, pick faces and name them. But a roster of faces can only exist once detection has run, and detection is the slow part. So the order is:

1. **Scan** (unchanged: detect and embed every face once; cached).
2. **Teach**: the user names a few clear faces per person. Folder names help (section 4).
3. **Sort**: instant re-classification against those examples. Faces nobody matches go to Unknown or Others.
4. **Review**: the borderline faces are shown as yes/no questions. Each answer becomes another example, and the sort re-runs.

Steps 2 to 4 repeat in seconds. This is how digiKam (confirmed faces train recognition), Apple Photos ("Review additional photos") and Google Photos (confirm/deny "Is this X?") work.

## 3. Backend

### 3.1 Examples = the existing `face_assignments` table
`face_assignments (content_hash, bbox, person_id, source)` already survives rescans and already overrides clustering (`persist_face_scan` step 2). A user-named example is a row with **`source = 'user'`**. No new table. (Optional later: `source='reference'` if we need to tell "named as example" apart from "moved by hand".)

### 3.2 New module `core/faces/classify.py` (replaces DBSCAN when examples exist)
For every face that is not already user-assigned:

- Score each named person by **mean of the top-3 similarities to that person's examples** (nearest examples, not the centroid; a centroid of stage and selfie photos looks like neither).
- **Auto-assign** if best score >= `AUTO_SIM` (start 0.45) **and** best minus second-best >= `MARGIN` (start 0.08). The margin stops a face that is half-Karina, half-Winter from being silently given to either.
- **Pending review** if best >= `SUGGEST_SIM` (start 0.32) but it fails either test. This reuses `pending_matches` and the existing Suggestions panel, so the "review before commit" safety rule is kept.
- **Unknown** otherwise. Run the old DBSCAN **only on the unknowns** to find unnamed people. That becomes the "Who is this?" list.

The thresholds are calibration knobs. Set them from the kpop library itself: hold out a few of each person's examples and measure. They are not fixed laws.

### 3.3 Background people (the "filler faces" worry)
Several signals, all cheap and already available (bbox size, detector confidence, file id):

1. **Open-set by construction.** A stranger in the background does not reach `AUTO_SIM` plus margin for any member, so they fall to Unknown instead of polluting Karina. This is the main protection, and DBSCAN lacks it.
2. **Prominence.** Store the frame size. A face whose width is under ~8 % of the frame width, or which is not among the 2 largest faces in its frame, is flagged `background`. It is never used as an example candidate, never auto-assigned, and only counts towards a person if it clears a stricter threshold.
3. **Recurrence.** Unknown clusters seen in fewer than 3 files collapse into one "Others" bucket. They are never shown as person cards. This is what turns "40 faces" into "5 members + Others".
4. **Explicit "Not a person I care about"**: already exists as reject/hide (`rejected_face_regions`, Hidden).

### 3.4 Folder names as hints (the exact kpop case)
`folder_patterns.py` already asks "is this folder mostly one person?". New use: for each subfolder whose name is not generic (not `Unsorted`, `2023`, `DCIM` and so on), run average-linkage clustering **inside that folder only**. Pick its dominant group and propose: *"Karina folder: 180 of 212 faces look like the same person. Name them Karina?"*, showing the 12 largest, sharpest faces. One confirmation gives ~12 good examples. It is a **proposal, never auto-applied** (the folder may hold group shots).

### 3.5 Endpoints (new, small)
- `GET  /v1/libraries/{id}/teach/candidates?under=<folder>&person=<id|unknown>&sort=quality` returns face tiles (face id, file, bbox, quality, current person, background flag). Crops come from the existing `/faces/{face_id}/thumbnail`.
- `GET  /v1/libraries/{id}/teach/folder-proposals` returns per-subfolder proposals (3.4).
- `POST /v1/libraries/{id}/teach/examples` with `{face_ids, person_id | new_name}` writes `face_assignments(source='user')` (creating the person if new).
- `POST /v1/libraries/{id}/teach/examples/remove` does the reverse.
- `POST /v1/libraries/{id}/teach/apply` runs classify and persist as a **job** (it has progress, so the job strip shows it). Returns counts per person, pending and unknown.

### 3.6 What stays
Detection, embeddings, caching, scan robustness (s95), pending_matches, merge, hide, reject, and person media all stay. DBSCAN stays for libraries with no examples and for the unknowns.

## 4. Frontend (WinUI) — one place to teach, reached from where the user already is

Guiding rules (CLAUDE.md): flagship features visible, cause and effect for every action, no buried menus, measure the layout in the running app.

### 4.1 Where it lives
A **"Who's who" page**, one per library, opened from:
- the **People page** header: when a library has a scan but fewer than 2 named people, a banner reads *"MediaMind found faces in KPOP. Teach it who's who for accurate results."* with a [Start] button;
- the **scan strip** when a faces scan finishes: [Teach who's who];
- the **Explorer command bar and context menu** on selected files or a folder: "Name faces in these…". This opens the same page, pre-filtered to that selection. This is the "go into the Karina folder and pick clear photos" mental model, with no second implementation.

No modal wizard. It is a normal page with its own back button, so the user can leave and come back.

### 4.2 Layout (two panes, fixed-size tiles)
```
┌ Who's who — KPOP ───────────────────────────────────────── [Sort people now] ┐
│ PEOPLE                 │ Folder: [All ▾] KPOP › Karina      Show: [Unnamed ▾]│
│ ● Karina     12 ex.    │ ┌──────────────────────────────────────────────────┐│
│ ● Winter      5 ex.    │ │ Suggested: Karina folder — 180 faces look alike  ││
│ ● Giselle     1 ex.    │ │ [12 face crops ...........]  [Name them Karina]  ││
│ ○ Ningning    0        │ └──────────────────────────────────────────────────┘│
│ + Add person           │ [96px face crops grid, largest/sharpest first,      │
│                        │  multi-select with Ctrl/Shift/checkbox]             │
│ Others (background) 214│                                                     │
├────────────────────────┴─────────────────────────────────────────────────────┤
│ 7 selected   [This is… ▾ (PersonChooser)]  [New person…]  [Not a person]    │
└──────────────────────────────────────────────────────────────────────────────┘
```
- **Tiles are face crops, not photos.** A group photo shows as 3 separate tiles, so the user picks the face, never the file. This answers "which person in this photo did you mean" and the background-face worry at the UI level. Background-flagged faces are hidden from this grid by default ("Show background faces" toggle).
- Fixed 96x96 tiles in an `ItemsRepeater` + `UniformGridLayout` (avoids GridView's size-from-first-item trap). Hover shows the file name and folder. Double-click opens the photo.
- The **Folder filter** is a breadcrumb scoped to the library's subfolders. Picking "Karina" shows only faces from there.
- The left pane shows **example counts** with a quiet hint at 0 ("needs 1 clear face") and at 5+ ("good").
- The bottom action bar appears only when something is selected. Keyboard: `Ctrl+A`, `Esc`, and `1`-`9` assign to the n-th person.

### 4.3 After [Sort people now]
- It runs as a job in the scan strip (visible progress, then result).
- It lands on a **results sheet in the same page**: *"Karina 412 files · Winter 388 · Giselle 96 · Ningning 41 · 63 need your eye · Others 214"*.
- **"Needs your eye"** reuses the existing Suggestions panel as a fast yes/no queue (big crop, "Is this Winter?" `Y` / `N` / `S`kip). Every answer adds an example. [Re-sort] is offered after 10 answers.
- The People page then shows only named people plus the real unknowns (3+ files). Others is one collapsed row.

### 4.4 States to design and measure
No scan yet (explains that a scan comes first) · scan running (page is read-only, shows progress) · 0 named · a person with 0 examples · a folder with no faces · a long name · a 1-face person · duplicate name (merge offer) · apply failed (error with Retry) · a library that is offline (existing 409 path).

## 5. Build order (each step shippable)
1. `classify.py` + unit tests on synthetic embeddings, plus an offline evaluation script on the kpop DB (numbers only). **Proves the gain before any UI.**
2. Teach endpoints + `apply` job; `persist_face_scan` accepts classifier labels (labels for unknowns come from DBSCAN).
3. Background flag (needs the frame size stored: additive schema v13, filled on the next scan; bbox-only fallback until then).
4. Who's who page: grid, people pane, action bar (frontend-design skill first, UIA measure).
5. Folder proposals + entry points (banner, strip button, Explorer command).
6. Needs-your-eye queue wired to the Suggestions panel; Others bucket on the People page.

Prerequisite: merge `wip/scan-robustness` (s95) first, because it touches the same scan runner.

## 6. Open questions for Hussain
- Should examples be **global** (Karina taught once and recognised in every library) or per library? Per library first is simpler. `global_people` exists as the later bridge.
- For organize/export: do only auto-assigned and confirmed faces count, or pending too? (Recommendation: confirmed only.)
