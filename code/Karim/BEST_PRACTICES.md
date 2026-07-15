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

Note: the capture tool currently has separate buttons for white-border and
all-caps rather than one combined "old design" category, and doesn't have an
incomplete-intersection button yet (it captures intersection *type" as a
separate field instead). Reconciling the tool's categories with this list
exactly is an open item, not resolved yet, flag inconsistencies rather than
silently picking one convention.

## Class balance

Deliberately capture some of every damage category you care about, not just
whatever's easiest to find, an imbalanced set biases the classifier. Capture
some no-damage examples too, the model needs negatives, not just damage
cases.

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
