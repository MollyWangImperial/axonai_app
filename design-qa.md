# Home Dashboard Design QA

- Source visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-fda1125a-96f6-45e6-863b-0e103897a524.png`
- Implementation screenshot: `C:\Users\LENOVO\Documents\New project\rehyn-home-implementation-final.png`
- Combined comparison: `C:\Users\LENOVO\Documents\New project\rehyn-home-comparison-final.png`
- Viewport: 1536 x 1024 CSS pixels
- Source pixels: 1536 x 1024
- Implementation pixels: 1536 x 1024
- Device scale factor: 1; no density normalization required
- State: signed-in local test profile, initial assessment not yet completed, light theme with the user's muted-brightness preference

## Full-View Evidence

The same-viewport side-by-side comparison confirms the reference hierarchy: brand and safety/settings controls, greeting and goal, points, three-step daily plan, three-domain progress board, progress link, and weekly summary. The implementation preserves the existing bottom tab navigation, so the weekly row sits just below the first viewport and remains reachable by normal scrolling.

The implementation uses the real care-plan state. The reference shows a post-assessment sample with exercises and populated trends; the captured local profile is pre-assessment, so it correctly shows the assigned initial assessment, excludes an unsafe/unassigned walking observation, and leaves progress charts empty.

## Fidelity Surfaces

- Typography: hierarchy, weight, wrapping, and zero letter spacing align with the reference and remain readable at the tested desktop and 390 x 844 mobile viewports.
- Spacing and layout: desktop grid, connectors, panel proportions, thin borders, and responsive vertical stacking are consistent with the source structure.
- Colors and tokens: restrained Rehyn green, muted app background, semantic alert color, and user brightness preference are preserved.
- Image quality: the source does not require photography or illustration on this screen; interface icons use the installed Ionicons library.
- Copy and content: labels are adapted to the actual algorithmic state instead of copying sample values.

## Focused Evidence

No separate crop was needed because the full-resolution comparison keeps the daily-plan labels, progress messages, and controls legible. The weekly summary was also opened in-browser and exposed its check-in history, activity completion, and survey schedule without console errors.

## Comparison History

1. Initial pass found a P2 state mismatch: a patient without a baseline assessment saw `Next assessment` with today's date in the third step.
2. The third step now reads Alira's selected task IDs and reports whether the `L6` walking observation is `Selected if safe` or `Not assigned`.
3. The weekly summary was updated to say `Initial assessment ready` until the baseline exists. The revised browser capture shows the corrected state and no actionable P0, P1, or P2 issue remains.

## Interaction Checks

- Weekly details toggle opens and exposes live summary data.
- `See full progress` navigates to `/progress` and browser back returns to Home.
- Browser console: no errors; only existing Expo web deprecation/support warnings were observed on the first pass.
- Production Expo web export completed successfully.

---

# Daily Life At A Glance Design QA

- Source visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-517cb756-6b33-48ef-9190-14585a852efd.png`
- Browser-rendered implementation: `C:\Users\LENOVO\Documents\New project\daily-life-desktop-final.png`
- Focused implementation crop: `C:\Users\LENOVO\Documents\New project\daily-life-implementation-panel-final.png`
- Combined comparison: `C:\Users\LENOVO\Documents\New project\daily-life-comparison-final.png`
- Desktop viewport: 1774 x 1100 CSS pixels; device scale factor 1
- Mobile viewport: 390 x 844 CSS pixels; device scale factor 1
- Source pixels: 1774 x 887; focused source panel: 1675 x 823
- Implementation pixels: 1774 x 1100; focused implementation panel: 1676 x 808
- Density normalization: none. The focused crops are shown side by side at their native pixel sizes.
- State: signed-in local patient, survey-only report, light theme, three activities mapped to full help and moving around mapped to independent

## Full-View Evidence

The desktop browser capture confirms the target structure: one framed panel, title and explanatory subtitle, source badge, one plain-language summary, four full-width activity rows with semantic rails and status pills, and a short methodology footer. The report uses a wide desktop canvas while retaining the existing assessment-report header and pager.

