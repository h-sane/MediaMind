# MediaMind — User Guide

This guide tells you everything you need to run the app, reload it correctly
after changes, and work through the situations that come up while testing.
No coding knowledge required — just follow the steps in order.

---

## What the app can do right now

The app's main window is a **full Windows-Explorer clone** — navigation
pane, tabs, address bar, view modes, search/filter, drag-and-drop, context
menus, the works — scoped to real drives and folders on your machine and
filtered to media (images, GIFs, videos, audio; other file types are hidden,
not touched). There is no "add a folder" step before you can look around:
the app opens straight to a **Home** page and you navigate exactly like the
real File Explorer.

- **Navigate** — a Home page (pinned folders + Recent Files), a drive/folder
  tree, multiple tabs (`Ctrl+T`/`Ctrl+W`/`Ctrl+Tab`), an address bar with
  clickable breadcrumbs or a type-in path (UNC/network paths like
  `\\server\share` work too), back/forward/up, live search with an escalate-
  to-recursive-subfolder-search option, and Type/Date/Size filter chips.
- **View** — six view modes: Large icons, Tiles, List, Details, Content, and
  **Gallery** (a recursive, date-grouped view of every media file under the
  current folder — the "camera roll" view). Details' columns can be
  resized, reordered, and shown/hidden via the columns picker. Sort and
  Group-by work in every view; view mode and sort are remembered per folder
  and persist across restarts.
- **Organize** — select (click, Ctrl/Shift, marquee-drag, arrow keys,
  type-ahead-to-select), cut/copy/paste, rename, new folder, create
  shortcut, compress to ZIP / extract, delete (Recycle Bin or permanent,
  with confirmation), and a single-level undo/redo — all from the toolbar,
  right-click menu, or keyboard shortcuts.
