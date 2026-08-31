# Block 5 — Files-Integration UI Blueprint

**Status:** authoritative design for Block 5 (ADR-0012). Nothing here is built yet.
**Base decision (locked, 2026-08-31 revision):** the tech-stack constraint was
removed. We are **not** rebuilding on React. The new MediaMind frontend is a
**fork of `files-community/Files`** — the mature open-source Windows File
Explorer (44.8k★, MIT with MPL-2.0 on some files; both compatible with our
Apache-2.0 project). The existing **Python FastAPI engine is kept unchanged**;
the C#/WinUI app calls it over localhost HTTP + WebSocket exactly as the
Electron app does today. This makes MediaMind Windows-only for now, which
matches the project's stated Windows-first priority.

Local checkouts this blueprint is grounded in:
- Files source: `winui-frontend/Files/` (real code, cited below).
- Python engine: `backend/src/mediamind/` (real routes, cited below).
- The Electron bridge we are replacing: `app/src/main/backend.ts`,
  `app/src/renderer/src/api/client.ts` (the proven spawn/token/endpoint model).

The `frontend-design` skill's *principles* still bind — deliberate, non-generic,
a real quality floor (keyboard focus, reduced-motion, responsive panes) — but
they are now expressed in **WinUI/XAML + Fluent** terms and, above all, by
**conforming to Files' existing design system** (its XAML resources, converters,
`SectionType` sidebar model, `BaseLayoutPage` view modes). We inherit a
production Fluent aesthetic; we do not invent a web one. Per Files' own
`AGENTS.md`: "use existing XAML resources, controls, converters, commands, and
localization patterns. Avoid one-off styles or hard-coded user-visible strings."
That rule is our design language.

---

## 1. Files architecture (real project + namespace names)

**Solution / toolchain.** One solution `Files.slnx` (new-style solution file),
**.NET 10** (`global.json` pins SDK `10.0.102`, `rollForward: latestMajor`),
**WinUI 3 / Windows App SDK**, C#. Built with msbuild, not `dotnet build`:
`msbuild -restore Files.slnx -p:Configuration=Debug -p:Platform=x64` (from
`AGENTS.md`). Native-AOT-aware: `AGENTS.md` forbids new `DllImport`/`ComImport`
and runtime reflection, and requires CsWin32 for interop. Package identity via
`src/Files.App/Package.appxmanifest` (MSIX).

**Projects** (`winui-frontend/Files/src/`):

| Project | Role |
|---|---|
| `Files.App` | Main WinUI 3 app — views, viewmodels, services, actions, XAML resources. Everything we touch lives here. |
| `Files.App.Controls` | Shared custom XAML controls (e.g. the sidebar control, toolbars). |
| `Files.App.Storage` | Concrete storage-service implementations (native FS, FTP, cloud). |
| `Files.Core.Storage` | Storage abstractions/contracts (interfaces the storage services implement). |
| `Files.App.CsWin32` | Generated Win32/COM interop; `NativeMethods.txt` is the source of truth. |
| `Files.App.Server` | An out-of-process **COM activation host** (`Program.cs` registers `AppInstanceMonitor` via `RoRegisterActivationFactories`) used for the elevated / secondary-instance file-operation channel. **Not** a generic process launcher — do not mistake it for the Python-spawn seam. |
| `Files.App.BackgroundTasks` | Windows background-task entry points. |
| `Files.Core.SourceGenerator` | Roslyn generators/analyzers (settings serialization, localized strings, etc.). |
| `Files.Shared` | Shared attributes/extensions/common code. |
| `Files.App.Launcher`, `Files.App.OpenDialog`, `Files.App.SaveDialog` | Small shim exes for shell/dialog integration. |

**MVVM + DI.** CommunityToolkit.Mvvm with the `Ioc.Default` container. The
container is assembled in **`Files.App/Helpers/Application/AppLifecycleHelper.cs`
→ `ConfigureHost(AppModel)`** (line ~297) as one long, flat chain:
`services.AddSingleton<IUserSettingsService, UserSettingsService>() … .AddSingleton<SidebarViewModel>() …`.
`App.xaml.cs` calls `Ioc.Default.ConfigureServices(provider)` (lines 92, 156).
**This chain is exactly where our engine service and people-viewmodels get
registered** — one line each, matching the surrounding pattern.

