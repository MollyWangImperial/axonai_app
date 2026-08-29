export type PatientSurveyStep = {
  key: string;
  question: string;
  helper?: string;
  type: "text" | "number" | "single" | "multi";
  options?: { value: string; label: string; emoji?: string }[];
  optional?: boolean;
};

export const PATIENT_SURVEY_STEPS: PatientSurveyStep[] = [
  { key: "preferred_name", question: "What should we call you?", helper: "We'll use this name in your exercises and check-ins.", type: "text" },
  { key: "age_band", question: "Which age range are you in?", type: "single",
    options: [
      { value: "under_20", label: "Under 20" },
      { value: "20-29", label: "20 - 29" },
      { value: "30-39", label: "30 - 39" },
      { value: "40-49", label: "40 - 49" },
      { value: "50-59", label: "50 - 59" },
      { value: "60-69", label: "60 - 69" },
      { value: "70-79", label: "70 - 79" },
      { value: "80+", label: "80 or older" },
    ] },
  { key: "gender", question: "How do you describe your gender?", helper: "Choose the answer that feels right for you.", type: "single",
    options: [
      { value: "female", label: "Female" },
      { value: "male", label: "Male" },
      { value: "transgender_woman", label: "Transgender woman" },
      { value: "transgender_man", label: "Transgender man" },
      { value: "non_binary", label: "Non-binary" },
      { value: "self_describe", label: "Another gender identity" },
      { value: "prefer_not_to_say", label: "Prefer not to say" },
    ] },
  { key: "months_since_stroke", question: "Roughly how many months since your stroke?", helper: "An estimate is fine — this helps tune your plan to your recovery stage.", type: "number" },
  { key: "affected_areas", question: "Which areas of your body were affected?", helper: "Select every area that applies.", type: "multi",
    options: [
      { value: "left_upper", label: "Left upper limb (shoulder, arm or hand)" },
      { value: "left_lower", label: "Left lower limb (hip, leg or foot)" },
      { value: "right_upper", label: "Right upper limb (shoulder, arm or hand)" },
      { value: "right_lower", label: "Right lower limb (hip, leg or foot)" },
      { value: "face_speech", label: "Face or speech" },
      { value: "other", label: "Another area" },
      { value: "unsure", label: "Not sure yet" },
    ] },
  { key: "dominant_hand", question: "Which is your dominant hand (before stroke)?", type: "single",
    options: [
      { value: "right", label: "Right-handed", emoji: "✋" },
      { value: "left", label: "Left-handed", emoji: "🤚" },
      { value: "ambidextrous", label: "Both / Ambidextrous", emoji: "🙌" },
    ] },
  { key: "mobility_level", question: "How do you usually get around?", type: "single",
    options: [
      { value: "independent", label: "I walk independently", emoji: "🚶" },
      { value: "cane", label: "With a cane", emoji: "🦯" },
      { value: "walker", label: "With a walker / frame", emoji: "🚶‍♀️" },
      { value: "wheelchair", label: "I use a wheelchair", emoji: "♿" },
    ] },
  { key: "primary_goal", question: "What's the one thing you'd love to do again?", helper: "Examples: hold my grandchild, eat with a fork, button my own shirt, paint, type at the computer.", type: "text" },
  { key: "secondary_goals", question: "Any other goals? Tap all that apply.", type: "multi",
    options: [
      { value: "reach_overhead", label: "Reach overhead", emoji: "🙆" },
      { value: "self_feed", label: "Self-feed", emoji: "🍽️" },
      { value: "dress", label: "Dress independently", emoji: "👔" },
      { value: "write", label: "Write / draw", emoji: "✍️" },
      { value: "drive", label: "Drive again", emoji: "🚗" },
      { value: "cook", label: "Cook", emoji: "🍳" },
      { value: "play_music", label: "Play music", emoji: "🎸" },
      { value: "exercise", label: "Exercise / sports", emoji: "🏃" },
      { value: "other", label: "Other" },
    ], optional: true },
  { key: "medical_conditions", question: "Do you have any pre-existing medical conditions?", helper: "Select all that apply. This helps us keep guidance appropriate and safe.", type: "multi",
    options: [
      { value: "hypertension", label: "High blood pressure" },
      { value: "arthritis", label: "Arthritis" },
      { value: "heart_condition", label: "Heart condition" },
      { value: "diabetes", label: "Diabetes" },
      { value: "cancer", label: "Cancer" },
      { value: "other", label: "Another condition" },
      { value: "none", label: "None of these" },
    ], optional: true },
  { key: "has_caregiver", question: "Is someone helping you at home (family, caregiver)?", type: "single",
    options: [
      { value: "yes", label: "Yes — I have help", emoji: "🤝" },
      { value: "no", label: "No, mostly on my own", emoji: "🌿" },
    ] },
];
