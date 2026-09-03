# Sitting Ability Survey Design QA

## Reference intent

- Present sitting safety through three large illustrated choices and a separate uncertainty choice.
- Preserve the stored values `independent`, `needs_support`, `unable`, and `not_sure` for assessment selection.
- Make support and safety status understandable without relying on text alone.

## Responsive behavior

- Wide screens show the three primary choices in one row, followed by a full-width uncertainty row.
- Narrow screens stack the choices and retain large touch targets.
- Every option exposes radio accessibility state and keeps the established test ID.

## Verification checklist

- [x] Question and helper text match the requested wording.
- [x] All four answer choices can be selected.
- [x] Selected state is visible without relying on colour alone.
- [x] Continue remains disabled until a choice is made.
- [x] No overlap or horizontal clipping at desktop and phone widths.
- [x] Stored values remain compatible with Alira's assessment-readiness rules.

Final result: passed.