The 390 x 844 mobile capture confirms that rows stack without horizontal page overflow (`body.scrollWidth === window.innerWidth === 390`). Status pills use the available row width and do not clip.

## Fidelity Surfaces

- Typography: the desktop title, activity names, support labels, and supporting copy reproduce the reference hierarchy; compact sizes keep the same hierarchy on mobile. Letter spacing remains zero.
- Spacing and layout: the final panel measures 1676 x 808 against the 1675 x 823 source crop. Header, summary, four-row list, and footer align in the same order and proportions.
- Colors and visual tokens: the muted Rehyn surface, deep green text, amber help state, and soft green independent state preserve the reference semantics and the app's display-preference palette.
- Image quality and icons: the source contains UI icons rather than raster imagery. The implementation uses installed Material Community and Ionicons glyphs; no placeholder, inline SVG, or CSS-drawn asset is used.
- Copy and content: the displayed values come from the existing survey/assessment mapping. The sample wording matches the reference while unassessed activities remain explicitly separate.

## Focused Evidence

The combined focused comparison keeps all row labels, helper text, badges, rails, and footer controls legible. The implementation differs only in the exact library glyph shapes, a P3 fidelity limitation that does not change meaning or layout.

## Comparison History

1. Initial desktop pass found a P1 layout issue: the report's old 620 px content limit clipped the right-side support pills. The report canvas now expands to 1724 px on wide screens while remaining fluid on narrow screens.
2. The first focused comparison found a P2 density mismatch: the panel was 719 px tall and its typography and rows were materially smaller than the reference. Desktop typography, row heights, icon scale, status pills, and panel padding were increased; the final panel is 808 px tall against the 823 px reference.
3. The first mobile pass found a P2 clipped status pill. Compact panel padding and full-width mobile status pills removed the overflow. The revised mobile capture has no horizontal overflow.

## Interaction Checks

- `How these results are estimated` opens the methodology modal.
- The modal settles to an opaque, readable state and `Done` closes it.
- The browser-rendered DOM exposes the source badge, summary, four activity rows, four status labels, footer, and modal text.
- Current final reload has no relevant console errors. Existing Expo web support/deprecation warnings remain outside this component.
- Production Expo web export completed successfully.

final result: passed

---

# Rehab Plan Preparation Design QA

- Source visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-f9a8e0d3-17a7-4f43-b9a4-eade5acdef72.png`
- Desktop browser capture: `C:\Users\LENOVO\Documents\New project\design-qa-rehab-loader-desktop.png`
- Mobile browser capture: `C:\Users\LENOVO\Documents\New project\design-qa-rehab-loader-mobile.png`
- Desktop viewport: 1280 x 720 CSS pixels
- Mobile viewport: 390 x 844 CSS pixels
- State: assessment review complete, exercise selection active, plan creation pending

## Full-View Evidence

The live `/rehab-plan` loading branch now matches the reference hierarchy: centered page header, pale clipboard-and-heart icon, prominent preparation title, bordered vertical progress card, and a short timing expectation. The off-white background, dark green typography, restrained borders, and compact geometry remain consistent with the surrounding Rehyn report and plan screens.

## Progress Semantics

- `Reviewing your assessment` tracks retrieval of the selected assessment.
- `Choosing suitable exercises` tracks the adaptive Alira care-plan request.
- `Creating your plan` tracks dose application and stored exercise-progress assembly.
- Each stage has a short minimum display period to avoid unreadable flicker when local data returns immediately.
- The completed, active, and pending status visuals update from the real asynchronous workflow.

## Responsive And Interaction Checks

- The 390 x 844 layout wraps long stage labels without clipping and has no horizontal overflow.
- The back control remains available during preparation.
- The demo route advances from the preparation screen into `Today's plan` successfully.
- The browser reports no console errors during the transition.
- Focused ESLint, 38 feature tests, and the production Expo web export pass.

final result: passed

---

# Movement Map Design QA

