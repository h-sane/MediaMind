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
