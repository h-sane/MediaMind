# MediaMind Mobile — Technical Specification

Companion to `STACK.md`. Describes the on-device architecture, the inference
pipeline, the data model, and how the desktop engine's guarantees are preserved
on the phone.

---

## 1. Architecture (all on-device)

```
┌──────────────────────────────────────────────────────────┐
│  Jetpack Compose UI  (People · Library · Clean · Search)   │
└───────────────┬───────────────────────────┬───────────────┘
                │ StateFlow / events         │
        ┌───────▼────────┐          ┌────────▼─────────┐
        │  Scan service   │          │  Search service   │
        │ (WorkManager)   │          │  (LLM + Whisper)  │
        └───────┬────────┘          └────────┬─────────┘
                │                             │
   ┌────────────▼─────────────┐   ┌───────────▼────────────┐
   │  Inference layer          │   │  On-device LLM (Gemma) │
   │  ORT Mobile + QNN (NPU)   │   │  Whisper Tiny (voice)  │
   │  • BlazeFace detect       │   └────────────────────────┘
   │  • MobileFaceNet embed    │
   └────────────┬─────────────┘
                │ embeddings + boxes
   ┌────────────▼─────────────┐   ┌────────────────────────┐
   │  Clustering + dedupe      │   │  SQLite index          │
   │  (union-find / greedy)    │◄──┤  photos, faces(BLOB),  │
   └───────────────────────────┘   │  persons, dupes        │
                                    └────────────────────────┘
                MediaStore  ──►  (source of truth; never mutated without consent)
```

No component makes a network call in the serving path.

---

## 2. Scan pipeline

Runs as a WorkManager job; progress is streamed to the UI (the scanning screen in
the prototype is the real contract — percent, current stage, "0 bytes sent").

1. **Enumerate** media via `MediaStore` (respecting the media-first default:
   images + video first). Store `photo(id, uri, taken_at, size, folder)`.
2. **Detect** faces per image with BlazeFace on the NPU → bounding boxes.
3. **Embed** each face crop with MobileFaceNet → 512-d INT8/FP16 vector.
4. **Cluster** embeddings into persons (see §4).
5. **Dedupe** in parallel: perceptual hash (dHash/pHash) buckets + exact SHA for
   byte-identical files → duplicate groups with a "best copy" pick (highest
   resolution / largest / sharpest).
6. **Persist** everything to SQLite. Re-scans are incremental (only new/changed
   `MediaStore` rows).

Per-file try/except: one undecodable file never aborts the scan (desktop V0
invariant). Files that fail decoding are recorded, never silently dropped.

---

## 3. Data model (SQLite)

```sql
photo   (id, media_uri, folder, taken_at, width, height, bytes, phash, sha, scanned_at)
face    (id, photo_id, bbox, embedding BLOB, quality, person_id NULL)
person  (id, name NULL, cover_face_id, created_at)          -- name NULL = unnamed cluster
dupe    (group_id, photo_id, is_keeper)                     -- keeper chosen, never auto-deleted
action  (id, kind, payload, created_at, undo_token)         -- audit trail / undo
```

`action` is the manifest: every consolidate/dedupe/export is logged with enough
state to undo the last one (desktop invariant #7).

---

## 4. Clustering

Greedy online clustering over cosine similarity:

- New face joins the nearest person whose centroid similarity ≥ `MATCH` (start
  ~0.5 for *suggestions*, ~0.9 for *auto-merge* — mirrors the desktop's
  suggestion vs auto-merge split).
- No match → new person, initially **unnamed** (surfaced under "Needs a name").
- Centroids updated incrementally. A later "consistency check" pass re-scores
  members and flags outliers for review (ported from desktop Block-4 UI).

`ponytail: greedy single-pass clustering; upgrade to HAC/rank-based merge only if
cluster quality is visibly poor on real libraries.`

---

## 5. Search (offline)

- **Text:** query → Gemma 2B parses intent into a structured filter
  `{person?, scene?, date_range?, media_type?}` → applied over SQLite. Person
  names resolve to `person_id`; scene terms hit the stretch tag model if present.
- **Voice:** Whisper Tiny transcribes on-device → same path.
- No embeddings or transcripts leave the device.

---

## 6. Safety invariants (carried over from desktop, non-negotiable)

1. **MediaStore is the source of truth**; SQLite is a rebuildable index.
2. **No deletion without explicit confirmation.** "Clean" always shows a review
   screen; the best copy is kept; nothing is removed until the user confirms.
3. **Consolidate/export are copy-based**, never destructive moves of originals.
4. **Everything routes somewhere** — no face or photo silently skipped;
   ambiguous ones go to "Needs a name" / a review list, visibly.
5. **Audit + undo:** every action logged; the last organize action is undoable.
6. **Cause and effect:** every backend action has a visible UI effect (progress,
   toast, updated count) — a silent success is treated as a bug.

---

## 7. NPU / delegate strategy

- Primary: ONNX Runtime Mobile with the **QNN EP** → Snapdragon NPU.
- Fallback chain: QNN → NNAPI → GPU (XNNPACK) → CPU, chosen at startup by a
  one-time capability probe. The app runs on any Android; it *shines* on the
  loaner's NPU (the HackTracker "on-device AI" signal).
- Benchmark hook logs per-stage latency + which delegate served it — useful for
  the technical-depth pitch.
