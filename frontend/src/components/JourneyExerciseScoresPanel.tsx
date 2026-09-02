import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import Svg, { Circle, G, Line, Text as SvgText } from "react-native-svg";

import { authedFetch } from "@/src/auth";
import { DisplayPalette, useDisplayPreferences } from "@/src/displayPreferences";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { radius, spacing } from "@/src/theme";

type ExerciseActivity = {
  id: string;
  exercise_id: string;
  exercise_name?: string;
  completed_reps: number;
  average_score: number;
  repetition_scores?: number[];
  completed_at: string;
  created_at?: string;
};

type ExerciseActivityResponse = {
  activities: ExerciseActivity[];
  target_score: number;
};

const CACHE_KEY = "journey-exercise-scores";
const DEFAULT_TARGET = 80;
const DAY_MS = 24 * 60 * 60 * 1000;

const DEMO_SCORE_VALUES = [74, 79, 77, 84, 82, 87, 85];
const DEMO_EXERCISES = [
  "Graded Forward Reach",
  "Hand Opening Practice",
  "Supported Sit-to-Stand",
  "Graded Forward Reach",
  "Pinch Practice",
  "Bilateral Arm Practice",
  "Hand-to-Mouth Practice",
];

function clampScore(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function readableExerciseName(activity: ExerciseActivity) {
  if (activity.exercise_name?.trim()) return activity.exercise_name.trim();
  return activity.exercise_id
    .replace(/^ex_/, "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function activityDate(activity: ExerciseActivity) {
  return activity.completed_at || activity.created_at || "";
}

function shortDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function longDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
  });
}

function makeDemoActivities(now = new Date()): ExerciseActivity[] {
  const end = new Date(now);
  end.setHours(12, 0, 0, 0);
  return DEMO_SCORE_VALUES.map((score, index) => {
    const completedAt = new Date(end.getTime() - (DEMO_SCORE_VALUES.length - 1 - index) * DAY_MS).toISOString();
    return {
      id: `demo-score-${index}`,
      exercise_id: `demo-exercise-${index}`,
      exercise_name: DEMO_EXERCISES[index],
      completed_reps: 5,
      average_score: score,
      repetition_scores: [score - 2, score, score + 2].map(clampScore),
      completed_at: completedAt,
    };
  });
}

function thisWeeksScores(activities: ExerciseActivity[], now = new Date()) {
  const cutoff = new Date(now);
  cutoff.setHours(23, 59, 59, 999);
  const start = new Date(cutoff.getTime() - 6 * DAY_MS);
  start.setHours(0, 0, 0, 0);

  return activities
    .filter((activity) => Number.isFinite(activity.average_score))
    .filter((activity) => {
      const completedAt = new Date(activityDate(activity)).getTime();
      return Number.isFinite(completedAt) && completedAt >= start.getTime() && completedAt <= cutoff.getTime();
    })
    .sort((a, b) => new Date(activityDate(a)).getTime() - new Date(activityDate(b)).getTime());
}

function ScoreChart({
  activities,
  target,
  palette,
  width,
}: {
  activities: ExerciseActivity[];
  target: number;
  palette: DisplayPalette;
  width: number;
}) {
  const height = 252;
  const left = 58;
  const right = 24;
  const top = 31;
  const bottom = 197;
  const lowestScore = Math.min(target, ...activities.map((activity) => activity.average_score));
  const yMin = lowestScore >= 60 ? 60 : Math.max(0, Math.floor((lowestScore - 10) / 10) * 10);
  const valueRange = Math.max(20, 100 - yMin);
  const yFor = (score: number) => top + ((100 - Math.max(yMin, Math.min(100, score))) / valueRange) * (bottom - top);
  const targetY = yFor(target);
  const plotWidth = width - left - right;

  return (
    <View
      style={{ width, height }}
      accessible
      accessibilityLabel={`${activities.length} exercise session scores. Personal goal ${target}.`}
      testID="journey-exercise-score-chart"
    >
      <Svg width={width} height={height}>
        <Line x1={left} y1={top} x2={width - right} y2={top} stroke={palette.border} strokeWidth={1} opacity={0.6} />
        <Line x1={left} y1={bottom} x2={width - right} y2={bottom} stroke={palette.border} strokeWidth={1.2} />
        <SvgText x={5} y={top + 5} fill={palette.muted} fontSize={13}>100</SvgText>
        <SvgText x={12} y={bottom + 5} fill={palette.muted} fontSize={13}>{yMin}</SvgText>

        <Line
          x1={left}
          y1={targetY}
          x2={width - right}
          y2={targetY}
          stroke={palette.text}
          strokeWidth={1.7}
          strokeDasharray="7 7"
          opacity={0.85}
        />
        <SvgText x={left + 10} y={targetY - 10} fill={palette.text} fontSize={12} fontWeight="700">
          Personal goal {target}
        </SvgText>

        {activities.map((activity, index) => {
          const x = activities.length === 1
            ? left + plotWidth / 2
            : left + (index / (activities.length - 1)) * plotWidth;
          const score = clampScore(activity.average_score);
          const y = yFor(score);
          const reachedGoal = score >= target;
          const stem = reachedGoal ? "#84AB88" : "#E8B94F";
          const marker = reachedGoal ? "#AFC9AF" : "#F3CF7C";

          return (
            <G key={activity.id}>
              <Line x1={x} y1={bottom} x2={x} y2={y} stroke={stem} strokeWidth={8} strokeLinecap="round" />
              <Circle cx={x} cy={y} r={30} fill={marker} opacity={0.16} />
              <Circle cx={x} cy={y} r={23} fill={marker} />
              <SvgText
                x={x}
                y={y + 6}
                fill="#173C2F"
                fontSize={17}
                fontWeight="800"
                textAnchor="middle"
              >
                {score}
              </SvgText>
              <SvgText
                x={x}
                y={232}
                fill={palette.text}
                fontSize={12}
                textAnchor="middle"
              >
                {shortDate(activityDate(activity))}
              </SvgText>
            </G>
          );
        })}
      </Svg>
    </View>
  );
}

