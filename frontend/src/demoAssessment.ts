import { Assessment, PatientAssessmentSummary } from "@/src/api";

export const DEMO_ASSESSMENT_ID = "rehyn-demo-assessment";

const createdAt = new Date().toISOString();

const clinicalReviewGate = {
  version: "demo-v1",
  status: "clear" as const,
  rehab_access: "allowed" as const,
  reason_code: "demo_sample",
  therapist_confirmation_required: false,
  patient_title: "Sample plan ready",
  patient_message: "This sample shows how Rehyn connects movement findings with practical next steps.",
  next_step: "Explore the sample plan. Your real plan will only use your completed assessment.",
  reporting_rule: "Demonstration data only. This is not a clinical result.",
};

export const demoAssessment: Assessment = {
  id: DEMO_ASSESSMENT_ID,
  created_at: createdAt,
  affected_side: "right",
  assessment_package: "initial",
  functional_issues: [
    {
      code: "DEMO_SHOULDER_EFFORT",
      label: "Higher right shoulder effort during reaching",
      description: "The sample movement pattern used more shoulder effort than the matched pattern.",
      source: "Demonstration musculoskeletal model",
      severity: "moderate",
      related_task: "T1",
      related_step: "T1-S1",
      phenotype_domain: "upper_limb",
    },
  ],
  rehab_plan: [
    {
      id: "demo_supported_reach",
      name: "Supported forward reach",
      description: "Slide the affected arm forward on a table, then return slowly while keeping the shoulder relaxed.",
      sets: 2,
      reps: 6,
      frequency: "Once daily",
      targets_issue: "DEMO_SHOULDER_EFFORT",
      source: "Demonstration exercise based on task-specific upper-limb practice",
      selection_reason: "Builds controlled reach while reducing unnecessary shoulder effort.",
      safety_note: "Stop if you feel pain, dizziness, or unusual fatigue. Review new exercises with your therapist.",
      requires_clinician_confirmation: true,
    },
    {
      id: "demo_hand_opening",
      name: "Relaxed hand opening",
      description: "Rest the forearm comfortably and slowly open the fingers before relaxing them again.",
      sets: 2,
      reps: 5,
      frequency: "Once daily",
      targets_issue: "DEMO_SHOULDER_EFFORT",
      source: "Demonstration exercise based on repetitive task practice",
      selection_reason: "Supports hand control alongside reaching practice.",
      safety_note: "Use a comfortable range and do not force stiff fingers.",
      requires_clinician_confirmation: true,
    },
  ],
  domain_assessments: [
    { domain: "upper_limb", label: "Upper limb", task_count: 3, completed_steps: 6, total_steps: 6, completion_percent: 100, interpretation: "Right shoulder effort was higher during reaching.", method: "Demo modeled estimate", clinical_status: "sample" },
    { domain: "hand", label: "Hand function", task_count: 3, completed_steps: 6, total_steps: 6, completion_percent: 100, interpretation: "Hand opening and closing appeared controlled in this sample.", method: "Demo movement observation", clinical_status: "sample" },
    { domain: "lower_limb", label: "Lower limb", task_count: 1, completed_steps: 2, total_steps: 2, completion_percent: 100, interpretation: "Walking appeared steady in this sample.", method: "Demo gait observation", clinical_status: "sample" },
  ],
  clinician_measures: [],
  biomechanical_estimates: [],
  measurement_form: {
    version: "demo-v1",
    reporting_rule: "Demonstration data only.",
    summary: { auto_filled: 2, model_filled: 0, clinician_filled: 0, tool_filled: 0, pending: 0 },
    domains: [
      {
        domain: "upper_limb",
        label: "Upper limb",
        auto_filled: 2,
        model_filled: 0,
        clinician_filled: 0,
        tool_filled: 0,
        pending: 0,
        rows: [
          { code: "UL_SHOULDER_ELEVATION", label: "Arm elevation", scale: "demo", source_type: "camera", source_label: "Sample camera estimate", status: "sample", value: 72, unit: "deg", method: "Sample pose estimate", confidence: "demo", requirement: "Completed reaching task", applicable_to_submitted_tasks: true },
          { code: "UL_TRUNK_COMPENSATION", label: "Trunk movement", scale: "demo", source_type: "camera", source_label: "Sample camera estimate", status: "sample", value: 9, unit: "deg", method: "Sample pose estimate", confidence: "demo", requirement: "Completed reaching task", applicable_to_submitted_tasks: true },
        ],
      },
    ],
    scale_readiness: [],
  },
  clinical_review_gate: clinicalReviewGate,
};

