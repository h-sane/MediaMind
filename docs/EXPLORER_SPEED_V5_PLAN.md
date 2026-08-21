# Explorer Speed V5 — Whole-Stack Performance Audit & Plan

Status: **AUDIT + PLAN. Nothing implemented.** This is a full-stack performance
audit of the Explorer shell — every layer from the React render tree down to
Win32 syscalls — measured against how Windows File Explorer actually works.
Written against real code at commit `4c958c3`.

The goal Hussain set: **milliseconds-fast, everywhere — not just the one path I
named.** This document treats the slowness as systemic, because it is. There
are ~20 distinct problems across 6 layers; fixing only the media path (the
first draft of this plan) would have left most of them standing.

---

## 0. How Windows File Explorer is fast — the exact techniques

These are the concrete mechanisms; each maps to a gap below.

1. **MFT-batched enumeration.** Explorer lists a directory with
   `FindFirstFileEx(FindExInfoBasic, …, FIND_FIRST_EX_LARGE_FETCH)`, reading
   entries in large batches straight from the NTFS Master File Table. Name,
   size, timestamps, and attributes arrive *with* the enumeration — **zero
   extra `stat()` per file.**
2. **Persistent thumbnail cache (`thumbcache_*.db`).** A per-user, memory-mapped
   database under `%LocalAppData%\Microsoft\Windows\Explorer`, split into fixed
   sizes (16/32/48/96/256/768/1024/1280/1920/2560). A thumbnail is computed
   **once** and reused across folders, sessions, and reboots.
3. **Cache-first, async-fill.** Explorer asks `IShellItemImageFactory::GetImage`
   with `SIIGBF_INCACHEONLY` first — an instant hit or nothing. On a miss it
   shows the generic file-type icon *immediately* and computes the real
   thumbnail on a **background worker pool**, prioritized to visible items and
   **cancelled** when you scroll past them.
4. **Embedded-thumbnail fast path.** For JPEGs the photo thumbnail provider
   reads the ~160 px thumbnail embedded in the file's EXIF (APP1) block — a few
   KB, **no full-image decode.** Only larger requests trigger a full decode.
5. **Size quantization.** Explorer only ever requests one of the cache's fixed
   sizes matched to the current icon view. It never decodes a bespoke size for a
   48 px tile, and holds decoded bitmaps **only for near-visible items.**
6. **Streaming / memory-mapped opens.** The Preview Pane and Photos/Media Player
   open a **file handle** and decode progressively: one-frame seek for a video's
   first paint, then stream. There is **never** a "read the whole file into
   memory first" step for a local file.
7. **UI thread never blocks.** Enumeration, property retrieval, and thumbnailing
   all run on background (STA/MTA) threads; the list is virtualized so only
   visible items are realized.

MediaMind currently violates 1, 3, 4, 5, and 6, and does 2 only partially.

---

## 1. Layer-by-layer findings (every gap, ranked within layer)

### Layer A — Media transfer (renderer ↔ backend)  ← biggest felt cost

| # | Finding | Evidence | Technique it breaks |
|---|---------|----------|--------------------|
| A1 | **Every media byte is downloaded into a `Blob` before display** — thumbnails, previews, *and* full video/image. `fetch → res.blob() → createObjectURL`. No HTTP range, no progressive/streaming decode. A 300 MB video is fully transferred + held in RAM before frame 1. | `client.ts` `fs.rawUrl/previewUrl/thumbnailUrl`; `hooks.ts` all `*Url` hooks | #6 streaming |
| A2 | **CSP `media-src 'self' blob:`** forbids pointing `<video>`/`<audio>` at the backend origin — the blob path is the *only* legal path today. | `renderer/index.html` | #6 |
| A3 | **Blob URLs are revoked on unmount** → the browser can never cache a thumbnail by URL. Every folder revisit re-fetches and the backend re-encodes the HTTP body, even on an L2 cache hit. | `hooks.ts` cleanup in every `*Url` hook | #2/#3 cache reuse |
| A4 | **Always requests `size=256`** regardless of the 36–128 px tile it's drawn at → over-decode, over-transfer, over-memory (oversized bitmaps in both caches). | `FileThumbnail` default; `IconGridView` passes no size | #5 quantization |

