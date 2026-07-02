# MediaMind — User Guide (Session 02 state)

This guide tells you everything you need to do to run the app and test what has been built so far. No coding knowledge is required — just follow the steps in order.

---

## What the app can do right now

- **Add folders** — tell MediaMind which folders to watch
- **Find duplicates** — scan a folder for exact copies and visually similar images/videos
- **Review duplicates** — see groups of duplicate files with thumbnails, mark which ones to keep or trash
- **Bulk rules** — auto-mark files with "keep best quality / keep newest / keep largest"
- **Trash duplicates** — move marked files to the Windows Recycle Bin (files are never permanently deleted; you can restore from the Recycle Bin)

---

## Prerequisites (one-time setup, already done on your machine)

| What | Where on your machine |
|---|---|
| Python 3.11 + MediaMind backend | `C:\Users\husai\faces-env` |
| Node.js + npm | Already installed |
| MediaMind app | `C:\Users\husai\Desktop\CODES\MediaMind` |

You do **not** need to install anything. Everything is already set up.

---

## How to run the app

### Step 1 — Open a terminal

Press **Win + X** → choose **Terminal** (or **PowerShell**).

### Step 2 — Navigate to the app folder

```
cd C:\Users\husai\Desktop\CODES\MediaMind\app
```

### Step 3 — Start the app

```
npm run dev
```

Wait about 5–10 seconds. You will see output like:

```
  VITE v7.x  ready in ...
  ...
  Electron started
```

The MediaMind window will open automatically.

### Step 4 — Stop the app

Press **Ctrl + C** in the terminal, then close the window.

---

## What you will see on first launch

The app opens to a **Libraries** screen — your list of folders MediaMind knows about. It will be empty the first time.

The top-right shows the engine status dot:
- **Green** = Python backend is running, ready
- **Orange** = starting up (wait a few seconds)
- **Red** = error (re-run `npm run dev`)

---

## How to test the duplicate finder (the main feature)

### 1. Add a test folder

You need a folder with some duplicate or near-duplicate images or videos. A few ideas:
- A phone backup folder
- Your Downloads folder (often has duplicate images)
- Any folder with copied/renamed photos

Click **Add folder** → select the folder → it appears in the list.

### 2. Open the folder

Click on the folder row. It opens the **Library Detail** screen with a "Duplicates" card.

### 3. Start a scan

Click **Find duplicates**. The button becomes a progress bar showing:
- Phase: "scanning" then "hashing"
- File count progress (e.g. "340 / 4,567 files")
- A Cancel button if you want to stop early

For a folder with ~1,000 files, the scan takes roughly 10–30 seconds depending on how many images are present (images take longer because they also get a perceptual hash for visual similarity).

### 4. Review results

When the scan finishes, you see a summary line like:

> **37 groups · 112 files · 1.2 GB reclaimable**

Click **Review duplicates** to open the review screen.

### 5. The review screen

Each card is a group of duplicate files:
- **"Exact copy"** badge = byte-identical files (same content, possibly different names/folders)
- **"Visually similar"** badge = images that look the same but may differ in size, quality, or format

Each file tile shows:
- A thumbnail preview
- File dimensions (for images), file size, modification date
- A "Best" badge on the file MediaMind suggests keeping (highest resolution, then largest, then oldest)
- **Keep** / **Trash** buttons

### 6. Mark files

Click **Keep** or **Trash** on individual files. Tiles update instantly:
- Green highlight = marked Keep
- Red/faded = marked Trash

**Rule: every group must keep at least one file.** If you try to trash everything in a group, it will be rejected.

**Bulk rules** (top of the review screen): apply a rule to ALL groups at once:
- **Keep best quality** — keeps the suggested "Best" file in each group
- **Keep newest** — keeps the most recently modified file in each group
- **Keep largest** — keeps the largest file in each group

### 7. Execute (move to Recycle Bin)

When you have marked files, a sticky bar appears at the bottom:

> **41 files marked · frees 1.2 GB** | [Move to Recycle Bin]

Click **Move to Recycle Bin**. A confirmation dialog appears showing a preview plan. Click **Confirm** to proceed.

Files go to the **Windows Recycle Bin** — they are never permanently deleted. You can restore them from the Recycle Bin at any time.

A manifest CSV is saved inside the library's `.mediamind/manifests/` folder — a complete audit trail of what was moved.

---

## Possible issues and what to do

| Symptom | What to do |
|---|---|
| Engine dot stays orange for >30 seconds | Close app, re-run `npm run dev` |
| "Engine offline" (red dot) | Python env may have an issue. Run `C:\Users\husai\faces-env\Scripts\python.exe -m mediamind` in a separate terminal to see the error |
| "No previous scan found" on the library detail screen | Normal — you haven't scanned that folder yet. Click "Find duplicates" |
| Scan seems stuck / very slow | Large libraries (10,000+ files) can take a few minutes. The progress bar is live; wait it out or Cancel |
| "A scan is already running for this library" | A scan is in progress. Wait for it to finish or cancel it |
| Duplicate review screen shows "Could not load" | Scan may have been cancelled or failed. Go back and rescan |
| All Trash buttons are greyed out after bulk rule | You applied a bulk rule — all "trash" files are already marked. Click the Execute footer to proceed |
| Confirm dialog says "Review changed — please re-check" | You marked files then the review changed. Refresh by going back and re-entering the review screen |

---

## What is NOT available yet

These features are planned for future sessions:

- **Face recognition / People** — the "People" section shows "Coming soon"
- **Face-based folder sorting** — not yet built
- **Settings screen** — no settings UI yet
- **App packaging** — the app only runs in dev mode (`npm run dev`) for now

---

## File safety guarantees

MediaMind is designed to never lose or destroy your files:

1. Files are **moved to the Recycle Bin**, never hard-deleted
2. You must **explicitly confirm** before anything is moved
3. A **dry-run preview** is shown in the confirm dialog before you commit
4. Every operation is recorded in a **manifest CSV** (audit trail) inside the library's `.mediamind/manifests/` folder
5. Files that **can't be found** at execute time are skipped with an error, not trashed blindly

---

## Folder structure created by MediaMind

When you add a folder, MediaMind creates a `.mediamind/` subfolder inside it:

```
your-photos/
├─ .mediamind/
│  ├─ index.db          ← local database (scan results, resolutions)
│  └─ manifests/        ← CSV audit logs of every operation
├─ photo1.jpg
├─ photo2.png
└─ ...
```

This folder belongs to the library and travels with it. Deleting it just means the next scan starts fresh — no user photos are stored inside it.
