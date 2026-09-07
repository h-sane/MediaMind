# Brief for Claude Design — MediaMind mobile

**How to use:** open Claude Design → template **"Mobile app design"** → Model
**Opus 5** → Design system **None** (let it propose one) → paste everything below
the line. After it generates, screenshot each screen back to Claude Code for
critique + a refinement pass.

---

Design a **native Android app** called **MediaMind** — a *private, on-device AI
photo organizer*. It scans the phone's camera roll and organizes it **by the
people in it**, finds duplicates to free space, and answers plain-language
searches — and it does all of this **on-device**, so no photo ever leaves the
phone. The wedge against Google Photos is exactly that privacy: the AI runs
locally on the phone's NPU.

**Audience:** everyday people with years of unsorted photos who don't want to
upload their family's faces to the cloud. Warm, human, trustworthy — not a
sterile utility.

**Platform:** Android (iQOO 15, 6.85" 2K AMOLED, 144Hz). Design at 390×844.

## Visual direction (follow exactly — do NOT default to generic AI looks)

- **Ground:** true black `#000000` (deliberate for AMOLED — photos glow off it;
  do not use tinted near-black like #0B0B0B).
- **Text:** warm off-white `#F5F3EF`; secondary warm grey `#9A968D`.
- **Accents — each carries ONE meaning, never decoration:**
  - Ember-gold gradient `#F6B24B → #F2762E` = **people, memory, primary actions**.
  - Electric indigo `#7C6CF0` = **on-device AI / NPU** (every "runs locally"
    signal, scan progress).
  - Teal `#38D6C0` = **storage / cleaning** only.
- **The one bold moment:** the *recognition frame* — a glowing amber bounding box
  lighting up on a face as the AI detects it. Use it on onboarding + scanning.
  Everything else stays quiet and disciplined.
- Rounded, soft cards but vary the treatment per screen (people = circular
  clusters, clean = a full-bleed storage hero) — avoid identical rounded cards
  with the same grey shadow everywhere. Subtle film grain over the black is
  welcome. Motion light: one scan animation, gentle screen transitions.

## Screens (design all six + bottom nav)

Bottom tab bar, in this order (flagship features are top-level): **People ·
Library · Clean · Search.**

1. **Onboarding** — a face with a glowing amber recognition frame + sweeping scan
   line; an indigo pill "Runs on-device · Snapdragon NPU"; headline
   "Your photos. Your people. Never the cloud."; body "MediaMind finds every
   person in your camera roll, clears duplicates, and organizes it all — right
   here on your phone. No uploads. No accounts."; one gold CTA "Scan my photos";
   fine print "4,812 photos on this device · nothing has left it".
2. **Scanning** — a spinning indigo radar with a big % in the middle; stage text
   ("Looking for faces…" → "Grouping people…" → "Finding duplicates…"); a teal
   privacy line "0 photos uploaded · 0 bytes sent".
3. **People** (home) — indigo status "Found 23 people in 4,812 photos ·
   on-device"; a **"Needs a name"** row first (circular avatars ringed in indigo,
   "+ Name this person"), then a **"Named"** grid (gold-ringed avatars: Amara 218,
   Dad 174, Priya 203, Kabir 142, Nani 97, Ravi 64). Avatars are warm duotone
   gradients (no real photos needed).
4. **Person detail** — hero avatar + "Amara · 218 photos across 5 albums ·
   2019–2026"; two action cards **Consolidate** ("Gather all 218 into one place")
   and **Export** ("Share or back up privately"); then a photo grid.
5. **Library** — media-first photo grid (3-col, some tall tiles, occasional amber
   face-frame on a tile); a search bar "Ask for a photo… 'Mom at the beach'" with
   an indigo mic button; filter chips (All media / Photos / Videos / Screenshots
   / This year) with "All media" selected.
6. **Clean** — a teal reclaim hero "2.3 GB · 128 duplicates and 44 near-identical
   shots" with a progress meter; a teal CTA "Review & free 2.3 GB"; a list of
   duplicate groups (stacked thumbnails, "Keep best"); fine print "Nothing is
   deleted until you confirm. The best copy is always kept."

## Copy tone

Plain, active, from the user's side. Buttons say what happens. Privacy is stated
as fact, never sold. No all-caps eyebrows, no "→" on buttons.

## Reference

A working HTML version of this exact design is already built at
`mobile/prototype/index.html` — match its layout, palette, and the recognition-
frame moment; improve the polish and typography.
