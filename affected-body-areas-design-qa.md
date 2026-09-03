# Affected Body Areas Design QA

- Reference: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-db4f0448-eeab-447e-8d5b-52ffd0ea50cb.png`
- Desktop capture: `output/playwright/affected-area-final-wide.png` at 1600 x 1000.
- Mobile capture: `output/playwright/affected-area-final-mobile.png` at 390 x 844.
- Selected-state capture: `output/playwright/affected-area-selected.png`.

The implementation follows the reference hierarchy with a central age-appropriate anatomy image, four labelled limb selectors, separate face/speech, another-area, and unsure controls, strong selected states, and an account-compatible answer model. Tablet and phone widths use a stacked layout so controls and labels do not overlap.

Interaction checks passed: multiple affected areas can be selected, `Not sure yet` clears conflicting selections, selecting a specific area clears `Not sure yet`, and the existing typed description flow remains connected to `Another area`. The final browser pass reported no application console errors.

The implementation intentionally retains Rehyn's age-specific photorealistic anatomy assets rather than substituting the reference's single illustrated male figure.

Final result: passed.
