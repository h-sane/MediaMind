---
name: run-desktop
description: Build, run, and drive the MediaMind Electron desktop app on Windows. Use when asked to start the desktop app, take a screenshot of it, or interact with its UI.
---

MediaMind is an Electron + React desktop app (`app/`) over a Python FastAPI
engine (`backend/`) spawned by the Electron main process. For agent/automated
use, drive it via the Playwright `_electron` REPL at `app/scripts/driver.mjs`.
No xvfb/DISPLAY setup needed — this runs on native Windows with a real
session.

All paths are relative to `app/`.

## Build

The driver launches the **built** app (`out/main/index.js`, per
`package.json`'s `main` field) — rebuild after any source change:

```bash
cd app
npm run build   # electron-vite build; ~15s
```

## Run (agent path)

`playwright-core` is a devDependency of `app/`. `driver.mjs` lives inside
`app/scripts/` specifically so Node's ESM bare-specifier resolution (which
walks up from the *importing file's own location*, not the process cwd)
finds `app/node_modules/playwright-core` — running it from anywhere else
(e.g. copied out to `.claude/`) fails with `ERR_MODULE_NOT_FOUND`. If you
ever need a one-off custom script instead of the REPL, it must also live
inside `app/` for the same reason — write it as `app/.tmp-*.mjs`, run it,
delete it when done; never commit it.

The driver queues commands and runs them strictly one at a time (each line
waits for the previous command's promise to resolve) and waits for that
queue to fully drain before exiting, even on a fast EOF — so it's safe to
pipe or redirect a whole command sequence in one shot without manual pacing:

```bash
cd app
echo -e "launch\nss initial\nquit" | node scripts/driver.mjs
# or, for a longer scripted sequence:
node scripts/driver.mjs < commands.txt
```

Screenshots land in `app/.driver-shots/` (override: `SCREENSHOT_DIR`).

### Commands

| command | what it does |
|---|---|
| `launch` | launch the built app, wait for the window |
| `ss [name]` | screenshot → `.driver-shots/<name>.png` |
| `click <css-sel>` | click element (via DOM, not coords) |
| `click-text <text>` | click first button/a/[role=button] containing text |
| `focus <css-sel>` | explicitly move keyboard focus (use before `type` on an `<input>` — see Gotchas) |
| `type <text>` / `press <key>` | keyboard input |
| `wait <css-sel>` | wait for element, 10s timeout |
| `sleep <ms>` | pause N milliseconds (prefer `wait` on a selector when possible; use this for async work with no DOM signal to wait on, e.g. a mutation round-trip) |
| `eval <js>` | evaluate in the page, print JSON |
| `text [css-sel]` | print innerText |
| `windows` | list all windows |
| `quit` | close app, exit |

## Run (human path)

```bash
cd app
npm run dev   # electron-vite dev with hot reload — opens a window
```

## Gotchas

- **`click-text` matches the nav-pane tree row before a same-named content-pane
  tile** — the nav pane renders first in the DOM (`ExplorerShell.tsx`:
  `<NavigationPane /><ContentPane />`), so a bare text match hits the tree,
  not the grid tile. Clicking the tree row still navigates correctly (it
  calls the same `navigate()`), but if you specifically need the content-pane
  tile, scope the query with `:not(aside *)` or similar.
- **`click`-ing a native `<input>` via `element.click()` doesn't reliably move
  keyboard focus** in this Electron/Chromium context — a `type` right after
  a `click` on a search box or similar can type nothing. Use `focus <sel>`
  right before `type` instead; `click`'s side effect is fine for `<button>`
  elements.
- **A `type` command's duration scales with text length**
  (`page.keyboard.type(text, {delay: 30})` ≈ 30ms × character count) — a long
  path can take a couple of seconds. The driver's own command queue only
  guarantees ordering between commands, not a minimum wait after `type`
  finishes before the *next* command starts doing something meaningful (e.g.
  asserting on the typed value) — if a follow-up check depends on the type
  having visibly landed, give it a moment or re-check with `wait`.
- **First folder listing after opening a location is often incomplete** —
  subfolders whose "has media below" state is still unknown come back and
  get filled in over ~1-3s as the backend's background walker resolves them
  (see `core/media_index.py`). Wait ~2-3s after navigating before screenshotting
  if you need the final state.
- **Backend takes a few seconds to boot** — wait ~5-6s after `launch` before
  the first real interaction; earlier than that, `/v1/fs/*` calls will fail
  and the content pane shows an error state.
