# MediaMind Mobile — Software / Product Specification

What the app *is* to a user, the screens, the flows, and what's in scope for the
**screening submission** vs. the **30-hour build**.

---

## 1. One-liner

**MediaMind is the private, on-device AI that organizes your camera roll by the
people in it** — finds everyone, clears duplicates, frees space, and answers
plain-language searches, without a single photo ever leaving the phone.

## 2. Who / why

- **Audience:** anyone with a phone full of years of unsorted photos who is
  uneasy about uploading their family's faces to a cloud service.
- **Job:** turn a chaotic camera roll into something organized by *people* and
  free of clutter — privately.
- **Wedge vs. Google Photos:** structurally cannot be matched — MediaMind does
  face grouping and search **on-device**, so it's genuinely private, works
  offline, and costs no cloud storage.
- **Track fit:** Open Innovation (local model at core) or Smart Living
  (everyday convenience). On-device model = rubric bonus + the 15% creative-
  phone-use score (camera, voice, NPU).

## 3. Core screens (all in the prototype)

| Screen | Purpose | Flagship feature it surfaces |
|---|---|---|
| **Onboarding** | The privacy thesis + single CTA "Scan my photos" | On-device / NPU badge, "nothing leaves your phone" |
| **Scanning** | Cause-and-effect: live progress, "0 bytes sent" | On-device inference, privacy |
| **People** | The home. People clusters; "Needs a name" first, then named | Face grouping (the differentiator) |
| **Person detail** | One person's photos + Consolidate / Export | Organize-by-person, private export |
| **Library** | Media-first grid + conversational + voice search | NL/voice search, media-first doctrine |
| **Clean** | Reclaim-space hero, duplicate groups, keep-best | Duplicate detection, safe delete |

Bottom nav order = information architecture: **People, Library, Clean, Search** —
flagship features are top-level, never buried (MediaMind UX doctrine).

## 4. Key flows

1. **First run:** Onboarding → grant photo access → Scan (live progress) → lands
   on **People** with clusters ready, most as "Needs a name".
2. **Name a person:** tap an unnamed cluster → name it → all their photos inherit
   the name; future scans auto-assign confident matches.
3. **Organize a person:** Person detail → **Consolidate** (gather copies into one
   place) or **Export** (share/back up) — copy-based, never destructive.
4. **Free space:** **Clean** → review duplicate groups (best copy pre-selected) →
   confirm → space reclaimed. Nothing deleted without confirmation.
5. **Find a photo:** Library search bar or mic → "Mom at the beach last summer" →
   on-device LLM/Whisper → results. Fully offline.

## 5. Non-negotiable product rules (from MediaMind doctrine)

- **Media-first by default**; a visible toggle shows all files.
- **Every backend action has a visible effect** (progress, toast, updated count).
- **No deletion or destructive move without explicit confirmation**; originals in
  `MediaStore` are never mutated silently.
- **Model licenses surfaced before download.**

## 6. Scope

**Screening submission (due Sept 8, 12:00 IST) — priority: looks great, need not
be functional:**
- The interactive prototype (`mobile/prototype/index.html`, published as an
  Artifact) covering all six screens + the scan animation.
- This doc set (stack, tech spec, software spec, implementation plan).
- A short written pitch mapping the app to the rubric.

**30-hour build (Chennai, Sept 12–13) — must run on the iQOO 15 at demo:**
- MVP: real `MediaStore` scan → BlazeFace detect → MobileFaceNet embed →
  clustering → **People** populated on-device; **Clean** with real dHash dupes;
  name-a-person. This is the demoable core.
- Stretch: LLM/Whisper search; scene tags; consolidate/export writes.

## 7. Out of scope (screening)

- Real inference, real photo I/O, persistence — the prototype fakes these
  deliberately; the plan below is where they get built.
