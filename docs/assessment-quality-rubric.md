# Assessment Quality and Rewards

Version: `rehyn-task-quality-1`. These are camera-guided task scores, not Fugl-Meyer,
ARAT, strength measurements, diagnoses, or clinically validated recovery scores.
Reference values are configurable engineering targets requiring clinician review.
They do not instruct a patient to force movement or exceed comfortable ROM.

## Calculation

- Upper limb, hand and lower limb each have a maximum of 100.
- The assigned tasks divide that module equally. Each task's defined steps have
  equal weight inside that task. Missing tasks/steps stay in the denominator.
- Step score = (20 for observed target completion + 80 times mean reference-ROM
  attainment) times the form factor. Each confirmed compensation reduces the form
  factor by 0.2, with a floor of 0.4. Attainment is capped at 1.
- ROM uses median measurements at the endpoint, not a straight elbow at rest or
  a single best frame. At least five fresh samples are needed for each criterion.
- An explicitly recorded assisted task has its score halved. Needing a helper
  in the survey alone is not proof that a task was physically assisted.
- Missing ROM or postural evidence gives `null`, not zero or 100. Unobservable
  individual compensation checks are separately marked as not measured.
- Old results retain their completion status. New measurements are not invented
  retrospectively. Uploaded walking videos without step-specific evidence stay
  ungraded rather than treating successful upload as perfect walking.

## Detection

The rubric in `backend/assessment_quality.py` covers every defined assessment step.
Examples: forward reach uses 150-degree elbow extension and 60-degree arm elevation;
hand-to-mouth uses 110-degree elbow flexion; hand opening and pinch use 0.8 of the
existing gesture metric. Returns and setup use target control plus posture.

`backend/assessment_quality.js` collects same-model pose world coordinates,
landmark visibility of at least 0.65 and the selected affected hand. It calibrates
against a stable median resting posture. Compensation requires 500 ms of sustained
evidence; a tracking gap resets the active warning. Red dotted paths mark the
corresponding body region, with a correction alongside the camera.

Supported checks: trunk lean, excess shoulder lift beyond an arm-elevation
allowance, head drop in hand-to-mouth, wrist alignment changes and pelvis hiking.
Deliberate trunk shifts and sit-to-stand movement are excluded from trunk warnings.
Coarse pose finger points cannot reliably distinguish inward from outward wrist
bend; feedback says alignment change, and foreshortened/occluded views abstain.
These checks do not cover every possible clinical compensation.

Reference context (not validation of the numerical rubric):
- [MediaPipe pose landmark outputs and visibility](https://ai.google.dev/edge/mediapipe/solutions/vision/pose_landmarker)
- [Canadian Stroke Best Practices: upper extremity rehabilitation](https://www.strokebestpractices.ca/recommendations/stroke-rehabilitation-delivery/1-initial-stroke-rehabilitation-screening-and-assessment)

## Rewards

Rewards do not depend on movement grade: 10 for the entire daily plan, 20 for each
completed saved assessment (initial or later), and 2 for the daily check-in.
No repetition, individual exercise, caregiver routine or weekly-round bonuses.
Test shortcuts do not earn real assessment points. Award identities are the
account's calendar date and unique assessment id, respectively.

## Verification

- 134 focused Python tests and five Node tracking tests passed after integrating
  the latest shared-branch update.
- Production web build and ESLint on edited UI files passed.
- Desktop Chrome and iPhone-sized WebKit checked with synthetic local fixtures:
  results expansion, task feedback, scrolling, continuation and no horizontal
  overflow. Canvas checks confirmed a red dotted warning renders when active
  and renders no warning when inactive.
- Account save/reload regression test preserves raw per-step evidence and scores.
- Physical camera accuracy still needs patient/clinician testing. Browser tests
  verify rendering and logic, not real-world diagnostic accuracy.
- Full TypeScript checking still reports pre-existing errors in assessment.tsx,
  exercise.tsx and persona-chat.tsx, outside these changes.

## Settings testing results

Settings > Testing defaults to the six initial patient tasks T1, T2, T3, H1,
H3 and H4; the L6 walking upload is excluded from this list. Existing guided
exercises remain on their own tab. Tests launch one selected task through the
same camera calibration, instructions and target checks used for patients.

Completing a test sends its transient step evidence to
`POST /api/testing/assessment-score`. The signed-in endpoint calculates the
existing rubric, returns step equations and supplemental measurement summaries,
and performs no patient-history, care-plan, credit or reward writes. Failed
calculations can be retried without repeating the movement; missing evidence
stays unscored. Retesting starts a fresh runner and returning dismisses to Testing.

Supplemental shoulder elevation, elbow extension/bend, shoulder-to-wrist reach
normalised by arm length, trunk lean, shoulder lift, wrist alignment and target
occupancy are captured from valid samples. They do not introduce a new scoring
formula. Shoulder elevation is an upper-arm/torso angle, not isolated sagittal
shoulder flexion. Per-step summaries show the median of up to 600 recent valid
samples, an endpoint median of up to 120 in-target samples when at least five
exist, full-step extrema and sample counts. Target occupancy counts all valid
samples. Duration includes instructions and waiting, not just movement time.

Tests cover the six-task list, authentication, invalid task/step IDs, missing
measurements, exact score components, and isolation from patient storage.
Browser verification uses synthetic evidence, not a physical patient movement.
