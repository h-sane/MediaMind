# People view is an offline-resilient catalog over an off-drive index

The People view is backed by a **global index stored in app-data** (not inside
the library folder), with **thumbnails keyed by content-hash** rather than a
live file `stat()`. So a Person's media that lives on a **volatile drive**
(Cryptomator, cloud-backed, removable) still displays — badged **offline** —
when that drive is unmounted, and browsing is instant because it reads the
catalog instead of decrypting the drive.

**Why:** Today the per-library index lives *inside* the library folder, so it
vanishes when the Cryptomator drive unmounts; and thumbnails are keyed by a live
`stat()`, so the cached preview (which physically survives in app-data) becomes
unreachable when the original is offline — blank tiles. Every browse also paid
Cryptomator's per-file decryption cost. Volatile drives are first-class for this
user, not an edge case. Choosing the catalog model fixes the breakage *and* the
slowness with one decision.

**Considered and rejected:** a live-only view (show only what's mounted now) —
simpler, but it's exactly the vanishing-act the user needs eliminated.

**Consequences:** Stays within the project rule "filesystem is the source of
truth; the index is a rebuildable cache" — nothing lives *only* in the catalog;
a cached thumbnail of an offline file is a remembered preview of on-disk truth,
reconciled when the drive returns. Operations that need the actual bytes
(opening a full video, Consolidating onto the drive) are gracefully disabled
("mount the drive to do this") or queued until it remounts — never faked. The
preview cache stays hard-bounded (existing 2 GB LRU cap); content-hash keying
means duplicates share one cached thumbnail.
