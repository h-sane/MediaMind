# UI/UX overhaul is a first-class dedicated workstream; implementation must use the right tooling

The UI/UX is make-or-break for adoption: no amount of backend correctness matters
if the surface is broken and the flow is confusing. The current hand-built
Explorer clone has interactions that fall short of a real file explorer — basic
mechanics that come *free* in a proven base are limping here because they were
re-derived by hand. The UI/UX overhaul is therefore treated as its own dedicated
block (peer to the scan-performance block, ADR-0006), not a reskin tacked onto
feature work.

**Approach — ground-up rebuild on a cloned open-source file explorer (option C).**
The user chose to **clone a professional, permissively-licensed open-source file
explorer as the new base** rather than reskin or patch the hand-built shell.
Rationale (the user's, and sound): the basic mechanics — cut/copy/paste,
properties, context menus, keyboard navigation, fast rendering — already *work*
in a proven explorer, so we inherit them instead of re-deriving them badly, and
we learn professional patterns to apply to the new people-flow features layered
on top. A targeted rebuild (option B) was recommended but explicitly rejected:
from the user's experience, "what isn't broken is only the basic stuff that
shouldn't be broken anyway," so preserving the current shell has little value.

**Hard constraint — licensing.** The cloned explorer MUST be **MIT / BSD /
Apache-2.0** licensed, because MediaMind's app code is Apache-2.0. A GPL/copyleft
explorer may be *studied* for technique but its code must NOT be copied in.
Choosing a license-compatible base is a first-step gate of this block.

The people-flow features (ADRs 0001–0011) — currently not wired into any shell —
get built into this new base with a dedicated front-end agent.

## Implementation tooling mandate (applies to ALL of this blueprint)

Implementation agents working from these documents MUST use the available Claude
Code skills rather than improvising:

- **Front-end / UI:** use a dedicated front-end design skill. As of this
  blueprint, **no UI-beautification skill is installed** — one must be selected
  and installed from the Claude Code marketplace at implementation kickoff (with
  the user's approval). Figma skills (`figma-design-to-code`,
  `figma-generate-design`) are available if a design-tool-driven flow is chosen.
  Front-end work is owned by a **dedicated agent** whose sole job is to make the
  app genuinely beautiful, efficient, and correct — separate from the agent that
  defines the backbone.
- **Backend / system design:** `ponytail` (lean code, no over-engineering — reach
  for stdlib/existing utilities before new code), `codebase-design` (deep
  modules), `domain-modeling` (keep `CONTEXT.md` and these ADRs current as the
  model evolves).
- **Verification:** `verify` and the project's `run-desktop` skill — drive the
  real app end-to-end, never stop at typecheck.

**Division of labour:** one agent owns the backbone and direction — the endpoints,
data flow, and every decision captured in these ADRs plus the current app's real
state. A separate, dedicated front-end agent owns making it look and feel
excellent, working from that backbone.

## Block 5 kickoff — base selection (2026-08-31)

A comprehensive GitHub search (177 unique file-manager/explorer repos, ranked by
stars with license + language) established that **no mature, GUI-desktop,
Windows-Explorer-grade file manager exists that is both permissively licensed
(MIT/BSD/Apache) and on our React/web stack.** The best candidates each fail on
exactly one axis:

- `files-community/Files` (44.8k★, **MIT**) — the definitive modern Windows
  Explorer clone, but **C#/WinUI3** (Windows-only, foreign stack).
- `spacedriveapp/spacedrive` (38.9k★) — beautiful modern **React/Tailwind** UI,
  but **FSL** (source-available, not permissive) — study only.
- `aleksey-hoffman/sigma-file-manager` (6.5k★) — Tauri + **Vue**, custom
  non-permissive license.
- `kimlimjustin/xplorer` (5.7k★) — Tauri + React, but **AGPL-3.0** (copyleft).
- `warpdesign/react-explorer` (290★, MIT) — Electron + React, but an **older
  stack** (MobX + Blueprint.js) — a downgrade from ours.

**Decision (final): adopt `files-community/Files` as the new frontend base
(C#/.NET + WinUI 3).** After the initial base-selection above, the human
**removed the tech-stack constraint entirely** — React/Electron was never a
requirement (Claude chose it originally); the only requirements are speed,
efficiency, correctness, and a clean license. With the stack open, the choice is
unambiguous: `files-community/Files` (44.8k★) is the best mature, complete, fast,
permissively-licensed Windows File Explorer clone in existence, and every
modern *cross-platform* alternative is disqualified on licensing (Spacedrive =
FSL, Sigma = custom non-permissive, Xplorer = AGPL). So we **clone Files as the
MediaMind frontend** and build the people-flow features into it.

- **License:** Files is MIT with some MPL-2.0 files. MPL-2.0 is OSI-approved
  weak (file-level) copyleft, freely combinable with Apache-2.0; for an
  open-source project like MediaMind, compliance is trivial (modified MPL files
  stay open, which they already are). Acceptable despite being outside the strict
  MIT/BSD/Apache gate. (Verify the exact per-file split in the clone's LICENSE
  files at setup.)
- **Backend unchanged:** the Python FastAPI face-recognition / dedupe engine
  stays exactly as-is; the WinUI app calls it over localhost HTTP just as the
  Electron app did. All the safety-critical Python pipeline is untouched.
- **Consequence — Windows-only for now:** WinUI 3 / Windows App SDK is
  Windows-only. This matches the project's stated Windows-first priority and the
  user's platform. If cross-platform later becomes a hard requirement, that is a
  future pivot; it does not gate Block 5.
- **The current Electron/React `app/`** is superseded and will be retired once
  the Files-based frontend reaches parity; it is not deleted pre-emptively.
- **Toolchain:** the machine had no .NET SDK / Visual Studio; the C# toolchain
  (.NET SDK + Windows App SDK + build workloads) is installed at kickoff via
  winget. Windows 11 build 26200 supports WinUI 3.

The React-rebuild path (former "option A") is superseded by this decision.

**Tooling set up at kickoff:** the `frontend-design` skill (Anthropic-authored,
`claude-plugins-official`) is installed at project scope — it enforces
distinctive, production-grade UI and a quality floor (responsive, keyboard focus,
reduced motion), and is the mandated design authority for all Block 5 front-end
work. A dedicated front-end agent leads the integration design.
