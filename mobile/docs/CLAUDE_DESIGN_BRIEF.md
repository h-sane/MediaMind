# Brief for Claude Design — MediaMind mobile (gallery app)

**How to use:** Claude Design → template **"Mobile app design"** → Model
**Opus 5** → Design system **None** → paste everything below the line. It will
produce **runnable front-end files** (not just mockups) — build them with the
tech stack specified in §7 so the backend can be connected afterward. After it
generates, screenshot the screens back to Claude Code for a critique + refinement
pass.

---

## 0. What this is — read first

**MediaMind is a full gallery app for Android** — a complete replacement for the
phone's default Gallery / Google Photos. The primary experience is **browsing your
photos and videos**, exactly like Google Photos. On top of that gallery, MediaMind
adds three standout capabilities — **face recognition (People), duplicate cleanup,
and AI/voice search** — placed as *secondary features in the sidebar/tabs, exactly
where Google Photos puts its equivalents.* They are **not** the main screen and
there is **no "Scan my photos" hero button.** The app opens straight into the
photo grid; face grouping and duplicate detection happen quietly in the
background, surfaced through People and Utilities — just like Google Photos.

Think **Google Photos, rebuilt privately and on-device**: same gallery-first
information architecture, plus better People tools and duplicate cleanup, with all
the AI running locally on the phone (nothing uploaded).

## 1. Reference product: Google Photos (2025) — match this IA

Google Photos' current structure, which we mirror:

- **Floating pill bottom bar:** `Photos · Collections` grouped in a pill, plus a
  **separate round Search button**. (We use **Photos · Collections · Search** — a
  clean 3-destination gallery nav.)
- **Photos tab** — the home: one big reverse-chronological grid of all photos &
  videos. Pinch to change zoom (day / month / year). Multi-select. A date
  scrubber on the right edge.
- **Collections tab** (Google renamed this from "Library" in 2024) — a grid of
  auto-groupings with pill shortcuts at the top for **Favorites, Utilities,
  Archive, Trash**, and cards for **People, On-device folders, Albums, Videos,
  Screenshots, Places, Moments (memories)**. "Free up space" lives under
  **Utilities**.
- **Search** — a search bar with **AI natural-language search** ("Ask" — Google's
  is Gemini-powered "Ask Photos"), a **People & pets** row, **Places** map, and a
  **Things/categories** grid.

We keep this exact IA and slot our features into it (see §4).

## 2. Where each feature goes (feature → placement)

| Feature | Placement (mirrors Google Photos) |
|---|---|
| Browse photos/videos (the main job) | **Photos** tab — reverse-chron grid, zoom levels, multi-select |
| Full-screen photo viewer | Tap any photo → swipeable viewer with action bar |
| Memories / highlights | "Moments" card in **Collections** |
| **People (face recognition)** — our flagship | Prominent **People** card in **Collections** + a **People & pets** row in **Search**. Enhanced beyond Google: name unnamed people inline, merge, consolidate. |
| **Duplicate cleanup** — our flagship | Under **Collections → Utilities → Free up space → Duplicates**. Review groups, keep best, reclaim space. |
| **AI + voice search** — our flagship | The **Search** bar: natural-language query + a voice mic. |
| On-device folders (filesystem-first DNA) | "On this device" card in **Collections** |
| Albums, Favorites, Archive, Trash, Screenshots, Places | Standard **Collections** cards/shortcuts, as in Google Photos |
| Privacy / on-device story | A quiet, consistent badge + a subtle "Processing on device" chip during background indexing; a privacy note in Search and Settings. **Never a centerpiece.** |

## 3. Design language (our identity — deliberate, not generic)

Distinct from Google Photos' white chrome, tuned for the iQOO 15's 2K AMOLED:

- **Ground:** true black `#000000` (photos glow off it; premium; power-saving on
  AMOLED — a deliberate choice, not tinted near-black).
- **Text:** warm off-white `#F5F3EF`; secondary warm grey `#9A968D`.
- **Accents, each with ONE meaning (never decoration):**
  - Ember-gold gradient `#F6B24B → #F2762E` = **people & primary actions**.
  - Electric indigo `#7C6CF0` = **on-device AI / search / indexing** signals.
  - Teal `#38D6C0` = **storage / cleanup** only.
