# MediaMind — People-Flow Blueprint

The end-to-end design for MediaMind's facial-recognition / people-organisation
flow, produced in a structured design session (grilling + domain modelling) on
**2026-08-30**. This document is the connected overview; the binding decisions
live as ADRs in `docs/adr/`, and the vocabulary lives in `CONTEXT.md`. Read all
three together.

> **Nothing here is implemented yet.** This is a blueprint. Implementation
> happens in later sessions, one block at a time (see the Roadmap below).

---

## 1. The problem this solves (the user's real situation)

The user is an avid collector of photos and videos *of specific people*, pulled
from many sources (WhatsApp, Telegram, social media, downloads). New files land
scattered across the system — Downloads, the Telegram folder, and a
**Cryptomator drive backed by Google Drive** (used because local storage is
scarce, so files **stream on-demand** from the cloud). The user has *already*
hand-built a folder structure (`Family/`, `Friends/`, `pop/kpop/twice/`, …) that
encodes relationships only they know. Two pains:

1. Manually filing every new file into the right person's folder is exhausting.
2. Plain face-recognition-into-folders can't help, because it doesn't know the
   user's relationship structure and it drowns the result in background faces.

## 2. The shape of the solution

Not two layers but **three, plus two cross-cutting concerns**:

1. **Detect & cluster** — raw face recognition turns pixels into face-groups.
2. **Resolve identity** — messy clusters become **named, trusted Persons**
   (naming, merging, splitting, rejecting, parking strangers). The hard middle.
3. **View & consolidate** — the fast virtual **People view** (find/show, never
   moves a file) and one-click **Consolidation** into a Person's **Primary
   Location** (the only thing that moves bytes, always reviewed).

Cross-cutting: **relationships/grouping** (the folder-derived Group tree) and
**index ⇄ filesystem truth** (the catalog stays honest as drives — especially
Cryptomator — mount and unmount).

## 3. How the whole flow connects (narrative)

- The always-on **watcher** (armed by one toggle) watches a designated set of
  **roots** — the user's library folders plus auto-suggested inboxes (Downloads,
  Telegram, WhatsApp), *not* the whole disk. [ADR-0009]
- A new file is ingested in **one pass** that does **both** face detection and
  **duplicate** detection. Duplicates surface at the top of **Suggestions**.
  [ADR-0003]
- Faces are matched **only against Persons the user has named** (curated). A
  high-confidence match silently joins that Person's view; an uncertain one waits
  in **Suggestions**; a face matching nobody is *not* invented into a Person — it
  goes to the browsable **recurring-unnamed-faces** surface to be named later.
  [ADR-0001, ADR-0013→§Q13 floor]
- On setup, MediaMind **bootstraps** Persons, Groups and Primary Locations by
  reading the existing folder structure — judged by **face content, not folder
  name**, and always as a **reviewed proposal**. Event/mixed folders
  (`marriage/`, `unsorted/`) are left alone. [ADR-0002]
