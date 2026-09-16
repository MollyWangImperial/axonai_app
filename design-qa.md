# Rehyn landing-page design QA

Date: 2026-09-16

## Visual truth and evidence

- Source visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-fa8daf29-3d19-4341-b733-0f3428f9621f.png` at 1851 × 849 pixels.
- Survey visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-915bbe6e-c3c7-4b2e-ad91-5277282506c7.png` at 1207 × 1305 pixels.
- Survey result visual truth: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-38be15ce-8f08-48f5-b15e-4ed473b4f11c.png` at 1386 × 1132 pixels.
- Supplied background asset: `C:\Users\LENOVO\AppData\Local\Temp\codex-clipboard-744c1103-65fd-4ec8-b185-514dbbe15e46.png` at 1746 × 901 pixels.
- Project background asset: `frontend/assets/images/rehyn-landing-hero-background.png`; its SHA-256 matches the supplied background.
- Implementation route: `http://127.0.0.1:4185/sign-in`.
- Browser-rendered implementation capture: Codex in-app browser capture emitted during this QA run. The browser API does not persist the screenshot to a filesystem path.
- Desktop comparison viewport: 1851 × 849 CSS pixels at device scale factor 1, matching the source visual's pixel dimensions.
- Responsive comparison viewport: 390 × 844 CSS pixels at device scale factor 1.
- Survey comparison viewport: 1207 × 1305 CSS pixels at device scale factor 1, matching the survey source visual's pixel dimensions.
- Survey result comparison viewport: 1386 × 1132 CSS pixels at device scale factor 1, matching the result source visual's pixel dimensions.
- State: signed out landing page plus the first survey question with no answer selected. Selected-answer, later-question, result, and compact states were also checked.

## Findings

No outstanding P0, P1, or P2 visual or interaction findings.

- The desktop header, logo, navigation, divider, and green Sign in button follow the source hierarchy and spacing.
- The dark-green hero panel begins and ends at the same approximate horizontal points as the source. Its clipped edge follows the source's inward-to-outward curve without obscuring the headline.
- The supplied background image is used directly. Its desktop crop shifts upward to align the patient's face, reaching hand, phone, and tripod with the source composition.
- The white-and-green, three-line display headline retains the source hierarchy. The third line is fixed as “All from home.”
- The desktop headline scale and text column are constrained so all three lines remain inside the green panel without crossing its curved edge.
- The subtitle and bright-green discovery CTA match the source's placement, scale, and contrast.
- At 390 × 844, the header stays usable, all headline lines fit without horizontal clipping, the CTA remains fully visible, and the image follows beneath the green panel.
- The survey now uses the reference's full white surface, large close control, compact step counter, long progress bar, two-line title, grouped answer rows, large circular selectors, and full-width action.
- At 1207 × 1305, the survey's progress bar, title, description, grouped options, and Continue button align within approximately 12 pixels of the supplied reference.
- At 390 × 844, the survey preserves the same hierarchy without clipped copy or horizontal overflow; answer rows wrap naturally and the action remains visible.
- The completion screen now matches the supplied result reference with the “Start with a movement check” heading, supporting line, large movement-check graphic, three checkmarked benefits, divider, and full-width “Sign up to try Rehyn” action.
- At 390 × 844, the completion screen stacks the illustration and benefits without horizontal overflow, and the sign-up action remains fully visible.

## Required fidelity surfaces

- Fonts and typography: the implementation uses the app's existing web-safe Arial display treatment, strong optical weight, tight letter spacing, and source-like line height. Navigation and support text retain lighter weights. The survey reproduces the reference's large question, softer description, and readable answer labels. No headline truncation was found at the checked viewports.
- Spacing and layout rhythm: desktop left alignment, header height, hero spacing, subtitle gap, CTA size, and panel-to-image split are aligned with the reference. The survey uses the source's 60-pixel side margins, 132-pixel desktop answer rows, and 112-pixel desktop action. Compact layouts stack cleanly.
- Colors and visual tokens: the hero uses the supplied Rehyn green `#004A38`; the “All from home.” line and actions use the brighter reference green `#3DD45A`; primary copy is white. Contrast remains readable.
- Image quality and asset fidelity: the exact second attachment is bundled as the background without regeneration, stretching, replacement, or placeholder treatment. The existing supplied Rehyn logo remains unchanged.
- Copy and content: the headline reads “More progress. More confidence. All from home.” The CTA reads “See if Rehyn could help you”. The first survey hint now matches the supplied reference: “Choose one small moment you would like to feel easier.”