- **Drag and drop** — drag files/folders onto another folder (in the grid,
  the folder tree, or a Quick Access pin) to move them; hold Ctrl while
  dropping to copy instead. Drag a folder onto the "Quick access" header to
  pin it. You can also drag files in from Windows Explorer to copy them into
  the current folder. (Dragging files *out* of MediaMind into another app
  isn't implemented yet — see "What is NOT available yet".)
- **Quick Access** — pin frequently-used folders (via drag or right-click),
  shown above the folder tree, reorderable by dragging, persisted across
  restarts.
- **Preview & Properties** — a collapsible preview pane (tabbed
  Preview/Details) shows a selected file's thumbnail or an inline
  video/audio player plus its metadata; a full Properties dialog (Alt+Enter)
  adds a disk-usage gauge for folders.
- **OS integration** — Open with… (native chooser), Reveal in File Explorer,
  Copy as path, Send to, and a "Recent deletions" history panel (the History
  icon in the toolbar) that lists everything you've deleted and hands off to
  the real Windows Recycle Bin to restore a file.
- **Find duplicates, People (face recognition), Providers, Organize-by-
  person** — these engine features are fully built and tested on the
  backend, but as of this writing they are **not yet wired into the
  Explorer window** (see "Where the older features went"). They exist as
  working code and can be reached again once that integration happens.

---

## Prerequisites (one-time setup, already done on your machine)

| What | Where on your machine |
|---|---|
| Python 3.11 + MediaMind backend | `C:\Users\husai\faces-env` |
| Node.js + npm | Already installed |
| MediaMind app | `C:\Users\husai\Desktop\CODES\MediaMind` |

You do **not** need to install anything yourself. Everything is already set up.

---

## How to run the app

### Step 1 — Open a terminal

Press **Win + X** → choose **Terminal** (or **PowerShell**).

### Step 2 — Navigate to the app folder

```
cd C:\Users\husai\Desktop\CODES\MediaMind\app
```

### Step 3 — Start the app

```
npm run dev
```

Wait about 5–10 seconds. You'll see Vite and Electron start up in the
terminal, and the MediaMind window opens automatically.

### Step 4 — Stop the app

Press **Ctrl + C** in the terminal, then close the window. See
**"If the app won't fully close"** below if a window or process lingers.

---

## How to reload after a change

This is the part that trips people up, because **it depends on what changed**:

- **Something in a screen, button, or anything you clicked on** (the visual
  app) → the app **hot-reloads automatically**. You'll see it flicker/update
  within a second or two. No action needed.
- **Something about how the app starts up, talks to the engine, or the
  window itself** → hot-reload **does not** pick this up reliably. You need
  to fully restart:
  1. Press **Ctrl+C** in the terminal running `npm run dev`.
  2. Close the MediaMind window if it's still open.
  3. Check nothing was left running (see below) — this is the step people
     usually skip.
  4. Run `npm run dev` again.

### Checking nothing was left running

Electron sometimes leaves background processes alive even after you close
the window and Ctrl+C the terminal. If the app behaves like it's running old
code after a restart, this is almost always why. In PowerShell:

```powershell
Get-Process | Where-Object { $_.ProcessName -match "electron|python" } | Select-Object Id, ProcessName
```

If that shows anything, kill the whole tree by PID (replace `<PID>` with the
**topmost** one — usually the lowest/first `electron.exe` or the `node.exe`
running `electron-vite`):

```powershell
taskkill /PID <PID> /F /T
```

Then confirm the list above is empty and start `npm run dev` again.

---

## What you will see on first launch

The app opens to **Home** — a page with tiles for your pinned folders (empty
until you pin something) and a "Recent Files" grid of media you've recently
opened or touched. A thin amber banner at the very top reads "Starting
engine…" for the first few seconds while the Python backend boots, then
disappears; if it turns into "Engine offline — retrying…" instead, see
Troubleshooting below.

Use the folder tree on the left (or the drive list under "This PC") to
navigate — there's no "add a folder" step. Every folder is filtered to show
only subfolders that contain media (or might, until the background check
finishes) and the media files themselves; everything else on disk is simply
not shown. Network paths work too — type a UNC path like `\\server\share`
into the address bar and it navigates like any local folder.

### Getting around

- **Tabs** — the strip above the address bar; `Ctrl+T` opens a new tab at
  the current folder, `Ctrl+W` closes the active one, `Ctrl+Tab` /
  `Ctrl+Shift+Tab` cycle between them.
- **Address bar** — shows breadcrumbs for the current path; click the empty
  space to its right to edit it as raw text (type a path, press Enter).
- **Search box** (top right) — live, name-only filter over the current
  folder's contents; `Ctrl+Shift+F` (or pressing Enter with something
  typed) escalates the same query into a recursive search of every
  subfolder. Clears when you navigate away.
- **Filters icon** — toggles a row of Type / Date / Size filter chips.
- **View icon** — switch between Large icons, Tiles, List, Details, Content,
  and Gallery. Sort-by and Group-by are the two dropdowns next to it.
- **Preview pane icon** — toggles a right-side panel (Preview/Details tabs)
  for the selected file, including inline playback for video and audio.
- **History icon** — opens the "Recent deletions" panel (see below).
- **Quick access** — right-click any folder → "Pin to Quick access", or
  drag a folder onto the "Quick access" label in the nav pane. Hover a pin
  to reveal an "×" to unpin; drag pins up/down to reorder them.

### Organizing files

