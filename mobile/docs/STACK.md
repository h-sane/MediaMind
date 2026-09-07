# MediaMind Mobile — Technology Stack

**Context:** iQOO Hackathon 2026 (City Battles, Chennai). Phone-first, on-device
AI at the core scores bonus points; live product must serve inference *on the
device* at demo time (cloud-only inference is penalized). Loaner device: iQOO 15,
Snapdragon 8 Elite Gen 5, Android 16 / OriginOS 6, 12–16 GB RAM.

The desktop MediaMind engine (Python + FastAPI + InsightFace/ONNX) **does not
port to the phone**. Python-on-Android is fragile and the InsightFace `buffalo_l`
model is both heavy and non-commercial. The mobile app is a **native Android app
with an on-device inference layer**. The desktop's *product logic* (face
clustering, duplicate grouping, consolidation, the safety invariants) is the
reference we reimplement, not the code we ship.

---

## Chosen stack

| Layer | Choice | Why (over the alternatives) |
|---|---|---|
| **App shell / UI** | **Kotlin + Jetpack Compose** | Native gives first-class access to the NPU delegates, `MediaStore`, CameraX, and background work. Flutter/RN add a bridge layer between us and the exact hardware the rubric rewards. Compose matches the dark, motion-light prototype cheaply. |
| **Face detection** | **MediaPipe Face Detector** (BlazeFace, TFLite) | Ships tuned for mobile, runs on GPU/NPU delegate, sub-10 ms/frame. No model-license burden. |
| **Face embedding** | **MobileFaceNet** (or ArcFace-mobile) as **ONNX / TFLite**, quantized INT8 | ~1–4 MB, 512-d embeddings, runs on the NPU. Replaces `buffalo_l` (300 MB, non-commercial) — Apache/MIT-friendly mobile alternative aligned with the app's Apache-2.0 license. |
| **On-device inference runtime** | **ONNX Runtime Mobile** with the **QNN execution provider** (Qualcomm NPU); **NNAPI / GPU** fallback | QNN targets the Snapdragon NPU directly — the "creative phone use" and "technical depth" story. NNAPI fallback keeps it running on any Android. |
| **Natural-language / voice search** | **Gemma 2B** (Q4) via **MLC-LLM** *or* **ONNX Runtime GenAI**; **Whisper Tiny** for speech-to-text | Organizer-named on-device models. LLM turns "Mom at the beach" into a face + scene filter; Whisper Tiny does voice search fully offline. 2–4B Q4 (~1.5–2.5 GB) fits the 12–16 GB device comfortably. |
| **Scene / caption tags** (stretch) | Small on-device image-tagging model (e.g. MobileCLIP / a TFLite classifier) | Lets search match "beach", "birthday" without cloud. Stretch goal — not required for screening. |
| **Vector store + metadata** | **SQLite** (bundled) with embeddings as `BLOB`; brute-force cosine over a few thousand faces | At phone-library scale (thousands, not millions of faces) a linear scan is milliseconds. No vector-DB dependency. `ponytail: linear scan; add an ANN index (usearch/hnswlib) only if libraries exceed ~50k faces.` |
| **Photo access** | Android **`MediaStore`** + **Photo Picker** / `READ_MEDIA_IMAGES` | The OS is the source of truth — matches MediaMind's "filesystem is truth" doctrine. We index, never hide, never move without consent. |
| **Async / scanning** | Kotlin Coroutines + **WorkManager** | Background scan survives app switches; progress surfaced in UI (cause-and-effect doctrine). |
| **Offline-first** | No network calls in the serving path | The privacy pitch *and* the rubric requirement. OpenRouter credits are used **only** for pre-event dataset/prompt prep, never live. |

---

## Deliberately not used

- **Cloud face/vision APIs** at demo time — penalized by the rubric and breaks the
  privacy pitch. (OpenRouter is prep-only, per event rules.)
- **The Python backend / InsightFace `buffalo_l`** — non-commercial license, too
  heavy, no clean Android path.
- **Flutter / React Native** — the NPU-delegate access we want is cleanest native.
- **A bundled vector database** — SQLite + linear scan is enough at this scale.

## Model licensing note

Every downloadable model must have its license surfaced before use (MediaMind
doctrine). MobileFaceNet, Gemma, and Whisper are all redistributable under
permissive/open terms compatible with the app's Apache-2.0 license — a deliberate
break from the desktop's non-commercial `buffalo_l`.