- **Signature detail:** a soft amber **recognition frame** on a face — used only in
  People contexts (person tiles, the viewer's "who's in this photo" overlay), not
  on the home grid and never as a hero.
- Chrome is quiet and photo-first: the grid is the star; the floating nav pill and
  translucent top bar sit lightly over it. Subtle film grain optional. Motion
  light — pinch-zoom grid transition, smooth viewer swipe, gentle tab changes.

## 4. Screens to build

1. **Photos (home)** — translucent top bar (account avatar, a small on-device
   privacy badge); full-bleed reverse-chron grid of photos + videos (video tiles
   show a duration chip); pinch-zoom day/month/year; a floating date scrubber;
   long-press → multi-select mode with a contextual action bar (share, add to
   album, delete, favorite).
2. **Photo viewer** — full-screen photo, swipe left/right; bottom action bar
   (Share, Edit, Favorite, Info, Delete); an **Info** sheet showing date, size,
   folder, and **"People in this photo"** (amber-framed face chips); for a face,
   tap → person.
3. **Collections** — top pill row (Favorites · Utilities · Archive · Trash); a 2-col
   card grid: **People** (first, largest — avatars peeking), On this device,
   Albums, Videos, Screenshots, Places, Moments. Utilities opens a list including
   **Free up space (Duplicates)**.
4. **People** (from Collections/Search) — grid of person avatars; **unnamed people
   first** ("Tap to name", ringed in indigo), then **named** (gold-ringed, e.g.
   Amara 218, Dad 174, Priya 203, Kabir 142, Nani 97, Ravi 64). A subtle indigo
   status: "Found 23 people · on-device".
5. **Person detail** — hero avatar + "Amara · 218 photos · 2019–2026"; actions
   **Rename**, **Merge**, **Consolidate**; then the person's photo grid.
6. **Search** — search bar with placeholder "Ask for a photo… 'Mom at the beach'"
   and a voice **mic** (indigo); below it a **People & pets** avatar row, a
   **Places** map card, and a **Things** category grid (Screenshots, Documents,
   Selfies, Videos, Receipts). A results state showing a filtered grid.
7. **Duplicates (Free up space)** — a teal reclaim header ("2.3 GB · 128
   duplicates"); duplicate groups as stacked thumbnails with the best copy
   pre-selected ("Keep best"); a confirm CTA "Review & free 2.3 GB"; note:
   "Nothing is deleted until you confirm."
8. **Onboarding (single screen, minimal)** — NOT a scan hero. A clean
   permission-grant: brand mark, one line "MediaMind organizes your photos
   privately, on your phone", a primary button **"Allow access to photos"**, and a
   small "Nothing ever leaves your device." Granting lands directly in **Photos**.
9. **Settings** (light) — on-device processing toggle, model/license info,
   theme, about. Reinforces the privacy story here, not on the home screen.

## 5. Copy tone

Plain, active, from the user's side. Buttons name what happens ("Free up space",
then a toast "Freed 2.3 GB"). Privacy stated as fact, never sold. No all-caps
eyebrows, no "→" on buttons, no marketing fluff on functional screens.

## 6. Empty & loading states

- First launch, before indexing finishes: Photos shows the real grid immediately;
  People shows "Finding people… running on your device" with an indigo progress
  chip (cause-and-effect — background work is always visible).
- Empty People: "No people yet. As MediaMind indexes your photos, the people in
  them appear here."

## 7. Front-end tech stack (BUILD WITH THIS — output runnable files)

Produce a real, runnable Expo project, not just screens. The backend/engine gets
connected later, so keep all data behind a swappable layer.

- **Framework:** **Expo (React Native) + TypeScript**.
- **Navigation:** **Expo Router** (file-based; a `(tabs)` group for Photos /
  Collections / Search, native stack for viewer, person, duplicates, settings).
- **Styling:** **NativeWind v4** (Tailwind for RN). Put the palette in §3 into
  `tailwind.config.js` as theme tokens (`bg-black`, `text-ink`, `accent-amber`,
  `accent-indigo`, `accent-teal`) — never hardcode hex in components.
- **Icons:** **lucide-react-native**.
- **Images & lists:** **expo-image** for tiles; **@shopify/flash-list** for the
  performant photo grid.
- **Gestures/motion:** **react-native-reanimated** + **react-native-gesture-handler**
  (pinch-zoom grid, swipe viewer, sheet transitions).
- **State:** **Zustand**.
- **Data layer (critical for backend hookup):** define typed repository interfaces
  — `PhotoRepository`, `PeopleRepository`, `DuplicatesRepository`,
  `SearchRepository` — and ship a **mock implementation** that returns placeholder
  data. Screens consume repositories through hooks (`usePhotos()`,
  `usePeople()`…); **no screen hardcodes data.** This is the seam where the
  on-device engine gets connected later.
- **Placeholder media (no external URLs — offline/CSP-safe):** a `<PhotoTile>` /
  `<Avatar>` component renders a deterministic warm-duotone gradient from an item
  id, so the gallery looks full and real without bundling photos. Video tiles add
  a duration chip.
- **No network calls anywhere.** All data is local/mock.
- **Project shape:** standard Expo Router app —
  `app/(tabs)/index.tsx` (Photos), `app/(tabs)/collections.tsx`,
  `app/(tabs)/search.tsx`, `app/viewer/[id].tsx`, `app/person/[id].tsx`,
  `app/duplicates.tsx`, `app/settings.tsx`, `app/onboarding.tsx`; shared UI in
  `components/`, repositories in `data/`, tokens in `theme/`.

## 8. What Claude Code will do after

Connect the real engine to the repository interfaces: `expo-media-library` for the
actual camera roll, `expo-sqlite` for the index, and on-device face detection /
embedding + duplicate hashing via native inference modules
(`onnxruntime-react-native` / ExecuTorch with the NNAPI-QNN NPU delegate). The
cleaner the repository seam, the smaller that work is — so keep screens purely
presentational and data-agnostic.
