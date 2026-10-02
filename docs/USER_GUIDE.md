# MediaMind — User Guide

This guide covers the MediaMind desktop app for Windows: how to install or
start it, what each part does, and what to check when something looks wrong.
No coding knowledge is needed.

MediaMind is a file explorer built for photos and videos. It works on your
real folders. Nothing is imported into a hidden library, and nothing is
deleted or moved without you saying so.

---

## Starting the app

### From a release (no setup)

1. Download `MediaMind-<version>-WinUI-x64.zip` from the project's GitHub
   Releases page and unzip it.
2. Right-click **Install-MediaMind.ps1** and choose **Run with PowerShell**.
   Accept the admin prompt. The script trusts the test certificate that ships
   in the zip, installs the Windows App Runtime, then installs MediaMind.
3. Open **Files - Dev** from the Start menu. The app still carries that name
   and icon; the MediaMind name comes later.

The engine that finds faces and duplicates is bundled inside the app. You do
not install Python or start anything else.

Release v0.4.0 is older than this guide. It has the explorer, Scan for
People, the People sidebar and Suggestions. Who's who, the Duplicates page,
people's folders and automatic filing arrive with the next release; until
then they are in the build from source.

### From source (development)

See "Development setup" in the root [`README.md`](../README.md). In short:
build `winui-frontend/Files/`, then launch **Files - Dev** from the Start
menu. After a code change, close the app, build again, and launch again.

---

## What you see first

The window works like Windows File Explorer: a sidebar on the left, tabs
across the top, an address bar, a toolbar, and the folder's contents in the
middle.

Two things are different from File Explorer:

- **Folders show photos and videos only.** Documents and other files are
  still on disk, just not listed. Press **Ctrl+M**, or choose **Show all
  files**, to see everything. Press it again to go back.
- **People is near the top of the sidebar.** It lists everyone MediaMind has
  found in the folders you have scanned.

---

## The usual order of work

1. **Scan a folder for people.** This finds the faces and also finds
   duplicate copies.
2. **Name a few faces per person** in Who's who, then choose **Sort people
   now**.
3. **Answer the questions** MediaMind is not sure about (Needs your check).
4. **Clear out duplicates.**
5. Optional: **give each person a folder** and move their pictures into it.
6. Optional: **watch a folder** so new pictures are sorted as they arrive.

Each step is described below.

---

## 1. Scan for People

