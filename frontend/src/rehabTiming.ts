import type { RehabExercise } from "@/src/api";

export function estimateRehabMinutes(exercises: Pick<RehabExercise, "sets" | "reps">[]) {
  return exercises.reduce((total, exercise) => {
    const guidedSeconds = Math.max(60, exercise.sets * exercise.reps * 15);
    return total + Math.max(3, Math.ceil((guidedSeconds + 60) / 60));
  }, 0);
}
