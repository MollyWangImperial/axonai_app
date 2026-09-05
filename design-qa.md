# Design QA: Affected Body Areas Survey

Reference: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-db4f0448-eeab-447e-8d5b-52ffd0ea50cb.png`

Implementation captures:

- Desktop: `output/playwright/affected-area-final-wide.png` at 1600 x 1000.
- Mobile: `output/playwright/affected-area-final-mobile.png` at 390 x 844.
- Selected state: `output/playwright/affected-area-selected.png`.

## Comparison

- The question, helper text, progress indicator, central body figure, four limb controls, and three additional-area controls follow the reference hierarchy.
- The body figure uses Rehyn's age-appropriate anatomy asset to remain consistent with the movement-map experience.
- Selected controls use a green border, soft green fill, side badge, and check icon.
- `Not sure yet` is exclusive and clears conflicting body-area selections.
- Tablet and mobile widths switch to a stacked layout so controls do not overlap and all text remains readable.
- Desktop and mobile captures showed no application console errors.

## Remaining Differences

- Rehyn's existing photorealistic anatomy asset is used instead of the reference's illustrated male figure.
- Connector lines and per-limb tinting are omitted because the app supports age-specific anatomy images and the selectable cards already provide the interactive state.

Final result: passed.

---

# Design QA: iPhone Home Layout

Source bug reports:

- `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-75fbad6f-2f84-4ced-acbd-1b233216164d.jpg`
- `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-1e5dfb77-8a7e-4a76-97ff-335266a143d0.jpg`

Combined comparison evidence:

- Daily flow: `output/playwright/iphone-day-before-after.png`
- Weekly summary: `output/playwright/iphone-week-before-after.png`

## Viewport and state

- The source captures are 1280 x 2781-pixel iPhone screenshots, approximately a 430 CSS-pixel viewport at phone pixel density.
- The corrected implementation was inspected in WebKit at 430 x 932 CSS pixels and at 393 x 659 CSS pixels.
- State: signed-in patient, not yet checked in today, initial assessment available, default text scale, light theme.

## Comparison

- Daily steps now use content-sized stacked rows on phone. The Check in button no longer collides with the next step's lock icon, and each title, status, description, and action remains within its own section.
- The weekly summary now has a full-width heading and readable summary line. Calendar and Show details occupy a separate equal-width action row instead of compressing the summary into a one-character column.
- The expanded weekly details and calendar dialog were checked separately at phone width; labels wrap normally and actions remain within the viewport.
- Home, Journey, Alira, and My Time all reported document width equal to viewport width with no visible overflowing elements.
- The iOS standalone-app status bar uses the non-overlay style so app content begins below the system status area.

## Findings

- P1 fixed: the weekly status sentence collapsed into a one-character-wide column and expanded the panel to nearly a full page.
- P1 fixed: vertically flexible daily steps allowed the first action to overlap the following lock marker.
- P2 fixed: phone header and points-badge sizing used desktop proportions and reduced available content width.
- No remaining P0, P1, or P2 responsive issues were found in the four primary tabs, the weekly expanded state, or the calendar dialog.

Final result: passed.

---

# Design QA: Affected-arm Movement Spectrum

Source visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-9d330231-65b1-4bf5-8b33-672b4d24e007.png`

Implementation evidence:

- Desktop selected state: `D:\repos\axonai_app_conflict_290826_1558\.codex-qa\affected-arm-spectrum-desktop.png`
- Local QA route: `http://localhost:4175/onboarding`
- Reference: 1999 × 786 pixels. Implementation capture: 1999 × 782 pixels.
- State: question 8 of 19, “With help” selected, default text scale, light theme.

## Full-view comparison evidence

- The final implementation and reference were inspected together at original resolution in a single comparison pass.
- The content order matches the reference: question and safety helper, centered picture prompt, four-step movement spectrum, and two large secondary choices.
- The four circular pictures use one consistent older patient, chair, palette, crop, and illustration treatment. The selected state uses the reference’s green halo, stronger border, and check badge.
- The horizontal line and “More movement” / “Less movement” cues preserve the intended left-to-right meaning without changing the stored survey values.
- Rehyn’s existing survey back control, step counter, sticky Continue action, and brand tokens are intentionally retained around the selected design.

