export type ExerciseActivity = {
  id: string;
  exercise_id: string;
  exercise_name?: string;
  day?: string;
  completed_reps: number;
  average_score?: number | string | null;
  repetition_scores?: number[];
  completed_at?: string;
  created_at?: string;
  testing_shortcut?: boolean;
};

export type ScoredExerciseActivity = Omit<ExerciseActivity, "average_score" | "day"> & {
  average_score: number;
  day: string;
};

export type DailyExerciseScore = {
  id: string;
  day: string;
  completed_at: string;
  created_at?: string;
  average_score: number;
  session_count: number;
};

const DAY_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

function localDayKey(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function activityDay(activity: ExerciseActivity): string | null {
  if (activity.day && DAY_PATTERN.test(activity.day)) return activity.day;
  const timestamp = activity.completed_at || activity.created_at;
  if (!timestamp) return null;
  const date = new Date(timestamp);
  return Number.isNaN(date.getTime()) ? null : localDayKey(date);
}

export function weeklyExerciseScoreData(
  activities: ExerciseActivity[],
  now = new Date(),
): { activities: ScoredExerciseActivity[]; dailyScores: DailyExerciseScore[] } {
  const end = new Date(now);
  end.setHours(23, 59, 59, 999);
  const start = new Date(end);
  start.setDate(start.getDate() - 6);
  start.setHours(0, 0, 0, 0);
  const firstDay = localDayKey(start);
  const lastDay = localDayKey(end);

  const scoredActivities = activities
    .flatMap((activity): ScoredExerciseActivity[] => {
      if (activity.average_score === null || activity.average_score === undefined || activity.average_score === "") return [];
      const score = Number(activity.average_score);
      const day = activityDay(activity);
      if (!Number.isFinite(score) || !day || day < firstDay || day > lastDay) return [];
      return [{ ...activity, day, average_score: Math.max(0, Math.min(100, score)) }];
    })
    .sort((a, b) => {
      const aTime = new Date(a.completed_at || a.created_at || `${a.day}T12:00:00`).getTime();
      const bTime = new Date(b.completed_at || b.created_at || `${b.day}T12:00:00`).getTime();
      return aTime - bTime;
    });

  const byDay = new Map<string, number[]>();
  for (const activity of scoredActivities) {
    const scores = byDay.get(activity.day) || [];
    scores.push(activity.average_score);
    byDay.set(activity.day, scores);
  }

  const dailyScores = [...byDay.entries()].map(([day, scores]) => ({
    id: `daily-exercise-score-${day}`,
    day,
    completed_at: `${day}T12:00:00`,
    average_score: Math.round((scores.reduce((sum, score) => sum + score, 0) / scores.length) * 10) / 10,
    session_count: scores.length,
  }));

  return { activities: scoredActivities, dailyScores };
}
