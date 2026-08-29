# Folder placement overrides the face model; per-person consistency check is the counterweight

A file sitting directly inside a Person's bound folder is a **confirmed human
label**: it is attributed to that Person regardless of the face model — no
detected face, or a face the model reads as someone else, does not change it. The
face model still runs on the file to catch *other* people in it (a group photo
saved into one person's folder still surfaces the others), but it can never
*remove* or *override* the placement attribution, and the folder's own person
never needs Suggestions review for that file.

**Why:** Two of the project's deepest rules — "the filesystem is the source of
truth" and "human review beats machine." A folder the user maintains by hand *is*
a human labelling. The face model misclassifies; the user's hand does not (about
their own intent).

**This inverts current behaviour.** Today (`store/bindings.py`), membership
inside a bound folder is still decided by the face model: a file whose faces
don't match the bound person is treated as an **outlier** and set aside. Placement
does not currently override the model — this decision reverses that.

**The counterweight — a per-person consistency check (on demand).** The model's
disagreement is not discarded, only demoted to advisory. On request, MediaMind
sweeps a Person's files, runs face recognition, and flags every file the model
disagrees with (no matching face, or a face matching a *different* named person),
ranked by how strongly it disagrees. The user then **confirms** (model was wrong,
keep) or **corrects** (move to the right person). This reuses the existing outlier
computation — surfaced as an audit tool rather than only used to withhold routing.

**Consequences:**
- Misfiling risk is accepted but catchable: dropping Dad into Mom's folder shows
  as Mom, until the consistency check flags it and the user corrects it.
- Synergy with video (ADR-0011 / Q12): a shaky, low-confidence video normally
  routes to Suggestions, but a video saved directly into a person's folder is
  confirmed by placement and skips review.