## Focused responsive comparison evidence

- Desktop: image scale was increased after the first pass to match the reference’s dominant pictorial hierarchy and to keep labels directly below each picture.
- Mobile at 390 × 844: the spectrum becomes a two-column picture grid with a compact direction key. All six radio choices remain reachable in the existing scroll container and there is no horizontal overflow.
- The first mobile pass exposed cramped wrapping in “My arm was not affected.” The secondary-choice artwork, label, and indicator were rebalanced; the final label wraps cleanly to two lines.

## Required fidelity surfaces

- Typography: large, high-weight question and answer labels preserve the patient-facing hierarchy and remain readable on phone and desktop.
- Spacing and layout: wide screens use the reference’s single horizontal spectrum; smaller screens wrap predictably without clipping.
- Colors and states: the existing Rehyn green palette supplies the track, borders, halo, check state, and Continue action with sufficient contrast.
- Image quality: six dedicated 640 × 640 transparent PNG assets are used; no emoji, CSS drawings, inline SVG artwork, or placeholder imagery substitutes for the patient illustrations.
- Accessibility: every choice is a semantic radio with an explicit selected state and descriptive image label; controls remain large touch targets and keyboard focus remains visible.
- Behavior: selecting another answer clears the previous radio state, enables Continue, and Continue advances to “Which arm movements are difficult in everyday life?”

## Verification

- Expo web production export: passed in an isolated worktree so unrelated user worktree deletions were not modified.
- `frontend/app/onboarding.tsx` ESLint: passed.
- `backend/tests/test_survey_exercise_plan.py`: 11 passed.
- Browser console: zero application errors. One expected Expo Notifications web-support warning was observed on mobile.

## Findings and history

- P2 fixed: mobile secondary-choice copy wrapped one trailing character onto its own line.
- P3 accepted: the attached concept omits the production survey’s persistent Continue action; the existing action is retained so the real flow remains explicit and consistent.
- No remaining P0, P1, or P2 visual, interaction, accessibility, or responsive issues were found.

Final result: passed.

---

# Design QA: Forward Reach Compensation Evidence

Source visual truth: the phone-camera demonstration supplied in the conversation on 2026-09-03, showing a red dotted outline around an observed trunk and shoulder compensation.

Implementation route: `http://127.0.0.1:8001/api/rehab/runner?exercise_id=ex_reach&reps=3&test_mode=compensation_feedback`

## Visual comparison

- The live camera overlay uses a high-contrast red dotted outline around the torso for forward trunk lean.
- Shoulder hiking uses a separate red dotted shoulder-and-neck outline on the survey-selected affected side.
- The repetition feedback places the annotated camera frame directly below the score, followed by plain-language problem labels and measured degrees.
- The temporary-image label and deletion message make the short-lived handling visible to the patient.
- Desktop and 390 x 844 phone captures were inspected. Text stays readable, the image remains contained, and the feedback actions stay reachable while scrolling.

## Interaction and privacy checks

- A three-frame live streak prevents single-frame flicker; final evidence is shown only for compensation that passes the existing stricter frame-count and ratio confirmation.
- The frame is encoded only into an in-memory data URL. The capture function contains no fetch, WebView message, local/session storage, IndexedDB, or file write.
- Continue, Exit, the next repetition reset, exercise completion, and page close all clear the image source and JavaScript reference.
- The annotated frame is not included in repetition telemetry or Alira action logs.

## Findings

- No actionable P0, P1, or P2 visual or interaction issues remain.
- Actual camera-frame appearance depends on the patient's lighting and framing; the red outline geometry itself was verified in both responsive layouts.

Final result: passed.

---

# Design QA: Rehyn Landing Page

Source visual truth: conversation://rehyn-landing-reference-2026-09-03 (the 1536 × 1024 landing-page image selected by the user immediately before implementation).

