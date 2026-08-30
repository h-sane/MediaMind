# Scan performance is a dedicated block; streaming is a permanent constraint

Scan throughput is treated as its own investigation-and-planning effort, not a
quick tune inside the people-flow design. Two independent problems compound:
(1) media streamed on-demand from Google Drive (through Cryptomator) forces a
download per file, and (2) the scan pipeline is too slow **even on local fixed
drives** — seconds per file where it should be a fraction of a second. Problem
(2) is an architecture issue to root-cause, and it is not caused by the drive.

**Hard constraints (firm regardless of what the investigation finds):**

- **Streaming is permanent.** The user relies on Google Drive precisely because
  local storage is scarce; switching cloud files to "available-offline" local
  caching is not an option. Any solution must work while files stream.
- **Scan while streaming, with minimal reads.** Face detection should sample only
  a few frames — 2–3 snapshots even for a long video — so scanning a streamed
  file pulls the least bytes possible, ideally *during* the stream rather than
  after a full download.
- **Robust across all drive types** — streamed cloud, locally-cached, and plain
  fixed C:/D: — without assuming any of them.
- Pairs with ADR-0005: whatever the scan costs, it is paid **once** and
  auto-resumed across sessions, never repeated.

**Why record it now:** these constraints bound the eventual design no matter what
the root-cause investigation concludes, and the obvious suggestion ("just cache
locally") is explicitly ruled out.

**Status:** constraints accepted; a dedicated root-cause investigation +
optimization plan is pending. That investigation must attribute where the
per-file seconds actually go — decode vs. model inference vs. per-file overhead
(stat/hash/DB) vs. video frame extraction vs. lack of concurrency — on a *local*
folder first (to isolate the architecture problem from the streaming problem),
and check whether already-scanned files are being needlessly re-scanned, whether
inference runs on CPU vs GPU, the detector's input resolution, how many frames
are sampled per video today, and whether decode/inference is parallelised across
cores.

---

## Investigation findings (Block 2, session 61)

Profiled on a **local** folder (`test/Unsorted`, real portraits) with the
production venv (`faces-env`), buffalo_l, 8-core CPU. Isolates the architecture
problem from Google-Drive streaming as the ADR requires.

| Cost component | Measured |
|---|---|
| Model load (`prepare()`), once per scan | 2.1 s |
| Decode per image (`cv2.imread`) | ~26 ms |
| **Detect + embed per frame (CPU)** | **~310–385 ms** ← 90%+ of per-file time |
| Per image, end to end | ~0.34 s |
| Per 15-frame video (inference only) | **~4.7 s** + seeks |

**Where the seconds go:** almost entirely CPU model inference. Decode, hashing,
and DB overhead are negligible by comparison. The embed (ArcFace `w600k_r50` at a
fixed 112×112) is a hard per-face floor; detection (`det_10g`) scales with
`det_size` (640→320 cut only 385→235 ms because the embed floor is fixed).

**Answers to the ADR's mandated questions:**

- **Re-scan skipping — already correct.** Content-hash cache (`lookup_file_cache`
  + `get_cached_faces`) skips both hashing and detection for unchanged files
  (V4 Phase 1). Not a source of waste.
- **CPU vs GPU — CPU only.** The venv's onnxruntime exposes only
  `CPUExecutionProvider` (no CUDA/DirectML build installed); `ctx_id=-1`. This is
  the single largest factor in absolute per-frame cost.
- **Detector resolution — 640×640.** Lowering it speeds detection but risks
  missing small faces in group shots and doesn't touch the embed floor; a
  recall-risky, low-value knob. Left at 640.
- **Frames per video — flat 15 (`DEFAULT_VIDEO_FRAMES`), 8 for GIF.** This is the
  dominant driver of the "seconds per file" on video and directly contradicts
  ADR-0011 (progressive early-exit; ~2–3 for the common single-subject clip,
  ~10 hard cap, never more). **This is the biggest local-scan lever.**
- **Parallelised across cores — within a call, yes; across files, no.** ONNX
  Runtime already spreads one inference across `cpu_count − 2` intra-op threads
  (`_apply_cpu_budget`), so the sequential per-file loop in `detect_batch` is
  *not* leaving cores idle. Process-level per-file parallelism would oversubscribe
  those same cores and reload the ~300 MB model per worker — net loss on CPU.
  Hashing is already thread-parallel; detection correctly is not. So "lack of
  concurrency" is **not** the bottleneck it appears to be.

## Optimization plan (ranked by impact ÷ effort)

1. **Cut the flat video-frame cap 15 → 10 now (landed this session).** Safe,
   ratified by ADR-0011's "never more than ~10", one constant, no accuracy loss
   to the common case. ~33% off every large video immediately. The full win —
   progressive early-exit that reaches 2–3 on single-subject clips — needs the
   identity engine to track "distinct people seen" and is therefore **Block 3
   (ADR-0011)**, not this block.
2. **GPU execution provider — highest per-frame ceiling, hardware/dependency
   gated.** Installing `onnxruntime-directml` (broad Windows GPU support) or
   `onnxruntime-gpu` (CUDA) could cut the ~310 ms embed+detect floor by an order
   of magnitude. Needs a compatible GPU and a dependency swap; must fall back to
   CPU cleanly. A user decision (their hardware), not an automatic change.
3. **Optional "fast scan" model pack (buffalo_s).** Smaller recognition net →
   lower embed floor, lower accuracy. Offer as an opt-in speed/accuracy trade,
   not the default. Block 3+ territory alongside the confidence model.

Detector-size reduction and per-file process parallelism were **considered and
rejected** for the reasons in the findings above.
