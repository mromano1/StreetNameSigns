# Stakeholder handoff email template

Per `docs/superpowers/plans/2026-08-04-stakeholder-packaging-plan.md` section 4:
one email, one zip (or link), one video link, a time estimate, and a contact.
Keep it this short -- the video and `INSTALL_GUIDE.md` carry the detail.

Fill in the bracketed parts before sending.

---

**Subject:** Street Sign Capture -- 5-minute install

Hi [NAME],

This is a small Chrome extension for flagging damaged street signs while
browsing Street View or Cyclomedia Street Smart -- draw a box around a
sign, pick what's wrong with it, and it saves the details for us. No
account, no install beyond Chrome itself, and it works fully offline once
installed (it never talks to any city database directly -- see the "this
is normal" section in the attached guide if you're curious why).

**It takes about 5 minutes to set up.** Two ways to do it:

1. **Watch first (recommended):** [90-SECOND VIDEO LINK] shows the whole
   install and one real capture, start to finish, no sound needed.
2. Then follow the attached `INSTALL_GUIDE.pdf` step by step -- it has a
   screenshot for every step.

**Attached:** `street-sign-capture-extension-v[VERSION].zip`
(if it's too large for email, use this link instead: [ONEDRIVE LINK])

Once you've done a few captures, open the extension's icon in Chrome's
toolbar, click **Export CSV**, and send that file back to me (the guide's
last step shows exactly where it saves).

If anything looks broken or confusing at any point, stop and reach out --
don't try to work around it. I'm at [EMAIL/PHONE].

Thanks,
[YOUR NAME]

---

## Notes for whoever sends this (not part of the email)

- Confirm the zip was built with `python scripts/build_extension_package.py`
  *after* regenerating `signs_data.json` for this stakeholder's actual
  browsing area (see the packaging plan section 1) -- the build script
  hard-fails if the coverage doesn't match `EXPECTED_ZIPS`, so a clean run
  means this is already checked.
- Record the video with Xbox Game Bar (Win+Alt+R) per the packaging plan
  section 4 -- don't attempt to script/automate this.
- Double check the recipient's `welcome.html` "try it" link (in the zip)
  actually points at a corner *you've personally confirmed* has a visibly
  damaged sign, not just SIMS coverage -- see the comment in
  `extension/welcome.html`.