Implementation evidence:

- Desktop: D:\repos\axonai_app_conflict_290826_1558\output\browser\landing-page-desktop-viewport.png
- Mobile: D:\repos\axonai_app_conflict_290826_1558\output\browser\landing-page-mobile-viewport.png
- Route: http://localhost:8090/sign-in

Viewport and normalization:

- Desktop source and implementation are both 1536 × 1024 pixels at a 1536 × 1024 CSS viewport.
- Mobile implementation is 390 × 844 pixels at a 390 × 844 CSS viewport.
- Browser density is 1 CSS pixel per captured pixel; no density normalization was required.
- State: signed-out landing page, no modal, first headline phrase (“feels clearer.”), animations settled.

## Full-view comparison evidence

- Information architecture matches the selected design: white navigation, a short deep blue-green hero with only the large recovery statement, one white transition band, and the three connected product stages below.
- All copy the user explicitly removed is absent from the landing surface. The only conversion action above the fold is the compact “Start free” header button.
- Desktop proportions, left-aligned headline, right-weighted pulse artwork, and the green/white contrast preserve the source composition.
- The mobile layout keeps the same hierarchy, moves the product stages into one readable column, preserves 44px+ controls, and shows no overlap or horizontal clipping.

## Focused-region comparison evidence

- Hero and header: the Rehyn pulse logo, navigation density, two-line display headline, dark field, and luminous right-side trajectory asset were checked at native screenshot size.
- Product story: the “Check movement,” “Follow your plan,” and “See progress” previews were checked in the rendered viewport; labels, icons, card radii, progress chart, and action affordance remain readable.
- Separate crops were not required because both focused regions are legible at 1:1 in the desktop capture.

## Required fidelity surfaces

- Fonts and typography: uses the product’s existing system-font treatment with large, high-weight display type; wrapping and line height match the source hierarchy on desktop and remain readable on mobile.
- Spacing and layout rhythm: hero height, transition-band height, page gutters, three-column stage grid, and mobile stacking follow the selected composition without repeated sections.
- Colors and visual tokens: deep Rehyn green, warm white, white headline, and brighter green changing phrase align with the supplied reference and existing product palette.
- Image quality and asset fidelity: frontend/assets/images/landing-pulse-network.png is a dedicated 1774 × 887 generated raster asset, positioned and cropped for the hero rather than approximated with placeholder shapes.
- Copy and content: removed the eyebrow, descriptive paragraph, assessment CTA, timing line, animation controls, and supporting sentence requested by the user. Rotating phrases remain concise and stroke-recovery appropriate.
- Icons: visible interface icons use the existing Ionicons family and Rehyn pulse mark.
- Accessibility and behavior: semantic headings and links are present, modal fields retain labels and test IDs, reduced-motion preferences stop rotation/drift, and large tap targets are preserved.

## Interaction and runtime checks

- Headline changed from “feels clearer.” to “moves with you.” after the timed transition.
- “How it works,” “For families,” “Sign in,” “Start free,” the preview cards, and the existing authentication modal were exercised.
- Desktop and mobile browser console checks returned zero errors.
- frontend/app/sign-in.tsx passes ESLint.
- Expo web production export completed successfully.
- Project-wide TypeScript still reports pre-existing errors in unrelated screens; no errors remain in app/sign-in.tsx.

## Findings

- No actionable P0, P1, or P2 differences remain.
- P3: the generated pulse paths are slightly quieter than the reference’s more numerous trajectories. This is acceptable because it preserves the calm visual hierarchy and keeps the headline dominant.

## Comparison history

- Final comparison pass: no P0/P1/P2 findings; no post-comparison visual fix was required.

## Implementation checklist

- [x] Match the selected simplified landing-page hierarchy.
- [x] Preserve functional navigation and account entry.
- [x] Add calm headline and hero motion with reduced-motion support.
- [x] Verify desktop and mobile rendering.
- [x] Verify production export and browser console.

Final result: passed.
