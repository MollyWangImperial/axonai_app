# Journey Progress Panel Design QA

- source visual truth path: user-attached Journey reference screenshot in the current task (inline source, 1752 x 899 px)
- implementation screenshot path: journey-desktop-qa-final.png
- responsive implementation screenshot path: journey-mobile-qa-final.png
- desktop viewport: 1600 x 900 CSS px, device scale factor 1
- mobile viewport: 390 x 844 CSS px, device scale factor 1
- state: signed-in patient, demo mode enabled, sample progress and demo assessment visible
- density normalization: source and implementation were reviewed as CSS-scale desktop captures; composition was compared proportionally because the supplied reference is 1752 px wide and the implementation capture is 1600 px wide

## Full-view comparison evidence

The implementation matches the source hierarchy: Journey heading and Add entry action, one wide progress container, three equal functional columns, Journal & milestones immediately below, then Assessment history. Desktop spacing, separators, muted surfaces, compact labels, and the right-aligned full-progress action follow the source composition. The endpoint of every line uses three layered brand-colour rings and a highlight point, making the latest result visibly luminous without changing the measured trend.

The mobile layout changes the three-column row into a horizontal snap carousel so headings, dates, insights, and chart marks stay legible without shrinking. The rest of the Journey information remains in the source order and the persistent tab bar remains unobstructed.

## Focused region comparison evidence

The progress panel was checked separately for:
- typography: compact, high-weight headings and readable small dates/insights with no negative tracking
- spacing: consistent card padding, equal desktop columns, stable chart height, and clear section rhythm
- colours: existing Rehyn muted-white palette, pale green history line, dark green current point, and sufficient contrast in light/dark theme tokens
- image quality: no raster assets are used in this data-visualisation region; chart paths and markers render sharply through the installed react-native-svg dependency
- copy: Reaching, Hand control, Walking, their concise insights, Sample progress, and See full progress match the source intent
- interaction: See full progress navigates to /progress; phone content clips cleanly and remains horizontally scrollable
- browser console: no errors or warnings during the final interaction pass

## Comparison history

### Iteration 1
- P2: On the 390 px phone viewport, the first few pixels of the next trend heading and date were visible at the right edge of the progress card.
- Fix: recalculated each mobile panel from the actual card content width, clipped the scroll viewport, and clipped the card boundary.
- Post-fix evidence: journey-mobile-qa-final.png shows only the active Reaching panel with no text leakage or horizontal page overflow.

### Iteration 2
- No actionable P0/P1/P2 differences remained.
- Desktop evidence: journey-desktop-qa-final.png
- Mobile evidence: journey-mobile-qa-final.png

## Residual notes

- Date formatting follows the user's browser locale, so the captured dates appear in the localised month/day format rather than forcing English.
- Real regressions or flat results use honest review/steady language; the glow highlights recency, not guaranteed improvement.

final result: passed