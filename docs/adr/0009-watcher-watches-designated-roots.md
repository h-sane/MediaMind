# The watcher watches designated roots (auto-suggested inboxes), not the whole system

The always-on watcher watches a user-designated set of **roots** — the user's
organized library roots plus the "inbox" folders where new files land (Downloads,
Telegram, WhatsApp, etc.) — not the entire filesystem. Inboxes are auto-detected
and suggested. Anything outside the watched roots is ignored.

**Why not whole-system:** even though person-matching is curated (only named
people count), the watcher still has to *decode every image it sees* to check for
those people. Pointed at all of C:, it grinds through Windows icons, browser
caches, app assets, memes, and screenshots — thousands of files that will never
contain a tracked person — each paying the decode cost the performance branch is
already fighting. Files only ever *land* in a handful of places, so watched-roots
gives the same practical coverage for a tiny fraction of the work.

**Consequences:**
- **Setup UX is a hard requirement, not a nicety.** The current folder-by-folder
  selection friction is a named blocker. Inboxes must be auto-detected and
  suggested, added with a single tap, and the watched set shown as a clear,
  plain-language list. Effortless setup is part of the feature.
- Resource behaviour while the user is actively working (throttling, pausing
  under load / on battery) is handled in the scan-performance block (ADR-0006),
  not here.