- Source visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-4fe0d291-7d36-4d4c-beb5-661abb4e4c00.png`
- Browser-rendered implementation: `C:\Users\LENOVO\Documents\New project\design-qa-movement-map.png`
- Expanded-details implementation: `C:\Users\LENOVO\Documents\New project\design-qa-movement-map-details.png`
- Browser viewport: 1280 x 720 CSS pixels
- State: sample assessment, older-adult anatomy, right side affected, light theme

## Full-View Evidence

The browser capture confirms the reference structure: one framed movement-map surface, concise title and area count, front-view indicator, centered age-matched anatomy, three always-visible labeled findings, and a full-width selected-area tray. The app remains front-only because Rehyn does not capture a back view.

## Fidelity Surfaces

- Typography and spacing preserve the reference hierarchy without oversized panel text.
- Marker centers reuse Rehyn's verified anatomy coordinates. The anatomical right shoulder, hand, and knee remain on the viewer's left.
- Each marker has concentric semantic rings, a moving halo, a bright glint, and a stronger selected state.
- Marker colors and summaries come from the real domain findings and completion status rather than hard-coded sample colors.
- The narrow layout stacks the selected-area block, detail command, navigator, metrics, and plan action to prevent text collisions.

## Interaction Checks

- Selecting a marker updates the area title, status, and plain-language summary.
- Previous and next controls wrap through all highlighted areas and update the `1 of 3` position.
- `View details` expands the real task coverage, finding count, matched demand, and plan action; `Hide details` collapses it.
- Browser measurement reports no horizontal document overflow at the tested viewport.
- Focused ESLint, 48 backend/static tests, and the production Expo web export pass.

final result: passed

---

# Assessment Anatomy Marker Design QA

- Source issue: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-c9d85881-6450-4e74-8252-e3e82c876e98.png`
- Browser-rendered implementation: `C:\Users\LENOVO\Documents\New project\anatomy-markers-desktop-final.png`
- Combined comparison: `C:\Users\LENOVO\Documents\New project\anatomy-markers-comparison-final.png`
- Desktop viewport: 1872 x 846 CSS pixels; device scale factor 1
- Mobile viewport: 390 x 844 CSS pixels; device scale factor 1

## Coordinate Verification

The anatomy image and its markers now share one centered portrait coordinate frame. The desktop browser measurement confirms that the right-shoulder, right-hand, and right-knee marker centers resolve to the configured `29.5% / 21.5%`, `13% / 49%`, and `42% / 70%` coordinates inside that frame. These positions remain stable when the report expands from mobile to wide desktop widths.

## Visual And Interaction Checks

- The shoulder marker sits over the patient's anatomical right shoulder (viewer left).
- The hand marker sits over the patient's anatomical right hand.
- The lower-limb marker sits over the patient's anatomical right knee.
- Selecting the hand marker updates the detail panel to the right-hand finding.
- The 390 x 844 mobile layout retains marker alignment and has no horizontal page overflow.
- Focused ESLint and the production Expo web export pass.

final result: passed

---

# Rehab Plan Design QA

