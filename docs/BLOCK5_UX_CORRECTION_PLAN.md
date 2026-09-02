# Block 5 — UX Correction Plan (media-first surfacing)

**Status:** planned 2026-09-03 (session 88). Not yet implemented. Next session
starts here.

## Why this exists

Block 5 shipped a working Files clone with the MediaMind engine bundled and most
feature *logic* present — but the **product** the grill (s56) designed did not
survive into the UI. An audit of the WinUI source (s88) found the failures are a
*class*, not the few examples the user named:

- **No media-first view.** No media-only default filter anywhere — the app shows
  PDFs/Word/markdown like any file explorer. (Not even in the Block 5 UI blueprint;
  a documentation miss.)
- **Flagship features buried or invisible**, and the build ignored its own
  blueprint's IA:
  - "Scan for People" is a **right-click context-menu item only** (no visible
    button); it **hangs 100s on `POST /v1/libraries`, times out, swallows the
    error** — zero feedback (user clicked 6× per debug.log).
  - **People section is dead last** in the sidebar (`SectionType` enum ends
    `…WSL, FileTag, People`). Blueprint §3 said "after Library, before Drives."
  - **Suggestions** is a hidden **toolbar flyout**, not the persistent badged
    right-side inbox the blueprint specified.
  - **Duplicate detection** has full backend API (`Duplicates`, `DuplicateFlags`,
    dedupe job) but **no UI** — completely invisible.
  - **Bootstrap onboarding** is buried in the Watched Folders **settings page**,
    not a first-run HomePage widget/wizard.
  - **Watch-a-folder** is only reachable via Settings; no "Watching N" pill, no
    one-click "watch this folder".
- **No cause/effect feedback** on any action.

## Target information architecture (the design)

**Sidebar order (top → bottom):** Home → **People** → Pinned/Quick access →
Libraries → Drives (This PC) → Cloud → Network → WSL → Tags. People sits in the
**top cluster**, right under Home.

**Main view:** media-only by default (images + video), with a visible
`Show all files` toggle in the command bar. Media tiles are the default
experience.

**Command bar (folder context):** visible `Scan for People` and `Watch this
folder` buttons — not hidden in right-click. Right-click keeps them too, but the
primary surface is the command bar.

**People/Person page:** person-centric (ADR-0007) — Groups hold only sub-Groups +
Persons; media appears under a Person. Person command bar exposes `Consolidate to
primary`, `Check for misfiled photos`, `Rename`, `Set primary folder`. The flow
after opening a Person = their media grid; opening a Group = its sub-Groups/Persons.

**Suggestions:** persistent right-side dockable pane (Info-pane pattern) with an
always-visible **badge count**: duplicates (top) → uncertain matches → recurring
unnamed → low-confidence video. Reachable from a always-present toolbar button
with the count, not a bare flyout.

**Onboarding:** first-run HomePage widget "Set up People from your folders" →
bootstrap wizard. Plus a persistent "Watching N folders" status pill.

**Feedback (everywhere):** each action shows pending → progress → success/error in
the main UI (inline banner/toast + a real progress surface), never a silent log.

## Phased build order (each phase verified end-to-end from the user's POV)

- **Phase A — Media-first identity.** Add a media-only default filter to the
  folder view (image/video extensions via existing `FileExtensionHelpers`), with a
  visible `Show all files` toggle persisted in settings. *Verify:* open a mixed
  folder → only media shows by default; toggle reveals all. **This is step 1.**

- **Phase B — Surface the flagships.** Reorder `SectionType`/`SectionOrder` so
  People is in the top cluster. Promote `Scan for People` and `Watch this folder`
  to visible command-bar buttons. Make Suggestions a persistent badged pane.
  *Verify:* every flagship reachable in ≤1 obvious click; People near top.

- **Phase C — Cause & effect.** Wire visible pending/progress/success/error into
  `ScanForPeopleAction` and all person actions (Consolidate, ConsistencyCheck,
  Rename, SetPrimary). Stop swallowing exceptions silently. *Verify:* clicking
  scan shows immediate visible state and a visible outcome (success or error).

- **Phase D — Fix the scan hang.** Root-cause `POST /v1/libraries` blocking ≥100s
  (registry.add / watcher-registration enumerating remote paths synchronously —
  see the startup `watcher: native events unavailable` storm). Make registration
  return immediately; move watch setup off the request thread. *Verify:* real
  click on a real folder registers in <2s and a scan job starts visibly.

- **Phase E — Fill the invisible features.** Render **duplicates** as the top
  group of Suggestions (API already exists). Move **bootstrap** to a first-run
  HomePage widget + wizard. Add the **"Watching N" status pill**. Confirm
  consistency-check results land in Suggestions. *Verify:* each feature reachable
  and functional from the main UI.

- **Phase F — End-to-end + package.** Full real-user pass on a real test folder
  (scan → people appear → name → consolidate preview → undo), then rebrand
  Files→MediaMind and repackage the managed MSIX. *Verify:* the whole people flow
  works by hand, no backdoors.

## Verification standard (applies to every phase)

Drive the **real** interaction (real click, real folder with faces, visible
result) — via automation or by hand — on data that contains the conditions that
break in production. Never a rigged empty fixture. Never mark verified via an
API/UIA `Invoke()` backdoor. (See `feedback_verify_end_to_end_user_perspective`.)

## Key source anchors (WinUI fork)

- Sidebar order: `Files.App/Data/Contracts/INavigationControlItem.cs` (`SectionType`
  enum) + `Files.App/ViewModels/UserControls/SidebarViewModel.cs`.
- Scan action: `Files.App/Actions/MediaMind/ScanForPeopleAction.cs` (silent-fail
  paths at lines 45–57); surfaced only in
  `Files.App/Data/Factories/ContentPageContextFlyoutFactory.cs:552`.
- People items/page: `Files.App/Data/Items/MediaMind/{PeopleGroupItem,PersonItem}.cs`,
  `Files.App/Views/People/PeopleGroupPage.xaml`.
- Suggestions: `Files.App/UserControls/MediaMind/SuggestionsPane.xaml`, hosted in
  `Files.App/UserControls/NavigationToolbar.xaml:431-465` (flyout — move to a
  docked pane).
- Duplicates API (no UI yet): `Files.App/Services/MediaMind/MediaMindApiClient.cs`
  (`DuplicatesApi`, `DuplicateFlagsApi`, dedupe job `StartAsync`).
- Bootstrap: `Files.App/Utils/MediaMind/BootstrapWizard.cs` +
  `Files.App/Dialogs/BootstrapWizardDialog.xaml.cs` (launched from
  `WatchedFoldersViewModel` — move to first-run/HomePage).
- Watcher settings: `Files.App/Views/Settings/WatchedFoldersPage.xaml`.
- Engine hang: backend `registry.add()` / watcher registration (bounded probe in
  commit `6fa1c7b` was insufficient for real folders).
