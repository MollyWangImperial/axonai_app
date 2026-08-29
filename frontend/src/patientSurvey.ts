export type PatientSurveyStep = {
  key: string;
  question: string;
  helper?: string;
  type: "text" | "number" | "single" | "multi";
  options?: { value: string; label: string; emoji?: string }[];
  optional?: boolean;
};

export const ASSESSMENT_READINESS_KEYS = [
  "sitting_ability",
  "affected_arm_movement",
  "affected_hand_movement",
  "mobility_level",
  "movement_pain",
  "instruction_support",
] as const;

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
  { key: "sitting_ability", question: "Can you sit upright safely in a stable chair for about 3 minutes?", helper: "This tells Alira whether seated arm and hand tasks are suitable.", type: "single",
    options: [
      { value: "independent", label: "Yes, without someone holding me" },
      { value: "needs_support", label: "Only with support or someone helping" },
      { value: "unable", label: "No, not safely at the moment" },
      { value: "not_sure", label: "I am not sure" },
    ] },
  { key: "affected_arm_movement", question: "While sitting, how much can you move your affected arm by yourself?", helper: "Do not test it now. Choose what is normally safe and comfortable for you.", type: "single",
    options: [
      { value: "most_movements", label: "I can lift and reach with most of the arm" },
      { value: "some_movement", label: "I can make some movement without help" },
      { value: "help_only", label: "I can move it only with help" },
      { value: "no_movement", label: "I cannot move it by myself" },
      { value: "not_affected", label: "My arm was not affected" },
      { value: "not_sure", label: "I am not sure" },
    ] },
  { key: "affected_hand_movement", question: "How much can you open and move the fingers of your affected hand?", helper: "This helps Alira avoid assigning a hand task that is not currently possible.", type: "single",
    options: [
      { value: "opens_and_moves", label: "I can open my hand and move my fingers" },
      { value: "some_finger_movement", label: "I have some finger movement" },
      { value: "very_little_movement", label: "I have very little finger movement" },
      { value: "no_movement", label: "I cannot move my fingers by myself" },
      { value: "not_affected", label: "My hand was not affected" },
      { value: "not_sure", label: "I am not sure" },
    ] },
  { key: "mobility_level", question: "Can you walk a short distance safely using your usual support?", helper: "Alira will assign the walking video only when you normally walk without hands-on help.", type: "single",
    options: [
      { value: "independent", label: "I walk independently", emoji: "🚶" },
      { value: "cane", label: "With a cane", emoji: "🦯" },
      { value: "walker", label: "With a walker / frame", emoji: "🚶‍♀️" },
      { value: "person_assist", label: "Only with hands-on help from another person" },
      { value: "wheelchair", label: "I use a wheelchair", emoji: "♿" },
      { value: "unable_walk", label: "I cannot walk at the moment" },
      { value: "not_cleared", label: "I have been advised not to walk" },
      { value: "unsure", label: "I am not sure what is safe" },
    ] },
  { key: "movement_pain", question: "How much pain do you usually have when moving?", helper: "Severe or worsening pain pauses camera tasks until you have clinical advice.", type: "single",
    options: [
      { value: "none", label: "No movement pain" },
      { value: "mild", label: "Mild pain" },
      { value: "moderate", label: "Moderate pain" },
      { value: "severe_or_worsening", label: "Severe or worsening pain" },
      { value: "not_sure", label: "I am not sure" },
    ] },
  { key: "instruction_support", question: "Can you follow spoken instructions and use the screen during an assessment?", helper: "A helper can stay with you without doing the movement for you.", type: "single",
    options: [
      { value: "independent", label: "Yes, by myself" },
      { value: "helper_preferred", label: "Yes, but I would prefer someone nearby" },
      { value: "helper_required", label: "I need someone to help with instructions or the screen" },
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