- Source visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-b63e603b-be0c-4603-a11a-8e6a196efd32.png`
- Browser-rendered implementation: `C:\Users\LENOVO\Documents\New project\design-qa-rehab-plan.png`
- Browser viewport: 1280 x 720 CSS pixels
- State: sample two-exercise plan, no exercises completed, light theme

## Full-View Evidence

The browser capture confirms the requested hierarchy: a plain-language daily plan summary, one linear progress indicator, one prominent safety notice, compact numbered exercise rows, and a centered disabled completion command. Exercise names, dose, focus, instructions, and progress remain driven by the active Alira plan.

## Fidelity Surfaces

- The page uses a 1100 px reading width, 148 px safety notice, 254 px exercise rows, and restrained 8 px corners.
- Exercise artwork is the existing Rehyn task-specific raster imagery rather than a generic placeholder.
- The old progress rings, boxed summary metrics, repeated rationale cards, and sticky completion footer are removed.
- Narrow layouts stack the rationale and exercise actions to prevent text or controls from colliding.

## Interaction Checks

- `Why this exercise?` expands both the data-derived selection reason and exercise-specific safety note.
- `Demo` opens the existing exercise demonstration modal.
- `Begin exercise` retains the guided-exercise credit check and route.
- `Complete session` remains disabled until every exercise reaches its stored repetition target.
- Browser measurement reports no horizontal overflow at the tested viewport.
- Focused ESLint, 90 focused tests, and the production Expo web export pass.

final result: passed

---

# Three-Section Assessment Report Design QA

- Source visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-aaa28e10-bfca-4bb6-886f-6d9df19dde52.png`
- Browser-rendered implementation: `C:\Users\LENOVO\Documents\New project\design-qa-three-section-report.png`
- Movement-map interaction capture: `C:\Users\LENOVO\Documents\New project\design-qa-three-section-map.png`
- Browser viewport: 1280 x 720 CSS pixels
- State: sample assessment with observed upper-limb, hand, and lower-limb tasks

## Full-View Evidence

The assessment report now presents the requested hierarchy in order: `Your movement scores`, `What this means for daily life`, and `Your movement map`. The first viewport shows the full score panel and the start of the daily-life interpretation, while normal scrolling exposes the complete activity rows and interactive anatomy map.

## Score Semantics

- Scores are derived from guided-task evidence, not hard-coded for patient assessments.
- Upper-limb scoring uses guided-step completion with explicit penalties for detected findings and shoulder compensation.
- Hand scoring uses available opening and pinch-control percentages, falling back to completed guided steps.
- Lower-limb scoring uses bilateral symmetry when available, falling back to completed guided steps.
- Missing or skipped domains display `Not observed` and no numeric score.
- The panel explicitly states that these are guided-task scores and not a clinical measure.

## Interaction Checks

- The daily-life source badge distinguishes observed, estimated, and mixed evidence.
- `How these results are estimated` retains its existing methodology modal.
- Selecting the hand marker updates the movement-map detail to `Right hand`, `Moving well`, 100% task coverage, and zero findings.
- Browser measurement reports no horizontal overflow; all three main sections measure 1120 px at the tested viewport.
- Focused ESLint, 44 report tests, and the production Expo web export pass.

final result: passed

---

# Emergency FAST Entry Design QA

- Source visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-c09f7b8b-68bc-4ef2-8d59-9887e44d2ceb.png`
- Desktop browser capture: `C:\Users\LENOVO\Documents\New project\design-qa-fast-desktop.png`
- Mobile browser capture: `C:\Users\LENOVO\Documents\New project\design-qa-fast-mobile.png`
- Desktop viewport: 1280 x 720 CSS pixels
- Mobile viewport: 390 x 844 CSS pixels
- State: pre-camera guided FAST introduction

## Full-View Evidence

The FAST entry now follows the requested safety-first hierarchy: full-screen header and leave command, unmistakable red prototype notice, immediate 999 callout, Face/Arms/Speech overview, one primary guided-check command, and concise camera/transcription disclosures. The hidden Emergency tab no longer leaves the normal app tab bar visible on this route.

## Safety And Privacy Semantics

- The page tells patients to use a phone and not wait for the check when signs are visible or symptoms began suddenly.
- Camera processing remains on-device and video is not saved.
- The speech disclosure states that a short recording is securely transmitted for transcription.
- Privacy and technical-limitations controls open readable modal details.
- Starting the guided flow adds `autostart=1`, so the existing automatic Face, Arms, and Speech runner begins without showing a duplicate intro.

## Responsive And Interaction Checks

- The 390 x 844 layout stacks the three steps and preserves readable emergency copy without overlap or horizontal overflow.
- The mobile header remains on one line without colliding with `Leave`.
- The Privacy details modal opens and closes successfully.
- Browser inspection reports no console errors.
- Focused ESLint, six emergency-flow tests, and the production Expo web export pass.

final result: passed
