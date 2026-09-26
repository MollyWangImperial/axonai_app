import React, { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Image,
  ImageSourcePropType,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import Svg, { Circle } from "react-native-svg";
import { colors, spacing, radius } from "@/src/theme";
import { fetchAssessment, Assessment, RehabExercise } from "@/src/api";
import { storage } from "@/src/utils/storage";
import { authedFetch } from "@/src/auth";
import PaywallModal from "@/src/components/PaywallModal";
import { DEMO_ASSESSMENT_ID, demoAssessment } from "@/src/demoAssessment";

type ExerciseProgress = {
  completed_reps: number;
  total_reps: number;
  last_score: number | null;
  best_score: number | null;
  sessions: number;
};

const SUPPORTED_REACH_IMAGE = require("../assets/images/rehab-supported-forward-reach.png") as ImageSourcePropType;
const HAND_OPENING_IMAGE = require("../assets/images/rehab-relaxed-hand-opening.png") as ImageSourcePropType;
const PROGRESS_KEY = (planId: string, exId: string) => `ex_progress_v1:${planId}:${exId}`;

function exerciseImage(exercise: RehabExercise): ImageSourcePropType {
  const text = `${exercise.name} ${exercise.description} ${exercise.targets_issue}`.toLowerCase();
  return /hand|finger|grip|palm|thumb/.test(text) ? HAND_OPENING_IMAGE : SUPPORTED_REACH_IMAGE;
}

function exerciseFocus(exercise: RehabExercise): string {
  const text = `${exercise.name} ${exercise.targets_issue}`.toLowerCase();
  if (/hand|finger|grip|palm|thumb/.test(text)) return "Hand control";
  if (/walk|gait|balance|step|leg/.test(text)) return "Walking control";
  if (/shoulder|reach|arm/.test(text)) return "Shoulder mobility";
  return "Movement control";
}

function exercisePurpose(exercise: RehabExercise): string {
  if (exercise.selection_reason) return exercise.selection_reason;
  const focus = exerciseFocus(exercise);
  if (focus === "Hand control") return "Supports comfortable hand opening and control for everyday tasks.";
  if (focus === "Walking control") return "Supports steadier movement and confidence during everyday walking.";
  return "Builds controlled reach while reducing unnecessary shoulder effort.";
}

function exerciseSafety(exercise: RehabExercise): string {
  return exercise.safety_note || "Use a comfortable range. Stop if you feel pain, dizziness, or unusual fatigue.";
}

function ProgressRing({ percent, size = 72 }: { percent: number; size?: number }) {
  const strokeWidth = size >= 70 ? 9 : 7;
  const radiusValue = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radiusValue;
  const value = Math.max(0, Math.min(100, percent));

  return (
    <View style={{ width: size, height: size, alignItems: "center", justifyContent: "center" }}>
      <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
        <Circle cx={size / 2} cy={size / 2} r={radiusValue} fill="none" stroke="#DDE3DE" strokeWidth={strokeWidth} />
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={radiusValue}
          fill="none"
          stroke={colors.brandPrimary}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${circumference} ${circumference}`}
          strokeDashoffset={circumference - (value / 100) * circumference}
          rotation="-90"
          origin={`${size / 2}, ${size / 2}`}
        />
      </Svg>
      <Text style={[styles.ringText, size < 70 && styles.ringTextSmall]}>{value}%</Text>
    </View>
  );
}

export default function RehabPlanScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState<Record<string, ExerciseProgress>>({});
  const [paywallOpen, setPaywallOpen] = useState(false);
  const [paywallReason, setPaywallReason] = useState<string | undefined>();
  const [demonstrationId, setDemonstrationId] = useState<string | null>(null);

  const planId = id || "default";
  const isDemo = id === DEMO_ASSESSMENT_ID;
  const isWide = width >= 860;

  const loadProgress = React.useCallback(async (plan: Assessment) => {
    const out: Record<string, ExerciseProgress> = {};
    for (const ex of plan.rehab_plan) {
      try {
        const raw = await storage.getItem(PROGRESS_KEY(planId, ex.id), "");
        out[ex.id] = typeof raw === "string" && raw
          ? JSON.parse(raw)
          : { completed_reps: 0, total_reps: ex.sets * ex.reps, last_score: null, best_score: null, sessions: 0 };
      } catch {
        out[ex.id] = { completed_reps: 0, total_reps: ex.sets * ex.reps, last_score: null, best_score: null, sessions: 0 };
      }
    }
    setProgress(out);
  }, [planId]);

  useEffect(() => {
    (async () => {
      try {
        if (id) {
          const assessment = id === DEMO_ASSESSMENT_ID ? demoAssessment : await fetchAssessment(id);
          setData(assessment);
          await loadProgress(assessment);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [id, loadProgress]);

  useFocusEffect(
    React.useCallback(() => {
      if (data) loadProgress(data);
    }, [data, loadProgress])
  );

  const completedCount = Object.values(progress).filter((item) => item.completed_reps >= item.total_reps).length;
  const totalExercises = data?.rehab_plan.length || 0;
  const planPercent = Math.round((completedCount / Math.max(1, totalExercises)) * 100);
  const allComplete = totalExercises > 0 && completedCount >= totalExercises;
  const estimatedMinutes = Math.max(5, totalExercises * 5);
  const demonstrationExercise = useMemo(
    () => data?.rehab_plan.find((exercise) => exercise.id === demonstrationId) || null,
    [data, demonstrationId]
  );

  const openGuidedExercise = async (exercise: RehabExercise) => {
    setDemonstrationId(null);
    void Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    if (!isDemo) {
      try {
        const response = await authedFetch("/api/credits/balance");
        const balance = await response.json();
        const needed = balance.costs?.guided_exercise ?? 30;
        if (!balance.subscription_active && (balance.credits ?? 0) < needed) {
          setPaywallReason("You're out of credits. Subscribe to unlock unlimited guided exercises.");
          setPaywallOpen(true);
          return;
        }
      } catch {
        // The exercise runner performs the final access check when connectivity returns.
      }
    }
    router.push({
      pathname: "/exercise",
      params: { exercise_id: exercise.id, name: exercise.name, plan_id: planId, sets: String(exercise.sets), reps: String(exercise.reps) },
    });
  };

  if (loading) {
    return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brandPrimary} /></View>;
  }

  if (!data) {
    return <View style={[styles.container, styles.center]}><Text>No plan available.</Text></View>;
  }

  if (data.clinical_review_gate?.rehab_access !== "allowed" || data.rehab_plan.length === 0) {
    const gate = data.clinical_review_gate;
    const awaiting = gate?.status === "awaiting_model_analysis";
    const noRehabNeeded = gate?.status === "no_rehab_needed" || gate?.rehab_access === "not_needed";
    const title = gate?.patient_title || "No rehabilitation plan is available";
    const message = gate?.patient_message || "This assessment did not produce exercises for automatic recommendation.";
    const nextStep = gate?.next_step || "Return home and review the result with your therapist if you still have symptoms.";
    return (
      <View style={styles.container}>
        <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
          <Pressable onPress={() => router.replace("/")} style={styles.backBtn} testID="plan-blocked-back">
            <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.headerTitle}>Rehab plan</Text>
          <View style={styles.headerSpacer} />
        </View>
        <View style={[styles.center, styles.blockedContent]} testID={noRehabNeeded ? "plan-no-rehab-needed" : "plan-clinical-review-hold"}>
          <View style={styles.blockedIcon}>
            <Ionicons name={noRehabNeeded ? "checkmark-circle-outline" : awaiting ? "hourglass-outline" : "people-outline"} size={30} color={colors.brandPrimary} />
          </View>
          <Text style={styles.blockedTitle}>{title}</Text>
          <Text style={styles.blockedText}>{message}</Text>
          <Text style={styles.blockedNext}>{nextStep}</Text>
          <Pressable onPress={() => router.replace("/")} style={styles.blockedButton} testID="plan-blocked-home">
            <Ionicons name="home-outline" size={20} color={colors.onBrandPrimary} />
            <Text style={styles.guidedBtnText}>Return home</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="plan-back" accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={26} color={colors.brandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Rehab plan</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={styles.scrollContent}>
        <View style={styles.page}>
          {isDemo && (
            <View style={styles.demoBanner} testID="rehab-demo-banner">
              <Ionicons name="sparkles" size={22} color="#775C97" />
              <Text style={styles.demoBannerText}>Sample plan for preview only. Confirm any real exercises with your therapist.</Text>
            </View>
          )}

          <View style={[styles.summaryPanel, isWide && styles.summaryPanelWide]}>
            <View style={styles.summaryCopy}>
              <Text style={styles.summaryTitle}>Today&apos;s plan</Text>
              <Text style={styles.summarySubtitle}>{totalExercises} exercises tailored to your focus areas</Text>
            </View>
            <View style={[styles.summaryMetrics, isWide ? styles.summaryMetricsWide : styles.summaryMetricsNarrow]}>
              <View style={[styles.metricBox, !isWide && styles.metricBoxNarrow]}>
                <View style={styles.metricIcon}><Ionicons name="clipboard-outline" size={26} color={colors.brandPrimary} /></View>
                <Text style={styles.metricText}>{totalExercises} exercises</Text>
              </View>
              <View style={[styles.metricBox, !isWide && styles.metricBoxNarrow]}>
                <View style={styles.metricIcon}><Ionicons name="time-outline" size={28} color={colors.brandPrimary} /></View>
                <Text style={styles.metricText}>About {estimatedMinutes} minutes</Text>
              </View>
            </View>
            <View style={[styles.summaryProgress, isWide && styles.summaryProgressWide]} testID="plan-progress-summary">
              <ProgressRing percent={planPercent} />
              <Text style={styles.summaryProgressText}>{completedCount} of {totalExercises} complete</Text>
            </View>
          </View>

          <View style={styles.exerciseList}>
            {data.rehab_plan.map((exercise, index) => {
              const itemProgress = progress[exercise.id] || { completed_reps: 0, total_reps: exercise.sets * exercise.reps, last_score: null, best_score: null, sessions: 0 };
              const percent = Math.min(100, Math.round((itemProgress.completed_reps / Math.max(1, itemProgress.total_reps)) * 100));
              const isDone = percent >= 100;
              const status = isDone ? "Complete" : percent > 0 ? "In progress" : "Not started";

              return (
                <View key={exercise.id} style={[styles.exerciseCard, isWide && styles.exerciseCardWide, isDone && styles.exerciseCardDone]} testID={`exercise-${exercise.id}`}>
                  <View style={[styles.illustrationPanel, isWide && styles.illustrationPanelWide]}>
                    <Image source={exerciseImage(exercise)} style={styles.exerciseImage} resizeMode="contain" accessibilityLabel={`Demonstration of ${exercise.name}`} />
                  </View>
                  <View style={styles.exerciseBody}>
                    <View style={styles.exerciseHeader}>
                      <View style={[styles.exerciseNumber, isDone && styles.exerciseNumberDone]}>
                        {isDone ? <Ionicons name="checkmark" size={20} color="#FFFEFA" /> : <Text style={styles.exerciseNumberText}>{index + 1}</Text>}
                      </View>
                      <View style={styles.exerciseHeadingCopy}>
                        <View style={styles.titleAndTag}>
                          <Text style={styles.exerciseTitle}>{exercise.name}</Text>
                          <View style={styles.focusTag}><Text style={styles.focusTagText}>{exerciseFocus(exercise)}</Text></View>
                        </View>
                        <Text style={styles.exerciseMeta}>{exercise.sets} sets × {exercise.reps} reps · {exercise.frequency}</Text>
                      </View>
                      <View style={[styles.statusTag, isDone && styles.statusTagDone, percent > 0 && !isDone && styles.statusTagActive]} testID={`exercise-progress-${exercise.id}`}>
                        <Text style={[styles.statusTagText, isDone && styles.statusTagTextDone]}>{status}</Text>
                      </View>
                    </View>
                    <View style={styles.exerciseRule} />
                    <Text style={styles.exerciseDescription}>{exercise.description}</Text>
                    <View style={[styles.calloutRow, isWide && styles.calloutRowWide]}>
                      <View style={[styles.callout, styles.purposeCallout]}>
                        <Ionicons name="help-circle-outline" size={26} color={colors.brandPrimary} />
                        <View style={styles.calloutCopy}>
                          <Text style={styles.purposeTitle}>Why this helps</Text>
                          <Text style={styles.calloutText}>{exercisePurpose(exercise)}</Text>
                        </View>
                      </View>
                      <View style={[styles.callout, styles.safetyCallout]}>
                        <Ionicons name="warning-outline" size={27} color="#A06D2F" />
                        <View style={styles.calloutCopy}>
                          <Text style={styles.safetyTitle}>Safety</Text>
                          <Text style={styles.calloutText}>{exerciseSafety(exercise)}</Text>
                        </View>
                      </View>
                    </View>
                    {itemProgress.last_score != null && <Text style={styles.sessionScore}>Last guided session: {itemProgress.last_score}/100</Text>}
                    <View style={styles.exerciseActions}>
                      <Pressable onPress={() => setDemonstrationId(exercise.id)} style={styles.demoLink} testID={`exercise-demo-${exercise.id}`}>
                        <Ionicons name="eye-outline" size={18} color={colors.brandPrimary} />
                        <Text style={styles.demoLinkText}>View demonstration</Text>
                      </Pressable>
                      <Pressable onPress={() => openGuidedExercise(exercise)} style={styles.guidedBtn} testID={`exercise-guided-${exercise.id}`}>
                        <Ionicons name="play" size={18} color="#FFFEFA" />
                        <Text style={styles.guidedBtnText}>{isDone ? "Practice again" : percent > 0 ? "Continue exercise" : "Start exercise"}</Text>
                      </Pressable>
                    </View>
                  </View>
                </View>
              );
            })}
          </View>
        </View>
      </ScrollView>

      <View style={[styles.completionBar, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
        <View style={[styles.completionBarInner, !isWide && styles.completionBarInnerNarrow]}>
          <View style={styles.completionCount}>
            <ProgressRing percent={planPercent} size={52} />
            <Text style={styles.completionCountText}>{completedCount} of {totalExercises} exercises complete</Text>
          </View>
          <Pressable disabled={!allComplete} onPress={() => router.replace("/")} style={[styles.finishButton, !allComplete && styles.finishButtonDisabled]} testID="plan-done">
            <Ionicons name="checkmark-circle" size={21} color={allComplete ? "#FFFEFA" : "#9AA09C"} />
            <Text style={[styles.finishButtonText, !allComplete && styles.finishButtonTextDisabled]}>Finish session</Text>
          </Pressable>
        </View>
      </View>

      <Modal visible={!!demonstrationExercise} transparent animationType="fade" onRequestClose={() => setDemonstrationId(null)}>
        <View style={styles.modalBackdrop}>
          {demonstrationExercise && (
            <View style={styles.modalCard} testID="exercise-demonstration-modal">
              <View style={styles.modalHeader}>
                <View>
                  <Text style={styles.modalEyebrow}>Exercise demonstration</Text>
                  <Text style={styles.modalTitle}>{demonstrationExercise.name}</Text>
                </View>
                <Pressable onPress={() => setDemonstrationId(null)} style={styles.modalClose} accessibilityLabel="Close demonstration">
                  <Ionicons name="close" size={24} color={colors.onSurface} />
                </Pressable>
              </View>
              <View style={styles.modalImageWrap}><Image source={exerciseImage(demonstrationExercise)} style={styles.modalImage} resizeMode="contain" /></View>
              <Text style={styles.modalInstruction}>{demonstrationExercise.description}</Text>
              <Text style={styles.modalSafety}>{exerciseSafety(demonstrationExercise)}</Text>
              {!!demonstrationExercise.source && <Text style={styles.modalSource}>Source: {demonstrationExercise.source}</Text>}
              <Pressable onPress={() => openGuidedExercise(demonstrationExercise)} style={styles.modalStart} testID="demonstration-start-exercise">
                <Ionicons name="play" size={18} color="#FFFEFA" />
                <Text style={styles.guidedBtnText}>Start guided exercise</Text>
              </Pressable>
            </View>
          )}
        </View>
      </Modal>

      <PaywallModal visible={paywallOpen} onClose={() => setPaywallOpen(false)} onSubscribed={() => undefined} reason={paywallReason} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  header: { minHeight: 72, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border },
  backBtn: { width: 48, height: 48, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 22, lineHeight: 28, fontWeight: "800", color: colors.onSurface },
  headerSpacer: { width: 44 },
  scrollContent: { paddingHorizontal: spacing.md, paddingTop: spacing.md, paddingBottom: 126 },
  page: { width: "100%", maxWidth: 1360, alignSelf: "center" },
  demoBanner: { flexDirection: "row", alignItems: "center", gap: spacing.sm, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.md, marginBottom: spacing.md, backgroundColor: "#F6F0EA", borderWidth: 1, borderColor: "#E6CFC0" },
  demoBannerText: { flex: 1, fontSize: 16, lineHeight: 23, fontWeight: "700", color: "#6B493A" },
  summaryPanel: { backgroundColor: "#FFFEFA", borderRadius: radius.md, borderWidth: 1, borderColor: colors.borderStrong, padding: spacing.lg, marginBottom: spacing.lg, gap: spacing.md, shadowColor: "#24362F", shadowOpacity: 0.05, shadowRadius: 10, shadowOffset: { width: 0, height: 3 }, elevation: 1 },
  summaryPanelWide: { flexDirection: "row", alignItems: "center", paddingHorizontal: 32 },
  summaryCopy: { minWidth: 260, flex: 1 },
  summaryTitle: { fontSize: 28, lineHeight: 34, fontWeight: "800", color: colors.onSurface, marginBottom: 6 },
  summarySubtitle: { fontSize: 16, lineHeight: 24, color: colors.onSurfaceSecondary },
  summaryMetrics: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  summaryMetricsWide: { flex: 1.35, justifyContent: "center" },
  summaryMetricsNarrow: { flexWrap: "nowrap" },
  metricBox: { minHeight: 84, minWidth: 190, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, backgroundColor: "#FAFBF7" },
  metricBoxNarrow: { minWidth: 0, minHeight: 92, flex: 1, flexDirection: "column", justifyContent: "center", paddingHorizontal: spacing.sm, gap: 4 },
  metricIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: "#EDF4EF" },
  metricText: { fontSize: 16, lineHeight: 22, color: colors.onSurface, fontWeight: "700" },
  summaryProgress: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  summaryProgressWide: { borderLeftWidth: 1, borderLeftColor: colors.divider, paddingLeft: 32, minWidth: 240, justifyContent: "center" },
  summaryProgressText: { fontSize: 17, lineHeight: 23, fontWeight: "700", color: colors.onSurface },
  ringText: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  ringTextSmall: { fontSize: 11 },
  exerciseList: { gap: spacing.md },
  exerciseCard: { backgroundColor: "#FFFEFA", borderRadius: radius.md, borderWidth: 1, borderColor: colors.borderStrong, overflow: "hidden", shadowColor: "#24362F", shadowOpacity: 0.04, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  exerciseCardWide: { flexDirection: "row", minHeight: 300 },
  exerciseCardDone: { borderColor: colors.success },
  illustrationPanel: { height: 245, backgroundColor: "#EEF3EC", borderBottomWidth: 1, borderBottomColor: colors.border, padding: spacing.sm },
  illustrationPanelWide: { width: 320, height: "auto", minHeight: 300, borderBottomWidth: 0, borderRightWidth: 1, borderRightColor: "#E0E4E1" },
  exerciseImage: { width: "100%", height: "100%" },
  exerciseBody: { flex: 1, padding: spacing.lg },
  exerciseHeader: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  exerciseNumber: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  exerciseNumberDone: { backgroundColor: colors.success },
  exerciseNumberText: { color: "#FFFEFA", fontSize: 18, fontWeight: "800" },
  exerciseHeadingCopy: { flex: 1, minWidth: 0 },
  titleAndTag: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  exerciseTitle: { fontSize: 22, lineHeight: 29, fontWeight: "800", color: colors.onSurface },
  focusTag: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: 999, backgroundColor: "#E6EFE8" },
  focusTagText: { color: "#2C5C3A", fontSize: 13, fontWeight: "700" },
  exerciseMeta: { marginTop: 5, fontSize: 16, lineHeight: 22, color: colors.brandPrimary, fontWeight: "700" },
  statusTag: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: "#F0F1F0" },
  statusTagActive: { backgroundColor: "#FFF1D9" },
  statusTagDone: { backgroundColor: "#E1F1E6" },
  statusTagText: { color: "#53645A", fontSize: 13, fontWeight: "700" },
  statusTagTextDone: { color: "#2C7543" },
  exerciseRule: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.md },
  exerciseDescription: { fontSize: 16, lineHeight: 24, color: colors.onSurface, marginBottom: spacing.md },
  calloutRow: { gap: spacing.sm },
  calloutRowWide: { flexDirection: "row" },
  callout: { flex: 1, minHeight: 104, flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, padding: spacing.md, borderWidth: 1, borderRadius: radius.md },
  purposeCallout: { backgroundColor: "#F1F6F2", borderColor: "#D7E3DA" },
  safetyCallout: { backgroundColor: "#FFF8EE", borderColor: "#F0D4A8" },
  calloutCopy: { flex: 1 },
  purposeTitle: { fontSize: 16, lineHeight: 21, fontWeight: "800", color: "#2F6A43", marginBottom: 4 },
  safetyTitle: { fontSize: 16, lineHeight: 21, fontWeight: "800", color: "#96520F", marginBottom: 4 },
  calloutText: { fontSize: 16, lineHeight: 23, color: colors.onSurfaceSecondary },
  sessionScore: { marginTop: spacing.sm, fontSize: 16, lineHeight: 22, fontWeight: "700", color: colors.brandPrimary },
  exerciseActions: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "flex-end", gap: spacing.md, marginTop: spacing.md },
  demoLink: { minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingHorizontal: spacing.sm },
  demoLinkText: { color: colors.brandPrimary, fontSize: 16, fontWeight: "700", textDecorationLine: "underline" },
  guidedBtn: { minHeight: 52, minWidth: 184, paddingHorizontal: spacing.lg, flexDirection: "row", gap: 7, backgroundColor: colors.brandPrimary, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  guidedBtnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 16 },
  completionBar: { position: "absolute", left: 0, right: 0, bottom: 0, paddingTop: spacing.sm, paddingHorizontal: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border },
  completionBarInner: { width: "100%", maxWidth: 1360, alignSelf: "center", minHeight: 78, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.md, padding: spacing.sm, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md, backgroundColor: "#F6F9F4" },
  completionBarInnerNarrow: { minHeight: 64, flexDirection: "column", alignItems: "stretch" },
  completionCount: { flexDirection: "row", alignItems: "center", gap: spacing.md, flex: 1 },
  completionCountText: { fontSize: 16, lineHeight: 22, fontWeight: "800", color: colors.onSurface },
  finishButton: { minHeight: 54, minWidth: 290, borderRadius: radius.md, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg },
  finishButtonDisabled: { backgroundColor: "#E3E5E3" },
  finishButtonText: { color: colors.onBrandPrimary, fontSize: 16, fontWeight: "800" },
  finishButtonTextDisabled: { color: "#9AA09C" },
  blockedContent: { flex: 1, padding: spacing.xl },
  blockedIcon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary, marginBottom: spacing.md },
  blockedTitle: { fontSize: 26, lineHeight: 33, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginBottom: spacing.sm },
  blockedText: { fontSize: 16, lineHeight: 24, color: colors.onSurfaceSecondary, textAlign: "center" },
  blockedNext: { fontSize: 16, lineHeight: 24, fontWeight: "700", color: colors.onSurface, textAlign: "center", marginTop: spacing.md },
  blockedButton: { minHeight: 52, flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, alignItems: "center", marginTop: spacing.xl },
  modalBackdrop: { flex: 1, padding: spacing.md, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(10, 22, 16, 0.72)" },
  modalCard: { width: "100%", maxWidth: 620, maxHeight: "92%", borderRadius: radius.md, backgroundColor: colors.surface, padding: spacing.lg },
  modalHeader: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.md },
  modalEyebrow: { fontSize: 12, fontWeight: "800", color: colors.brandPrimary, textTransform: "uppercase", marginBottom: 4 },
  modalTitle: { fontSize: 26, lineHeight: 33, fontWeight: "800", color: colors.onSurface },
  modalClose: { width: 48, height: 48, borderRadius: 24, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  modalImageWrap: { height: 330, marginVertical: spacing.md, borderRadius: radius.sm, backgroundColor: "#F3F6F3", overflow: "hidden" },
  modalImage: { width: "100%", height: "100%" },
  modalInstruction: { fontSize: 16, lineHeight: 24, color: colors.onSurface, marginBottom: spacing.sm },
  modalSafety: { fontSize: 16, lineHeight: 23, color: "#96520F", backgroundColor: "#FFF7EA", borderWidth: 1, borderColor: "#EBCB9C", borderRadius: radius.md, padding: spacing.sm },
  modalSource: { marginTop: spacing.sm, fontSize: 11, lineHeight: 16, color: colors.onSurfaceTertiary },
  modalStart: { minHeight: 54, marginTop: spacing.md, borderRadius: radius.md, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
});
