# Nested Group tree mirroring folders; one home Group per Person

Groups form a **nested tree that mirrors the user's physical folder nesting**
(`pop > kpop > twice`), built by bootstrap (ADR-0002) from the folder structure.
A Person belongs to exactly **one home Group** — the Group whose folder contains
their Primary Location. Opening a Group shows **direct contents only** (its child
Groups and the Persons homed directly there), with an optional "show everything
below" toggle.

**Why nested, not flat tags:** the user already built this hierarchy on disk and
wants the People tab to navigate like the folder structure. Mirroring reads it
for free.

**Why one home Group, not multi-membership:** a Person's folder physically lives
in exactly one place, so one home keeps Consolidation's destination unambiguous.
The cross-group case (a collab photo, a two-band member) is already covered by
the **Person axis** — a photo shows under every Person in it regardless of which
single folder it lives in — so multi-Group membership buys little. If a real need
appears, add lightweight *cross-listing* (show a Person under a second Group
without moving their folder) later; not built now.

**Why direct-contents, not transitive, by default:** a top Group like `pop` can
sit above tens of thousands of files; always loading descendants would make the
top of the tree the slowest thing to open, contradicting the "instant browsing"
requirement. Direct-contents keeps every level instant; the toggle covers the
occasional full sweep.
