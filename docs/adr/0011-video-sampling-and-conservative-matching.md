# Video: separate sampling for dedup vs face-rec; conservative auto-matching

Videos use **two different sampling strategies** for two different jobs, and video
face matches are treated **conservatively** (biased toward human review).

**Duplicate detection** fingerprints a video from a small fixed number of
snapshots (2–3), enough to compare it against other videos (whole-video
duplicates; sub-clip detection remains deferred per ADR-0003).

**Face recognition** uses **progressive sampling with early-exit, capped by a
budget:** sample frames spread across the video; after each, update the running
set of distinct people seen; **stop early when that set stops growing** across a
few consecutive frames (the "cast" has settled — the cheap common case for a
video that is *about* one or two people); otherwise continue to a hard frame-
budget cap (a short clip naturally takes ~2–3, a long video up to ~10, never
more). Crucially, it does **not** stop at the first named person found — that
would miss co-appearing people; the stop signal is "stopped finding anyone new."

**Conservative matching:** video face-rec is frequently low-confidence, so unless
the system is near-certain, a video's person match routes to **Suggestions** for
the user to confirm visually rather than being auto-joined. Exception: a video
saved directly into a Person's folder is confirmed by placement (ADR-0010) and
skips review.

**Why:** minimise bytes pulled from streamed cloud files (early-exit means easy
videos cost 2–3 reads, not the full budget); accept that absence of a face can
never be *proven* by sampling (a brief appearance in a long video can be missed —
a bounded, understood risk); and lean on human visual judgement where the model
is weak.
