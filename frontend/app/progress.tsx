import React, { useCallback, useMemo, useState } from "react";
import { ProgressStoryCard } from "@/src/components/ProgressStoryCard";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Assessment, fetchAssessment } from "@/src/api";
import { authedFetch } from "@/src/auth";
import { DEMO_ASSESSMENT_ID } from "@/src/demoAssessment";
import { colors, radius, spacing } from "@/src/theme";
import { loadUserPreferences } from "@/src/userPreferences";
import { storage } from "@/src/utils/storage";

type AssessmentPoint = {
  id: string;
  date: string;
  shoulder_flexion_deg: number | null;
  trunk_lean_deg: number | null;
  reach_completion: number | null;
  bilateral_symmetry: number | null;
  pinch_grip: number | null;
  hand_opening: number | null;
  walking_skipped?: boolean;
  issues_count: number;
  exercises_count: number;
};

type Summary = {
  assessments: AssessmentPoint[];
  issues_history: { issue: string; count: number }[];
  first_seen: string | null;
  count?: number;
};

type MovementRow = {
  id: "reach" | "hand" | "walking";
  label: string;
  status: string;
  value: string;
  icon: React.ComponentProps<typeof Ionicons>["name"];
  direction: "up" | "steady";
};

type ProgressViewModel = {
  headline: string;
  headlineValue: string;
  headlineMetric: string;
  supportiveText: string;
  movementRows: MovementRow[];
  sessionsCompleted: number;
  sessionsGoal: number;
  sessionLabel: string;
  nextStep: string;
};

type ExerciseProgress = {
  completed_reps: number;
  total_reps: number;
  last_score: number | null;
  best_score: number | null;
  sessions: number;
};

const EMPTY_SUMMARY: Summary = { assessments: [], issues_history: [], first_seen: null };
const PROGRESS_KEY = (planId: string, exerciseId: string) => `ex_progress_v1:${planId}:${exerciseId}`;

const DEMO_VIEW: ProgressViewModel = {
  headline: "You're moving more comfortably",
  headlineValue: "24%",
  headlineMetric: "Less effort when reaching",
  supportiveText: "Small steps are adding up.",
  movementRows: [
    { id: "reach", label: "Reaching", status: "Improving", value: "24% easier", icon: "accessibility-outline", direction: "up" },
    { id: "hand", label: "Hand control", status: "Improving", value: "12% steadier", icon: "hand-left-outline", direction: "up" },
    { id: "walking", label: "Walking", status: "Moving well", value: "Steady", icon: "walk-outline", direction: "steady" },
  ],
  sessionsCompleted: 5,
  sessionsGoal: 7,
  sessionLabel: "sessions completed this week",
  nextStep: "Complete 2 more sessions this week",
};

function normalizeMetric(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.abs(value) <= 1.5 ? value * 100 : value;
}

function metricChange(points: AssessmentPoint[], key: keyof AssessmentPoint) {
  const values = points
    .map((point) => normalizeMetric(point[key] as number | null))
    .filter((value): value is number => value != null);
  if (values.length < 2) return null;
  return Math.max(-99, Math.min(99, Math.round(values[values.length - 1] - values[0])));
}

function bestMetricChange(points: AssessmentPoint[], keys: (keyof AssessmentPoint)[]) {
  const changes = keys.map((key) => metricChange(points, key)).filter((value): value is number => value != null);
  if (!changes.length) return null;
  return Math.round(changes.reduce((total, value) => total + value, 0) / changes.length);
}

function movementRow(
  id: MovementRow["id"],
  label: string,
  icon: MovementRow["icon"],
  change: number | null,
  improvementWord: string,
  hasBaseline: boolean,
): MovementRow {
  if (change != null && change >= 2) {
    return { id, label, icon, status: "Improving", value: `${change}% ${improvementWord}`, direction: "up" };
  }
  if (change != null && change <= -2) {
    return { id, label, icon, status: "Needs review", value: "Review", direction: "steady" };
  }
  if (hasBaseline) {
    return { id, label, icon, status: "Baseline recorded", value: "Steady", direction: "steady" };
  }
  return { id, label, icon, status: "Not measured yet", value: "Pending", direction: "steady" };
}

