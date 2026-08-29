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
