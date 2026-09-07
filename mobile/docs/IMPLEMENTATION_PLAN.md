# MediaMind Mobile — Implementation Plan

Two horizons: the **screening submission** (today) and the **30-hour Chennai
build** (Sept 12–13). See `SOFTWARE_SPEC.md` §6 for scope split.

---

## Horizon A — Screening submission (today, before 12:00 IST)

Priority per the event doc: the frontend **looks great**; functionality not
required.

- [x] Read hackathon rules; fix product direction (on-device private photo
      organizer) and track (Open Innovation / Smart Living).
- [x] Design direction (AMOLED black; amber=people, violet=on-device AI,
      teal=storage; recognition-frame as the one bold moment).
- [x] Interactive prototype — 6 screens + scan animation
      (`mobile/prototype/index.html`, published as an Artifact).
- [x] Stack, tech spec, software spec, this plan.
- [ ] **Pitch text** for the Reskilll submission form (300–500 words: problem,
      why on-device, how it maps to the rubric, what runs on the NPU).
- [ ] Screenshots of the prototype for the submission gallery.
- [ ] Submit on iqoo.reskilll.com before the cutoff.

## Horizon B — 30-hour Chennai build (Sept 12–13)

Ordered so there's a **demoable app at every checkpoint** (evaluation rounds are
Saturday evening + Sunday morning).

**Phase 0 — Skeleton (hrs 0–3).** Compose app matching the prototype: nav, four
tabs, static screens wired to a fake repository. Guarantees a running app on the
phone from hour 3.

**Phase 1 — Photo access + index (hrs 3–7).** `MediaStore` enumeration → SQLite
`photo` rows → Library grid shows the *real* camera roll (media-first). First
"the phone's own photos" moment.

**Phase 2 — On-device faces (hrs 7–15). The core.**
- ORT Mobile + QNN wired; capability probe + delegate fallback.
- BlazeFace detect → MobileFaceNet embed on the NPU.
- Scan job with live progress (the scanning screen becomes real).
- Greedy clustering → **People** populated with real clusters; name-a-person.
- *Checkpoint for Saturday-evening eval: real on-device face grouping.*

**Phase 3 — Clean (hrs 15–20).** dHash/pHash + exact SHA duplicate grouping;
keep-best selection; review-and-confirm delete via `MediaStore` (with
confirmation, audit row, undo). Real GB reclaimed.

**Phase 4 — Search (hrs 20–26). Stretch, high pitch value.** Whisper Tiny voice
→ Gemma 2B intent parse → SQLite filter. Even person-name + date-only search is a
strong offline demo.

**Phase 5 — Polish + pitch (hrs 26–30).** Consolidate/export writes if time;
per-stage latency overlay for the technical-depth story; rehearse the 3–5 min
demo on the iQOO 15; ensure Office Kit mirroring works (10% of score).

---

## Risk register

| Risk | Mitigation |
|---|---|
| QNN EP setup eats hours | NNAPI/GPU fallback is the safety net; get *any* delegate running first, optimize to NPU after. |
| Model conversion (ONNX/TFLite quantize) painful | Pre-convert MobileFaceNet + BlazeFace **before** the event (allowed prep); commit the artifacts. |
| Sideload/dev-options unknown on loaner | Confirm at check-in (open question in the event doc). Have an APK ready; test install path early. |
| On-device LLM too slow/heavy | Search is Phase 4/stretch — the People + Clean core stands without it. |
| Photo-permission UX on Android 16 | Use the Photo Picker path; test the exact OriginOS 6 permission flow on the loaner first thing. |

## Pre-event prep (allowed; do before Sept 12)

- Convert + quantize BlazeFace and MobileFaceNet to ONNX/TFLite; verify they load
  under ORT Mobile with QNN and NNAPI. Commit the model files + a licenses note.
- Stand up the Compose skeleton (Phase 0) so hour 0 starts at Phase 1.
- Practice Office Kit phone↔laptop mirroring (pc.vivoglobal.com).
- Use OpenRouter prep credits only for offline dataset/prompt prep — never the
  live serving path.

## Branch / repo

- Work on `mobile/hackathon-prototype` (this branch). The Android app lives under
  `mobile/android/` when the build starts; the prototype + docs under
  `mobile/prototype/` and `mobile/docs/`.
