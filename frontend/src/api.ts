import { authedFetch } from "@/src/auth";
import { API_BASE as BASE } from "@/src/config";

export type TaskStep = {
  id: string;
  voice: string;
  caption: string;
  target: { x: number; y: number; r: number; landmark: string };
  hold_ms: number;
  measure?: string[];
  movement_required?: boolean;
  failure_phenotype?: {
    code: string;
    domain: string;
    label: string;
    description: string;
    severity: string;
    source: string;
    rehab_code: string;
  };
};

export type Task = {
  id: string;
  title: string;
  view: string;
  focus: string;
  steps: TaskStep[];
  advanced_marker_required?: boolean;
  advanced_label?: string;
  recommended_objects?: string[];
  safety_tier?: "seated" | "spotter_required";
  safety_note?: string;
};

export type AssessmentPackageId = "upper_limb" | "hand" | "lower_limb" | "balance";

export type AssessmentPackage = {
  id: AssessmentPackageId;
  title: string;
  subtitle: string;
  task_count: number;
};

export type FunctionalIssue = {
  code: string;
  label: string;
  description: string;
  source: string;
  severity: string;
  related_task: string;
  related_step?: string | null;
  phenotype_domain?: string | null;
};

export type RehabExercise = {
  id: string;
  name: string;
  description: string;
  sets: number;
  reps: number;
  frequency: string;
  targets_issue: string;
  source: string;
  selection_reason?: string | null;
  safety_note?: string | null;
  requires_clinician_confirmation?: boolean;
};

export type Assessment = {
  id: string;
  created_at: string;
  affected_side: string;
  functional_issues: FunctionalIssue[];
  rehab_plan: RehabExercise[];
  domain_assessments: {
    domain: string;
    label: string;
    task_count: number;
    completed_steps: number;
    total_steps: number;
    completion_percent: number;
    interpretation: string;
    method: string;
    clinical_status: string;
  }[];
  clinician_measures: {
    code: string;
    value: unknown;
    method: string;
    provenance: string;
    clinical_status: string;
  }[];
  biomechanical_estimates: {
    code: string;
    label: string;
    value: unknown;
    unit?: string | null;
    method: string;
    provenance: string;
    confidence: string;
    interpretation: string;
  }[];
  measurement_form?: {
    version: string;
    reporting_rule: string;
    summary: {
      auto_filled: number;
      model_filled: number;
      clinician_filled: number;
      tool_filled: number;
      pending: number;
    };
    domains: {
      domain: string;
      label: string;
      auto_filled: number;
      model_filled: number;
      clinician_filled: number;
      tool_filled: number;
      pending: number;
      rows: {
        code: string;
        label: string;
        scale: string;
        source_type: string;
        source_label: string;
        status: string;
        value: unknown;
        unit?: string | null;
        method: string;
        confidence: string;
        requirement: string;
        applicable_to_submitted_tasks: boolean;
      }[];
    }[];
    scale_readiness: {
      scale: string;
      status: string;
      formal_score: unknown;
      reason: string;
    }[];
  };
  muscle_activation_diagnosis?: MuscleActivationDiagnosis;
  rehabilitation_goals?: {
    version: string;
    method: string;
    status: string;
    short_term: RehabilitationGoal[];
    long_term: RehabilitationGoal[];
    missing_information: string[];
    safety_rule: string;
    generation_rule: string;
    measurement_form_version?: string | null;
  };
};

export type MuscleActivationFinding = {
  code: string;
  package: string;
  anomaly_type: "hypoactivation" | "hyperactivation" | "timing_disorder" | "co_contraction";
  anomaly_label: string;
  label: string;
  muscles: string;
  pipeline_route: string;
  pipeline_route_label: string;
  severity: string;
  interpretation: string;
  evidence_metrics: Record<string, unknown>;
  related_tasks: string[];
  citation: string;
};

export type MuscleActivationDiagnosis = {
  version: string;
  method: string;
  reporting_rule: string;
  anomaly_taxonomy: Record<string, string>;
  packages_evaluated: string[];
  findings: MuscleActivationFinding[];
};

export type RehabilitationGoal = {
  id: string;
  horizon: "short_term" | "long_term";
  domain: string;
  domain_label: string;
  statement: string;
  timeframe: string;
  baseline: string;
  target: string;
  outcome_measure: string;
  review_schedule: string;
  linked_task_ids: string[];
  linked_issue_codes: string[];
  patient_priority?: string | null;
  patient_agreement_required: boolean;
  clinician_confirmation_required: boolean;
  status: string;
  evidence: {
    id: string;
    source: string;
    title: string;
    organization: string;
    year: number;
    url: string;
    rules: string[];
    retrieval_score: number;
    matched_tags: string[];
  }[];
};

export async function fetchTasks(packageId: AssessmentPackageId = "upper_limb"): Promise<{
  tasks: Task[];
  voice_id: string;
  package_id: AssessmentPackageId;
  package_title: string;
  package_subtitle: string;
  packages: AssessmentPackage[];
}> {
  const res = await fetch(`${BASE}/api/assessment/tasks?package=${encodeURIComponent(packageId)}`);
  return res.json();
}

export async function fetchHistory(): Promise<Assessment[]> {
  const res = await authedFetch("/api/assessment/history");
  return res.json();
}

export async function fetchAssessment(id: string): Promise<Assessment> {
  const res = await fetch(`${BASE}/api/assessment/${id}`);
  return res.json();
}

export const POSE_RUNNER_URL = `${BASE}/api/pose/runner`;