function buildRealView(summary: Summary, sessionsCompleted: number): ProgressViewModel {
  const points = summary.assessments;
  const latest = points[points.length - 1];
  const reachChange = metricChange(points, "reach_completion");
  const handChange = bestMetricChange(points, ["hand_opening", "pinch_grip"]);
  const walkingChange = metricChange(points, "bilateral_symmetry");
  const positiveChanges = [reachChange, handChange, walkingChange].filter((value): value is number => value != null && value > 0);
  const bestChange = positiveChanges.length ? Math.max(...positiveChanges) : null;
  const assessmentCount = points.length;
  const hasReach = normalizeMetric(latest?.reach_completion) != null || normalizeMetric(latest?.shoulder_flexion_deg) != null;
  const hasHand = normalizeMetric(latest?.hand_opening) != null || normalizeMetric(latest?.pinch_grip) != null;
  const hasWalking = normalizeMetric(latest?.bilateral_symmetry) != null;
  const sessionGoal = 7;
  const cappedSessions = Math.min(sessionGoal, Math.max(0, sessionsCompleted));

  let headline = "Your first recovery picture is ready";
  let headlineValue = "1st";
  let headlineMetric = "Assessment complete";
  let supportiveText = "Complete another check-in to see what is changing.";

  if (assessmentCount > 1 && bestChange != null) {
    headline = "You're moving more comfortably";
    headlineValue = `${bestChange}%`;
    headlineMetric = bestChange === reachChange
      ? "More comfortable reaching"
      : bestChange === handChange
        ? "Steadier hand control"
        : "More even movement";
    supportiveText = "Small steps are adding up.";
  } else if (assessmentCount > 1) {
    headline = "Your recovery is building consistency";
    headlineValue = String(assessmentCount);
    headlineMetric = "Recovery check-ins completed";
    supportiveText = "Your results are ready to review together.";
  }

  const walkingRow = latest?.walking_skipped
    ? { id: "walking" as const, label: "Walking", icon: "walk-outline" as const, status: "Not observed", value: "Skipped", direction: "steady" as const }
    : movementRow("walking", "Walking", "walk-outline", walkingChange, "steadier", hasWalking);

  return {
    headline,
    headlineValue,
    headlineMetric,
    supportiveText,
    movementRows: [
      movementRow("reach", "Reaching", "accessibility-outline", reachChange, "easier", hasReach),
      movementRow("hand", "Hand control", "hand-left-outline", handChange, "steadier", hasHand),
      walkingRow,
    ],
    sessionsCompleted: cappedSessions,
    sessionsGoal: sessionGoal,
    sessionLabel: "guided sessions completed",
    nextStep: cappedSessions < sessionGoal
      ? `Complete ${sessionGoal - cappedSessions} more session${sessionGoal - cappedSessions === 1 ? "" : "s"}`
      : "You completed this week's goal",
  };
}

async function loadExerciseSessions(assessment: Assessment) {
  const sessionCounts = await Promise.all(assessment.rehab_plan.map(async (exercise) => {
    try {
      const raw = await storage.getItem(PROGRESS_KEY(assessment.id, exercise.id), "");
      const parsed = typeof raw === "string" && raw ? JSON.parse(raw) as ExerciseProgress : null;
      return Math.max(0, Number(parsed?.sessions || 0));
    } catch {
      return 0;
    }
  }));
  return sessionCounts.reduce((total, value) => total + value, 0);
}

function MovementProgressRow({ item, isLast, wide }: { item: MovementRow; isLast: boolean; wide: boolean }) {
  return (
    <View style={[styles.movementRow, !wide && styles.movementRowMobile, !isLast && styles.movementRowDivider]} testID={`progress-domain-${item.id}`}>
      <View style={[styles.movementIdentity, !wide && styles.movementIdentityMobile]}>
        <View style={[styles.movementIcon, !wide && styles.movementIconMobile]}>
          <Ionicons name={item.icon} size={wide ? 34 : 28} color="#0B5D38" />
        </View>
        <View style={styles.movementCopy}>
          <Text style={[styles.movementLabel, wide && styles.movementLabelWide, !wide && styles.movementLabelMobile]}>{item.label}</Text>
          <Text style={[styles.movementStatus, !wide && styles.movementStatusMobile]}>{item.status}</Text>
        </View>
      </View>
      <View style={[styles.movementValueWrap, !wide && styles.movementValueWrapMobile]}>
        <View style={[styles.movementDirection, !wide && styles.movementDirectionMobile]}>
          <Ionicons name={item.direction === "up" ? "trending-up-outline" : "arrow-forward-outline"} size={wide ? 28 : 23} color="#16833F" />
        </View>
        <Text style={[styles.movementValue, wide && styles.movementValueWide, !wide && styles.movementValueMobile]}>{item.value}</Text>
      </View>
    </View>
  );
}

