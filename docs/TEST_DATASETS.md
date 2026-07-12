# MediaMind — Test Dataset Guide

**Purpose:** curated public datasets for building an automated test suite that
exercises MediaMind's two flagship engines — **duplicate detection** (exact +
near-duplicate) and **face recognition/clustering** (photos, GIFs, video) —
across the full format list in `docs/PRD.md` §3 (JPEG/PNG/BMP/WebP/TIFF, HEIC/
HEIF/AVIF, GIF, and mp4/mov/avi/mkv/webm/m4v/3gp/mpg/wmv/flv/ts/mts/m2ts/ogv).

Drop downloaded material into a `final_dataset/` folder with the structure
suggested in §7, then point a future Claude Code session at it to generate
pytest fixtures and integration tests.

---

## 1. Face recognition — still images (identity clustering)

| Dataset | Size | Why it fits | License / access |
|---|---|---|---|
| **LFW (Labeled Faces in the Wild)** | 13,233 images, 5,749 identities | The standard face-verification benchmark; small enough to run full pipeline tests in CI. Some identities have only 1 photo (good "singleton/noise" test case for DBSCAN), others have 100+ (good "big cluster" case). | Public, research use. [Kaggle mirror](https://www.kaggle.com/datasets/atulanandjha/lfwpeople) · [official site](http://vis-www.cs.umass.edu/lfw/) |
| **CelebA** | 202,599 images, 10,177 identities | Good for stress-testing clustering at scale and for bias/robustness checks (40 attribute labels incl. pose, lighting, occlusion). | Non-commercial research. [Kaggle](https://www.kaggle.com/datasets/jessicali9530/celeba-dataset) |
| **AgeDB** | 12,240 images, 440 identities | Same person across decades — tests whether your model over-splits an identity due to age drift. | Research use, request form. |
| **CASIA-WebFace** | 494,414 images, 10,575 identities | Larger stress test if you need tens-of-thousands-of-faces scale for the "Future Scope" ANN/incremental clustering work. | Non-commercial research, Google Drive mirror. |
| **DigiFace-1M** (Microsoft) | 1.22M synthetic images, 110K identities | **No consent/privacy concerns at all** (fully synthetic) — good for a redistributable fixture set in your own test repo without licensing headaches. | MIT-style permissive, [GitHub](https://github.com/microsoft/DigiFace1M) |
| **5 Faces Dataset** | ~750 images, 5 identities | Tiny — good smoke-test fixture, fast CI. | [Kaggle](https://www.kaggle.com/datasets/anku5hk/5-faces-dataset) |

**Recommendation for MediaMind specifically:** use **LFW** as the primary
face-clustering fixture (matches your V0 `--eps`/DBSCAN tuning workflow well —
mix of singleton and large identities) and **DigiFace-1M** (subsample a few
hundred identities) as a license-clean, redistributable fixture you can commit
alongside your own test suite without worrying about real people's images.

---

## 2. Face recognition — video (same person across photo + clip, per PRD F2 acceptance criteria)

| Dataset | Size | Why it fits | Access |
|---|---|---|---|
| **YouTube Faces (YTF)** | 3,425 clips, 1,595 identities, 48–6,070 frames/clip | Directly tests PRD's "a person in a photo and a video lands in one cluster" requirement — pair it with LFW images of overlapping celebrities where possible. | [Official site](https://www.cs.tau.ac.il/~wolf/ytfaces/) (request form) · [Kaggle: "YouTube Faces With Facial Keypoints"](https://www.kaggle.com/datasets/selfishgene/youtube-faces-with-facial-keypoints) (pre-cropped, easier to use) |
| **DFDC (DeepFake Detection Challenge)** | 100K+ 10-second clips, 3,426 actors, real **mp4** | Real, unmanipulated subset gives you genuine mp4 clips with consistent identities across many videos each — good frame-sampling stress test. (Skip the deepfake/manipulated subset — not relevant to your use case.) | [ai.facebook.com/datasets/dfdc](https://ai.facebook.com/datasets/dfdc) — free registration |
| **DH-FaceVid-1K** | 270,043 clips, 20,000+ identities, 1,200 hrs | If you want a much larger/newer video-identity corpus for scale testing. | Research license, see paper repo. |

**Practical note:** most "real" face-video datasets ship as **mp4** only. To
cover your other supported containers (mov, avi, mkv, webm, m4v, 3gp, wmv,
flv, ts, mts, m2ts, ogv) you'll likely need to **transcode a handful of YTF/
DFDC clips yourself** with `ffmpeg` (one clip → 15 container variants) rather
than finding native datasets in each format — those don't really exist publicly
at any volume. This is the practical path the community actually uses for
"does my loader open every container" tests.

---

## 3. GIFs with people/faces

There is no widely-used "faces-in-GIFs" benchmark — this is a real gap. Two
practical options:

1. **TGIF (Tumblr GIF) dataset** — 100K GIFs with captions, general content
   (not face-specific), collected from Tumblr. Filter for the subset whose
   captions mention "man/woman/face/person/selfie" etc., then run your own
   face detector to keep only GIFs that actually contain faces. [GitHub
   (URLs + scripts)](https://github.com/raingo/TGIF-Release) ·
   [Hugging Face mirror](https://huggingface.co/datasets/HuggingFaceM4/TGIF)
   ⚠️ Only URLs are distributed — you must download the underlying GIFs
   yourself (some links will be dead in 2026; expect attrition).
2. **Generate your own from YTF/DFDC clips** — take a few of the video clips
   from §2 and convert short segments to GIF with `ffmpeg`
   (`ffmpeg -i clip.mp4 -vf "fps=10,scale=320:-1" out.gif`). This guarantees
   known-identity GIFs that match your video fixtures, which is more useful
   for testing than random Tumblr content anyway (you already know the ground
   truth: "this GIF = this photo = this video, same person").

**Recommendation:** don't spend time hunting for a dedicated GIF-faces
dataset — synthesize your GIF fixtures from the same YTF/DFDC clips you use
for video tests. That also directly proves the PRD's "global clustering
across photo + video + GIF" requirement with one shared identity per person.

---

## 4. Duplicate detection — exact & near-duplicate images

| Dataset | Size | Why it fits | Access |
|---|---|---|---|
| **INRIA Copydays** | ~3,000 images (with JPEG/crop/scale attacks) | Built specifically to benchmark near-duplicate detection (re-encoding, cropping, scaling) — matches PRD F1.2 ("same image re-encoded/resized") almost exactly. | [Official page](https://lear.inrialpes.fr/~jegou/data.php#copydays) |
| **UKBench** | 10,200 images, 2,550 groups of 4 | Clean, simple ground truth (each group = 4 near-dupes of one object) — easy to turn into pytest assertions ("group of 4 in, 1 group out"). | Widely mirrored, e.g. via `imagededup` benchmark scripts. |
| **INRIA Holidays** | 1,491 images, 500 clusters | Personal-photo-realistic content (vacation photos) — closer to MediaMind's actual target use case than object-benchmark datasets. | [Hugging Face](https://huggingface.co/datasets/randall-lab/INRIA-holidays) |
| **Synthetic benchmark (10K images, 2,501 dup groups)** | 10,000 images | Ground-truth generator approach: exact copies + rotation (90/180/270°) + flips — good for exact-hash and simple-transform test cases. Reproduce with the augmentation recipe in ["Effective near-duplicate image detection using perceptual hashing and deep learning"](https://www.researchgate.net/publication/393235277) if you want full control instead of downloading. | — |

**Recommendation:** use **INRIA Copydays** as your primary near-duplicate
fixture (re-encode/resize matches your F1.2 spec directly) and generate your
**own exact-duplicate cases** trivially — copy files byte-for-byte and re-save
some as different formats/quality levels with Pillow (covers "resized JPEG
copy" and cross-format dupe, e.g. same photo as .jpg and .heic).

---

## 5. Duplicate detection — video

Video near-dup benchmarks exist but are old/research-oriented and PRD V1 only
requires **byte-exact** video matching (F1.2: "videos are matched byte-exact
in V1") — so you don't need a near-duplicate video corpus at all for V1
tests. If/when near-dup video matching becomes in-scope (not currently
planned), **CC_WEB_VIDEO** (12,790 clips, 24 query sets with human-annotated
near-dup labels) is the standard benchmark: [official
page](http://vireo.cs.cityu.edu.hk/webvideo/).

For now, byte-exact video dup tests are trivial to construct yourself: take
any clip from §2, copy it, and re-save one copy at a different container
(mp4 → mov) to verify your test correctly does **not** treat re-encoded video
as a duplicate under the V1 byte-exact rule.

---

## 6. Odd/edge-case formats (HEIC, HEIF, AVIF, exotic containers)

Public "datasets" don't really exist for these — use small sample-file
galleries designed for decoder testing:

- HEIC/HEIF samples: [SampleYogi](https://www.sampleyogi.com/samples/sample-heic), [ConvertICO](https://convertico.com/samples/heic/), [heic.digital](https://heic.digital/samples/) (real iPhone/Android HEIC captures — useful since they contain real faces, unlike synthetic test charts)
- AVIF samples: [ConvertICO AVIF samples](https://convertico.com/samples/)
- HEIF reference/edge cases (bursts, derived images): [Nokia HEIF examples](http://nokiatech.github.io/heif/examples.html)

Pull a handful of real-face HEIC/AVIF photos from these galleries specifically
to test the `pillow-heif` decode path and the "undecodable file → holding
area" safety invariant (intentionally include a couple of malformed/renamed
files too).

---

## 7. Suggested `final_dataset/` layout

```
final_dataset/
├── faces_images/           # LFW subset + DigiFace-1M subset
│   ├── person_A/ *.jpg
│   └── person_B/ *.jpg
├── faces_video/            # YTF or DFDC clips, transcoded to multiple containers
│   ├── person_A/clip.mp4
│   ├── person_A/clip.mov      # ffmpeg-transcoded copy, same identity
│   └── person_A/clip.mkv
├── faces_gif/               # ffmpeg-generated GIFs from faces_video clips
│   └── person_A/clip.gif
├── dedupe_exact/            # byte-identical copies (different filenames/subfolders)
├── dedupe_near/             # INRIA Copydays subset (resized/re-encoded pairs)
├── dedupe_cross_format/     # same photo saved as .jpg/.png/.heic/.webp
├── format_edge_cases/       # real-face HEIC/AVIF samples, one corrupt file, one non-media file
└── ground_truth.csv         # your own manifest: file → true identity / true dup-group
                              # (needed to assert pass/fail in pytest)
```

A `ground_truth.csv` you maintain by hand is the single most important file
here — none of the public datasets encode ground truth in the exact shape
your test assertions need, so plan to write a small script that builds it
from folder names as you assemble the set.

---

## 8. Licensing note

Most face datasets above (LFW, CelebA, AgeDB, CASIA-WebFace, YTF, DFDC) are
**research/non-commercial only** — fine for local, private testing, but do
**not** commit real people's face images into the public MediaMind GitHub
repo. Keep `final_dataset/` out of version control (add it to `.gitignore`)
and treat it as a local fixture cache. Only **DigiFace-1M** (synthetic) is
safe to consider redistributing as a committed CI fixture.

---

## Sources

- [Best Face Recognition Datasets in 2026 — Axonlab](https://axonlab.ai/face-recognition-datasets/)
- [20 Best Face Recognition Datasets for ML in 2026 — Unidata](https://unidata.pro/blog/best-ml-face-recognition-datasets/)
- [YouTube Faces Database — official](https://www.cs.tau.ac.il/~wolf/ytfaces/)
- [YouTube Faces With Facial Keypoints — Kaggle](https://www.kaggle.com/datasets/selfishgene/youtube-faces-with-facial-keypoints)
- [The DeepFake Detection Challenge (DFDC) Dataset](https://ar5iv.labs.arxiv.org/html/2006.07397)
- [DH-FaceVid-1K](https://arxiv.org/html/2410.07151v2)
- [Effective near-duplicate image detection using perceptual hashing and deep learning](https://www.researchgate.net/publication/393235277_Effective_near-duplicate_image_detection_using_perceptual_hashing_and_deep_learning)
- [Benchmarks — Imagededup](https://idealo.github.io/imagededup/user_guide/benchmarks/)
- [INRIA Holidays Dataset — Hugging Face](https://huggingface.co/datasets/randall-lab/INRIA-holidays)
- [CC_WEB_VIDEO: Near-Duplicate Web Video Dataset](http://vireo.cs.cityu.edu.hk/webvideo/)
- [Tumblr GIF (TGIF) Dataset — GitHub](https://github.com/raingo/TGIF-Release)
- [LFW - People (Face Recognition) — Kaggle](https://www.kaggle.com/datasets/atulanandjha/lfwpeople)
- [5 Faces Dataset — Kaggle](https://www.kaggle.com/datasets/anku5hk/5-faces-dataset)
- [VGGFace2 paper](https://arxiv.org/pdf/1710.08092)
- [DigiFace-1M — GitHub](https://github.com/microsoft/DigiFace1M)
- [HEIC sample files — SampleYogi](https://www.sampleyogi.com/samples/sample-heic)
- [HEIF Example Images — Nokia](http://nokiatech.github.io/heif/examples.html)
