# Curated, layered People pipeline (not auto-discovery)

The people flow is a three-layer pipeline — (1) detect & cluster faces, (2)
resolve clusters into named **Persons**, (3) view & consolidate — and the
People view is **curated**: only Persons the user explicitly names exist. New
faces are matched against named Persons only; a face that matches nobody is
never auto-promoted into a Person.

**Why:** The user tracks a handful of real people. Auto-discovering everyone
(Google Photos style) floods the view with background strangers — the exact
pain point that motivated the project. Curated makes "strangers can't bloat the
view" the default physics of the system.

**Consequences:** Faces that recur but are unnamed are *not* discarded — they
live on a browsable "recurring unnamed faces" surface the user can name from at
any time (so the ~40% of people without folders yet are never lost). Because of
this, the Suggestions tray only ever contains plausible matches to existing
Persons, never a wall of strangers. High-confidence matches auto-join a Person's
view silently; uncertain ones wait in Suggestions; nothing is auto-*moved* on
confidence alone.
