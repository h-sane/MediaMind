# People view V2 — Faces / Folders modes, cross-scan grouping, pinning

Status: design, 2026-09-26. Not implemented. Supersedes the per-library tile
layout of the s92 People tab (`PeopleHomePage` / `PeopleGroupPage`).

## Why (what is broken today)

Verified in code, not assumed:

- "Scan for People" registers **each scanned folder as its own library**
  (`ScanForPeopleAction.ScanOneAsync` → `Libraries.AddAsync(folderPath)`).
  `LibraryRegistry.add` has no nesting or overlap logic.
- A person's `primary_folder_path` and the People tree are **library-relative**
  (`store/people_tree.py`), and the tree endpoint is per library
  (`GET /libraries/{id}/people-tree`). `PeopleManager` builds one top-level tile
  per library.
- Result: scanning `kpop/twice`, then `kpop/ive`, then `kpop/blackpink` yields
  three unrelated top-level tiles. Nothing knows they share `kpop`, and there is
  no way for the user to say so.
- There is no Faces-first flat view and no pinning.

## Answers to the scan-time question

Measured (ADR-0006, CPU only, 8 cores): ~0.34 s per image, ~4.7 s per 15-frame
video. So 30,000 photos is roughly 3 hours, 50,000 roughly 5 hours; days only
happens with thousands of videos (10,000 videos is ~13 hours) or a slow/streamed
drive. Scans are resumable (content-hash cache, ADR-0005 journal), so scanning
one subfolder at a time is safe and the people appear incrementally.

## Design

### 1. Hierarchy from absolute paths (automatic grouping)

Stop deriving groups from library-relative paths. Each library has an absolute
root, so a person's home folder is `library.root / primary_folder_path`. Build
the Folders tree from these **absolute** paths across all libraries:

    kpop/            <- virtual group, no library of its own
      twice/         <- library A
      ive/           <- library B
      blackpink/     <- library C

`kpop` appears automatically as soon as two scanned folders share it. Ancestors
above the shallowest scanned folder are collapsed (never show `C:\Users\...`
chains): the tree starts at the deepest common ancestor of each cluster of
libraries. New backend endpoint `GET /v1/people-tree` (global, all libraries)
replaces N per-library calls; `PeopleManager` makes one request.

### 2. Manual grouping (for when folders do not share a parent)

User-defined **collections**, stored app-level (`people_collections.json` in
`app_data_dir()`, never inside a library): `{id, name, members:[folder-abs-path |
library id]}`. A member overrides the automatic placement. UI: right-click a
Folders-mode card → "Move to collection…" (pick or create), and drag a card onto
a collection card. Removing a collection returns members to their automatic
place. The filesystem is never touched (safety rule 4).

### 3. Two modes with a top toggle

Segmented control at the top of the People page: **Faces | Folders**, choice
persisted (`ApplicationData` local settings). Default: **Faces**.

- **Faces**: one flat, virtualized grid of circular person tiles across every
  library, one tile per identity (uses the existing global person link store,
  `/people`, so the same person scanned in two libraries is one tile). Sort:
  pinned first, then named by media count, then unnamed by media count.
  Filter box: name search. A "Not named yet" chip filters to unnamed.
- **Folders**: the tree from section 1/2 as folder cards with the existing
  circular face-stack previews; opening a card drills in (breadcrumb across the
  top), leaf persons open the person media view. Same pin affordance.

### 4. Pinning

Pins are app-level (`people_pins.json`): `{kind: "person"|"folder", key}`, where
a person key is the global person id (or `library:person` until linked) and a
folder key is the absolute path (or collection id). Pin from the card's hover
pin button and its context menu. A **Pinned** row sits above the grid in both
modes (persons and folder cards mixed, drag to reorder), so a pin made in one
mode is visible in the other. Pinned persons also list under the People sidebar
entry. A missing (offline/deleted) pinned target shows as a dimmed card with
"Unavailable", never silently dropped.

### 5. Scan-overlap hazard (must handle)

If `kpop/twice` is scanned as a library and later `kpop` itself is scanned, the
same people and files would exist in two libraries. Rule: when registering a
folder that contains existing libraries, or lies inside one, the scan skips
already-covered subfolders and the UI says so in the scan progress card ("Twice
was already scanned — skipping"). Until built, the Folders tree de-duplicates by
preferring the deeper library for a given person-in-folder.

## Visual plan (WinUI, matches the Files shell — not a new visual language)

- **Color**: use Fluent theme resources only (`SolidBackgroundFillColorBase`,
  `CardBackgroundFillColorDefault`, `AccentFillColorDefaultBrush`). One accent =
  the user's Windows accent. Pinned state = filled accent pin glyph; no new hex.
- **Type**: Segoe UI Variable as the shell already uses. Person name
  `BodyStrongTextBlockStyle`, counts `CaptionTextBlockStyle` in secondary
  foreground. Sentence case, no all-caps labels.
- **Layout**: Faces mode is a dense circle-tile grid (190 px cells, ~6 per row as
  already tuned in s92), left-aligned; Folders mode reuses the s92 folder card
  with face stack and "+N" badge. Toggle sits top-left of the command row, pin
  row directly under it, then the grid.
- **The one memorable thing**: the face itself — circles are large and edge to
  edge, everything else (chrome, badges, counts) stays quiet.
- **Motion**: only in response to action — the toggle cross-fades the two grids;
  pinning moves the card into the Pinned row with a short connected animation.
  Respects reduced motion.
- **Copy**: "Faces", "Folders", "Pin", "Unpin", "Move to collection…", "Not named
  yet", empty state "No people yet — open a folder and choose Scan for People".

```
[ Faces | Folders ]   [search people…]   [Not named yet]      [Scan for People]
Pinned
 (o) Nayeon   (o) Jisoo   [kpop folder card]
------------------------------------------------------------------------------
 (o) (o) (o) (o) (o) (o)
 (o) (o) (o) (o) (o) (o)
```

## Phases (each independently shippable)

1. Backend: global `GET /v1/people-tree` (absolute-path grouping) + tests.
2. Backend: `people_pins.json` + `people_collections.json` stores and routes.
3. WinUI: Faces/Folders toggle, Faces grid, switch `PeopleManager` to the global
   tree. Preference persisted.
4. WinUI: pin UI (hover pin, context menu, Pinned row, sidebar entries).
5. WinUI: collections UI (move-to-collection, drag onto card).
6. Backend: scan-overlap skip + progress messaging.

Each WinUI phase invokes the `frontend-design` skill first (project rule).

## Open decisions (defaults chosen)

- Faces mode across libraries relies on the global person link store; unlinked
  same-person duplicates show as separate tiles until the existing
  link-suggestions flow merges them. Default: accept.
- Pin order: manual drag order. Default: yes.
