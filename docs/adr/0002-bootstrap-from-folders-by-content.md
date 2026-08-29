# Bootstrap Persons/Groups from existing folders by face content, reviewed

On setup, MediaMind proposes Persons, Groups, and Primary Locations by reading
the user's existing folder structure — but judged by each folder's **face
content, not its name**, and always as a **proposal the user confirms**, never
an automatic commit. A folder is proposed as a Person only if one person covers
≥75% of its face-photos; as a Group only for a small recurring set of people;
otherwise nothing is proposed and the folder is left untouched.

**Why:** The user's folders already encode their relationships (`Family/`,
`Friends/`, per-person subfolders), so reading them imports the whole
relationship map for free. But folder *names* are unreliable — `marriage/`,
`beach/`, `unsorted/` are events or deliberately-mixed dumps, not people.
Content (whose faces, how consistently) is the only trustworthy signal, and it
correctly leaves events/mixed folders unclassified.

**Consequences:**
- "Not proposed as a Person" ≠ "excluded from the People view" — every folder is
  still face-scanned, so a Person's photos sitting in a mixed folder still
  appear under them.
- Ambiguous folders are left quietly alone (not interrogated one-by-one); their
  faces feed the view to be named at leisure. A reject/lock handles the rare
  false positive.
- A Group may *optionally* bind to a physical parent folder but is not required
  to (e.g. a view-only "BLACKPINK" group with no folder).
- A manual "mark this folder as a Group" override exists for legitimate large
  groups the size heuristic misses (9+ member idol groups); the auto-detect size
  cap is relaxed toward the domain, with face-coverage as the real group/event
  discriminator.
