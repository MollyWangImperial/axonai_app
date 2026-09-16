export type DiscoveryKey = "goal" | "curiosity" | "support" | "audience";
export type DiscoveryAnswers = Partial<Record<DiscoveryKey, string>>;

type DiscoveryOption = { id: string; label: string };
type DiscoveryQuestion = {
  id: DiscoveryKey;
  title: string;
  hint: string;
  options: DiscoveryOption[];
};

export const discoveryQuestions: DiscoveryQuestion[] = [
  {
    id: "goal",
    title: "Which everyday win would mean the most?",
    hint: "Picture one small moment you would like to feel easier.",
    options: [
      { id: "reach", label: "Reaching a shelf or lifting a cup" },
      { id: "hand", label: "Using my hand for buttons, cutlery or a pen" },
      { id: "walking", label: "Feeling more confident moving around" },
      { id: "discover", label: "Finding out what my body can do today" },
    ],
  },
  {
    id: "curiosity",
    title: "What would you like to discover about movement?",
    hint: "Choose the question you would most like to explore.",
    options: [
      { id: "changes", label: "Am I making small changes I haven't noticed?" },
      { id: "together", label: "How do my arm, hand and body work together?" },
      { id: "focus", label: "Which movement could I focus on next?" },
      { id: "starting", label: "What does my starting point look like?" },
    ],
  },
  {
    id: "support",
    title: "What would make practice feel more worthwhile?",
    hint: "Think about what would help you come back tomorrow.",
    options: [
      { id: "guidance", label: "Clear guidance, one movement at a time" },
      { id: "feedback", label: "Feedback while I practise" },
      { id: "progress", label: "Seeing my effort and progress over time" },
      { id: "routine", label: "A simple plan that fits into my day" },
    ],
  },
  {
    id: "audience",
    title: "Who are you exploring this for?",
    hint: "Your next step should feel relevant to you.",
    options: [
      { id: "self", label: "Myself, after a stroke" },
      { id: "supporter", label: "Someone I support after a stroke" },
      { id: "exploring", label: "I'm learning about the options" },
    ],
  },
];

const goalDetails: Record<string, { focus: string; detail: string }> = {
  reach: { focus: "Reaching and lifting", detail: "Explore movements behind everyday actions such as reaching towards an object and lifting your arm." },
  hand: { focus: "Everyday hand use", detail: "Explore hand movements behind grasping, releasing and everyday tasks that matter to you." },
  walking: { focus: "Moving around with confidence", detail: "Explore Rehyn's supported movement-check and practice options for moving around after stroke." },
  discover: { focus: "Understanding today's movement", detail: "A guided movement check gives you a starting point to explore before following your programme." },
};

const curiosityDetails: Record<string, { title: string; detail: string }> = {
  changes: { title: "Make changes easier to notice", detail: "Review your recorded activity and movement results over time, including days when progress feels hard to judge." },
  together: { title: "Get curious about how you move", detail: "Guided movement tasks and camera feedback let you explore how different parts of your body move during a task." },
  focus: { title: "Find a clearer focus", detail: "Your movement check helps shape a programme, so you can see what to practise next." },
  starting: { title: "See your starting point", detail: "Begin with a movement check and return to your results as you continue practising." },
};

const supportDetails: Record<string, { title: string; detail: string }> = {
  guidance: { title: "Follow one step at a time", detail: "Spoken instructions guide you through each movement and repetition." },
  feedback: { title: "Get feedback during practice", detail: "Camera-based guidance offers movement cues as you practise." },
  progress: { title: "Give your effort a place to show", detail: "Your activity calendar, points and progress views keep a record of the practice you put in." },
  routine: { title: "Start with a plan for your day", detail: "See your assigned activities together, with guided steps to help you begin." },
};

export function getDiscoveryResult(answers: DiscoveryAnswers) {
  // This is an interest survey, not an eligibility score or a prediction of recovery.
  if (!discoveryQuestions.every(q => q.options.some(option => option.id === answers[q.id]))) return null;
  const goal = goalDetails[answers.goal!];
  return {
    focus: goal.focus,
    title: answers.audience === "supporter"
      ? "Rehyn could help you support their next step."
      : answers.audience === "exploring"
        ? "Rehyn could help you explore what's possible."
        : "Rehyn could help you find your next step.",
    introduction: answers.audience === "supporter"
      ? "Here are some ways to explore Rehyn together, based on what matters to you."
      : "Here are some parts of Rehyn you might find useful, based on your interests.",
    features: [
      { title: goal.focus, detail: goal.detail },
      curiosityDetails[answers.curiosity!],
      supportDetails[answers.support!],
    ],
  };
}
