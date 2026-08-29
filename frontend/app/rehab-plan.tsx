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
import { DisclaimerBanner } from "@/src/components/MedicalDisclaimer";

type ExerciseProgress = {
  completed_reps: number;
  total_reps: number;
  last_score: number | null;
  best_score: number | null;
  sessions: number;
};

type AdaptiveCarePlan = {
  safety?: { status?: string; message?: string; blocks_exercise?: boolean };
  exercise_plan?: { action?: string; dose_change_percent?: number; reason?: string };
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

function applyAdaptiveDose(plan: Assessment, carePlan: AdaptiveCarePlan | null): Assessment {
  const adjustment = carePlan?.exercise_plan;
  if (adjustment?.action !== "reduce_next_session" || (adjustment.dose_change_percent || 0) >= 0) return plan;
  const factor = Math.max(0.5, 1 + Number(adjustment.dose_change_percent || 0) / 100);
  return {
    ...plan,
    rehab_plan: plan.rehab_plan.map((exercise) => ({
      ...exercise,
      reps: Math.max(1, Math.floor(exercise.reps * factor)),
      selection_reason: `${exercise.selection_reason || "Selected from the approved exercise library."} Alira reduced the next-session dose after the latest check-in.`,
    })),
  };
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
  const [adaptiveCarePlan, setAdaptiveCarePlan] = useState<AdaptiveCarePlan | null>(null);
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
        if (typeof raw === "string" && raw) {
          const saved = JSON.parse(raw) as ExerciseProgress;
          const adjustedTotal = ex.sets * ex.reps;
          out[ex.id] = { ...saved, total_reps: adjustedTotal, completed_reps: Math.min(saved.completed_reps || 0, adjustedTotal) };
        } else {
          out[ex.id] = { completed_reps: 0, total_reps: ex.sets * ex.reps, last_score: null, best_score: null, sessions: 0 };
        }
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
          let carePlan: AdaptiveCarePlan | null = null;
          if (id !== DEMO_ASSESSMENT_ID) {
            try {
              const response = await authedFetch("/api/alira/care-plan");
              if (response.ok) carePlan = await response.json();
            } catch {
              // Keep the last assessment plan when the adaptive service is temporarily unavailable.
            }
          }
          const adjustedAssessment = applyAdaptiveDose(assessment, carePlan);
          setAdaptiveCarePlan(carePlan);
          setData(adjustedAssessment);
          await loadProgress(adjustedAssessment);
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

  if (adaptiveCarePlan?.safety?.blocks_exercise || data.clinical_review_gate?.rehab_access !== "allowed" || data.rehab_plan.length === 0) {
    const gate = data.clinical_review_gate;
    const adaptiveHold = Boolean(adaptiveCarePlan?.safety?.blocks_exercise);
    const awaiting = gate?.status === "awaiting_model_analysis";
    const noRehabNeeded = gate?.status === "no_rehab_needed" || gate?.rehab_access === "not_needed";
    const title = adaptiveHold ? "Pause today's exercises" : gate?.patient_title || "No rehabilitation plan is available";
    const message = adaptiveHold
      ? adaptiveCarePlan?.safety?.message || "Your latest check-in needs attention before exercise continues."
      : gate?.patient_message || "This assessment did not produce exercises for automatic recommendation.";
    const nextStep = adaptiveHold
      ? "Follow the safety message above and contact your stroke rehabilitation team before restarting this plan."
      : gate?.next_step || "Return home and review the result with your therapist if you still have symptoms.";
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
          <DisclaimerBanner />
          {isDemo && (
            <View style={styles.demoBanner} testID="rehab-demo-banner">
              <Ionicons name="sparkles" size={22} color="#675080" />
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
                        {isDone ? <Ionicons name="checkmark" size={20} color="#FFFFFF" /> : <Text style={styles.exerciseNumberText}>{index + 1}</Text>}
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
                        <Ionicons name="warning-outline" size={27} color="#B96612" />
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
                        <Ionicons name="play" size={18} color="#FFFFFF" />
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
            <Ionicons name="checkmark-circle" size={21} color={allComplete ? "#FFFFFF" : "#9AA09C"} />
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
                <Ionicons name="play" size={18} color="#FFFFFF" />
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
  container: { flex: 1, backgroundColor: "#FBFCFA" },
  center: { alignItems: "center", justifyContent: "center" },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, backgroundColor: "#FFFFFF", borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 19, fontWeight: "800", color: "#123E2D" },
  headerSpacer: { width: 44 },
  scrollContent: { paddingHorizontal: spacing.md, paddingTop: spacing.md, paddingBottom: 126 },
  page: { width: "100%", maxWidth: 1360, alignSelf: "center" },
  demoBanner: { flexDirection: "row", alignItems: "center", gap: spacing.sm, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 14, marginBottom: spacing.md, backgroundColor: "#F3EDFA", borderWidth: 1, borderColor: "#D9C8ED" },
  demoBannerText: { flex: 1, fontSize: 13, lineHeight: 18, fontWeight: "700", color: "#5C486F" },
  summaryPanel: { backgroundColor: "#FFFFFF", borderRadius: radius.sm, borderWidth: 1, borderColor: "#D8DED9", padding: spacing.lg, marginBottom: spacing.lg, gap: spacing.md },
  summaryPanelWide: { flexDirection: "row", alignItems: "center", paddingHorizontal: 32 },
  summaryCopy: { minWidth: 260, flex: 1 },
  summaryTitle: { fontSize: 25, fontWeight: "800", color: "#123E2D", marginBottom: 6 },
  summarySubtitle: { fontSize: 14, lineHeight: 20, color: colors.onSurfaceSecondary },
  summaryMetrics: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  summaryMetricsWide: { flex: 1.35, justifyContent: "center" },
  summaryMetricsNarrow: { flexWrap: "nowrap" },
  metricBox: { minHeight: 72, minWidth: 190, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.md, borderWidth: 1, borderColor: "#D7DCD8", borderRadius: radius.sm, backgroundColor: "#FFFFFF" },
  metricBoxNarrow: { minWidth: 0, minHeight: 92, flex: 1, flexDirection: "column", justifyContent: "center", paddingHorizontal: spacing.sm, gap: 4 },
  metricIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: "#EDF4EF" },
  metricText: { fontSize: 15, color: colors.onSurface, fontWeight: "700" },
  summaryProgress: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  summaryProgressWide: { borderLeftWidth: 1, borderLeftColor: colors.divider, paddingLeft: 32, minWidth: 240, justifyContent: "center" },
  summaryProgressText: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  ringText: { fontSize: 14, fontWeight: "800", color: colors.onSurface },
  ringTextSmall: { fontSize: 11 },
  exerciseList: { gap: spacing.md },
  exerciseCard: { backgroundColor: "#FFFFFF", borderRadius: radius.sm, borderWidth: 1, borderColor: "#D9DEDA", overflow: "hidden" },
  exerciseCardWide: { flexDirection: "row", minHeight: 300 },
  exerciseCardDone: { borderColor: "#8EB59D" },
  illustrationPanel: { height: 245, backgroundColor: "#F3F6F3", borderBottomWidth: 1, borderBottomColor: "#E0E4E1", padding: spacing.sm },
  illustrationPanelWide: { width: 320, height: "auto", minHeight: 300, borderBottomWidth: 0, borderRightWidth: 1, borderRightColor: "#E0E4E1" },
  exerciseImage: { width: "100%", height: "100%" },
  exerciseBody: { flex: 1, padding: spacing.lg },
  exerciseHeader: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  exerciseNumber: { width: 38, height: 38, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  exerciseNumberDone: { backgroundColor: colors.success },
  exerciseNumberText: { color: "#FFFFFF", fontSize: 18, fontWeight: "800" },
  exerciseHeadingCopy: { flex: 1, minWidth: 0 },
  titleAndTag: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  exerciseTitle: { fontSize: 20, lineHeight: 25, fontWeight: "800", color: "#123E2D" },
  focusTag: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: 999, backgroundColor: "#E6EFE8" },
  focusTagText: { color: "#427454", fontSize: 12, fontWeight: "700" },
  exerciseMeta: { marginTop: 4, fontSize: 13, color: colors.brandPrimary, fontWeight: "700" },
  statusTag: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: "#F0F1F0" },
  statusTagActive: { backgroundColor: "#FFF1D9" },
  statusTagDone: { backgroundColor: "#E1F1E6" },
  statusTagText: { color: "#6D736F", fontSize: 12, fontWeight: "700" },
  statusTagTextDone: { color: "#2C7543" },
  exerciseRule: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.md },
  exerciseDescription: { fontSize: 15, lineHeight: 22, color: colors.onSurface, marginBottom: spacing.md },
  calloutRow: { gap: spacing.sm },
  calloutRowWide: { flexDirection: "row" },
  callout: { flex: 1, minHeight: 88, flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, padding: spacing.md, borderWidth: 1, borderRadius: radius.sm },
  purposeCallout: { backgroundColor: "#F1F6F2", borderColor: "#D7E3DA" },
  safetyCallout: { backgroundColor: "#FFF8EE", borderColor: "#F0D4A8" },
  calloutCopy: { flex: 1 },
  purposeTitle: { fontSize: 13, fontWeight: "800", color: "#2F6A43", marginBottom: 3 },
  safetyTitle: { fontSize: 13, fontWeight: "800", color: "#A7580E", marginBottom: 3 },
  calloutText: { fontSize: 12, lineHeight: 17, color: colors.onSurfaceSecondary },
  sessionScore: { marginTop: spacing.sm, fontSize: 12, fontWeight: "700", color: colors.brandPrimary },
  exerciseActions: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "flex-end", gap: spacing.md, marginTop: spacing.md },
  demoLink: { minHeight: 44, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingHorizontal: spacing.sm },
  demoLinkText: { color: colors.brandPrimary, fontSize: 14, fontWeight: "700", textDecorationLine: "underline" },
  guidedBtn: { minHeight: 46, minWidth: 174, paddingHorizontal: spacing.lg, flexDirection: "row", gap: 7, backgroundColor: colors.brandPrimary, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  guidedBtnText: { color: "#FFFFFF", fontWeight: "800", fontSize: 14 },
  completionBar: { position: "absolute", left: 0, right: 0, bottom: 0, paddingTop: spacing.sm, paddingHorizontal: spacing.md, backgroundColor: "#FFFFFF", borderTopWidth: 1, borderTopColor: colors.divider },
  completionBarInner: { width: "100%", maxWidth: 1360, alignSelf: "center", minHeight: 74, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.sm, padding: spacing.sm, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  completionBarInnerNarrow: { minHeight: 64, flexDirection: "column", alignItems: "stretch" },
  completionCount: { flexDirection: "row", alignItems: "center", gap: spacing.md, flex: 1 },
  completionCountText: { fontSize: 14, fontWeight: "800", color: colors.onSurface },
  finishButton: { minHeight: 50, minWidth: 290, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg },
  finishButtonDisabled: { backgroundColor: "#E3E5E3" },
  finishButtonText: { color: "#FFFFFF", fontSize: 15, fontWeight: "800" },
  finishButtonTextDisabled: { color: "#9AA09C" },
  blockedContent: { flex: 1, padding: spacing.xl },
  blockedIcon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary, marginBottom: spacing.md },
  blockedTitle: { fontSize: 22, fontWeight: "800", color: colors.onSurface, textAlign: "center", marginBottom: spacing.sm },
  blockedText: { fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary, textAlign: "center" },
  blockedNext: { fontSize: 15, lineHeight: 22, fontWeight: "700", color: colors.onSurface, textAlign: "center", marginTop: spacing.md },
  blockedButton: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.sm, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, alignItems: "center", marginTop: spacing.xl },
  modalBackdrop: { flex: 1, padding: spacing.md, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(10, 22, 16, 0.72)" },
  modalCard: { width: "100%", maxWidth: 620, maxHeight: "92%", borderRadius: radius.sm, backgroundColor: "#FFFFFF", padding: spacing.lg },
  modalHeader: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.md },
  modalEyebrow: { fontSize: 12, fontWeight: "800", color: colors.brandPrimary, textTransform: "uppercase", marginBottom: 4 },
  modalTitle: { fontSize: 24, lineHeight: 30, fontWeight: "800", color: "#123E2D" },
  modalClose: { width: 42, height: 42, borderRadius: 21, borderWidth: 1, borderColor: colors.divider, alignItems: "center", justifyContent: "center" },
  modalImageWrap: { height: 330, marginVertical: spacing.md, borderRadius: radius.sm, backgroundColor: "#F3F6F3", overflow: "hidden" },
  modalImage: { width: "100%", height: "100%" },
  modalInstruction: { fontSize: 15, lineHeight: 22, color: colors.onSurface, marginBottom: spacing.sm },
  modalSafety: { fontSize: 13, lineHeight: 19, color: "#9A570F", backgroundColor: "#FFF8EE", borderWidth: 1, borderColor: "#F0D4A8", borderRadius: radius.sm, padding: spacing.sm },
  modalSource: { marginTop: spacing.sm, fontSize: 11, lineHeight: 16, color: colors.onSurfaceTertiary },
  modalStart: { minHeight: 50, marginTop: spacing.md, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
});