export function JourneyExerciseScoresPanel({ demoMode }: { demoMode: boolean }) {
  const { palette } = useDisplayPreferences();
  const { width: viewportWidth } = useWindowDimensions();
  const wide = viewportWidth >= 760;
  const cached = getScreenCache<ExerciseActivityResponse>(CACHE_KEY);
  const [payload, setPayload] = useState<ExerciseActivityResponse>(cached ?? { activities: [], target_score: DEFAULT_TARGET });
  const [loading, setLoading] = useState(!cached);
  const [showDetails, setShowDetails] = useState(false);

  const load = useCallback(async () => {
    if (!getScreenCache<ExerciseActivityResponse>(CACHE_KEY)) setLoading(true);
    try {
      const response = await authedFetch("/api/alira/activities?limit=100");
      if (!response.ok) throw new Error("Unable to load exercise scores");
      const result = await response.json();
      const next: ExerciseActivityResponse = {
        activities: Array.isArray(result.activities) ? result.activities : [],
        target_score: Number.isFinite(Number(result.target_score)) ? Number(result.target_score) : DEFAULT_TARGET,
      };
      setPayload(next);
      setScreenCache(CACHE_KEY, next);
    } catch {
      if (!getScreenCache<ExerciseActivityResponse>(CACHE_KEY)) {
        setPayload({ activities: [], target_score: DEFAULT_TARGET });
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    void load();
  }, [load]));

  const target = clampScore(payload.target_score || DEFAULT_TARGET);
  const activities = useMemo(
    () => demoMode ? makeDemoActivities() : thisWeeksScores(payload.activities),
    [demoMode, payload.activities],
  );
  const average = activities.length
    ? Math.round(activities.reduce((sum, activity) => sum + activity.average_score, 0) / activities.length)
    : null;
  const minimumChartWidth = wide ? 640 : 560;
  const availableWidth = Math.min(1000, Math.max(280, viewportWidth - (wide ? 96 : 64)));
  const chartWidth = Math.max(minimumChartWidth, availableWidth, 128 + activities.length * (wide ? 106 : 92));
  const goalCopy = average == null
    ? "Your next score will appear here"
    : average > target
      ? "Above your personal goal"
      : average === target
        ? "At your personal goal"
        : "Building towards your personal goal";

  return (
    <View
      style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}
      testID="journey-exercise-scores"
    >
      <View style={[styles.header, !wide && styles.headerNarrow]}>
        <View style={styles.titleRow}>
          <Text style={[styles.heading, { color: palette.text }]}>This week&apos;s exercise scores</Text>
          {demoMode ? (
            <View style={[styles.sampleBadge, { backgroundColor: palette.soft }]}>
              <Text style={[styles.sampleBadgeText, { color: palette.text }]}>SAMPLE</Text>
            </View>
          ) : null}
        </View>

        <View style={[styles.summary, !wide && styles.summaryNarrow]}>
          {average == null ? null : (
            <View style={styles.averageRow}>
              <Text style={[styles.averageValue, { color: palette.text }]}>{average}</Text>
              <Text style={[styles.averageLabel, { color: palette.text }]}>average</Text>
            </View>
          )}
          <Text style={[styles.goalCopy, { color: palette.muted }]}>{goalCopy}</Text>
          {activities.length ? (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ expanded: showDetails }}
              onPress={() => setShowDetails((current) => !current)}
              style={({ pressed }) => [styles.detailsButton, pressed && styles.pressed]}
              testID="journey-exercise-score-details-toggle"
            >
              <Text style={[styles.detailsButtonText, { color: palette.brand }]}>View exercise details</Text>
              <Ionicons name={showDetails ? "chevron-up" : "chevron-forward"} size={19} color={palette.brand} />
            </Pressable>
          ) : null}
        </View>
      </View>

      {loading && !demoMode && !activities.length ? (
        <View style={styles.emptyState}>
          <ActivityIndicator color={palette.brand} />
          <Text style={[styles.emptyText, { color: palette.muted }]}>Loading your exercise scores...</Text>
        </View>
      ) : activities.length ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chartScroll}>
          <ScoreChart activities={activities} target={target} palette={palette} width={chartWidth} />
        </ScrollView>
      ) : (
        <View style={[styles.emptyState, { backgroundColor: palette.soft }]}>
          <View style={[styles.emptyIcon, { backgroundColor: palette.surface }]}>
            <Ionicons name="stats-chart-outline" size={25} color={palette.brand} />
          </View>
          <View style={styles.emptyCopy}>
            <Text style={[styles.emptyTitle, { color: palette.text }]}>Complete a guided exercise to begin</Text>
            <Text style={[styles.emptyText, { color: palette.muted }]}>Each point will show the average of all scored repetitions in that exercise session.</Text>
          </View>
        </View>
      )}

      {showDetails && activities.length ? (
        <View style={[styles.detailsList, { borderTopColor: palette.border }]} testID="journey-exercise-score-details">
          {activities.slice().reverse().map((activity, index) => (
            <View
              key={activity.id}
              style={[styles.detailRow, index > 0 && { borderTopColor: palette.border, borderTopWidth: 1 }]}
            >
              <View style={styles.detailCopy}>
                <Text style={[styles.detailName, { color: palette.text }]}>{readableExerciseName(activity)}</Text>
                <Text style={[styles.detailMeta, { color: palette.muted }]}>
                  {longDate(activityDate(activity))} · {activity.repetition_scores?.length || activity.completed_reps || 0} scored repetitions
                </Text>
              </View>
              <View style={[styles.detailScore, { backgroundColor: activity.average_score >= target ? "#DCEBDD" : "#F9E8BC" }]}>
                <Text style={styles.detailScoreValue}>{clampScore(activity.average_score)}</Text>
                <Text style={styles.detailScoreLabel}>avg</Text>
              </View>
            </View>
          ))}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.lg,
    overflow: "hidden",
  },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: spacing.lg },
  headerNarrow: { flexDirection: "column", gap: spacing.sm },
  titleRow: { flex: 1, flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  heading: { fontSize: 20, lineHeight: 26, fontWeight: "900" },
  sampleBadge: { borderRadius: radius.pill, paddingHorizontal: 9, paddingVertical: 4 },
  sampleBadgeText: { fontSize: 10, lineHeight: 13, fontWeight: "900" },
  summary: { minWidth: 210, alignItems: "flex-start" },
  summaryNarrow: { minWidth: 0, width: "100%" },
  averageRow: { flexDirection: "row", alignItems: "baseline", gap: spacing.xs },
  averageValue: { fontSize: 42, lineHeight: 48, fontWeight: "900" },
  averageLabel: { fontSize: 16, lineHeight: 22, fontWeight: "700" },
  goalCopy: { marginTop: 1, fontSize: 13, lineHeight: 18, fontWeight: "600" },
  detailsButton: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.xs },
  detailsButtonText: { fontSize: 14, lineHeight: 19, fontWeight: "800", textDecorationLine: "underline" },
  pressed: { opacity: 0.68 },
  chartScroll: { paddingTop: spacing.sm },
  emptyState: {
    minHeight: 150,
    borderRadius: radius.sm,
    marginTop: spacing.lg,
    padding: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.md,
  },
  emptyIcon: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  emptyCopy: { flex: 1, maxWidth: 540 },
  emptyTitle: { fontSize: 16, lineHeight: 22, fontWeight: "900" },
  emptyText: { fontSize: 13, lineHeight: 19, marginTop: 3 },
  detailsList: { borderTopWidth: 1, marginTop: spacing.sm, paddingTop: spacing.xs },
  detailRow: { minHeight: 72, flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm },
  detailCopy: { flex: 1, minWidth: 0 },
  detailName: { fontSize: 15, lineHeight: 20, fontWeight: "800" },
  detailMeta: { marginTop: 3, fontSize: 12, lineHeight: 17 },
  detailScore: { minWidth: 58, minHeight: 50, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  detailScoreValue: { color: "#173C2F", fontSize: 18, lineHeight: 21, fontWeight: "900" },
  detailScoreLabel: { color: "#38594B", fontSize: 10, lineHeight: 12, fontWeight: "800" },
});