- The **People view** is strictly person-centric: a **Group** tree (mirroring the
  user's nested folders) holds only sub-Groups and Persons; **files appear only
  under a Person**, never loose under a Group. [ADR-0007, ADR-0008]
- A file the user **manually places in a Person's folder** is a trusted human
  label that **overrides the face model**; an on-demand **consistency check**
  lets the user catch their own misfiles. [ADR-0010]
- **Videos** are sampled progressively (early-exit when the cast stabilises,
  capped) and matched conservatively — low-confidence video routes to Suggestions
  for visual review. [ADR-0011]
- The whole thing is an **offline-resilient catalog** (global, off-drive index;
  content-hash-keyed thumbnails) so the People view is instant and survives
  Cryptomator unmounting — offline items are badged, not broken. [ADR-0004]
- Every long or file-modifying operation is **journaled and auto-resumed** after
  any interruption; scans (which can run many hours) resume from their checkpoint
  on next launch instead of restarting. [ADR-0005]

## 4. Decision index (ADRs)

| ADR | Decision |
|---|---|
| 0001 | Curated, layered People pipeline (not auto-discovery); recurring-unnamed surface |
| 0002 | Bootstrap Persons/Groups from existing folders by **face content**, reviewed |
| 0003 | Duplicate detection folded into the pipeline; top of Suggestions; soft gate at Consolidation |
| 0004 | People view is an **offline-resilient catalog** over an off-drive, content-hash-keyed index |
| 0005 | **Write-ahead journal + auto-resume** for moves *and* long scans; never prevent unmount |
| 0006 | **Scan performance is a dedicated deep-dive block**; streaming is permanent |
| 0007 | People tab is strictly **person-centric**; Groups never hold media directly |
| 0008 | **Nested Group tree** mirroring folders; one home Group per Person |
| 0009 | Watcher watches **designated roots** (auto-suggested inboxes), effortless setup |
| 0010 | **Folder placement overrides the face model**; per-person consistency check |
| 0011 | Video: progressive sampling + conservative (review-biased) matching |
| 0012 | **UI/UX overhaul** = clone a permissively-licensed OSS file explorer; tooling mandate |

Two decisions from the session are intentionally *not yet* their own ADRs because
they are parameters of ADR-0001 rather than standalone architecture: the
**confidence split** (high → auto-join view, low → Suggestions) and the **Q13
recurrence floor** (show recurring unnamed faces above a small appearance
threshold, with a "show all" escape hatch). They are captured here and in the
handoff; fold them into ADR-0001's implementation.

## 5. Two dedicated deep-dive blocks

These are *not* ordinary feature work — each needs its own focused session with
the right tooling:

- **Scan performance (ADR-0006).** Root-cause why scans take 3–13 hours *even on
  local drives* (2–9 s/file is 10–50× too slow). Profile a *local* folder first
  to isolate the architecture problem from the Google-Drive streaming problem.
  Streaming is permanent — the fix must work while files stream (sample only a
  few frames), never by caching locally. Pairs with ADR-0005 so the cost is paid
  once and resumed, never repeated.
- **UI/UX overhaul (ADR-0012).** Clone a permissively-licensed (MIT/BSD/Apache)
  open-source file explorer as the new base; rebuild the surface on it; wire in
  the people-flow features with a **dedicated front-end agent** using a proper
  front-end design skill.

## 6. Implementation roadmap (the session-by-session order)

**ADR numbers are decision IDs, not build order.** The dependency-correct order
is these five blocks — one block ≈ one session, with a handoff between each:

- **Block 1 — Backend foundations.** ADR-0004 (off-drive catalog + content-hash
  thumbnails + offline badges) and ADR-0005 (write-ahead journal + auto-resume).
  Everything else reads/writes this index and needs safe, resumable operations,
  so this comes first.
- **Block 2 — Scan-performance deep-dive.** ADR-0006. *[DEEP DIVE]* Needs Block
  1's resumable infra; must precede running the always-on watcher at scale.
- **Block 3 — Identity engine.** ADR-0001 (+ confidence split + Q13 floor),
  ADR-0002 (bootstrap), ADR-0003 (dedup-in-flow), ADR-0010 (placement override +
  consistency check), ADR-0011 (video). The people-matching core.
- **Block 4 — People view & always-on.** ADR-0007 (person-centric tab), ADR-0008
  (nested Groups), ADR-0009 (watcher scope + effortless setup). Build with
  *deliberately minimal, functional* UI here — the polished surface is Block 5.
- **Block 5 — UI/UX overhaul.** ADR-0012. *[DEEP DIVE]* Clone the OSS explorer
  base and build the real, polished surface, wiring in all Block 3–4 features.

**Dependencies:** 1 → 2 (2 needs resumability); 3 needs 1 and benefits from 2; 4
needs 3 (needs Persons/Groups to display); 5 is last per the user's preference.

**Trade-off to decide at Block 4/5 boundary:** doing the UI overhaul last means
any interim feature-UI from Blocks 3–4 gets rebuilt on the new shell. Kept small
here by keeping interim UI minimal/functional. If avoiding that rework matters
more, the OSS-explorer shell clone (Block 5) can be pulled *earlier* so feature
UI is built once, in the right place. Flag this to the user at that point.

## 7. Tooling mandate (all blocks)

Per the user's explicit instruction, implementation agents MUST use the available
Claude Code skills, not improvise (full detail in ADR-0012):

- **Front-end/UI:** a dedicated front-end design skill (to be selected and
  installed from the marketplace at kickoff, with user approval — none is
  installed yet); a dedicated agent owns "make it beautiful." Figma skills are
  available if a design-tool flow is chosen.
- **Backend/system design:** `ponytail` (lean, no over-engineering),
  `codebase-design` (deep modules), `domain-modeling` (keep `CONTEXT.md`/ADRs
  current).
- **Verification:** `verify` + the project's `run-desktop` skill — drive the real
  app, never stop at typecheck.

## 8. Safety invariants (never violated by any of the above)

The project's non-negotiables still bind every block: never break/lose user
media; never delete without explicit confirmation; safety before performance; the
filesystem is the source of truth (the catalog is a rebuildable cache holding
nothing unique); moves are copy-then-delete; everything routes somewhere; every
operation is journaled; dry-run/preview before anything destructive; review
before commit; undo-friendly.
