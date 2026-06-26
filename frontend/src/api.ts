const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

export type TaskStep = {
  id: string;
  voice: string;
  caption: string;
  target: { x: number; y: number; r: number; landmark: string };
  hold_ms: number;
  measure?: string[];
};

export type Task = {
  id: string;
  title: string;
  view: string;
  focus: string;
  steps: TaskStep[];
};

export type FunctionalIssue = {
  code: string;
  label: string;
  description: string;
  source: string;
  severity: string;
  related_task: string;
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
};

export type Assessment = {
  id: string;
  created_at: string;
  affected_side: string;
  functional_issues: FunctionalIssue[];
  rehab_plan: RehabExercise[];
};

export async function fetchTasks(): Promise<{ tasks: Task[]; voice_id: string }> {
  const res = await fetch(`${BASE}/api/assessment/tasks`);
  return res.json();
}

export async function fetchHistory(): Promise<Assessment[]> {
  const res = await fetch(`${BASE}/api/assessment/history`);
  return res.json();
}

export async function fetchAssessment(id: string): Promise<Assessment> {
  const res = await fetch(`${BASE}/api/assessment/${id}`);
  return res.json();
}

export const POSE_RUNNER_URL = `${BASE}/api/pose/runner`;