## Full-view and focused comparison evidence

- Full view: the source and implementation were opened at the source's 1851 × 849 dimensions. The header-to-hero proportion, left text block, curved green boundary, patient placement, and right-side tripod are visibly aligned.
- Focused header review: logo scale, five navigation items, divider, and Sign in button are readable and vertically centered.
- Focused hero review: the headline, subtitle, and CTA maintain the requested ordering and do not collide with the clipped panel edge. The eyebrow text, divider line, and pulse icon have been removed.
- Focused responsive review: the 390 × 844 capture shows no horizontal overflow, clipped copy, or hidden CTA. No additional crop was needed for legibility.
- Survey full view: the source and implementation were compared at 1207 × 1305. Counter, progress, title wrapping, description, four-row option group, and primary action follow the reference composition.
- Survey focused review: selected rows use a pale-green fill and check icon, the Continue action becomes active after selection, and the close control remains clear at desktop and compact sizes.

## Comparison history

- First desktop pass: the panel used rounded corners, causing the boundary to start too far left and bulge over the patient's reaching hand. The panel was changed to a responsive multi-point clip that matches the source boundary at the top, centre, and bottom.
- First desktop pass: the patient's face and tripod sat lower than the source. The supplied background remains unchanged, while its desktop presentation is shifted upward to match the source crop.
- First compact pass: the small-screen headline was too large for the available width. The small-screen scale was reduced and the final 390-pixel capture confirms every line fits.
- Survey pass: the previous 640-pixel dialog, separated option cards, small title, and compact action were replaced with the full white 1208-pixel survey surface and source-sized controls. The final 1207 × 1305 capture matches the supplied hierarchy and spacing.
- Result pass: the former personalised feature card was replaced with the supplied 1386 × 1132 completion composition. The modal cap expands to 1400 pixels for this reference while the existing question layout remains unchanged at its 1207-pixel comparison viewport.
- Latest desktop pass: the changing third line was removed at the user's request. A screenshot also revealed “More confidence.” crossing the curved panel edge at a wide, shorter viewport, so the desktop headline cap was reduced to 68 pixels, its fluid scale was tightened, and the text column narrowed to 43.5%. The subtitle uses a narrower three-line treatment near the desktop breakpoint so it also remains inside the panel.
- Post-fix desktop and compact captures show no remaining P0/P1/P2 mismatch.

## Interaction and engineering verification

- The third headline line remained “All from home.” during a multi-second browser check, with no word-changing timer or transition.
- The three headline lines stayed inside the visible green panel at wide desktop, smaller desktop, and mobile test sizes.
- The hero CTA opens question 1 of the four-question discovery survey.
- Selecting an answer sets its accessible checked state, enables Continue, and advances to the next question.
- Back navigation, all four question transitions, the redesigned result, sign-up handoff, and existing sign-in handoff remain reachable.
- The header Sign in button opens the existing Sign in to Rehyn form.
- The production Expo web export passed.
- TypeScript and ESLint passed for the changed screen.
- The browser console reported no errors.

## Implementation checklist

- [x] Reference-matched desktop header and navigation
- [x] Curved dark-green hero panel
- [x] Exact supplied background image and aligned crop
- [x] Static “All from home.” green headline line
- [x] Headline constrained within the curved green panel
- [x] Responsive compact layout
- [x] Working discovery survey CTA
- [x] Reference-matched full-screen survey design
- [x] Responsive selected, progress, Back, and result states
- [x] Working sign-in action
- [x] Production build, TypeScript, lint, and browser verification

## Follow-up polish

- [P3] The source uses a perfectly smooth bespoke panel spline. The responsive web clip closely matches it, though its edge can differ by a few pixels at widths between the tested breakpoints.

final result: passed