Right-click for a context menu — Open/Open with…, Cut/Copy/Paste, Rename,
Pin to Quick access, Reveal in File Explorer, Copy as path, Send to
(zipped folder / desktop shortcut), Create shortcut, Compress to ZIP,
Extract (on archives), Properties, and Delete — or use the toolbar/keyboard
shortcuts. Delete offers Recycle Bin (default) or permanent delete (with an
explicit confirmation dialog, since it can't be undone). One level of
undo/redo is available (`Ctrl+Z` / `Ctrl+Y`, or the toolbar) for the most
recent move/copy/rename/delete/new-folder — making a new change clears the
redo slot, same as any editor.

Drag a file or folder onto another folder to move it; hold **Ctrl** while
dropping to copy instead. This works whether the destination is a folder
tile in the current view, a node in the folder tree, or a Quick Access pin.

**Recent deletions panel.** `Ctrl+Z` can only undo the single most recent
operation, and deletes are treated as a boundary it won't reach past (so it
never accidentally reverses an older, unrelated action). For a fuller
history, open the History icon's "Recent deletions" panel — it lists every
file you've deleted, most recent first. Files sent to the Recycle Bin get a
"Restore" button that opens the real Windows Recycle Bin for you to restore
from (MediaMind doesn't do the restore itself — see "What is NOT available
yet" for why); permanently-deleted files are shown greyed out since there's
nothing left to restore.

### Keyboard shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+T` / `Ctrl+W` | New tab / close tab |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | Next tab / previous tab |
| `Alt+←` / `Alt+→` / `Alt+↑` or `Backspace` | Back / forward / up one folder |
| Arrow keys | Move keyboard focus (Ctrl/Shift extend selection, like a mouse click) |
| Type a letter/number | Jump to (type-ahead select) the next matching item |
| `Ctrl+A` | Select all |
| `F2` | Rename |
| `Delete` | Delete (to Recycle Bin) |
| `Shift+Delete` | Delete permanently (asks for confirmation) |
| `Ctrl+X` / `Ctrl+C` / `Ctrl+V` | Cut / Copy / Paste |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo |
| `Ctrl+Shift+N` | New folder |
| `Ctrl+F`, `Ctrl+E`, or `F3` | Focus the search box |
| `Ctrl+Shift+F` | Search subfolders too (recursive search) |
| `F5` | Refresh |
| `Alt+Enter` | Properties |
| `Ctrl+Shift+1`–`4` | Icon size (extra large → small, in icon views) |
| `Escape` | Clear selection |

---

## Where the older features went

**Duplicate finding, People (face recognition), Providers, and organize-
by-person** are fully implemented and tested on the backend (and have
working screens in the codebase) but are **not currently reachable from the
app window** — the main window now shows only the Explorer-style file
browser described above. This is a deliberate, in-progress step: the plan
is to fold these features back in as actions within the Explorer shell
(e.g. a right-click "Find duplicates in this folder", a "People" panel)
rather than as a separate app-specific screen, but that integration work
hasn't started yet — it's a design decision for a dedicated conversation,
not incidental wiring. If you need one of these features today, ask — the
underlying API and screens still work, they just need to be temporarily
re-wired into the app's routing to reach them.

---

## Where to look when something seems broken

MediaMind keeps two persistent log files that survive restarts — check these
**first** before assuming something is broken, especially if the app looks
fine but a specific feature (thumbnails, a file operation) fails silently:

| Log file | What it contains |
|---|---|
| `%APPDATA%\MediaMind\logs\engine.log` | Every backend API request (method, path, status, timing) and full tracebacks for any backend error |
| `%APPDATA%\mediamind-app\logs\mediamind.log` | Electron startup/shutdown events and everything the Python engine prints |

In PowerShell, to see the last 50 lines of either:

```powershell
Get-Content "$env:APPDATA\MediaMind\logs\engine.log" -Tail 50
Get-Content "$env:APPDATA\mediamind-app\logs\mediamind.log" -Tail 50
```

If the app crashes or a screen goes blank, the renderer (the part you see)
also forwards its own errors into `mediamind.log` — so that file is the
right place to check for a frozen or blank-screen situation, not just engine
problems.

---

## Possible issues and what to do

| Symptom | What to do |
|---|---|
| "Starting engine…" banner stays up for >30 seconds | Close app, check for leftover processes (above), re-run `npm run dev` |
| "Engine offline — retrying…" banner | Check `engine.log` for a traceback. Or run `C:\Users\husai\faces-env\Scripts\python.exe -m mediamind` directly in a terminal to see the raw error |
| Thumbnails/photos don't show even though names/counts look right | Make sure you have the latest code and did a full restart, not just a hot-reload (this was a real, now-fixed bug — see below) |
| A brand-new folder shows "0 items" for a couple seconds then looks like it vanished | The background "does this folder contain media" check hasn't resolved yet — wait ~1-3s |
| App won't fully close / acts like it's running old code | See "Checking nothing was left running" above |
| Drag-and-drop doesn't seem to do anything | Confirm you're dropping directly onto a folder tile/row, a folder-tree node, or a Quick Access pin — dropping onto empty space in the *same* folder you dragged from is an intentional no-op |
| Pressing `Escape` doesn't close the media viewer / Properties dialog / a confirmation dialog | Known bug — click the × button or click outside the dialog instead |
| A right-click menu or dropdown seems to do nothing when clicked | Not a known app bug in normal mouse use — if you hit this, note exactly what you clicked and tell me |

The dedupe/People/organize screens (scan progress, duplicate review, bulk
rules, pending matches) aren't reachable from the app right now — see
"Where the older features went" above — so their old troubleshooting
entries have been removed from this table.

---

## Known bug found and fixed (2026-07-05)

Early on, thumbnails rendered as broken-image icons everywhere in the app
even though the backend was serving them correctly — the window's security
policy didn't allow `blob:` image sources, which is how thumbnails are
delivered to the browser. Fixed by allowing `blob:` alongside the existing
allowed sources; verified thumbnails render with real pixel dimensions. If
you ever see broken-image icons again, it's not this same bug (already
fixed) — check `engine.log` for that specific file's error instead.