### Layer B — Request pipeline (backend HTTP)

| # | Finding | Evidence | Fix technique |
|---|---------|----------|--------------|
| B1 | **Two stacked `BaseHTTPMiddleware` layers on every request** (`TokenAuthMiddleware` + the `@app.middleware("http")` request logger). BaseHTTPMiddleware runs each endpoint in a sub-task over anyio memory streams — per-request overhead *and* it can buffer/def eat streaming responses (hurts A1's fix too). At hundreds of thumbnail requests per folder this compounds. | `app.py:129-143`, `security.py` | Pure-ASGI middleware or auth-as-dependency; gate the logger to debug |
| B2 | **`resolve_os_path()` runs 3 filesystem syscalls per media request before the cache is consulted**: `Path.resolve()` (slow on Windows — opens the file to canonicalize), `.exists()`, *and* `app_data_dir().resolve()` (re-resolved every call). A grid of 300 tiles = ~900 pure-validation syscalls. | `pathsafe.py:33-41`, called by every `/fs/thumbnail|preview|raw|metadata` | Cache `app_data_dir().resolve()` at import; validate with `os.path.normpath` + denylist prefix check; drop the redundant `.exists()` (the decode's own `open` reports missing files) |
| B3 | **HTTP/1.1, 6-connection cap**, no response prioritization. Fine *if* requests are cheap and native `<img>` schedules them — bad when each is an expensive blob fetch with no priority. | uvicorn defaults | Native `<img>` + `fetchpriority` (Layer A fix) makes the 6 slots serve visible-first |

### Layer C — Directory enumeration (backend)

| # | Finding | Evidence | Fix technique |
|---|---------|----------|--------------|
| C1 | **`list_dir` opens a fresh SQLite connection *per subfolder*** through `media_index.check_full → _lookup` (connect + `PRAGMA journal_mode=WAL` + query + close, each call). A drive root with 40 folders = 40 connect/close cycles per listing — and the listing **re-runs every 1.5 s** while walks are pending (C3). | `fs.py:126`, `media_index.py:102-166` | One connection per request, reused across all subfolders; batch as a single `WHERE path IN (…)`; keep a long-lived read connection on `app.state` |
| C2 | **Pydantic model built per entry** (`BrowseFileOut`/`BrowseFolderOut`) for the whole folder. For 10k-file folders this is real allocation/validation cost on one thread. | `fs.py:130-165` | `response_model=None` + hand-built dicts, or `model_construct()` to skip validation on trusted internal data |
| C3 | **`has_media` polling re-fetches the entire listing every 1.5 s** until every subfolder's background walk finishes — repeating all of C1/C2 several times on a fresh drive. | `hooks.ts:235-240` `useBrowseDir` | A dedicated tiny `GET /fs/has-media?paths=…` that polls *only* unresolved folders; the main listing is fetched once |
| C4 | Per-entry `stat()`/`stat_facts()` — **not a real cost on Windows**: `os.scandir` caches the stat from the enumeration, so `entry.stat()` adds no syscall, and `st_file_attributes` is read from that cache. Noted so it isn't "fixed" pointlessly. | `fs.py`, `file_facts.py` | none — leave it |

### Layer D — Decode (backend, CPU)

| # | Finding | Evidence | Fix technique |
|---|---------|----------|--------------|
| D1 | **No embedded-EXIF-thumbnail fast path** — full-frame DCT decode even for a 96 px tile of a JPEG that already contains a 160 px thumbnail. | `thumbnails.py` `_generate_thumbnail_jpeg` | Read APP1 EXIF thumbnail first for `size ≤ 256` (Explorer technique #4); fall through to `_draft_decode_bgr` on miss |
| D2 | **Cold decode is GIL-bound.** cv2/PIL release the GIL during the C decode, so the anyio threadpool gives *partial* parallelism, but Python-level orchestration (draft setup, numpy view, imencode) serializes. No process pool. | `fs.py` sync `thumbnail`, `thumbnails.py` | Bounded `ProcessPoolExecutor` sized to CPU count for decode — **measure after D1/prewarm first** |
| D3 | Video thumbnail = `cv2.VideoCapture` first frame; per-file codec init is heavy cold. Cached, so only first-touch. | `thumbnails.py` `_first_frame` | Acceptable once prewarm (E) covers it; don't rewrite |

### Layer E — Warming & caching strategy

| # | Finding | Fix technique |
|---|---------|--------------|
| E1 | **No background pre-warm of a just-opened folder.** V4 ingest warms *registered libraries*, but ad-hoc drive/folder browsing decodes purely on demand. This is the difference between Explorer's cache-first-async-fill and our decode-on-scroll. | On `/fs/list`, enqueue a bounded background task to warm thumbnails for the listed media at the current tier size, visible-order first (Explorer technique #3). Reuses the existing L1/L2 cache. |
| E2 | L2 disk cache is good (mirrors thumbcache) — **keep.** The `repr(key)`→sha1 disk key and `os.utime` LRU are fine. | none |

### Layer F — React render tree (renderer)

| # | Finding | Evidence | Fix technique |
|---|---------|----------|--------------|
| F1 | **A full Radix `ContextMenu.Root` wraps every tile.** One context/portal machine per visible tile — heavy mount and heavy per-render. | `IconGridView` `Tile`, wrapped in `ExplorerContextMenu` | **One** context menu at the grid root; resolve the target from the right-clicked element's `data-entry-path`. This is how Explorer (and every fast web grid) does it |
| F2 | **No tile is `React.memo`'d** (0 across all content views). Any selection/focus change re-renders *all* visible tiles, each re-instantiating F1's Radix tree. | grep: 0 `memo` in `content/*.tsx` | `React.memo` tiles with primitive props; select `isSelected` per-tile from the store instead of threading a recomputed boolean from the parent |
| F3 | **`useDirectoryListing` re-sorts + re-filters the entire entries array on every search keystroke** (`searchQuery` is a memo dep feeding a full `.sort()`). | `useDirectoryListing.ts:249-289` | Debounce the search box; split the stable sort (memoized on data+sortKey) from the cheap filter; don't re-sort on every character |
| F4 | **One `IntersectionObserver` per tile** (`useNearViewport`) — churned on every scroll-recycle. | `Thumbnail`/`FileThumbnail` | Native `<img loading="lazy">` (Layer A) deletes all of them |
| F5 | **Grouped branch of `IconGridView` is un-virtualized** — renders every DOM tile when Group-by is on (known TODO; `GroupedVirtualGrid` already exists to reuse). | `IconGridView.tsx:225` | Reuse `GroupedVirtualGrid`; adapt marquee to windowing |

### Layer G — Memory

| # | Finding | Fix |
|---|---------|-----|
| G1 | Whole-file video/image blobs held in renderer RAM (A1). | Streaming (A) eliminates — the file is never fully in JS memory |
| G2 | 256 px bitmaps for 36 px tiles in both the 128 MB L1 and the browser image cache. | Quantization (A4) |

---

## 2. The plan — phased, each independently shippable & verifiable

Ordering is by **felt impact per unit of work**. Phases 1–4 are where the app
goes from "sluggish" to "native-feeling." Several phases are net *deletions*.

Project rules: work on `development`; per-phase handoff to `.claude/handoffs/`;
merge to `main` only after typecheck + build + `pytest` pass; verify each phase
live in the `test` folder before moving on.

### Phase 1 — Stream media; kill the blob path *(fixes A1, A2, A3; ~net deletion)*
- Main process: inject `X-MediaMind-Token` on all `http://127.0.0.1:*` requests
  via `session.defaultSession.webRequest.onBeforeSendHeaders` — so plain
  `<img>`/`<video>` carry auth; header-only middleware unchanged; token never in
  a URL.
- CSP: add `http://127.0.0.1:*` to `media-src`.
- `MediaViewer`: point `<video>/<audio>/<img>` `src` **directly** at
  `/fs/raw` / `/fs/preview` URLs. Starlette `FileResponse` serves Range → video
  streams and seeks.
- Delete the `raw/preview` blob hooks + client methods; add a `fsMediaUrl()`
  string builder.
- **Verify:** open a large D:-drive video — first frame < 2 s, scrub works.

### Phase 2 — Native `<img>` thumbnails *(fixes A3, A4, F4; net deletion)*
- Render `<img src={fsThumbUrl(path,size)} loading="lazy" decoding="async">`
  straight at `/fs/thumbnail`. Browser now does viewport-fetch, URL cache
  (instant revisits), the connection scheduler, and priority natively.
- Delete the thumbnail blob hooks + `useNearViewport` usage.
- Quantize `size` to the icon tier (small→96, medium→128, large/xl→256).
- **Verify:** scroll a 2000-file folder; revisit → instant from cache.

### Phase 3 — Backend request-path diet *(fixes B1, B2)*
- Replace `TokenAuthMiddleware` with pure-ASGI middleware (no BaseHTTPMiddleware
  sub-task); gate `log_requests` behind debug or make it pure-ASGI too.
- `resolve_os_path`: cache `app_data_dir().resolve()` at import; validate via
  `os.path.normpath` + denylist prefix; drop the redundant `.exists()`.
- **Verify:** time `/fs/thumbnail` cache-hit latency before/after (target: sub-ms
  server time on a hit).

### Phase 4 — Enumeration diet *(fixes C1, C2, C3)*
- `media_index`: one long-lived read connection on `app.state` (WAL, `check_same_thread=False` with a lock, or a per-request connection reused for all subfolders); batch subfolder lookups into a single query.
- New `GET /fs/has-media?paths=…`; `useBrowseDir` fetches the listing **once**
  and polls only unresolved folders through the new endpoint.
- Optional: `model_construct()` / `response_model=None` for the listing.
- **Verify:** open a 40-folder drive root — one listing fetch, no 1.5 s full
  re-fetches; large-folder open time.

### Phase 5 — Background thumbnail pre-warm *(fixes E1)*
- On `/fs/list`, enqueue a bounded warm task for listed media at tier size,
  visible-order first. Cache-first-async-fill, Explorer-style.
- **Verify:** first visit to a cold 500-photo folder fills visibly top-down with
  no scroll stalls.

### Phase 6 — React render weight *(fixes F1, F2, F3, F5)*
- Collapse per-tile context menus into one grid-level menu keyed off
  `data-entry-path`.
- `React.memo` tiles; per-tile store selection selector.
- Debounce search; split sort from filter.
- Virtualize the grouped branch via `GroupedVirtualGrid`.
- **Verify:** Ctrl+A and fast scroll on a 2000-file folder stay at 60 fps
  (DevTools Performance).

### Phase 7 — Decode fast paths *(fixes D1, then D2 only if measured)*
- Embedded-EXIF thumbnail fast path for `size ≤ 256`.
- **Measure** cold-folder decode with `bench_decode.py`; only if still
  CPU-bound, add a bounded `ProcessPoolExecutor` for decode.
- **Verify:** cold thumbnail decode time per image before/after.

---

## 3. What NOT to touch
- L2 on-disk thumbnail cache (right design; mirrors thumbcache).
- `_draft_decode_bgr` (fast; Phase 7 only adds a faster path in front).
- Image preview capping at 2560 px (correct first paint for stills).
- tanstack row virtualization.
- Per-entry `stat` in `list_dir` (free on Windows via scandir — C4).

## 4. Sequencing note
Phases 1–2 remove the single worst offender (whole-file blobs) and are mostly
deletions — do them first and re-measure. Phases 3–4 attack per-request and
per-listing overhead that touches *every* interaction. 5–7 are the polish that
takes it from "fast" to "milliseconds." Re-measure after each; the later phases
may prove unnecessary once the earlier ones land.
