# MediaMind — Domain Language

The shared vocabulary for MediaMind's people/facial-recognition flow: the
filesystem-first system that finds people across a user's scattered media,
shows them in a fast virtual view, and — on command — files their media into
real folders. This glossary is the source of truth for what each term *means*;
it deliberately holds no implementation detail or decisions (those live in
`docs/adr/`).

## Language

### People and identity

**Person**:
A named human identity the user has deliberately created. A Person exists only
because the user named it — the system never invents one. It owns a virtual set
of media and, optionally, a Primary Location.
_Avoid_: face, identity, contact.

**Cluster**:
A raw machine-produced grouping of similar-looking faces, before any human has
named it. A Cluster is a guess; a Person is a decision. Naming a Cluster is what
turns it into (or merges it into) a Person.
_Avoid_: group, bucket.

**Group**:
A named node in the People tab that holds **only** sub-Groups and Persons —
never media directly. Groups form a tree that mirrors the user's folder nesting
(e.g. `pop > kpop > twice`) and reflects relationships the user holds in their
head (Family, Friends, BLACKPINK). A Person has exactly one home Group (or none,
standing alone); a Group may optionally bind to a physical parent folder.
_Avoid_: folder, album, cluster, category.

**Recurring unnamed face**:
A face that appears repeatedly across the collection but belongs to no named
Person yet. Kept out of the main People view, but browsable on its own surface
so the user can find and name it at any time — not dependent on the system
prompting them first.
_Avoid_: unknown, stranger, pending person.

### Views and places

**People view**:
The fast, non-destructive virtual view of all Persons (and Groups). Shows every
photo/video of a Person regardless of where it physically lives. Reading it
never moves, changes, or deletes a file.
_Avoid_: gallery, album, people tab (as a formal term), library.

**Primary Location**:
The real on-disk home folder the user designates for a Person — usually a folder
that already exists in their hand-built structure. It is the destination for
Consolidation. A Person can exist without one.
_Avoid_: home folder, target folder, destination.

**Consolidation**:
The reviewed, user-initiated physical move of a Person's scattered media into
their Primary Location (copy-then-delete, per the safety invariants). The only
operation in the people flow that moves a byte on disk.
_Avoid_: sort, organize, export, filing.

### Review and quality

**Suggestions**:
The review tray where the system surfaces things needing a human decision:
uncertain face matches (below the auto-join confidence) and — at top priority —
detected Duplicates. Cleared by the user confirming, reassigning, or dismissing.
_Avoid_: pending, notifications, inbox.

**Duplicate**:
A redundant copy of media the collection already holds. Broader than same-name /
same-size: includes visual near-duplicates (same image at a different
resolution, size, or filename) and video sub-clips (a shorter clip wholly
contained in a longer video the user already has).
_Avoid_: copy, redundant file.

### Drives and state

**Volatile drive**:
A drive that can appear and disappear during normal use — a Cryptomator mount, a
cloud-backed drive, a removable drive — as opposed to an always-present fixed
local drive. The people flow treats these as first-class, not edge cases.
_Avoid_: external drive, network drive (too narrow).

**Offline** (of media):
State of media whose file currently lives on an unmounted Volatile drive. Still
shown in the People view from the catalog, badged as offline; openable and
movable only once the drive is remounted.
_Avoid_: missing, unavailable, lost.