---

## What is NOT available yet

- **Duplicate finding, People/face recognition, Providers, organize-by-
  person** — implemented and tested, not currently wired into the app
  window (see "Where the older features went" above).
- **Dragging files out of MediaMind** into another app or the Windows
  desktop (drag *in*, from Explorer into MediaMind, does work). Deferred
  because it needs Electron's native `webContents.startDrag`, which would
  compete with the in-app drag-and-drop library for the same browser drag
  event.
- **One-click Recycle Bin restore.** The "Recent deletions" panel shows your
  deletion history and can open the real Windows Recycle Bin, but restoring
  a specific file back to its original location is something you do in that
  Recycle Bin window yourself, not a button in MediaMind. This was a
  deliberate safety call — automating it would mean scripting Windows Shell
  operations against your real files without a well-tested way to verify
  they land back in the right place.
- **Escape doesn't close the media viewer, Properties dialog, or
  confirmation dialogs** — use the × button or click outside instead.
  Known, not yet fixed.
- **Column resize/reorder/visibility for Details view is remembered
  globally, not per folder** (unlike view mode and sort, which are
  remembered per folder).
- **App packaging** — an installer/executable via `electron-builder` isn't
  set up; you always run from source (`npm run dev` or a manual
  `npm run build`).
- **Settings screen** — no dedicated settings UI (so there's no toggle yet
  for things like showing hidden files or file extensions).
- Pagination/virtualization for very large folders (10,000+ files), a
  thumbnail disk cache, and external-drive-safe eject handling — deliberate
  scope cuts, not bugs.

---

## File safety guarantees

MediaMind is designed to never lose or destroy your files:

1. Files are **moved to the Recycle Bin by default**; permanent delete is a
   separate, explicitly-confirmed action.
2. You must **explicitly confirm** before anything is permanently deleted.
3. Every file operation (move/copy/rename/delete/new-folder) is recorded to
   an operation log, which is what powers undo/redo and the "Recent
   deletions" history panel.
4. Files that **can't be found** at execute time are skipped with an error,
   not silently trashed.

---

## Where MediaMind stores its own data

Explorer file operations (undo/redo history, the "Recent deletions" log,
Quick Access pins, Recent Files, per-folder view preferences) are stored
app-wide, not inside your folders:

```
%APPDATA%\MediaMind\
├─ fs_ops\           ← operation log powering undo/redo + Recent deletions
├─ logs\              ← engine.log (see Troubleshooting above)
└─ ...
```

Nothing is written into the folders you browse. The one exception is the
older, currently-unreachable dedupe/faces workflow (see "Where the older
features went"): if you were to reach one of those screens today, scanning
a folder there still creates a `.mediamind/` subfolder inside it
(`index.db` + `manifests/`) exactly as before — that behavior is unchanged,
just not reachable from the current UI.

Face-recognition models download to `~/.insightface` (shared with any other
tool built on the `insightface` package, so you never end up with duplicate
copies).
