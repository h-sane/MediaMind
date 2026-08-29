# Duplicate detection is part of the people pipeline, not a separate module

Duplicate detection runs inside the **same ingest pass** as face detection.
Duplicates surface at the **top of Suggestions**, ahead of other review. And
Consolidation shows a **soft-but-unmissable inline duplicate check** (with
"skip the duplicates" preselected) so redundant copies can't be filed into a
Primary Location unseen — but it never hard-blocks a move.

**Why:** Duplicate detection exists solely to serve collection quality. Run as a
separate module, it lets Consolidation faithfully copy 14 duplicates of a photo
into an otherwise-clean folder. It must be *upstream* of the move. The user's
typical workflow resolves duplicates first (early) and consolidates last, so the
move-time check is a backstop, not the main event.

**Consequences:** Never auto-deletes — duplicates are surfaced as a cluster with
a suggested keeper for the user to confirm (consistent with the project's
never-delete-without-confirmation rule). "Duplicate" is broader than
name/size: it includes visual near-duplicates (same image at different
resolution/size/filename). **Video sub-clip detection** (a short clip wholly
contained in a longer video) is deferred to a later phase as a distinct, heavier
problem (temporal fingerprinting), after exact + visual-near-duplicate for
images and whole-video duplicates ship.
