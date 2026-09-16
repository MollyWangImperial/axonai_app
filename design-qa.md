# Rehyn landing page verification

Date: 2026-09-16

## Visual truth and evidence

- Source layout: user-supplied `4e6e064503444ec02ec7af189157a602.png`, copied to `.codex-tmp/landing/reference.png` (1746 x 901 pixels).
- Source logo: `frontend/assets/images/rehyn-logo.png` (306 x 95 pixels). Its square's dominant colour is RGB (0, 74, 56), or `#004A38`.
- Implementation: `/sign-in`; screenshots in `.codex-tmp/landing/desktop.png`, `laptop.png`, `tablet.png`, `mobile.png`, and `small-mobile.png`.
- Viewports: 1746 x 901, 1366 x 768, 768 x 1024, 390 x 844, and 320 x 740 CSS pixels. Device scale factor 1; screenshot dimensions match CSS dimensions.
- State: signed out, default display preferences, no modal. `mobile-auth.png` also records the opened form and empty-submit validation.
- Full-view comparison: opened the 1746 x 901 source and implementation together at matching dimensions. Compared tablet screenshots together before and after the image-framing correction.
- Focused review: the complete logo, three headline lines, navigation, and primary button remain legible at the original screenshot resolution, so an additional enlarged crop was unnecessary.

## Findings and comparison history

1. Initial comparison (`desktop-v1.png`, `small-mobile-v1.png`): [P2] logo background appeared as a visible rectangle; the narrowest phone added an unwanted headline line; desktop headline extended too close to the reaching hand. Removed the logo background using the image editing tool and adjusted responsive type and header spacing.
2. Second comparison (`tablet-v2.png`): [P2] bottom-aligning the tablet image cropped the person's head. Changed the image to top alignment.
3. Final comparison (`desktop.png`, `tablet.png`, `small-mobile.png`): those findings are resolved. No outstanding P0/P1/P2 findings.

## Required fidelity surfaces

- Typography: static, selectable headline with the reference's three-line hierarchy. Arial bold provides a close available match; mobile sizing preserves the line structure. Exact font metrics cannot be recovered from the supplied raster.
- Spacing: preserved left alignment, large negative space, top navigation, rounded buttons, and the desktop photo composition. Narrow screens stack copy and photography while keeping every control reachable.
- Colours: all landing-page green accents and buttons use `#004A38`, intentionally replacing the reference's brighter green to match the supplied logo. Dark blue text follows the layout reference. Existing app display-brightness preferences still apply.
- Assets: supplied logo retained as source; transparent display version extracted with the built-in image tool. Hero background derived from the supplied reference with its UI text removed; page text and buttons are real controls.
- Copy: reproduced the headline, supporting sentence, both Explore Rehyn buttons, How it works, and About. About opens a description of Rehyn; existing authentication and direct sign-in/handoff routes are retained.

## Verification

- Production Expo web build passed.
- TypeScript check and ESLint for `app/sign-in.tsx` passed.
- Eight existing sign-in tests passed after updating obsolete landing-copy expectations.
- Isolated Chrome browser checks passed at all five viewport sizes: both Explore buttons, How it works, About, close controls, empty-form validation, and `?auth=signin`.
- No horizontal overflow or browser console errors in the final run. Machine-readable results: `.codex-tmp/landing/browser-results.json`.
- Automated checks cover the changed entry flow. They do not create a real patient account or repeat camera/rehabilitation workflows, which were not changed.

## Implementation checklist

- [x] Reference layout and supplied branding
- [x] Desktop and mobile screenshot comparison
- [x] Photo framing and readable responsive text
- [x] Working entry buttons and information dialogs
- [x] Existing sign-in contracts and production build

## Follow-up polish

- [P3] A source font file could further refine glyph widths; the supplied raster does not identify its typeface.

final result: passed
