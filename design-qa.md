# Rehyn landing page and discovery survey verification

Date: 2026-09-16

## Findings

No outstanding P0/P1/P2 visual or interaction findings.

- Initial browser checks found that React Native Web did not expose the radio selection through accessibilityState. Switched to aria-checked and supplied explicit progress ARIA values. The final browser run confirms selected answers remain accessible after Back and Review.
- The larger header action intentionally replaces the original Explore label. The desktop breakpoint is now 1120 pixels so navigation and branding remain within the viewport.
- The new survey is an interest-based introduction, not an eligibility or recovery assessment. Every completed path offers relevant Rehyn features and a sign-up action. The existing trial-code requirement is disclosed before sign-up.

## Visual truth and evidence

- Source layout: user-supplied 4e6e064503444ec02ec7af189157a602.png, copied to .codex-tmp/landing/reference.png (1746 x 901 pixels).
- Source logo: frontend/assets/images/rehyn-logo.png (306 x 95 pixels); existing transparent display version retained. Dominant brand green: RGB (0, 74, 56), #004A38.
- Updated visual asset: frontend/assets/images/rehyn-landing-hero-realistic.png (1746 x 901). Image-generated revision with natural daylight, skin texture, plain clothing and a less polished home setting, as requested. It is illustrative, not a patient testimonial.
- Implementation route: /sign-in. Browser screenshots are in .codex-tmp/landing-discovery/.
- Viewports: desktop.png 1746 x 901; laptop.png 1366 x 768; small-desktop.png 1120 x 740; tablet.png 768 x 1024; mobile.png 390 x 844; small-mobile.png 320 x 740. CSS and image dimensions match; device scale factor 1.
- State: signed out with default display preferences. Each viewport also has -survey.png, -result.png and -signup.png captures. These new modal states have no supplied raster reference and use the existing app's dialog conventions.
- Full-view comparison: opened the 1746 x 901 source and updated implementation in the same comparison input. The photo, header label and supplied logo are intentional user-requested differences; headline hierarchy and composition remain aligned with the original layout.
- Additional review: opened the 1120-pixel landing capture and desktop result, then the mobile landing, question, result and small-phone sign-up captures. No horizontal clipping or inaccessible controls. Long results and narrow-screen forms scroll within the dialog.
- Focused regions: logo, navigation, headline and buttons are readable at source resolution; no enlarged crop was needed.

## Comparison history

- Prior landing iteration resolved logo background edges, narrow headline wrapping and a tablet crop that cut off the subject's head. Those corrections are retained.
- Current visual comparison found no new P0/P1/P2 mismatch. The accessibility issue above was corrected and the complete interaction suite rerun against the rebuilt production bundle.

## Required fidelity surfaces

- Typography: the existing dark-blue, three-line desktop headline remains. The longer header action has responsive sizing and wraps on phones. Survey questions use a clear heading, short supporting sentence and large answer rows; results preserve a readable hierarchy.
- Spacing: original left alignment and desktop negative space are retained. Compact layouts stack copy above the photo. Survey controls have at least 48-pixel action heights; option rows begin at 66 pixels. Modal content scrolls on small screens.
- Colours: landing and survey actions use the supplied logo's #004A38. Selected answers use a pale green fill and checked icon. Disabled Continue is visually muted and cannot advance.
- Images: the regenerated photo retains the seated reaching subject and phone at right. The original supplied logo remains unchanged. Ionicons provide interface icons; no simulated raster assets or placeholder images.
- Copy: upper-right action reads "See if Rehyn could help you". Four questions cover everyday goals, movement curiosity, preferred support and who the visitor is exploring for. Results reflect those choices and invite sign-up without a fabricated score or recovery prediction. The main Explore Rehyn action remains available.

## Verification

- Production Expo web build passed.
- TypeScript and ESLint passed for the final changes.
- Eight existing backend sign-in regression tests passed.
- All 192 complete answer combinations return three defined relevant features. Incomplete and invalid answers return no result.
- Isolated Chrome checks passed at all six viewport sizes: header opens survey, unanswered steps cannot advance, four questions, Back/edit/review, personalised result, focus preserved in sign-up, close/reset, existing-user sign-in, hero action, form validation, information dialogs and direct sign-in query.
- Signed-out / still reaches the landing route. The regenerated photo loads, exact brand colour is applied and no horizontal page overflow occurs.
- No browser console errors. Machine-readable evidence: .codex-tmp/landing-discovery/browser-results.json.
- QA uses an isolated Chrome instance because the in-app browser automation runtime was unavailable. No real patient account was created. Camera and rehabilitation workflows are unchanged and were not retested in this scope.

## Implementation checklist

- [x] More photographic hero asset and supplied branding
- [x] Updated header action
- [x] Four-question survey with editable answers
- [x] Personalised result and sign-up handoff
- [x] Desktop/mobile visual review and interaction checks
- [x] Existing authentication checks and production build

## Follow-up polish

- [P3] At 320 pixels, the progress label and hint wrap. Both remain readable and the full survey is reachable by scrolling.
- [P3] A source font file could refine the original mockup's glyph widths; the supplied raster does not identify its typeface.

final result: passed
