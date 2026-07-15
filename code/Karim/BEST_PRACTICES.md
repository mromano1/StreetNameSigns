# Sign capture best practices (draft)

**This is a working draft, not a finished handbook.** It reflects what's been
learned so far from actually using the capture tool, not a formal spec. Expect
it to change. If you find a case it doesn't cover, add it rather than
guessing silently, everyone capturing images should be working from the same
rules.

## Angle

Shoot at a natural drive-by angle, whatever Street View gives you by default,
not a posed perpendicular shot. Training images should look like what the
model will actually see at inference time. Grab two different headings per
sign when you have time, it helps the model generalize instead of overfitting
to one viewing angle.

**Exception, bent signs:** shoot slightly oblique, not straight-on. A
straight-on shot flattens perspective and can hide a warped or creased panel
entirely. The deformation shows up as a break in what should be a straight
edge line, and that only reads clearly at an angle.

## Zoom / distance

Close enough that damage detail is actually legible, err toward too-zoomed
over too-wide. One sign (or a tight related pair at a corner) per shot, not
a whole intersection.

## Bounding box

Default: tight crop, sign plus its mount, minimal background.

Exceptions:
- **Wrong-direction:** leave a sliver of street/intersection in frame. A
  sign-only crop can't show which way it's actually pointing.
- **Hanging:** keep the mounting bracket/pole connection in frame, not just
  the sign face. "Hanging" is defined by the abnormal angle between sign and
  mount, cropping that out hides the defect itself.
- **Bent:** keep the full panel edge in frame (don't crop into the border),
  the kink usually shows up right at the edge.

## Damage categories

Confirmed categories (see the root `README.md` for reference photos):
missing, bent/damaged, old design (white border and/or all-caps), faded,
hanging, vandalized, wrong-direction ("red flagged"), incomplete
intersection.

### Why "old design" is split into two labels here, not one

The root README and `data/annotations.csv` treat "old design" as a single
combined category (white border and all-caps together). This tool instead
labels them as two independent categories, `white-border` and `all-caps`,
on purpose, and this matters for whoever trains a YOLO model on this data,
not just for capture:

All-caps and white-border are two separate, unambiguous visual features. A
labeler can say yes/no to each with high agreement. Lumping them into one
"old design" category forces the model to learn a single decision boundary
over signs that might have just one feature, just the other, or both, which
is exactly the kind of within-class variance that produces a noisier, less
precise classifier. Two clean binary labels generally train better than one
composite label whenever the underlying features don't perfectly co-occur,
and in practice they don't always co-occur here.

If you need "old design" as a single category anywhere downstream (matching
the README's language, a stakeholder demo, whatever), derive it as a rule
after the fact: `old_design = all_caps OR white_border`. Keep the model's
training labels split, since that's the better training signal, and compute
the composite label in post-processing rather than baking it into what the
model has to predict directly.

This is still an open reconciliation point with the rest of the pipeline
(see QUICKSTART.md), raise it before assuming either convention is final.

Note: the capture tool currently has separate buttons for white-border and
all-caps rather than one combined "old design" category, and doesn't have an
incomplete-intersection button yet (it captures intersection *type" as a
separate field instead). Reconciling the tool's categories with this list
exactly is an open item, not resolved yet, flag inconsistencies rather than
silently picking one convention.

## Missing signs: how to find and capture them

Unlike the other categories, there's no sign to photograph, so the heuristic
comes from the SIMS record and intersection geometry, not from the image.

- You already know exactly where a sign *should* be from the SIMS match
  (which corner, which street). Go there and check whether it's actually
  present.
- Use the intersection-type field the tool already asks for as the real
  detection logic: a 4-leg intersection should have 2 complete sign pairs, a
  T-intersection needs 1, dog-legs have their own rule. Count what's
  actually present against what that geometry expects. If the count comes up
  short, the specific corner that's short a sign is your missing-sign flag,
  this is the same rule-based logic the project scope describes for the
  missing-sign business rules.
- For the shot itself, skip the tight crop. Take a **wide contextual shot of
  the pole/mounting point** where the sign should be, an empty bracket (if
  visible) is stronger evidence of absence than a shot with no obvious
  mounting hardware at all. The story here is told by the metadata (corner,
  intersection type, SIMS order number), not by the image content, since
  there's nothing to see.

## Red flagged / wrong-direction signs: how to identify them

This category is about readability from the expected approach, not the
sign's physical condition.

- Street name signs are meant to be legible to traffic approaching from the
  cross street. Stand where that traffic would actually be and try to read
  it head-on. If you have to walk around to the back to read it, or the
  blade is turned edge-on to the street instead of facing traffic, that's
  the tell.
- A sign whose face points into a building, an alley, or away from the
  intersection entirely is an unambiguous case.
- The compass HUD can help here too: a street's grid orientation is roughly
  known ahead of time, so a sign rotated well off the expected angle relative
  to the street it names is a geometric flag, not just a visual gut call.

## Class balance

Deliberately capture some of every damage category you care about, not just
whatever's easiest to find, an imbalanced set biases the classifier. Capture
some no-damage examples too, the model needs negatives, not just damage
cases.

**Tip: use Street View's historical imagery to find damaged examples when
current imagery is mostly healthy signs.** DOT tends to repair the worst
offenders over time, so a corridor walked today will often skew toward "no
damage" even if damage was common there in the past. Google's Street View
viewer shows a small clock/calendar icon when multiple historical captures
exist for a location, letting you scroll back through past years, some of
those older captures may show a sign that's since been replaced or repaired.
This is genuinely useful for building out damaged-category training examples,
but tag these captures clearly (a note like "historical, [approx year],
condition may since be repaired") so nobody later mistakes them for a live
report of current condition, the whole point of tying captures to a SIMS
order number is that DOT can act on it, and an already-fixed sign isn't
actionable.

## Image quality

Skip frames with heavy glare, motion blur, or the sign half-occluded by a
truck, pole, or tree. A technically-fine shot that's visually noisy for the
wrong reason teaches the model bad signal. Prefer well-lit panoramas over
dusk/night ones where available.

## Metadata discipline

Verify the tool's auto-matched street names before saving, the corner match
is nearest-by-GPS, not guaranteed correct near dense intersections. Pick the
specific sign/corner from the candidate list rather than leaving whatever's
pre-selected by default.

## Historic district ("brown") signs

About 15% of corners in at least one tested ZIP code (10001) have only
historic-district-style signs, no standard green sign at all, concentrated in
areas like the West Village. These may be intentionally styled differently
(mixed case, different border) by design, not damaged. Whether/how to apply
the standard damage categories to these signs is an open question for the
DOT contacts, not resolved, don't guess at it case by case.