export default function ProgressScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { demo } = useLocalSearchParams<{ demo?: string }>();
  const wide = width >= 820;
  type ProgressCache = { summary: Summary; demoMode: boolean; sessionsCompleted: number; latestPlanId: string | null };
  const progressCacheKey = `progress-screen:${demo ?? ""}`;
  const cachedProgress = getScreenCache<ProgressCache>(progressCacheKey);
  const [summary, setSummary] = useState<Summary>(cachedProgress?.summary ?? EMPTY_SUMMARY);
  const [demoMode, setDemoMode] = useState(cachedProgress?.demoMode ?? (demo === "1"));
  const [loading, setLoading] = useState(!cachedProgress);
  const [sessionsCompleted, setSessionsCompleted] = useState(cachedProgress?.sessionsCompleted ?? 0);
  const [latestPlanId, setLatestPlanId] = useState<string | null>(cachedProgress?.latestPlanId ?? null);

  const load = useCallback(async () => {
    if (!getScreenCache<ProgressCache>(progressCacheKey)) setLoading(true);
    try {
      const [preferences, response] = await Promise.all([
        loadUserPreferences(),
        authedFetch("/api/progress/summary"),
      ]);
      const progressSummary = response.ok ? await response.json() as Summary : EMPTY_SUMMARY;
      const showDemo = demo === "1" || preferences.demoMode;
      setDemoMode(showDemo);
      setSummary(progressSummary);

      if (!showDemo && progressSummary.assessments.length) {
        const latestId = progressSummary.assessments[progressSummary.assessments.length - 1].id;
        const latestAssessment = await fetchAssessment(latestId).catch(() => null);
        if (latestAssessment) {
          setLatestPlanId(latestAssessment.id);
          setSessionsCompleted(await loadExerciseSessions(latestAssessment));
        } else {
          setLatestPlanId(null);
          setSessionsCompleted(0);
        }
      } else {
        setLatestPlanId(showDemo ? DEMO_ASSESSMENT_ID : null);
        setSessionsCompleted(0);
      }
    } catch {
      setSummary(EMPTY_SUMMARY);
      setLatestPlanId(demo === "1" ? DEMO_ASSESSMENT_ID : null);
      setDemoMode(demo === "1");
      setSessionsCompleted(0);
    } finally {
      setLoading(false);
    }
  }, [demo, progressCacheKey]);

  React.useEffect(() => {
    if (!loading) setScreenCache(progressCacheKey, { summary, demoMode, sessionsCompleted, latestPlanId });
  }, [loading, summary, demoMode, sessionsCompleted, latestPlanId, progressCacheKey]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const viewModel = useMemo(
    () => demoMode ? DEMO_VIEW : buildRealView(summary, sessionsCompleted),
    [demoMode, sessionsCompleted, summary],
  );
  const hasProgress = demoMode || summary.assessments.length > 0;

  const continuePlan = () => {
    if (latestPlanId) {
      router.push({ pathname: "/rehab-plan" as never, params: { id: latestPlanId } });
    } else {
      router.dismissTo("/");
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backButton} testID="progress-back" accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={28} color="#073F2A" />
        </Pressable>
        <Text style={styles.title}>Progress</Text>
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator size="large" color={colors.brandPrimary} /></View>
      ) : !hasProgress ? (
        <View style={styles.emptyWrap} testID="progress-empty">
          <View style={styles.emptyIcon}><Ionicons name="trending-up-outline" size={42} color={colors.brandPrimary} /></View>
          <Text style={styles.emptyTitle}>Your progress starts here</Text>
          <Text style={styles.emptyBody}>Complete your first assessment to create a recovery baseline and see what changes over time.</Text>
          <Pressable onPress={() => router.dismissTo("/")} style={styles.primaryButton} testID="progress-empty-cta">
            <Text style={styles.primaryButtonText}>Start assessment</Text>
            <Ionicons name="chevron-forward" size={21} color="#FFFFFF" />
          </Pressable>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
          <View style={styles.page}>
            <ProgressStoryCard />
            {demoMode && (
              <View style={styles.demoBanner} testID="progress-demo-banner">
                <Ionicons name="sparkles" size={24} color="#674AA8" />
                <Text style={styles.demoBannerText}>Demo progress using sample data.</Text>
              </View>
            )}

            <View style={[styles.heroCard, !wide && styles.heroCardMobile]} testID="progress-hero">
              <View style={[styles.heroIcon, wide && styles.heroIconWide]}>
                <Ionicons name="trending-up-outline" size={wide ? 96 : 48} color="#07542F" />
              </View>
              <View style={styles.heroCopy}>
                <Text style={[styles.heroHeadline, wide && styles.heroHeadlineWide]}>{viewModel.headline}</Text>
                <View style={[styles.heroMetricRow, !wide && styles.heroMetricRowMobile]}>
                  <Text style={[styles.heroValue, wide && styles.heroValueWide]}>{viewModel.headlineValue}</Text>
                  <View style={styles.heroMetricCopy}>
                    <Text style={[styles.heroMetric, wide && styles.heroMetricWide]}>{viewModel.headlineMetric}</Text>
                    <Text style={[styles.heroSupport, wide && styles.heroSupportWide]}>{viewModel.supportiveText}</Text>
                  </View>
                </View>
              </View>
            </View>

            <View style={styles.movementCard} testID="progress-movement-list">
              {viewModel.movementRows.map((item, index) => (
                <MovementProgressRow key={item.id} item={item} isLast={index === viewModel.movementRows.length - 1} wide={wide} />
              ))}
            </View>

            <View style={[styles.sessionsCard, !wide && styles.sessionsCardMobile]} testID="progress-weekly-sessions">
              <View style={styles.sessionCopy}>
                <Text style={[styles.sessionCount, wide && styles.sessionCountWide]}>{viewModel.sessionsCompleted} of {viewModel.sessionsGoal}</Text>
                <Text style={[styles.sessionLabel, wide && styles.sessionLabelWide]}>{viewModel.sessionLabel}</Text>
              </View>
              <View style={styles.sessionDots} accessibilityLabel={`${viewModel.sessionsCompleted} of ${viewModel.sessionsGoal} sessions completed`}>
                {Array.from({ length: viewModel.sessionsGoal }, (_, index) => {
                  const complete = index < viewModel.sessionsCompleted;
                  return (
                    <View key={index} style={[styles.sessionDot, wide && styles.sessionDotWide, complete && styles.sessionDotComplete]}>
                      {complete && <Ionicons name="checkmark" size={wide ? 22 : 16} color="#FFFFFF" />}
                    </View>
                  );
                })}
              </View>
            </View>

            <View style={[styles.nextCard, !wide && styles.nextCardMobile]} testID="progress-next-step">
              <View style={[styles.nextIdentity, !wide && styles.nextIdentityMobile]}>
                <View style={[styles.nextIcon, wide && styles.nextIconWide]}><Ionicons name="locate-outline" size={wide ? 52 : 34} color="#07542F" /></View>
                <View style={styles.nextCopy}>
                  <Text style={styles.nextEyebrow}>NEXT STEP</Text>
                  <Text style={[styles.nextTitle, wide && styles.nextTitleWide]}>{viewModel.nextStep}</Text>
                </View>
              </View>
              <Pressable onPress={continuePlan} style={[styles.primaryButton, wide && styles.primaryButtonWide]} testID="progress-continue-plan">
                <Ionicons name="chevron-forward" size={24} color="#FFFFFF" />
                <Text style={[styles.primaryButtonText, wide && styles.primaryButtonTextWide]}>{"Continue today's plan"}</Text>
              </Pressable>
            </View>
          </View>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FCFDFB" },
  topBar: { minHeight: 66, alignItems: "center", justifyContent: "center", borderBottomWidth: 1, borderBottomColor: "#E1E5DE", paddingHorizontal: spacing.md },
  backButton: { position: "absolute", left: spacing.md, width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 24, lineHeight: 30, fontWeight: "900", color: "#073F2A" },
  scroll: { paddingHorizontal: spacing.md, paddingTop: spacing.md, paddingBottom: 56 },
  page: { width: "100%", maxWidth: 1422, alignSelf: "center", gap: spacing.md },
  demoBanner: { minHeight: 68, flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderWidth: 1, borderColor: "#D6C5EE", borderRadius: radius.md, backgroundColor: "#F4EFFB" },
  demoBannerText: { flex: 1, fontSize: 16, lineHeight: 22, fontWeight: "800", color: "#563E94" },
  heroCard: { minHeight: 260, flexDirection: "row", alignItems: "center", gap: 44, paddingHorizontal: 58, paddingVertical: 28, borderWidth: 1, borderColor: "#DDE5D8", borderRadius: radius.md, backgroundColor: "#F3F7F0" },
  heroCardMobile: { minHeight: 0, flexDirection: "column", alignItems: "flex-start", gap: spacing.md, paddingHorizontal: spacing.md, paddingVertical: spacing.lg },
  heroIcon: { width: 84, height: 84, borderRadius: 42, alignItems: "center", justifyContent: "center", backgroundColor: "#E7EFE3", flexShrink: 0 },
  heroIconWide: { width: 210, height: 210, borderRadius: 105 },
  heroCopy: { flex: 1, minWidth: 0 },
  heroHeadline: { fontSize: 28, lineHeight: 34, fontWeight: "900", color: "#06452D" },
  heroHeadlineWide: { fontSize: 50, lineHeight: 56 },
  heroMetricRow: { flexDirection: "row", alignItems: "center", gap: 76, marginTop: spacing.md },
  heroMetricRowMobile: { alignItems: "flex-end", gap: spacing.md, marginTop: spacing.sm },
  heroValue: { fontSize: 58, lineHeight: 64, fontWeight: "900", color: "#004C2E", flexShrink: 0 },
  heroValueWide: { fontSize: 116, lineHeight: 122 },
  heroMetricCopy: { flex: 1, minWidth: 0, paddingBottom: 4 },
  heroMetric: { fontSize: 18, lineHeight: 24, fontWeight: "800", color: "#17221D" },
  heroMetricWide: { fontSize: 26, lineHeight: 32 },
  heroSupport: { fontSize: 15, lineHeight: 21, color: "#26342D", marginTop: 4 },
  heroSupportWide: { fontSize: 22, lineHeight: 29 },
  movementCard: { borderWidth: 1, borderColor: "#DDE3DA", borderRadius: radius.md, backgroundColor: "#FFFFFF", paddingHorizontal: spacing.md },
  movementRow: { minHeight: 106, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md, paddingVertical: spacing.sm, paddingHorizontal: 30 },
  movementRowMobile: { minHeight: 90, gap: spacing.sm, paddingHorizontal: spacing.sm },
  movementRowDivider: { borderBottomWidth: 1, borderBottomColor: "#E5E8E2" },
  movementIdentity: { flex: 1, minWidth: 0, flexDirection: "row", alignItems: "center", gap: spacing.md },
  movementIdentityMobile: { gap: spacing.sm },
  movementIcon: { width: 68, height: 68, borderRadius: 34, alignItems: "center", justifyContent: "center", backgroundColor: "#F0F4ED" },
  movementIconMobile: { width: 48, height: 48, borderRadius: 24 },
  movementCopy: { flex: 1, minWidth: 0 },
  movementLabel: { fontSize: 22, lineHeight: 27, fontWeight: "900", color: "#0B4A31" },
  movementLabelWide: { fontSize: 30, lineHeight: 36 },
  movementLabelMobile: { fontSize: 18, lineHeight: 22 },
  movementStatus: { fontSize: 15, lineHeight: 21, color: "#16833F", fontWeight: "700", marginTop: 2 },
  movementStatusMobile: { fontSize: 13, lineHeight: 18 },
  movementValueWrap: { flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: spacing.md, maxWidth: "43%" },
  movementValueWrapMobile: { gap: spacing.xs, maxWidth: "40%" },
  movementDirection: { width: 52, height: 52, borderRadius: 26, alignItems: "center", justifyContent: "center", borderWidth: 1.5, borderColor: "#16833F" },
  movementDirectionMobile: { width: 40, height: 40, borderRadius: 20 },
  movementValue: { fontSize: 17, lineHeight: 22, fontWeight: "900", color: "#16833F", textAlign: "right" },
  movementValueWide: { minWidth: 158, fontSize: 22, lineHeight: 28, textAlign: "left" },
  movementValueMobile: { maxWidth: 76, fontSize: 14, lineHeight: 18 },
  sessionsCard: { minHeight: 86, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.lg, paddingHorizontal: 44, paddingVertical: spacing.md, borderWidth: 1, borderColor: "#DDE3DA", borderRadius: radius.md, backgroundColor: "#FFFFFF" },
  sessionsCardMobile: { flexDirection: "column", alignItems: "stretch", paddingHorizontal: spacing.md },
  sessionCopy: { flexDirection: "row", alignItems: "baseline", flexWrap: "wrap", gap: spacing.md, flex: 1 },
  sessionCount: { fontSize: 30, lineHeight: 36, fontWeight: "900", color: "#06472D" },
  sessionCountWide: { fontSize: 40, lineHeight: 46 },
  sessionLabel: { fontSize: 15, lineHeight: 21, fontWeight: "700", color: colors.onSurface },
  sessionLabelWide: { fontSize: 20, lineHeight: 26 },
  sessionDots: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  sessionDot: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center", borderWidth: 1.5, borderColor: "#C9CEC6", backgroundColor: "#FFFFFF" },
  sessionDotWide: { width: 42, height: 42, borderRadius: 21 },
  sessionDotComplete: { borderColor: "#076136", backgroundColor: "#076136" },
  nextCard: { minHeight: 140, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.lg, paddingHorizontal: 34, paddingVertical: spacing.md, borderWidth: 1, borderColor: "#DCE4D8", borderRadius: radius.md, backgroundColor: "#F1F6EE" },
  nextCardMobile: { flexDirection: "column", alignItems: "stretch", paddingHorizontal: spacing.md, paddingVertical: spacing.lg },
  nextIdentity: { flex: 1, minWidth: 0, flexDirection: "row", alignItems: "center", gap: spacing.md },
  nextIdentityMobile: { alignItems: "flex-start" },
  nextIcon: { width: 68, height: 68, borderRadius: 34, alignItems: "center", justifyContent: "center", backgroundColor: "#E4EEE0", flexShrink: 0 },
  nextIconWide: { width: 86, height: 86, borderRadius: 43 },
  nextCopy: { flex: 1, minWidth: 0 },
  nextEyebrow: { fontSize: 13, lineHeight: 18, fontWeight: "900", color: "#16833F" },
  nextTitle: { fontSize: 22, lineHeight: 28, fontWeight: "900", color: "#06472D", marginTop: 3 },
  nextTitleWide: { fontSize: 29, lineHeight: 35 },
  primaryButton: { minHeight: 54, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.lg, borderRadius: radius.sm, backgroundColor: "#00613B" },
  primaryButtonWide: { minWidth: 340, minHeight: 70 },
  primaryButtonText: { color: "#FFFFFF", fontSize: 16, lineHeight: 21, fontWeight: "900", textAlign: "center" },
  primaryButtonTextWide: { fontSize: 20, lineHeight: 26 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyWrap: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: spacing.md },
  emptyIcon: { width: 88, height: 88, borderRadius: 44, backgroundColor: "#E8F0E5", alignItems: "center", justifyContent: "center" },
  emptyTitle: { fontSize: 24, lineHeight: 30, fontWeight: "900", color: "#073F2A", textAlign: "center" },
  emptyBody: { maxWidth: 420, fontSize: 16, lineHeight: 23, color: colors.onSurfaceSecondary, textAlign: "center" },
});