**Services** (`Files.App/Services/`, 58 files, grouped `App/`, `Settings/`,
`Storage/`, `Windows/`, `Git/`, …). Everything is interface-first
(`IStorageService`, `IQuickAccessService`, `IDialogService`, `IImageService`,
`IUpdateService`, `IThreadingService`, `ICommandManager`, the many
`I*SettingsService`). Settings services are **source-generated** and share a
context off `UserSettingsService`.

**Views / shell layout** (`Files.App/Views/`):
- `MainPage.xaml` — the outer shell (tab strip + sidebar + panes host).
- `ShellPanesPage.xaml` — the multi-pane (split-view) host.
- `Shells/` — the per-tab shell pages.
- `Layouts/` — the **view modes**: Details, Grid/Icons, Columns, etc., all
  derived from a shared `BaseLayoutPage` (`ViewModels/Layouts/`). This is where a
  new "People" view mode would slot if we need one (we mostly don't — see §3).
- `HomePage.xaml` + `ViewModels/HomeViewModel.cs` (+ widget viewmodels:
  `QuickAccessWidgetViewModel`, `RecentFilesWidgetViewModel`, …) — the
  card-based landing page. The bootstrap/onboarding surface (ADR-0002) is a
  natural home-widget analog.
- `Views/Settings/` — settings pages (e.g. `TagsPage.xaml` manages FileTags).

**Sidebar navigation (the key extension point).**
`ViewModels/UserControls/SidebarViewModel.cs` builds the sidebar from a fixed
`SectionType[] SectionOrder` (line ~78): `Home, Pinned, Library, Drives,
CloudDrives, Network, WSL, FileTag`. The enum is
`Files.App.Data.Contracts.SectionType` in
`Data/Contracts/INavigationControlItem.cs`. Each sidebar row implements
`INavigationControlItem` (has `Section`, `ItemType`, `MenuOptions`);
`NavigationControlItemType` is `{ Drive, LinuxDistro, Location, FileTag }`. Each
section has a `Show*Section` bool backed by `GeneralSettingsService`.

**`FileTag` is the load-bearing precedent for MediaMind.** It is the one
existing section that is a **virtual projection, not a physical location**: a tag
sidebar item navigates to a `tag:`-style path and the layout shows every file
carrying that tag, gathered from across the filesystem, with no folder actually
holding them. That is structurally identical to a **Person** ("show every photo
of this person regardless of where it lives" — CONTEXT.md "People view").
Everywhere this blueprint says "model People/Groups on FileTags," it means: copy
the `SectionType.FileTag` + `NavigationControlItemType.FileTag` +
`Views/Settings/TagsPage` + tag-search-path pattern, renamed for People.

**Auto-update already exists** (`Data/Contracts/IUpdateService.cs`,
`Services/App/SideloadUpdateService.cs` / `StoreUpdateService` /
`DummyUpdateService`, chosen by build channel in `ConfigureHost`). This **is** our
electron-updater replacement — no new mechanism needed. Sideload builds
self-update; Store builds defer to the Store.

---

## 2. The Python integration seam

**Nothing about the Python engine changes.** The seam is a single new C# service
that reproduces what `app/src/main/backend.ts` already does. The contract
(verified in `backend/src/mediamind/__main__.py`, `api/security.py`, `api/app.py`
and mirrored in `app/src/main/backend.ts`):

1. **Spawn** the engine: dev = venv `python -m mediamind`; packaged = the
   PyInstaller one-folder exe (today electron-builder ships it to
   `resources/engine/mediamind.exe`). Set env `MEDIAMIND_TOKEN=<random hex>`.
2. The engine picks a **free port**, binds `127.0.0.1`, and prints exactly one
   line `MEDIAMIND_PORT=<port>` to **stdout** (`__main__.py:37`). Parse it.
3. **Health-gate**: poll `GET /v1/health` with header `X-MediaMind-Token: <token>`
   until 200 (backend.ts `waitForHealth`, 30 s budget).
4. Every HTTP call carries `X-MediaMind-Token` (`api/security.py`
   `TokenAuthMiddleware`, ASGI, `hmac.compare_digest`). WebSocket auth is a
   **query param**: `ws://127.0.0.1:<port>/v1/progress?token=<token>`
   (`api/app.py:203`, WS can't read the header).
5. On shutdown, **force-kill the process tree** — backend.ts uses
   `taskkill /pid <pid> /T /F` on Windows because the engine exe is also named
   `mediamind.exe` and a lingering child blocks the updater. Our WinUI service
   must do the same (`Process.Kill(entireProcessTree: true)`).

**Where it lives.** One interface + implementation in `Files.App/Services/`,
registered in `ConfigureHost`. No new project needed (ponytail: a single service
is not worth a project). Follow the `IUpdateService`/`SideloadUpdateService`
shape exactly:

```csharp
// Files.App/Services/MediaMind/IMediaMindEngineService.cs
public interface IMediaMindEngineService
{
    Task<bool> EnsureStartedAsync(CancellationToken ct);   // spawn + port + health
    HttpClient Client { get; }                              // base http://127.0.0.1:{port}, token header preset
    IObservable<JobSnapshot> JobEvents { get; }             // WS /v1/progress fan-out
}
```

- Use the framework **`HttpClient`** (rung 3/5: BCL already does this — no Refit,
  no Polly for a localhost single-host client). Preset `BaseAddress` and the
  `X-MediaMind-Token` default request header once started.
- Use **`System.Diagnostics.Process`** with `RedirectStandardOutput=true` to read
  the `MEDIAMIND_PORT=` line. This is plain BCL; the `Files.App.Server` COM dance
  is irrelevant here.
- Use **`System.Net.WebSockets.ClientWebSocket`** for `/v1/progress`; surface job
  progress into Files' existing **`StatusCenterViewModel`** (the status-center /
  "ongoing operations" flyout Files already shows for copies/deletes), so face
  scans and consolidations render in the same place as native file ops. Do **not**
  build a parallel progress UI.
- Register: add `.AddSingleton<IMediaMindEngineService, MediaMindEngineService>()`
  to the `ConfigureHost` chain, and start it from `AppLifecycleHelper`'s
  post-activation init (`InitializeAppComponentsAsync`, called at
  `App.xaml.cs:238`) so it warms while the first frame renders.

**Real endpoints the WinUI app will call** (routers mounted under `/v1` in
`backend/src/mediamind/api/app.py:229-244`; request/response shapes already typed
in `app/src/renderer/src/api/client.ts` — port those DTOs to C# records
verbatim):

| Area | Route module | Key endpoints (all `/v1/…`) |
|---|---|---|
| Health / WS | `app.py` | `GET /health`, `WS /progress?token=` |
| Libraries | `routes/libraries.py` | `GET/POST /libraries`, `DELETE /libraries/{id}` |
| Filesystem browse | `routes/fs.py` | `/fs/drives`, `/fs/list`, `/fs/has-media`, `/fs/metadata`, `/fs/folder-faces`, `/fs/thumbnail`, `/fs/preview`, `/fs/quick-access`, `/fs/recent`, `/fs/settings`, `/fs/discovery/{suggestions,register,dismiss}` |
| FS ops (safe) | `routes/fs_ops.py` | `/fs/{new-folder,rename,delete,move,copy,undo,redo,create-shortcut}` |
| Scans / jobs | `routes/scans.py` | `POST /libraries/{id}/scans` (`type=dedupe\|faces`), job get/cancel |
| Duplicates | `routes/duplicates.py`, `routes/duplicate_flags.py` | `/libraries/{id}/duplicates`, `/duplicates/execute-job`, `/duplicate-flags` |
| People / faces | `routes/persons.py` | `/libraries/{id}/persons`, `/people-tree`, `/recurring-unnamed`, `/persons/{id}/media`, `/persons/merge`, `/faces/{id}/{reject,person,thumbnail}`, `/persons/{id}/primary-folder` |
| Review queues | `routes/pending.py`, `routes/multi_person.py` | `/pending`, `/pending/decisions`, `/multi-person`, `/route-choices` |
| Folder bindings / consistency | `routes/bindings.py` | `/bindings/refresh`, `/bindings/suggestions`, `/bindings/{id}/outliers`, `/bindings/suggestions/{id}/merge` |
| Consolidation (moves) | `routes/organize.py`, `routes/materialize.py` | `/organize/{preview,execute-job,undo,audit,duplicate-locations}`, `/persons/{id}/materialize` |
| Cross-library people | `routes/global_people.py` | `/global/people`, `/global/move-suggestions/{,dismiss,execute}`, `/global/moves/{undoable,undo}` |
| Providers (models) | `routes/providers.py` | `/providers`, `/providers/{id}/download` |

The full typed surface is in `app/src/renderer/src/api/client.ts` (≈1200 lines) —
**translate its interfaces to C# `record`s and its `api.*` methods to
`IMediaMindEngineService` calls**. That file is the spec; do not re-derive it.

**Thumbnails / media**: the engine serves `<img>`/`<video>`-style direct URLs
(`/v1/fs/thumbnail?path=…&size=…`, `/fs/preview`, `/faces/{id}/thumbnail`). In
WinUI these become `BitmapImage` sources fetched through the same `HttpClient`
(the token is on the client), feeding Files' existing `IImageService`/thumbnail
pipeline. Content-hash-keyed thumbnails + the 409 `library_offline` response
(`app.py:180`) give us ADR-0004 offline badging for free.

---

## 3. Feature integration map

Guiding rule: **coexist by reusing Files' own surfaces, never by inventing a
parallel shell.** People/Groups reuse the FileTag section pattern; review queues
reuse the StatusCenter + a dialog/pane; moves reuse Files' file-operation
confirmation + progress. One new sidebar section, one new "review" pane, a
handful of dialogs — that is the whole footprint.

**1. Person-centric People view (ADR-0007) + nested Groups (ADR-0008).**
- *Where:* a new `SectionType.People` in `INavigationControlItem.cs`, inserted in
  `SidebarViewModel.SectionOrder` (suggest after `Library`, before `Drives`), with
  a `ShowPeopleSection` flag on `GeneralSettingsService`. Sidebar items are
  `Group` nodes (expandable, mirroring folder nesting from `/people-tree`) and
  `Person` leaves — modeled on the FileTag section's virtual items.
- *Content:* clicking a Person navigates to a `person:{id}` pseudo-path; a Group
  to `group:{path}`. The **existing Grid/Details `BaseLayoutPage` renders the
  media** returned by `/persons/{id}/media` — no new view mode required. A Group
  page shows **only sub-Groups and Persons** (ADR-0007: Groups never hold media
  directly; enforce in the page's item source), with a "show everything below"
  toggle (ADR-0008 direct-contents default).
- *Fluent fit:* identical interaction to opening a tag or a drive — breadcrumb,
  tabs, back/forward, selection all come from the shell for free.
- *Naive break:* letting a Group page list loose media re-imports filesystem
  mess. The Group item source must project to Persons only.

**2. Always-on watcher over designated roots (ADR-0009).**
- *Where:* the engine already runs the watcher (`api/app.py` lifespan starts
  `LibraryWatcher` + `IngestWorker`); the UI only manages the **watched-root set**
  and shows status. A **Settings page** `Views/Settings/WatchedFoldersPage.xaml`
  (sibling of `TagsPage`) lists roots in plain language with one-tap add of
  auto-detected inboxes (`/fs/discovery/suggestions` → `/fs/discovery/register`).
  A persistent **status-bar/StatusCenter pill** ("Watching 6 folders") gives
  always-visible state.
- *Fluent fit:* Files already has a Settings shell and a status center; this is a
  new settings page + a status item, both native patterns.
- *Naive break:* equating "watched root" with Files' `Library` concept auto-scans
  huge trees. Keep watched roots an explicit, user-visible list (ADR-0009).

**3. Duplicates folded into ingest → top of Suggestions (ADR-0003).**
- *Where:* **not** a separate tool. Dedupe runs in the ingest pass; the UI reads
  `/duplicate-flags` (incremental) and `/libraries/{id}/duplicates` (full scan) and
  renders duplicate clusters as the **top group of the Suggestions pane** (feature
  4). At Consolidation, an inline **soft duplicate check with "skip duplicates"
  preselected** (feature 4/Consolidation), never a hard block.
- *Fluent fit:* a `TabView`/list section inside the review pane; duplicate
  clusters use the same thumbnail tiles as everything else.
- *Naive break:* re-porting the old standalone dedupe tool as its own mode
  competes with Suggestions and lets Consolidation copy dupes unseen.

**4. Suggestions surface + Consolidation.**
- *Suggestions where:* a dockable **Suggestions pane** (right side), modeled on
  Files' **Info/Preview pane** (`InfoPaneViewModel`, `IInfoPaneSettingsService`
  already exist — same show/hide + width-persist plumbing). It is a persistent
  **inbox with a badge count**: duplicates (top), uncertain face matches
  (`/pending`), recurring-unnamed prompts (`/recurring-unnamed`), low-confidence
  video (feature 7). Cleared by confirm/reassign/dismiss (`/pending/decisions`,
  etc.).
- *Consolidation where:* the **only byte-moving action**, launched from a Person's
  command bar / context menu ("Consolidate to primary location"). It opens a
  **review dialog** (`IDialogService` pattern) driven by `/organize/preview` (or
  `/persons/{id}/materialize/preview`): shows planned moves + the soft duplicate
  check, requires confirm, then runs `/organize/execute-job` /
  `/persons/{id}/materialize`. The engine does **copy-then-delete, journaled,
  count-checked** (ADR-0005 + CLAUDE.md safety invariants); the UI shows progress
  in StatusCenter and exposes `/organize/undo`.
- *Fluent fit:* review = a standard content dialog; progress = StatusCenter;
  undo = a command. No bespoke chrome.
- *Naive break:* auto-moving on confidence, or moving without the reviewed
  preview + count check, violates review-before-commit.

**5. Offline-resilient catalog badges (ADR-0004).**
- *Where:* People/Group/media tiles read the off-drive catalog, so they render
  instantly even when a volatile (Cryptomator) drive is unmounted. Offline items
  get a **Fluent corner badge** (reuse the cloud/sync `InfoBadge` overlay style
  Files already uses for cloud drives) rather than a blank tile; content-hash
  thumbnails still show. Operations needing bytes (open original, consolidate onto
  the drive) are **disabled with a "Connect the drive" tip**; the engine's 409
  `library_offline` is the signal (`api/app.py:180`, `isLibraryOffline` in
  client.ts).
- *Naive break:* keying thumbnails on a live `stat()` (blank tiles on unmount) —
  already solved backend-side; the UI must trust the catalog, not the live FS.

**6. Folder-placement-override + consistency check (ADR-0010).**
- *Where:* placement-attributed media already arrive flagged
  (`PersonMediaItem.via_placement` in client.ts). Show a small **"In this
  person's folder" glyph** on those tiles. The **consistency check** is an
  on-demand command on a Person ("Check for misfiled photos") that calls the
  bindings/outlier endpoints (`/bindings/{id}/outliers`, ranked disagreements) and
  presents results in the **Suggestions pane** as a ranked list to confirm (model
  was wrong, keep) or correct (reassign/move).
- *Naive break:* letting the face model silently drop placement-attributed files;
  placement wins, the check is advisory only.

**7. Video progressive-sampling review (ADR-0011).**
- *Where:* mostly backend. UI: low-confidence video matches route to the
  **Suggestions pane** as review cards with a **keyframe/scrubber preview** (Files'
  preview pipeline handles video), not auto-joined — unless placement-confirmed
  (feature 6). Video tiles carry the native duration/kind badge Files already
  renders.
- *Naive break:* treating a sampled video match as high-confidence auto-join.

**8. Bootstrap-from-folders reviewed proposal (ADR-0002).**
- *Where:* a **first-run onboarding flow** (a HomePage widget "Set up People from
  your folders" + a wizard dialog) driven by `/bindings/refresh` +
  `/bindings/suggestions`: lists proposed Persons / Groups / Primary Locations,
  each **editable, acceptable, or dismissable**, committed only on user action
  (`/bindings/suggestions/{id}/accept`, `/merge`). Event/mixed folders are left
  unproposed by the engine.
- *Fluent fit:* a multi-step content dialog + a home widget — both native.
- *Naive break:* auto-committing the proposal violates review-before-commit.

**Coexistence summary.** New sidebar section (People) sits beside Drives/Tags;
review lives in one Suggestions pane (Info-pane pattern); the single destructive
op (Consolidation) uses dialog-confirm + StatusCenter-progress + undo; watcher
config is a Settings page; onboarding is a home widget + wizard. No two features
own the same surface, and none replace the file-browsing shell — they layer on it.

---

## 4. Phased build order

Each phase is independently shippable and verifiable (build succeeds per
`AGENTS.md`; the phase's own flow driven end-to-end). Fork Files first; keep the
fork rebasable on upstream by isolating our code under `Services/MediaMind/`,
`ViewModels/People/`, `Views/People/` folders and minimizing edits to shared
files (only the DI chain, the `SectionType` enum, and `SectionOrder`).

- **Phase 0 — Toolchain + smoke test.** Install VS Build Tools / .NET 10 SDK
  (`global.json` 10.0.102), build `Files.slnx` x64, run it. Add
  `IMediaMindEngineService` that spawns the dev engine (`python -m mediamind`),
  reads `MEDIAMIND_PORT=`, health-checks `GET /v1/health`, and log the version to
  prove the round-trip. **Deliverable:** Files runs and the debug log shows a live
  `/v1/health` response from Python. Nothing user-visible yet.

- **Phase 1 — Engine service hardening + DTOs.** Flesh out the service: token
  header, typed `HttpClient` calls, WS `/v1/progress` → `StatusCenterViewModel`,
  process-tree kill on exit, packaged-vs-dev exe resolution. Port the client.ts
  DTOs to C# records. **Deliverable:** every engine endpoint callable from C#,
  job progress visible in the status center; verified against a real scan job.

- **Phase 2 — People as a sidebar section.** Add `SectionType.People`,
  the Group/Person sidebar items from `/people-tree`, and the Person media page on
  `BaseLayoutPage` via `/persons/{id}/media` (with offline badges, ADR-0004, and
  placement glyphs, ADR-0010). Naming/rename/merge. **Deliverable:** browse People
  and Groups in the real shell; open a person and see their media.

- **Phase 3 — Suggestions pane + duplicates.** Build the Info-pane-style
  Suggestions inbox with badge: duplicates (top), uncertain matches, recurring
  unnamed, video review cards. Wire confirm/reassign/dismiss. **Deliverable:** the
  review loop works; duplicates and pending matches resolve.

- **Phase 4 — Consolidation + consistency check.** The reviewed move dialog
  (`/organize/preview` → `/organize/execute-job`, soft dup check, count check,
  StatusCenter progress, `/organize/undo`) and the on-demand consistency check
  (bindings/outliers → Suggestions). **Deliverable:** the one byte-moving flow,
  fully safety-gated (copy-then-delete, journaled, undoable).

- **Phase 5 — Watcher settings + bootstrap onboarding.** WatchedFoldersPage with
  one-tap inbox add (`/fs/discovery/*`), status pill, and the first-run
  bootstrap-from-folders wizard (`/bindings/*`). **Deliverable:** onboarding +
  always-on watching configurable in-app.

- **Phase 6 — Packaging + polish.** MSIX packaging that bundles the PyInstaller
  engine and spawns it from the install dir; wire `SideloadUpdateService` as the
  update path; Fluent polish pass (empty/offline/error states, keyboard focus,
  reduced-motion, localized strings per `AGENTS.md`). **Deliverable:** an
  installable, self-updating build with the engine bundled.

---

## 5. Risks & open questions

**Top failure modes**
1. **Fork drift.** Diverging from upstream Files makes security/bugfix rebases
   painful. Mitigate by confining our code to new folders and touching only three
   shared files (DI chain, `SectionType`, `SectionOrder`); never reformat or
   refactor upstream files (AGENTS.md forbids opportunistic churn).
2. **AOT/trimming + interop rules.** `AGENTS.md` bans new `DllImport`/`ComImport`
   and runtime reflection and expects trim/AOT-clean builds. Our DTO
   (de)serialization must use **`System.Text.Json` source-generation**, not
   reflection, or builds/analysis break.
3. **Rebuilding file-manager mechanics we're adopting Files *to get*.** The whole
   point is to inherit working cut/copy/paste/context-menus/keyboard-nav. Keep our
   features additive; do not fork the layout/selection/DnD engine.
4. **Safety-invariant regressions at the C# seam.** Consolidation must never move
   without the reviewed preview + count check; the engine enforces copy-then-delete
   + journaling, but the UI must not offer any path that bypasses the preview.

**Decisions the human must make**
1. **How is the Python engine bundled and spawned inside an MSIX WinUI app?**
   Today electron-builder ships the PyInstaller one-folder to
   `resources/engine/mediamind.exe`. For MSIX we must include that folder as app
   content and `Process.Start` it from the package install dir — needs validating
   against MSIX process-launch and virtualized-filesystem constraints (and whether
   a full-trust package / `runFullTrust` capability is required). **Highest-risk
   unknown; recommend a Phase 0 spike.**
2. **Auto-update channel.** Confirm we adopt Files' `SideloadUpdateService`
   (self-updating sideload MSIX via GitHub releases, replacing electron-updater)
   rather than the Microsoft Store path. This drives signing/packaging choices and
   how updates ship the bundled engine alongside the app.
3. **Toolchain provisioning.** .NET 10 SDK (10.0.102) + Windows App SDK + VS 2022/
   "18" Build Tools + Windows SDK are now hard prerequisites for every build
   session (per `AGENTS.md`'s DevShell invocation). Confirm the dev machine and any
   CI are provisioned before Phase 1, and decide the CI/build story (msbuild, not
   `dotnet build`; x64 + arm64?).

**Lower-priority open items:** whether People needs its own `BaseLayoutPage`
subclass or can reuse Grid/Details as-is (default: reuse); whether the Suggestions
pane and Info pane can share one dock slot or need separate ones; localization —
all our user-visible strings must go through Files' resource/`.resw` system, not
literals (AGENTS.md).