export const demoPatientAssessmentSummary: PatientAssessmentSummary = {
  id: DEMO_ASSESSMENT_ID,
  created_at: createdAt,
  assessment_package: "initial",
  collection: {
    tasks_collected: 7,
    tasks_expected: 7,
    completed_steps: 14,
    total_steps: 14,
    completion_percent: 100,
    duration_ms: 178000,
    domains: [
      { domain: "upper_limb", label: "Upper limb" },
      { domain: "hand", label: "Hand function" },
      { domain: "lower_limb", label: "Lower limb" },
    ],
  },
  body_function_summary: {
    version: "demo-v1",
    overall_status: "review_recommended",
    model_analysis_complete: true,
    domains: [
      { domain: "upper_limb", label: "Upper limb", status: "review_recommended", tasks_completed: 3, tasks_observed: 3, step_completion_percent: 100, average_task_duration_ms: 24000, findings_count: 1, summary: "Reaching was completed, with more effort around the right shoulder than the matched sample pattern." },
      { domain: "hand", label: "Hand function", status: "no_observable_difficulty", tasks_completed: 3, tasks_observed: 3, step_completion_percent: 100, average_task_duration_ms: 18000, findings_count: 0, summary: "Hand opening and closing appeared controlled in the observed sample tasks." },
      { domain: "lower_limb", label: "Lower limb", status: "no_observable_difficulty", tasks_completed: 1, tasks_observed: 1, step_completion_percent: 100, average_task_duration_ms: 52000, findings_count: 0, summary: "The sample walking pattern appeared steady with evenly timed steps." },
    ],
    reporting_rule: "Demonstration data only. Your real snapshot will use your own recordings and analysis.",
  },
  rehab_plan_ready: true,
  clinical_review_gate: clinicalReviewGate,
  insights: {
    version: "demo-v1",
    status: "research_ready",
    badge: "Demo result",
    headline: "Walking looked steady. Your right shoulder may benefit from support during reaching.",
    summary: "Your walking pattern appeared steady, while the sample reach placed more demand on the right shoulder. This is an example of the story Rehyn creates from a completed assessment.",
    domain_metrics: [
      { domain: "upper_limb", label: "Right shoulder", completion_percent: 100, findings_count: 1, status: "review_recommended" },
      { domain: "hand", label: "Hand function", completion_percent: 100, findings_count: 0, status: "no_observable_difficulty" },
      { domain: "lower_limb", label: "Walking", completion_percent: 100, findings_count: 0, status: "no_observable_difficulty" },
    ],
    activation_profile: [
      { task_id: "T1", domain: "upper_limb", muscle: "deltoid_anterior_r", label: "Right anterior deltoid", mean: 0.52, peak: 0.71, template_mean: 0.4, delta_mean: 0.12 },
      { task_id: "T4", domain: "hand", muscle: "finger_extensors_r", label: "Right finger extensors", mean: 0.34, peak: 0.48, template_mean: 0.35, delta_mean: -0.01 },
      { task_id: "T7", domain: "lower_limb", muscle: "quadriceps_r", label: "Right quadriceps", mean: 0.41, peak: 0.58, template_mean: 0.42, delta_mean: -0.01 },
    ],
    modeled_domains: ["upper_limb", "hand", "lower_limb"],
    observations: [
      { title: "Your right shoulder worked harder", detail: "The sample reach used about 1.3 times the matched shoulder demand." },
      { title: "Walking looked steady", detail: "Step timing was even throughout the sample walking observation." },
    ],
    analysis_order: ["task_collection", "musculoskeletal_analysis", "patient_insights", "rehab_plan"],
    reporting_rule: "This sample is for product demonstration and is not a diagnosis or patient result.",
  },
};

