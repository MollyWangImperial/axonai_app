# Dominant Hand Survey Design QA

## Reference intent

- Ask which hand was dominant before the stroke.
- Show left and right choices around a rear-facing person so the displayed sides match the patient's own orientation.
- Keep the ambidextrous option visually distinct and easy to understand.
- Preserve the stored values `left`, `right`, and `ambidextrous` for downstream assessment logic.

## Responsive behavior

- Wide screens use a two-column layout with the person selector beside the both-hands choice.
- Narrow screens retain the left-person-right spatial relationship and place the both-hands choice below it.
- All three choices have persistent test IDs and radio accessibility state.

## Verification checklist

- [x] Question and helper text match the requested wording.
- [x] Left, right, and both can each be selected.
- [x] Selected state is visible without relying on colour alone.
- [x] Continue remains disabled until a choice is made.
- [x] No overlap or horizontal clipping at desktop and phone widths.
- [x] Existing affected-area step remains unchanged.
