// Maps a /predict response's predicted classes back to the capture panel's
// damage buttons, for pre-highlighting a guess before the user picks.
// Mirrors PHYSICAL_BUTTON_TO_CLASS in scripts/prepare_yolo_dataset_physical.py
// -- keep both in sync if that mapping ever changes.
const PHYSICAL_BUTTON_TO_CLASS = {
  bent: 'bent_damaged',
  'white-border': 'old_design',
  'all-caps': 'old_design',
  faded: 'faded',
  hanging: 'hanging',
  vandalized: 'vandalized',
};

// predictedClasses: [{class_name, confidence}, ...] from the /predict
// response. Returns { [buttonValue]: { preselect, confidence, hint } } for
// every button PHYSICAL_BUTTON_TO_CLASS knows about. Policy: a capture must
// never be savable purely on the model's own unconfirmed guess (a wrong
// guess could otherwise become a training label for the next retrain and
// entrench itself, especially for classes with very few real examples). So
// no class is ever pre-selected -- every matching button, whether the class
// maps from exactly one button (e.g. faded) or more than one (old_design ->
// white-border/all-caps), only hints the guess and leaves preselect false.
// The user must click every damage button themselves, every time.
function buildDamageGuessPlan(predictedClasses) {
  const plan = {};
  for (const buttonVal of Object.keys(PHYSICAL_BUTTON_TO_CLASS)) {
    plan[buttonVal] = { preselect: false, confidence: null, hint: false };
  }

  for (const { class_name: className, confidence } of predictedClasses || []) {
    const buttons = Object.keys(PHYSICAL_BUTTON_TO_CLASS).filter(
      (btn) => PHYSICAL_BUTTON_TO_CLASS[btn] === className
    );
    for (const btn of buttons) {
      plan[btn] = { preselect: false, confidence, hint: true };
    }
    // buttons.length === 0: predicted class has no matching button (e.g. an
    // unrecognized/future class name) -- ignored, that button's plan stays
    // at its default.
  }

  return plan;
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { buildDamageGuessPlan, PHYSICAL_BUTTON_TO_CLASS };
}