Open a folder and choose **Scan for People** on the toolbar (it is also in
the folder's right-click menu). Scan one group of pictures at a time rather
than a whole drive: a scan of a few thousand files finishes in minutes, and
a scan of tens of thousands can take hours.

The first scan downloads the face-recognition model (about 300 MB). Its
license is shown before the download starts.

While a scan runs, a strip at the bottom of the window shows what it is
doing: finding files, reading file details, identifying files, looking for
faces, looking for duplicates, grouping faces into people, saving. You can
keep browsing. Long videos on a slow or network drive can take a while per
file; the strip says so when one file is taking long.

A scan only reads your files. You can **stop** it from the strip; nothing on
your drive changes, and the people and duplicates you already had stay as
they were.

Files that could not be read are listed afterwards under **Not scanned**.
Open one to see who is in it, then tag it to a person by hand.

---

## 2. Who's who: name people

Choose **Who's who** on the toolbar while you are in a scanned folder. The
page shows the faces found there.

1. Select a few clear faces of one person. Five good examples is plenty.
2. Type a name under **Name as**, or pick someone you have already named.
3. Repeat for the other people.
4. Choose **Sort people now**. MediaMind matches every photo and video in the
   folder to your examples.

Things to know:

- **A name carries across folders.** Name someone in one folder, and a later
  scan of another folder recognises them from the same examples.
- **The list on the left** has one row per person, plus rows for **No one
  named yet**, **Needs your check**, **Group pictures**, and **No faces
  found**. A count line at the top says how many files are sorted, how many
  have faces nobody is named on yet, and how many have no faces.
- **Guests.** Someone who only turns up in a few pictures in this folder is
  listed under **Guests**, apart from the people the folder is about. Use the
  **Belongs to this folder** switch to move a person either way.
- **View full size.** Open any face to see the whole picture or video.
  Left and Right move between faces, the number keys 1 to 9 name the face,
  double-click or Ctrl+scroll zooms, 0 fits the picture again, Esc goes back.

### Needs your check

After a sort, faces MediaMind is unsure about wait here as yes-or-no
questions, likeliest matches first. The picture or video is shown full
height, with the answers in a column on the right.

| Key | Answer |
|---|---|
| `Y` | Yes, this is that person |
| `N` | No |
| `I` | Ignore this face in this file (someone in the background, say). The file will not be linked to that person, even after a rescan |
| `S` | Skip for now |
| `D` or `Del` | Delete the file (asks first) |
| `F` | Full screen |

**It's someone else** lets you pick the right person, or **Someone new…** to
type a new name. Your yes answers become examples too, so sort again
afterwards to use them.

### No faces found

Pictures and videos in which the scan found no face. Look at each one, then
keep it where it is, move it into a folder, or delete it.

---

## 3. Duplicates

Choose **Duplicates** on the toolbar. Scan for People already looks for
copies; **Find duplicates** runs the check on its own, and **Check again**
re-runs it.

There are two kinds, on two tabs:

- **Exact** copies are identical byte for byte. Keeping any one loses
  nothing.
- **Look alike** copies show the same picture at a different size or
  quality. Keep the best one.

For each set, click the copy to keep, or press its number. Then:

| Key | Action |
|---|---|
| `K` | Keep the chosen copy and remove the others |
| `N` | Not duplicates. The set is not shown again unless a file changes |
| `S` | Skip |
| `F` | View the copy full screen (Left and Right show the other copies) |

Removed copies go to the Recycle Bin. On a drive that has no Recycle Bin the
page tells you the delete is permanent before you confirm. **Select all**
lets you clear many sets in one go; the strip at the bottom counts the
deletions as they happen.

---

## 4. The People page

**People** in the sidebar shows everyone across all scanned folders.

- Switch between **Faces** (one tile per person) and **Folders** (people
  grouped by where their pictures live).
- **Pin** people you look at often, and group people into **Collections**.
- People who are not named yet are shown too. Type a name on the tile.
- **Merge** joins two entries that are the same person. **Remove** hides a
  person from People; your photos are not touched, and **Hidden** brings
  them back.
- **Possible duplicates** flags two entries that may be one person. Answer
  **Same person** or **Different people**.
- Open a person to see all their photos and videos.

### Suggestions

The Suggestions panel lists new pictures picked up from watched folders that
may show someone you have already named. Select the ones that are the same
person and choose **Confirm selected**, or **Reject selected**.

---

## 5. A folder for each person

In Who's who, select a person. The bar under the folder row has:

- **Choose folder…** sets the folder on disk where this person's pictures
  belong. It is the same for that name in every folder you scan. Nothing
  moves yet.
- **Move files to this folder** moves every picture and video of that
  person, from every scanned folder, into it. You see the counts first and
  confirm.

How the move behaves:

- Each file is copied first and removed from its old place only after the
  copy is complete.
- A file that is already in the person's folder as an identical copy stays
  where it is and is not copied again.
- You can **stop** a move from the strip. The files already moved are put
  back, and folders the move created are removed again if they are empty.
- A finished move can be undone from the People page.

### Group pictures

A picture with more than one named person can only live in one place, so
MediaMind asks. Under **Group pictures**, choose for each one: a person's
folder, an existing or new **group folder**, or **Leave it where it is**.
Tick **Do the same for every picture of exactly these people** and the
answer is remembered, including for new pictures later.

---

## 6. Watched folders

Open **Settings → Watched folders** and choose **Add folder…**. MediaMind
then notices new pictures and videos there and sorts them against the people
you have named.

Tick **File new pictures into people's folders** on a watched folder to have
confident matches moved into each person's folder by themselves. Group
pictures still wait for your answer in Who's who. This is off until you turn
it on for a folder.

---

## Long tasks and the strip at the bottom

Scans, sorts, moves, and duplicate removal show their progress in two
places: a card on the page where you started them, and the strip at the
bottom of the window when you go elsewhere. Both say what is happening, how
far along it is, and which file is being worked on. Tasks that can be
stopped safely have a **Stop** button, and it tells you what stopping will
and will not change before you confirm.

---

## Keyboard shortcuts

Everyday File Explorer shortcuts work as you expect (tabs, copy and paste,
rename, delete, refresh). The MediaMind ones:

| Shortcut | Where | Action |
|---|---|---|
| `Ctrl+M` | Any folder | Show all files / photos and videos only |
| `1`–`9` | Who's who viewer | Name the face as that person |
| `Left` / `Right` | Viewers | Previous / next |
| `Y` `N` `I` `S` `D` | Needs your check | Yes, No, Ignore face, Skip, Delete file |
| `K` `N` `S` | Duplicates | Keep and remove others, Not duplicates, Skip |
| `F` | Any picture or video viewer | Full screen |
| `0` | Any viewer | Fit the picture again |
| `Esc` | Any viewer | Leave full screen, then go back |

---

## File safety

1. **Nothing is deleted without you confirming it.** Deletes go to the
   Recycle Bin wherever the drive has one.
2. **Moves copy first.** A file is removed from its old place only after the
   copy is complete, so a crash or a pulled cable mid-move loses nothing.
3. **You review before anything is final.** Uncertain matches are questions,
   not decisions, and a move shows you what it will do first.
4. **Every move is recorded**, which is what lets it be undone.
5. **Your folders are the truth.** MediaMind's own records can always be
   rebuilt by scanning again.

---

## Where MediaMind keeps its own data

| Place | What is there |
|---|---|
| `.mediamind\` inside each scanned folder | That folder's index of files, faces and names. Deleting it loses nothing on disk; a rescan rebuilds it |
| `%APPDATA%\MediaMind\` | The list of scanned folders, settings, the record of people across folders, and the history of moves |
| `%APPDATA%\MediaMind\logs\engine.log` | What the engine did, with any error in full |
| `~\.insightface\` | The downloaded face-recognition model |

---

## If something looks wrong

| What you see | What to do |
|---|---|
| A page says the MediaMind engine isn't running | Close the app fully and open it again. If it repeats, look at the end of `engine.log` |
| A scan seems stuck on one file | Check the strip: it names the file and how long it has been on it. Long videos on a network or encrypted drive are slow. If it is truly stuck, stop the scan and start it again |
| Who's who says the folder hasn't been scanned | Run Scan for People on that folder first, then open Who's who again |
| Faces couldn't be loaded | The folder's drive is probably not connected or not unlocked. Connect it and open the page again |
| A video shows one still frame instead of playing | Windows cannot play that video's format inside the app. **Open file** plays it in your video player |
| A folder looks empty | It may hold no photos or videos. Press `Ctrl+M` to show all files |
| An opened tab says the drive is unplugged | Reconnect the drive and press Refresh |

To read the last 50 lines of the engine log, in PowerShell:

```powershell
Get-Content "$env:APPDATA\MediaMind\logs\engine.log" -Tail 50
```

---

## Known limits

- The app installs as **Files - Dev** with a test certificate. A signed
  build under the MediaMind name is not ready yet.
- Moving a person's files, group pictures, and automatic filing from watched
  folders are the newest features and have had the least real-world use.
  Try them on a small folder first.
- Undoing a people-move puts the files back, but those files need a rescan
  before their faces show again.
- A picture moved into a different scanned folder is recognised there after
  that folder's next scan.
- Windows only for now.

---

## The older Electron app

The first MediaMind desktop app was built with Electron and lives in `app/`.
The app described in this guide replaced it. The old one still runs from
source (`npm run dev` inside `app/`), and gets no new features.
