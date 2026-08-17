# INSTALL_GUIDE.md rewrite -- outline

Structural outline only, per the packaging plan section 4. Not the final
doc -- screenshots and the recording need Karim's hands-on session (real
Chrome UI, real Street Smart account), and the earlier attempt at
automating that stalled, so it's deliberately not attempted here. This
outline exists so writing the final doc is filling in known slots, not a
redesign. Export the final version to PDF, same as the current guide's
existing pattern.

**What's changing vs. the current `INSTALL_GUIDE.md`:** the current guide's
Step 2 ends on ambiguity ("a card should appear") with no positive
confirmation, and never documents where captures are saved or how to send
them back at all. Both are fixed below by the welcome page (already built,
`extension/welcome.html`) and a new final step.

---

### Front matter (before Step 0)

- One-paragraph "what this is," matching the handoff email's wording so
  the two documents don't drift (`extension/HANDOFF_EMAIL_TEMPLATE.md`).
- "Before you start" checklist -- keep the current guide's three bullets
  (Chrome only, the zip file, their own Street Smart login) unchanged,
  still accurate.
- State the time estimate up front: "about five minutes." (Plan section 4:
  "Setting the time expectation up front is most of the battle.")

### Step 0: Watch the video first

- One line: link to the ~90-second recording, framed as the primary
  artifact -- "this guide is the reference, not the first thing to read."
- **No screenshot needed** (it's a video link).

### Step 1: Unzip

- Keep current guide's Windows/Mac unzip instructions (still accurate,
  don't rewrite).
- **Add the load-bearing warning currently missing:** *"Put this folder
  somewhere permanent, like Documents. Chrome reads from it every time you
  use the tool -- don't delete it or move it to the Recycle Bin later."*
  (Verbatim from plan section 4 -- this exact framing, not a paraphrase.)
- **Screenshot needed:** Windows right-click context menu with "Extract
  All" circled.

### Step 2: Developer mode (the "scary part," defused)

- Open with the reassurance paragraph from plan section 4, verbatim:
  > "Chrome has a setting called 'Developer mode.' You'll need to turn it
  > on. This sounds alarming and it isn't -- it's just Chrome's way of
  > saying 'this add-on came from a person, not from Chrome's store.' It
  > doesn't change anything else about your browser, and you can turn it
  > back off when you're done using the tool."
- Then the mechanical steps (keep current guide's steps 2-5, still
  accurate: `chrome://extensions`, toggle, Load unpacked, pick folder).
- **Screenshots needed (4):**
  1. Address bar showing `chrome://extensions` typed in
  2. Developer mode toggle circled (upper right)
  3. "Load unpacked" button circled
  4. Folder picker showing a **correct** selection (the unzipped folder
     itself, not its parent) -- plan section 4 flags this as where people
     get it wrong; caption should say so explicitly.

### Step 3: Instant confirmation (replaces old Step 2's ambiguous ending)

- Explain that a new tab opens automatically the moment install succeeds
  (the welcome page, already built) -- no guessing required.
- Walk through the welcome page's own two steps as they appear on screen:
  pin the toolbar icon (with the puzzle-piece menu screenshot the welcome
  page itself references as a placeholder), then the "Open Street View and
  try it" button.
- **Screenshot needed:** the welcome page itself, mid-flow, with the pin
  step highlighted -- this can be a straight screenshot of
  `extension/welcome.html` once Karim swaps in a confirmed-damaged corner
  (see note in that file).

### Step 4: First capture, guided

- Explain what happens after clicking "Open Street View and try it" --
  floating Capture Sign button appears within a second or two at a
  location already known to work.
- Walk through one full capture: click Capture Sign, drag a box, fill the
  confirmation panel, Save.
- **Screenshots needed (3):** floating button visible on the page, the
  drag-box mid-selection, the filled-in confirmation panel before saving.

### Step 5: Where files go, and sending them back (net new -- currently
undocumented anywhere)

- State plainly, per plan section 4: captures save to **Downloads /
  manual_capture**. Export CSV from the popup lands in the same folder.
  Zip that folder (**Send to -> Compressed (zipped) folder**) and email it
  back.
- **Screenshots needed (3):** the popup's Export CSV button, the
  Downloads/manual_capture folder in File Explorer, the right-click
  "Send to" menu with the zip option visible.

### "This is normal" section (preemptive, not reactive troubleshooting)

Keep as a named section distinct from actual troubleshooting below --
these are expected, not errors:

- Chrome's developer-mode startup warning bubble -- dismiss with the X.
- "Outside your loaded SIMS data area" -- keep the current USER_GUIDE.md
  wording verbatim, plan section 4 calls it out as already good.
- The floating button only appears on Street View / Street Smart pages,
  on purpose.
- Reopening Chrome later: everything's still installed, nothing to redo.
- **New, per the SIMS-bundling work (packaging plan section 3.5):** the
  tool never queries any NYC DOT database while in use -- sign location
  data was already downloaded into the package.
- **No screenshots needed** -- this section is text-only reassurance.

### Troubleshooting (kept from the current guide, still accurate)

- Nothing appears -> refresh the page.
- Edited/replaced the extension folder -> reload extension **and** refresh
  the page (both required).
- Capture button stuck on "Capturing..." -> same fix as above.
- Still stuck -> contact Karim with a screenshot.
- **No new screenshots needed** -- carry over from the current guide as-is.

---

## Screenshot count for planning purposes

**11 total** (down from needing to guess): 1 unzip, 4 Developer-mode
steps, 1 welcome page, 3 first-capture, 3 export/send-back (one item, the
right-click zip menu, could double as a shared Step-1-style screenshot if
convenient). Matches the plan's "roughly twenty minutes of work" estimate
for hand-capturing with Snipping Tool (Win+Shift+S).
