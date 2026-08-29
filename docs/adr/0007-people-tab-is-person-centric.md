# The People tab is strictly person-centric; Groups never hold media directly

The People tab is a projection of media **by identity**, not a mirror of the
filesystem. Its hierarchy is `Group → sub-Group → … → Person → media`, and files
appear **only under a Person**. A Group contains only sub-Groups and Persons —
never media directly. There is no "loose media in a Group" concept in the People
tab.

**Why:** The People tab exists to answer "show me everything of this person,"
regardless of where files physically live. Letting a Group hold files directly
would re-import the filesystem's messiness (loose dumps, event folders) into the
one view whose whole purpose is to abstract it away.

**How physically-loose files are handled** (e.g. a photo sitting directly in
`pop/`, not in any subfolder):
- Contains a **named Person** → shown under that Person (and under each person in
  it, for group shots).
- Contains only **unnamed faces** → goes to the recurring-unnamed-faces surface
  until named; appears nowhere in the Group tree.
- Has **no recognizable face** → not in the People tab at all (still visible in
  the physical Explorer view).

**Two distinct views:** the Explorer / physical view shows files where they sit
on disk (including loose files, by folder); the People tab re-sorts purely by who
is in each file. The Group *tree* mirrors the user's folder nesting
(`pop > kpop > twice`), but that mirror is structural (groups/sub-groups only) —
file placement is always projected up to the Person, never shown loose under a
Group.

**Opening a Group** shows its child Groups and the Persons whose home is directly
there (ADR-0008 home-Group rule), plus a "show everything below" toggle; to reach
a photo you drill to a Person. Default is direct-contents (not transitive) so the
top of a large tree stays instant to open.
