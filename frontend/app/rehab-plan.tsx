import React, { useEffect, useMemo, useState } from "react";
import {
  Animated,
  ActivityIndicator,
  Easing,
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
import { colors, spacing, radius } from "@/src/theme";
import { fetchAssessment, Assessment, RehabExercise } from "@/src/api";
import { storage } from "@/src/utils/storage";
import { authedFetch, getUserId } from "@/src/auth";
import PaywallModal from "@/src/components/PaywallModal";
import { localDateString } from "@/src/components/DailyCheckInCalendar";
import { DEMO_ASSESSMENT_ID, demoAssessment } from "@/src/demoAssessment";
import { estimateRehabMinutes } from "@/src/rehabTiming";

type ExerciseProgress = {
  completed_reps: number;
  total_reps: number;
  last_score: number | null;
  best_score: number | null;
  sessions: number;
  last_session_scores?: number[];
  score_history?: { completed_at: string; average_score: number; repetition_scores: number[] }[];
};

type AdaptiveCarePlan = {
  safety?: { status?: string; message?: string; blocks_exercise?: boolean };
  exercise_plan?: {
    action?: string;
    dose_change_percent?: number;
    reason?: string;
    prescriptions?: {
      exercise_id: string;
      sets: number;
      reps: number;
      frequency: string;
      weekly_frequency?: number;
    }[];
  };
};

type PlanPreparationStage = 0 | 1 | 2;
type SessionDifficulty = "easy" | "medium" | "difficult";
type SessionVariation = "standard" | "alternate";

type DailySessionChoice = {
  date: string;
  difficulty: SessionDifficulty;
  variation: SessionVariation;
};

type ExerciseSessionOption = {
  exercise_id: string;
  name: string;
  requires_same_support_at_all_levels: boolean;
  alternate_variation: string;
  levels: Record<SessionDifficulty, {
    label: string;
    sets: number;
    reps: number;
    adjustment: string;
  }>;
};

type SessionOptionsResponse = {
  levels: SessionDifficulty[];
  variations: SessionVariation[];
  exercises: ExerciseSessionOption[];
  safety_rule: string;
};

const PREPARATION_STEPS = [
  "Reviewing your assessment",
  "Choosing suitable exercises",
  "Creating your plan",
] as const;

const MINIMUM_STAGE_DURATION_MS = 420;

const SUPPORTED_REACH_IMAGE = require("../assets/images/rehab-supported-forward-reach.png") as ImageSourcePropType;
const HAND_OPENING_IMAGE = require("../assets/images/rehab-relaxed-hand-opening.png") as ImageSourcePropType;
const PROGRESS_KEY = (planId: string, exId: string) => `ex_progress_v1:${planId}:${exId}`;
const SESSION_VISITS_KEY = (planId: string) => `rehab_session_visits_v1:${planId}`;
const DAILY_SESSION_CHOICE_KEY = (accountId: string) => `rehab_daily_session_choice_v1:${accountId}`;
const PLAN_VIEWED_KEY = (accountId: string, planId: string) => `rehab_plan_viewed_v1:${accountId}:${planId}`;

function isSessionDifficulty(value: unknown): value is SessionDifficulty {
  return value === "easy" || value === "medium" || value === "difficult";
}

function isSessionVariation(value: unknown): value is SessionVariation {
  return value === "standard" || value === "alternate";
}

async function dailySessionChoiceKey(planId: string): Promise<string> {
  const userId = await getUserId();
  return DAILY_SESSION_CHOICE_KEY(userId || `plan:${planId}`);
}

async function loadTodaySessionChoice(planId: string): Promise<DailySessionChoice | null> {
  const raw = await storage.getItem(await dailySessionChoiceKey(planId), "");
  if (typeof raw !== "string" || !raw) return null;
  try {
    const saved = JSON.parse(raw) as Partial<DailySessionChoice>;
    if (
      saved.date !== localDateString()
      || !isSessionDifficulty(saved.difficulty)
      || !isSessionVariation(saved.variation)
    ) return null;
    return saved as DailySessionChoice;
  } catch {
    return null;
  }
}

async function saveTodaySessionChoice(planId: string, choice: Omit<DailySessionChoice, "date">): Promise<void> {
  await storage.setItem(
    await dailySessionChoiceKey(planId),
    JSON.stringify({ ...choice, date: localDateString() } satisfies DailySessionChoice),
  );
}

async function claimFirstPlanAccess(planId: string): Promise<boolean> {
  const userId = await getUserId();
  const localKey = PLAN_VIEWED_KEY(userId || "anonymous", planId);
  const localValue: string | null = await storage.getItem(localKey, "" as string);
  const locallyViewed = localValue === "1";
  try {
    const response = await authedFetch(`/api/assessment/${encodeURIComponent(planId)}/rehab-plan-access`, {
      method: "POST",
    });
    if (response.ok) {
      const access = await response.json() as { first_access?: boolean };
      await storage.setItem(localKey, "1");
      return access.first_access === true && !locallyViewed;
    }
  } catch {
    // Account-scoped device storage preserves one-time behavior while offline.
  }
  if (!locallyViewed) await storage.setItem(localKey, "1");
  return !locallyViewed;
}

const DIFFICULTY_COPY: Record<SessionDifficulty, { label: string; summary: string; icon: keyof typeof Ionicons.glyphMap }> = {
  easy: { label: "Easy", summary: "Fewer repetitions and a more reachable target.", icon: "leaf-outline" },
  medium: { label: "Medium", summary: "Your usual dose and target position.", icon: "options-outline" },
  difficult: { label: "Difficult", summary: "A small dose increase and a higher or more precise target.", icon: "trending-up-outline" },
};

function nextDifficulty(level: SessionDifficulty): SessionDifficulty {
  if (level === "easy") return "medium";
  if (level === "medium") return "difficult";
  return "difficult";
}

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
  if (!adjustment || adjustment.action === "hold") return plan;
  const prescriptions = new Map(
    (adjustment.prescriptions || []).map((item) => [item.exercise_id, item]),
  );
  const change = Math.max(-20, Math.min(20, Number(adjustment.dose_change_percent || 0)));
  const factor = 1 + change / 100;
  return {
    ...plan,
    rehab_plan: plan.rehab_plan.map((exercise) => {
      const prescription = prescriptions.get(exercise.id);
      const actionText = change > 0
        ? "Alira made a small progression after reviewing the latest check-in and activity record."
        : change < 0
          ? "Alira made a small reduction after reviewing the latest check-in and activity record."
          : "Alira maintained this dose after reviewing the latest check-in and activity record.";
      return {
        ...exercise,
        sets: prescription?.sets ?? exercise.sets,
        reps: prescription?.reps ?? Math.max(1, Math.round(exercise.reps * factor)),
        frequency: prescription?.frequency ?? exercise.frequency,
        requires_clinician_confirmation: false,
        selection_reason: `${exercise.selection_reason || "Selected from the approved exercise library."} ${actionText}`,
      };
    }),
  };
}

function sessionDose(exercise: RehabExercise, difficulty: SessionDifficulty, requiresSameSupport: boolean) {
  if (difficulty === "easy") {
    return {
      sets: Math.max(1, exercise.sets - 1),
      reps: Math.max(3, Math.round(exercise.reps * 0.7)),
    };
  }
  if (difficulty === "difficult") {
    return {
      sets: requiresSameSupport ? exercise.sets : Math.min(4, exercise.sets + 1),
      reps: requiresSameSupport
        ? exercise.reps + 1
        : Math.min(20, Math.max(exercise.reps + 1, Math.round(exercise.reps * 1.15))),
    };
  }
  return { sets: exercise.sets, reps: exercise.reps };
}

function configureSessionPlan(
  plan: Assessment,
  difficulty: SessionDifficulty,
  options: ExerciseSessionOption[],
): Assessment {
  const optionById = new Map(options.map((option) => [option.exercise_id, option]));
  return {
    ...plan,
    rehab_plan: plan.rehab_plan.map((exercise) => {
      const option = optionById.get(exercise.id);
      const dose = sessionDose(exercise, difficulty, Boolean(option?.requires_same_support_at_all_levels));
      return { ...exercise, ...dose };
    }),
  };
}

function waitForMinimumStageTime(startedAt: number): Promise<void> {
  const remaining = Math.max(0, MINIMUM_STAGE_DURATION_MS - (Date.now() - startedAt));
  return new Promise((resolve) => setTimeout(resolve, remaining));
}

function RehabPlanPreparation({
  stage,
  onBack,
  topInset,
  compact,
}: {
  stage: PlanPreparationStage;
  onBack: () => void;
  topInset: number;
  compact: boolean;
}) {
  const pulse = React.useRef(new Animated.Value(0)).current;

  useEffect(() => {
    pulse.setValue(0);
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 760, easing: Easing.out(Easing.ease), useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 760, easing: Easing.in(Easing.ease), useNativeDriver: true }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [pulse, stage]);

  return (
    <View style={styles.preparationPage} testID="rehab-plan-preparation">
      <View style={[styles.preparationHeader, { paddingTop: topInset + spacing.sm }]}>
        <Pressable onPress={onBack} style={styles.preparationBack} accessibilityLabel="Go back" testID="rehab-plan-preparation-back">
          <Ionicons name="chevron-back" size={32} color="#175A43" />
        </Pressable>
        <Text style={styles.preparationHeaderTitle}>Rehab plan</Text>
        <View style={styles.preparationHeaderSpacer} />
      </View>

      <View style={[styles.preparationBody, compact && styles.preparationBodyCompact]}>
        <View style={[styles.preparationIcon, compact && styles.preparationIconCompact]}>
          <Ionicons name="clipboard-outline" size={compact ? 46 : 58} color="#175A43" />
          <View style={styles.preparationHeart}>
            <Ionicons name="heart-outline" size={compact ? 23 : 28} color="#175A43" />
          </View>
        </View>

        <Text style={[styles.preparationTitle, compact && styles.preparationTitleCompact]}>Preparing your rehab plan</Text>

        <View style={[styles.preparationCard, compact && styles.preparationCardCompact]}>
          {PREPARATION_STEPS.map((label, index) => {
            const completed = index < stage;
            const active = index === stage;
            return (
              <View key={label} style={styles.preparationStep} testID={`rehab-plan-preparation-step-${index}`}>
                <View style={styles.preparationTimelineColumn}>
                  {index > 0 && <View style={[styles.preparationLineTop, index <= stage && styles.preparationLineComplete]} />}
                  {active && (
                    <Animated.View
                      style={[
                        styles.preparationPulse,
                        {
                          opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.25, 0] }),
                          transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.35] }) }],
                        },
                      ]}
                    />
                  )}
                  <View style={[styles.preparationStatus, completed && styles.preparationStatusComplete, active && styles.preparationStatusActive]}>
                    {completed && <Ionicons name="checkmark" size={24} color="#FFFFFF" />}
                  </View>
                  {index < PREPARATION_STEPS.length - 1 && <View style={[styles.preparationLineBottom, index < stage && styles.preparationLineComplete]} />}
                </View>
                <Text style={[
                  styles.preparationStepText,
                  active && styles.preparationStepTextActive,
                  completed && styles.preparationStepTextComplete,
                  compact && styles.preparationStepTextCompact,
                ]}>{label}</Text>
              </View>
            );
          })}
        </View>

        <Text style={[styles.preparationHint, compact && styles.preparationHintCompact]}>This usually takes less than a minute.</Text>
      </View>
    </View>
  );
}

function RehabSessionPrompt({
  visible,
  currentDifficulty,
  switchExercises,
  increaseDifficulty,
  switchRecommended,
  onSwitchChange,
  onIncreaseDifficultyChange,
  onConfirm,
  onBack,
}: {
  visible: boolean;
  currentDifficulty: SessionDifficulty;
  switchExercises: boolean;
  increaseDifficulty: boolean;
  switchRecommended: boolean;
  onSwitchChange: (value: boolean) => void;
  onIncreaseDifficultyChange: (value: boolean) => void;
  onConfirm: () => void;
  onBack: () => void;
}) {
  const canIncrease = currentDifficulty !== "difficult";
  const choice = (
    value: boolean,
    selected: boolean,
    onChange: (value: boolean) => void,
    testID: string,
  ) => (
    <Pressable
      onPress={() => onChange(value)}
      style={[styles.promptChoice, selected && styles.promptChoiceSelected]}
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      testID={testID}
    >
      <Ionicons
        name={selected ? "radio-button-on" : "radio-button-off"}
        size={23}
        color={selected ? colors.brandPrimary : "#748078"}
      />
      <Text style={[styles.promptChoiceText, selected && styles.promptChoiceTextSelected]}>{value ? "Yes" : "No"}</Text>
    </Pressable>
  );

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onBack}>
      <View style={styles.promptBackdrop} testID="rehab-session-popup">
        <ScrollView contentContainerStyle={styles.promptScroll} bounces={false}>
          <View style={styles.promptCard} accessibilityViewIsModal>
            <View style={styles.promptHeader}>
              <View style={styles.promptIcon}><Ionicons name="options-outline" size={26} color={colors.brandPrimary} /></View>
              <Pressable onPress={onBack} style={styles.promptClose} accessibilityLabel="Close rehab plan">
                <Ionicons name="close" size={25} color="#526057" />
              </Pressable>
            </View>
            <Text style={styles.promptEyebrow}>BEFORE TODAY&apos;S PLAN</Text>
            <Text style={styles.promptTitle}>Would you like a small change today?</Text>
            <Text style={styles.promptIntro}>Your current level is <Text style={styles.promptIntroStrong}>{DIFFICULTY_COPY[currentDifficulty].label}</Text>. Changes apply only to today&apos;s session.</Text>

            <View style={styles.promptQuestion}>
              <View style={styles.promptQuestionHeading}>
                <Text style={styles.promptQuestionTitle}>Switch to a different set of exercises?</Text>
                {switchRecommended && <View style={styles.recommendedTag}><Text style={styles.recommendedTagText}>Suggested today</Text></View>}
              </View>
              <Text style={styles.promptQuestionCopy}>Train the same goals with alternate versions of your planned movements.</Text>
              <View style={styles.promptChoiceRow}>
                {choice(false, !switchExercises, onSwitchChange, "session-switch-no")}
                {choice(true, switchExercises, onSwitchChange, "session-switch-yes")}
              </View>
            </View>

            <View style={[styles.promptQuestion, !canIncrease && styles.promptQuestionDisabled]}>
              <Text style={styles.promptQuestionTitle}>Increase the difficulty for today?</Text>
              <Text style={styles.promptQuestionCopy}>{canIncrease ? `This moves one small step to ${DIFFICULTY_COPY[nextDifficulty(currentDifficulty)].label}, with a slightly higher target or dose.` : "You are already at today's highest available level."}</Text>
              <View style={styles.promptChoiceRow}>
                {choice(false, !increaseDifficulty, onIncreaseDifficultyChange, "session-increase-no")}
                <View style={[styles.promptChoiceWrap, !canIncrease && styles.promptDisabledChoice]} pointerEvents={canIncrease ? "auto" : "none"}>
                  {choice(true, increaseDifficulty && canIncrease, onIncreaseDifficultyChange, "session-increase-yes")}
                </View>
              </View>
            </View>

            <View style={styles.promptSafety}>
              <Ionicons name="shield-checkmark-outline" size={21} color="#A85006" />
              <Text style={styles.promptSafetyText}>Keep the same support or guarding. Stop for new pain, dizziness, marked fatigue, or loss of balance.</Text>
            </View>
            <Pressable onPress={onConfirm} style={styles.sessionConfirm} testID="session-show-plan">
              <Text style={styles.sessionConfirmText}>Show today&apos;s plan</Text>
              <Ionicons name="arrow-forward" size={22} color="#FFFFFF" />
            </Pressable>
          </View>
        </ScrollView>
      </View>
    </Modal>
  );
}

export default function RehabPlanScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { id, entry } = useLocalSearchParams<{ id: string; entry?: string }>();
  const [data, setData] = useState<Assessment | null>(null);
  const [adaptiveCarePlan, setAdaptiveCarePlan] = useState<AdaptiveCarePlan | null>(null);
  const [loading, setLoading] = useState(true);
  const [showPreparation, setShowPreparation] = useState(false);
  const [preparationStage, setPreparationStage] = useState<PlanPreparationStage>(0);
  const [progress, setProgress] = useState<Record<string, ExerciseProgress>>({});
  const [paywallOpen, setPaywallOpen] = useState(false);
  const [paywallReason, setPaywallReason] = useState<string | undefined>();
  const [demonstrationId, setDemonstrationId] = useState<string | null>(null);
  const [expandedPurposeIds, setExpandedPurposeIds] = useState<Set<string>>(new Set());
  const [sessionOptions, setSessionOptions] = useState<ExerciseSessionOption[]>([]);
  const [sessionDifficulty, setSessionDifficulty] = useState<SessionDifficulty>("medium");
  const [sessionVariation, setSessionVariation] = useState<SessionVariation>("standard");
  const [increaseDifficulty, setIncreaseDifficulty] = useState(false);
  const [sessionConfirmed, setSessionConfirmed] = useState(false);
  const [switchRecommended, setSwitchRecommended] = useState(false);
  const baseSessionPlanRef = React.useRef<Assessment | null>(null);
  const baseSessionDifficultyRef = React.useRef<SessionDifficulty>("medium");
  // A new ID is created whenever this rehab-plan screen is entered. The first
  // exercise calibrates against it; later exercises reuse that calibration.
  // Leaving the plan and starting rehab again mounts a new screen and ID.
  const rehabSessionIdRef = React.useRef(
    `rehab-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`,
  );

  const planId = id || "default";
  const isDemo = id === DEMO_ASSESSMENT_ID;
  const isCurrentAccountPlan = id === "account-current-plan";
  const enteredFromFreshAssessment = entry === "assessment_complete";
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
    let cancelled = false;
    (async () => {
      try {
        if (id) {
          setLoading(true);
          setData(null);
          setSessionConfirmed(false);
          setSessionOptions([]);
          setSessionVariation("standard");
          setIncreaseDifficulty(false);
          setPreparationStage(0);
          setShowPreparation(false);
          const assessment = id === DEMO_ASSESSMENT_ID
            ? demoAssessment
            : isCurrentAccountPlan
              ? await authedFetch("/api/rehab/current-plan").then(async (response) => {
                  const body = await response.json().catch(() => null);
                  if (!response.ok) throw new Error(body?.detail || "No current plan is available.");
                  return body as Assessment;
                })
              : await fetchAssessment(id);
          const firstAccess = id === DEMO_ASSESSMENT_ID || isCurrentAccountPlan ? false : await claimFirstPlanAccess(id);
          const shouldPrepare = enteredFromFreshAssessment && firstAccess;
          setShowPreparation(shouldPrepare);
          let stageStartedAt = Date.now();
          if (shouldPrepare) await waitForMinimumStageTime(stageStartedAt);
          if (cancelled) return;

          if (shouldPrepare) setPreparationStage(1);
          stageStartedAt = Date.now();
          let carePlan: AdaptiveCarePlan | null = null;
          if (id !== DEMO_ASSESSMENT_ID) {
            try {
              const response = await authedFetch("/api/alira/care-plan");
              if (response.ok) carePlan = await response.json();
            } catch {
              // Keep the last assessment plan when the adaptive service is temporarily unavailable.
            }
          }
          if (shouldPrepare) await waitForMinimumStageTime(stageStartedAt);
          if (cancelled) return;

          if (shouldPrepare) setPreparationStage(2);
          stageStartedAt = Date.now();
          const adjustedAssessment = applyAdaptiveDose(assessment, carePlan);
          const doseChange = Number(carePlan?.exercise_plan?.dose_change_percent || 0);
          const baseDifficulty: SessionDifficulty = doseChange < 0 ? "easy" : doseChange > 0 ? "difficult" : "medium";
          let loadedSessionOptions: ExerciseSessionOption[] = [];
          try {
            const exerciseIds = adjustedAssessment.rehab_plan.map((exercise) => exercise.id).join(",");
            const response = await authedFetch(`/api/rehab/session-options?exercise_ids=${encodeURIComponent(exerciseIds)}`);
            if (response.ok) {
              const sessionResponse = await response.json() as SessionOptionsResponse;
              loadedSessionOptions = sessionResponse.exercises || [];
            }
          } catch {
            // The plan remains usable with the generic difficulty descriptions.
          }
          try {
            const rawVisits = await storage.getItem(SESSION_VISITS_KEY(planId), "0");
            const visits = Math.max(0, Number.parseInt(String(rawVisits || "0"), 10) || 0);
            const recommendSwitch = (visits + 1) % 3 === 0;
            if (!cancelled) {
              setSwitchRecommended(recommendSwitch);
            }
          } catch {
            if (!cancelled) {
              setSwitchRecommended(false);
            }
          }

          const savedChoice = await loadTodaySessionChoice(planId);
          const selectedDifficulty = savedChoice?.difficulty || baseDifficulty;
          const selectedVariation = savedChoice?.variation || "standard";
          const sessionPlan = savedChoice
            ? configureSessionPlan(adjustedAssessment, selectedDifficulty, loadedSessionOptions)
            : adjustedAssessment;
          if (cancelled) return;
          baseSessionPlanRef.current = adjustedAssessment;
          baseSessionDifficultyRef.current = baseDifficulty;
          setAdaptiveCarePlan(carePlan);
          setSessionOptions(loadedSessionOptions);
          setSessionDifficulty(selectedDifficulty);
          setSessionVariation(selectedVariation);
          setIncreaseDifficulty(false);
          setSessionConfirmed(Boolean(savedChoice));
          setData(sessionPlan);
          await loadProgress(sessionPlan);
          if (shouldPrepare) await waitForMinimumStageTime(stageStartedAt);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [enteredFromFreshAssessment, id, isCurrentAccountPlan, loadProgress, planId]);

  useFocusEffect(
    React.useCallback(() => {
      if (data) {
        loadProgress(data);
      }
    }, [data, loadProgress])
  );

  useFocusEffect(
    React.useCallback(() => {
      let active = true;
      void (async () => {
        const savedChoice = await loadTodaySessionChoice(planId);
        const basePlan = baseSessionPlanRef.current;
        if (!active || savedChoice || !basePlan) return;
        setSessionDifficulty(baseSessionDifficultyRef.current);
        setSessionVariation("standard");
        setIncreaseDifficulty(false);
        setSessionConfirmed(false);
        setData(basePlan);
        const rawVisits = await storage.getItem(SESSION_VISITS_KEY(planId), "0");
        const visits = Math.max(0, Number.parseInt(String(rawVisits || "0"), 10) || 0);
        setSwitchRecommended((visits + 1) % 3 === 0);
        await loadProgress(basePlan);
      })();
      return () => {
        active = false;
      };
    }, [loadProgress, planId])
  );

  const completedCount = Object.values(progress).filter((item) => item.completed_reps >= item.total_reps).length;
  const totalExercises = data?.rehab_plan.length || 0;
  const planPercent = Math.round((completedCount / Math.max(1, totalExercises)) * 100);
  const allComplete = totalExercises > 0 && completedCount >= totalExercises;
  const estimatedMinutes = estimateRehabMinutes(data?.rehab_plan ?? []);
  const demonstrationExercise = useMemo(
    () => data?.rehab_plan.find((exercise) => exercise.id === demonstrationId) || null,
    [data, demonstrationId]
  );
  const togglePurpose = (exerciseId: string) => {
    setExpandedPurposeIds((current) => {
      const next = new Set(current);
      if (next.has(exerciseId)) next.delete(exerciseId);
      else next.add(exerciseId);
      return next;
    });
  };

  const confirmSessionChoice = async () => {
    if (!data) return;
    const selectedDifficulty = increaseDifficulty ? nextDifficulty(sessionDifficulty) : sessionDifficulty;
    const configuredPlan = configureSessionPlan(data, selectedDifficulty, sessionOptions);
    await saveTodaySessionChoice(planId, {
      difficulty: selectedDifficulty,
      variation: sessionVariation,
    });
    setSessionDifficulty(selectedDifficulty);
    setData(configuredPlan);
    await loadProgress(configuredPlan);
    try {
      const rawVisits = await storage.getItem(SESSION_VISITS_KEY(planId), "0");
      const visits = Math.max(0, Number.parseInt(String(rawVisits || "0"), 10) || 0);
      await storage.setItem(SESSION_VISITS_KEY(planId), String(visits + 1));
    } catch {
      // Session setup should still continue when local visit history is unavailable.
    }
    setSessionConfirmed(true);
  };

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
      params: {
        exercise_id: exercise.id,
        name: exercise.name,
        plan_id: planId,
        sets: String(exercise.sets),
        reps: String(exercise.reps),
        difficulty: sessionDifficulty,
        variation: sessionVariation,
        affected_side: data?.affected_side === "left" ? "left" : "right",
        rehab_session_id: rehabSessionIdRef.current,
      },
    });
  };

  if (loading && showPreparation) {
    return (
      <RehabPlanPreparation
        stage={preparationStage}
        onBack={() => router.back()}
        topInset={insets.top}
        compact={width < 700}
      />
    );
  }

  if (loading) {
    return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brandPrimary} /></View>;
  }

  if (!data) {
    return <View style={[styles.container, styles.center]}><Text>No plan available.</Text></View>;
  }

  const planAccess = data.clinical_review_gate?.rehab_access || "allowed";
  const interimPlan = planAccess === "interim" && data.rehab_plan.length > 0;
  const surveyBasedPlan = data.clinical_review_gate?.rehab_plan_source === "survey_reported_problems";
  if (adaptiveCarePlan?.safety?.blocks_exercise || (planAccess !== "allowed" && !interimPlan) || data.rehab_plan.length === 0) {
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
          <Pressable onPress={() => router.dismissTo("/")} style={styles.backBtn} testID="plan-blocked-back">
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
          <Pressable onPress={() => router.dismissTo("/")} style={styles.blockedButton} testID="plan-blocked-home">
            <Ionicons name="home-outline" size={20} color={colors.onBrandPrimary} />
            <Text style={styles.guidedBtnText}>Return home</Text>
          </Pressable>
        </View>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <RehabSessionPrompt
        visible={!sessionConfirmed}
        currentDifficulty={sessionDifficulty}
        switchExercises={sessionVariation === "alternate"}
        increaseDifficulty={increaseDifficulty}
        switchRecommended={switchRecommended}
        onSwitchChange={(value) => setSessionVariation(value ? "alternate" : "standard")}
        onIncreaseDifficultyChange={setIncreaseDifficulty}
        onConfirm={confirmSessionChoice}
        onBack={() => router.back()}
      />
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="plan-back" accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={26} color={colors.brandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Rehab plan</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scrollContent, { paddingBottom: Math.max(insets.bottom, spacing.xl) }]}>
        <View style={styles.page}>
          {surveyBasedPlan && (
            <View style={styles.interimBanner} testID="plan-survey-source-banner">
              <Ionicons name="document-text-outline" size={18} color="#6B4A0B" />
              <Text style={styles.interimBannerText}>
                Survey-based plan: these exercises come only from the functional difficulties you reported. Camera and model findings do not replace them.
              </Text>
            </View>
          )}
          {isDemo && (
            <View style={styles.demoBanner} testID="rehab-demo-banner">
              <Ionicons name="sparkles" size={20} color="#675080" />
              <Text style={styles.demoBannerText}>Sample plan for preview only. Confirm any real exercises with your therapist.</Text>
            </View>
          )}

          <View style={styles.planIntro} testID="plan-progress-summary">
            <Text style={[styles.summaryTitle, !isWide && styles.summaryTitleNarrow]}>Today&apos;s plan</Text>
            <Text style={styles.summarySubtitle}>{totalExercises} exercise{totalExercises === 1 ? "" : "s"} · about {estimatedMinutes} minutes</Text>
            <Text style={styles.sessionSummary}>{DIFFICULTY_COPY[sessionDifficulty].label} · {sessionVariation === "alternate" ? "alternate exercise set" : "familiar exercise set"}</Text>
            <View style={styles.progressRow}>
              <View style={styles.progressTrack}>
                <View style={[styles.progressFill, { width: `${Math.max(1, planPercent)}%` as `${number}%` }]} />
              </View>
              <Text style={styles.summaryProgressText}>{completedCount} of {totalExercises} complete</Text>
            </View>
          </View>

          <View style={[styles.safetyBanner, !isWide && styles.safetyBannerNarrow]} testID="plan-safety-banner">
            <View style={styles.safetyShield}><Ionicons name="shield-checkmark-outline" size={36} color="#B65C09" /></View>
            <View style={styles.safetyCopy}>
              <Text style={styles.safetyHeading}>Move safely</Text>
              <Text style={styles.safetyMessage}>Stop if you feel new pain, dizziness, marked fatigue, or loss of balance.</Text>
            </View>
          </View>

          <View style={styles.exerciseList}>
            {data.rehab_plan.map((exercise, index) => {
              const itemProgress = progress[exercise.id] || { completed_reps: 0, total_reps: exercise.sets * exercise.reps, last_score: null, best_score: null, sessions: 0 };
              const percent = Math.min(100, Math.round((itemProgress.completed_reps / Math.max(1, itemProgress.total_reps)) * 100));
              const isDone = percent >= 100;
              const purposeExpanded = expandedPurposeIds.has(exercise.id);

              return (
                <View key={exercise.id} style={[styles.exerciseCard, isWide && styles.exerciseCardWide, isDone && styles.exerciseCardDone]} testID={`exercise-${exercise.id}`}>
                  <View style={[styles.exerciseIndexColumn, !isWide && styles.exerciseIndexColumnNarrow]}>
                    <View style={[styles.exerciseNumber, isDone && styles.exerciseNumberDone]}>
                      {isDone ? <Ionicons name="checkmark" size={21} color="#FFFFFF" /> : <Text style={styles.exerciseNumberText}>{index + 1}</Text>}
                    </View>
                  </View>
                  <View style={[styles.illustrationPanel, isWide && styles.illustrationPanelWide]}>
                    <Image source={exerciseImage(exercise)} style={styles.exerciseImage} resizeMode="contain" accessibilityLabel={`Demonstration of ${exercise.name}`} />
                  </View>
                  <View style={styles.exerciseBody}>
                    <View style={styles.exerciseHeader}>
                      <View style={styles.exerciseHeadingCopy}>
                        <View style={styles.titleAndTag}>
                          <Text style={styles.exerciseTitle}>{exercise.name}</Text>
                          <View style={styles.focusTag}><Text style={styles.focusTagText}>{exerciseFocus(exercise)}</Text></View>
                          {isDone && <View style={styles.completeTag} testID={`exercise-progress-${exercise.id}`}><Text style={styles.completeTagText}>Complete</Text></View>}
                        </View>
                        <Text style={styles.exerciseMeta}>{exercise.sets} sets × {exercise.reps} reps</Text>
                      </View>
                    </View>
                    <Text style={styles.exerciseDescription}>{exercise.description}</Text>
                    {itemProgress.last_score != null && <Text style={styles.sessionScore}>Last guided session: {itemProgress.last_score}/100</Text>}

                    {purposeExpanded && (
                      <View style={styles.rationalePanel} testID={`exercise-rationale-${exercise.id}`}>
                        <View style={styles.rationaleRow}>
                          <Ionicons name="heart-outline" size={20} color={colors.brandPrimary} />
                          <Text style={styles.rationaleText}>{exercisePurpose(exercise)}</Text>
                        </View>
                        <View style={styles.rationaleRow}>
                          <Ionicons name="warning-outline" size={20} color="#B65C09" />
                          <Text style={styles.rationaleText}>{exerciseSafety(exercise)}</Text>
                        </View>
                      </View>
                    )}

                    <View style={[styles.exerciseFooter, !isWide && styles.exerciseFooterNarrow]}>
                      <Pressable onPress={() => togglePurpose(exercise.id)} style={styles.purposeLink} accessibilityRole="button" testID={`exercise-purpose-${exercise.id}`}>
                        <Ionicons name={purposeExpanded ? "chevron-up" : "chevron-down"} size={18} color={colors.brandPrimary} />
                        <Text style={styles.purposeLinkText}>Why this exercise?</Text>
                      </Pressable>
                      <View style={[styles.exerciseActions, !isWide && styles.exerciseActionsNarrow]}>
                        <Pressable onPress={() => setDemonstrationId(exercise.id)} style={styles.demoButton} accessibilityRole="button" testID={`exercise-demo-${exercise.id}`}>
                          <Ionicons name="play" size={18} color={colors.brandPrimary} />
                          <Text style={styles.demoButtonText}>Demo</Text>
                        </Pressable>
                        <Pressable onPress={() => openGuidedExercise(exercise)} style={styles.guidedBtn} accessibilityRole="button" testID={`exercise-guided-${exercise.id}`}>
                          <Text style={styles.guidedBtnText}>{isDone ? "Practice again" : percent > 0 ? "Continue exercise" : "Begin exercise"}</Text>
                          <Ionicons name="arrow-forward" size={20} color="#FFFFFF" />
                        </Pressable>
                      </View>
                    </View>
                  </View>
                </View>
              );
            })}
          </View>

          <Pressable disabled={!allComplete} onPress={() => router.dismissTo("/")} style={[styles.finishButton, !allComplete && styles.finishButtonDisabled]} accessibilityRole="button" testID="plan-done">
            <Ionicons name="checkmark-circle-outline" size={21} color={allComplete ? "#FFFFFF" : "#A3A8A4"} />
            <Text style={[styles.finishButtonText, !allComplete && styles.finishButtonTextDisabled]}>Complete session</Text>
          </Pressable>
        </View>
      </ScrollView>

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
  container: { flex: 1, backgroundColor: "#FAFBF9" },
  center: { alignItems: "center", justifyContent: "center" },
  preparationPage: { flex: 1, backgroundColor: "#FCFCFA" },
  preparationHeader: { minHeight: 74, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: "#DDE2DC", backgroundColor: "#FCFCFA" },
  preparationBack: { width: 48, height: 48, alignItems: "center", justifyContent: "center" },
  preparationHeaderTitle: { fontSize: 26, lineHeight: 32, fontWeight: "800", color: "#174D3A", letterSpacing: 0 },
  preparationHeaderSpacer: { width: 48 },
  preparationBody: { flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.lg, paddingBottom: 72 },
  preparationBodyCompact: { justifyContent: "flex-start", paddingTop: 54, paddingBottom: spacing.xl },
  preparationIcon: { width: 144, height: 144, borderRadius: 72, alignItems: "center", justifyContent: "center", backgroundColor: "#F1F5EF", marginBottom: 28 },
  preparationIconCompact: { width: 112, height: 112, borderRadius: 56, marginBottom: spacing.lg },
  preparationHeart: { position: "absolute", right: 31, bottom: 31, backgroundColor: "#F1F5EF", borderRadius: 18, padding: 1 },
  preparationTitle: { fontSize: 45, lineHeight: 55, fontWeight: "800", color: "#174D3A", letterSpacing: 0, textAlign: "center", marginBottom: 28 },
  preparationTitleCompact: { fontSize: 31, lineHeight: 39, marginBottom: spacing.lg },
  preparationCard: { width: "100%", maxWidth: 630, borderWidth: 1, borderColor: "#D7D9D1", borderRadius: radius.sm, backgroundColor: "#FFFFFF", paddingHorizontal: 66, paddingVertical: 24 },
  preparationCardCompact: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  preparationStep: { minHeight: 84, flexDirection: "row", alignItems: "center" },
  preparationTimelineColumn: { width: 54, height: 84, alignItems: "center", justifyContent: "center", marginRight: spacing.md },
  preparationStatus: { width: 48, height: 48, borderRadius: 24, borderWidth: 4, borderColor: "#C4C9C2", backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center", zIndex: 2 },
  preparationStatusComplete: { borderColor: "#246149", backgroundColor: "#246149" },
  preparationStatusActive: { borderColor: "#49A36C", backgroundColor: "#FFFFFF" },
  preparationPulse: { position: "absolute", width: 54, height: 54, borderRadius: 27, borderWidth: 3, borderColor: "#78C191", zIndex: 1 },
  preparationLineTop: { position: "absolute", top: 0, width: 3, height: 21, backgroundColor: "#C7CCC6" },
  preparationLineBottom: { position: "absolute", bottom: 0, width: 3, height: 21, backgroundColor: "#C7CCC6" },
  preparationLineComplete: { backgroundColor: "#4B9B6A" },
  preparationStepText: { flex: 1, minWidth: 0, fontSize: 23, lineHeight: 30, fontWeight: "500", color: "#245B49", letterSpacing: 0 },
  preparationStepTextActive: { fontWeight: "800" },
  preparationStepTextComplete: { fontWeight: "700" },
  preparationStepTextCompact: { fontSize: 18, lineHeight: 24 },
  preparationHint: { marginTop: 25, fontSize: 21, lineHeight: 28, color: "#245B49", textAlign: "center", letterSpacing: 0 },
  preparationHintCompact: { marginTop: spacing.lg, fontSize: 16, lineHeight: 22 },
  header: { minHeight: 58, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.xs, backgroundColor: "#FAFBF9", borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 19, lineHeight: 24, fontWeight: "800", color: "#123E2D" },
  headerSpacer: { width: 44 },
  sessionSetupScroll: { paddingHorizontal: spacing.md, paddingTop: spacing.xl, paddingBottom: 48 },
  sessionSetupPage: { width: "100%", maxWidth: 920, alignSelf: "center" },
  sessionSetupEyebrow: { fontSize: 13, lineHeight: 18, fontWeight: "800", color: "#4E7C62", letterSpacing: 0 },
  sessionSetupTitle: { marginTop: spacing.xs, fontSize: 36, lineHeight: 44, fontWeight: "800", color: "#123E2D", letterSpacing: 0 },
  sessionSetupIntro: { maxWidth: 720, marginTop: spacing.sm, fontSize: 17, lineHeight: 25, color: "#536159" },
  sessionSectionTitle: { marginTop: spacing.xl, marginBottom: spacing.sm, fontSize: 20, lineHeight: 27, fontWeight: "800", color: "#173F30" },
  sessionChoiceRow: { gap: spacing.sm },
  sessionChoice: { minHeight: 92, flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderWidth: 1, borderColor: "#CBD4CC", borderRadius: radius.sm, backgroundColor: "#FFFFFF" },
  sessionChoiceSelected: { borderWidth: 2, borderColor: colors.brandPrimary, backgroundColor: "#F0F7F2" },
  sessionChoiceIcon: { width: 46, height: 46, borderRadius: 23, alignItems: "center", justifyContent: "center", backgroundColor: "#E7EFE9" },
  sessionChoiceIconSelected: { backgroundColor: colors.brandPrimary },
  sessionChoiceCopy: { flex: 1, minWidth: 0 },
  sessionChoiceHeading: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  sessionChoiceLabel: { fontSize: 17, lineHeight: 23, fontWeight: "800", color: "#173F30" },
  sessionChoiceDescription: { marginTop: 3, fontSize: 14, lineHeight: 20, color: "#5C6861" },
  recommendedTag: { paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: "#DDEEDF" },
  recommendedTagText: { fontSize: 11, lineHeight: 15, fontWeight: "800", color: "#2D6B45" },
  difficultyRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  difficultyChoice: { flexGrow: 1, flexBasis: 220, minHeight: 138, padding: spacing.md, borderWidth: 1, borderColor: "#CBD4CC", borderRadius: radius.sm, backgroundColor: "#FFFFFF" },
  difficultyChoiceSelected: { borderWidth: 2, borderColor: colors.brandPrimary, backgroundColor: "#F0F7F2" },
  difficultyLabel: { marginTop: spacing.sm, fontSize: 18, lineHeight: 24, fontWeight: "800", color: "#173F30" },
  difficultySummary: { marginTop: 4, fontSize: 13, lineHeight: 19, color: "#5C6861" },
  sessionPreview: { marginTop: spacing.xl, borderTopWidth: 1, borderTopColor: "#D7DDD8" },
  sessionPreviewTitle: { paddingTop: spacing.lg, paddingBottom: spacing.sm, fontSize: 20, lineHeight: 27, fontWeight: "800", color: "#173F30" },
  sessionPreviewItem: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: "#E2E6E2" },
  sessionPreviewIcon: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center", backgroundColor: "#E8F0EA" },
  sessionPreviewCopy: { flex: 1, minWidth: 0 },
  sessionPreviewName: { fontSize: 16, lineHeight: 22, fontWeight: "800", color: "#173F30" },
  sessionPreviewDose: { marginTop: 3, fontSize: 14, lineHeight: 20, color: "#536159" },
  sessionPreviewVariation: { marginTop: 4, fontSize: 13, lineHeight: 19, fontWeight: "700", color: colors.brandPrimary },
  sessionPreviewSafety: { marginTop: 4, fontSize: 13, lineHeight: 19, fontWeight: "700", color: "#9A570F" },
  sessionSafetyNote: { marginTop: spacing.lg, flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, padding: spacing.md, borderWidth: 1, borderColor: "#E8C788", borderRadius: radius.sm, backgroundColor: "#FFF8EC" },
  sessionSafetyNoteText: { flex: 1, fontSize: 14, lineHeight: 21, color: "#6D4A18" },
  sessionConfirm: { width: "100%", maxWidth: 390, minHeight: 58, marginTop: spacing.xl, alignSelf: "center", paddingHorizontal: spacing.lg, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, borderRadius: radius.sm, backgroundColor: colors.brandPrimary },
  sessionConfirmText: { fontSize: 16, lineHeight: 22, fontWeight: "800", color: "#FFFFFF" },
  promptBackdrop: { flex: 1, backgroundColor: "rgba(18, 36, 29, 0.58)" },
  promptScroll: { flexGrow: 1, alignItems: "center", justifyContent: "center", padding: spacing.md },
  promptCard: { width: "100%", maxWidth: 620, padding: spacing.lg, borderRadius: radius.sm, backgroundColor: "#FAFBF9", borderWidth: 1, borderColor: "#D3DBD4" },
  promptHeader: { minHeight: 42, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  promptIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: "#E6EFE8" },
  promptClose: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  promptEyebrow: { marginTop: spacing.sm, fontSize: 12, lineHeight: 17, fontWeight: "800", color: "#4E7C62", letterSpacing: 0 },
  promptTitle: { marginTop: 4, fontSize: 28, lineHeight: 35, fontWeight: "800", color: "#123E2D", letterSpacing: 0 },
  promptIntro: { marginTop: spacing.xs, fontSize: 15, lineHeight: 22, color: "#536159" },
  promptIntroStrong: { fontWeight: "800", color: "#173F30" },
  promptQuestion: { marginTop: spacing.md, paddingTop: spacing.md, borderTopWidth: 1, borderTopColor: "#DCE2DD" },
  promptQuestionDisabled: { opacity: 0.68 },
  promptQuestionHeading: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.xs },
  promptQuestionTitle: { flexShrink: 1, fontSize: 18, lineHeight: 24, fontWeight: "800", color: "#173F30" },
  promptQuestionCopy: { marginTop: 4, fontSize: 14, lineHeight: 20, color: "#5C6861" },
  promptChoiceRow: { marginTop: spacing.sm, flexDirection: "row", gap: spacing.sm },
  promptChoiceWrap: { flex: 1 },
  promptChoice: { flex: 1, minHeight: 50, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, borderWidth: 1, borderColor: "#C7D0C9", borderRadius: radius.sm, backgroundColor: "#FFFFFF" },
  promptChoiceSelected: { borderWidth: 2, borderColor: colors.brandPrimary, backgroundColor: "#EDF5EF" },
  promptChoiceText: { fontSize: 16, lineHeight: 22, fontWeight: "700", color: "#536159" },
  promptChoiceTextSelected: { color: "#174D3A" },
  promptDisabledChoice: { opacity: 0.45 },
  promptSafety: { marginTop: spacing.md, flexDirection: "row", alignItems: "flex-start", gap: spacing.xs, padding: spacing.sm, borderRadius: radius.sm, backgroundColor: "#FFF8EC", borderWidth: 1, borderColor: "#E8C788" },
  promptSafetyText: { flex: 1, fontSize: 13, lineHeight: 19, color: "#6D4A18" },
  scrollContent: { paddingHorizontal: spacing.md, paddingTop: spacing.lg },
  page: { width: "100%", maxWidth: 1100, alignSelf: "center" },
  interimBanner: { flexDirection: "row", alignItems: "flex-start", gap: spacing.xs, backgroundColor: "#FFF4DA", borderRadius: radius.sm, padding: spacing.sm, marginBottom: spacing.sm },
  interimBannerText: { flex: 1, fontSize: 13, lineHeight: 18, color: "#6B4A0B", fontWeight: "700" },
  demoBanner: { flexDirection: "row", alignItems: "center", gap: spacing.sm, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, marginBottom: spacing.md, backgroundColor: "#F3EDFA", borderWidth: 1, borderColor: "#D9C8ED" },
  demoBannerText: { flex: 1, fontSize: 13, lineHeight: 18, fontWeight: "700", color: "#5C486F" },
  planIntro: { marginBottom: spacing.xl },
  summaryTitle: { fontSize: 38, lineHeight: 46, fontWeight: "800", color: "#123E2D" },
  summaryTitleNarrow: { fontSize: 28, lineHeight: 34 },
  summarySubtitle: { marginTop: 4, fontSize: 17, lineHeight: 24, color: colors.onSurfaceSecondary },
  sessionSummary: { marginTop: spacing.xs, fontSize: 14, lineHeight: 20, fontWeight: "700", color: colors.brandPrimary },
  progressRow: { marginTop: spacing.lg, flexDirection: "row", alignItems: "center", gap: spacing.md },
  progressTrack: { flex: 1, height: 8, borderRadius: 4, backgroundColor: "#DDE5DE", overflow: "hidden" },
  progressFill: { height: 8, minWidth: 8, borderRadius: 4, backgroundColor: "#58A477" },
  summaryProgressText: { minWidth: 132, fontSize: 15, lineHeight: 21, fontWeight: "700", color: "#164B35", textAlign: "right" },
  safetyBanner: { minHeight: 148, marginBottom: spacing.lg, borderWidth: 1, borderColor: "#EDB85D", borderRadius: radius.sm, backgroundColor: "#FFF8EC", paddingHorizontal: spacing.xl, paddingVertical: spacing.lg, flexDirection: "row", alignItems: "center", gap: spacing.lg },
  safetyBannerNarrow: { minHeight: 0, paddingHorizontal: spacing.md, paddingVertical: spacing.lg, gap: spacing.md },
  safetyShield: { width: 58, height: 58, alignItems: "center", justifyContent: "center" },
  safetyCopy: { flex: 1, minWidth: 0 },
  safetyHeading: { fontSize: 21, lineHeight: 27, fontWeight: "800", color: "#A85006" },
  safetyMessage: { maxWidth: 560, marginTop: 4, fontSize: 16, lineHeight: 23, color: colors.onSurfaceSecondary },
  exerciseList: { gap: spacing.md },
  exerciseCard: { position: "relative", backgroundColor: "#FFFFFF", borderRadius: radius.sm, borderWidth: 1, borderColor: "#D6DDD7", overflow: "hidden" },
  exerciseCardWide: { minHeight: 250, flexDirection: "row", alignItems: "stretch" },
  exerciseCardDone: { borderColor: "#8EB59D" },
  exerciseIndexColumn: { width: 64, alignItems: "center", paddingTop: spacing.xl },
  exerciseIndexColumnNarrow: { position: "absolute", top: spacing.md, left: spacing.md, width: 44, paddingTop: 0, zIndex: 3 },
  exerciseNumber: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  exerciseNumberDone: { backgroundColor: colors.success },
  exerciseNumberText: { color: "#FFFFFF", fontSize: 18, lineHeight: 22, fontWeight: "800" },
  illustrationPanel: { height: 220, margin: spacing.md, borderWidth: 1, borderColor: "#DCE2DD", borderRadius: radius.sm, backgroundColor: "#F5F7F4", overflow: "hidden", padding: spacing.xs },
  illustrationPanelWide: { width: 190, height: 204, marginLeft: 0, marginRight: 0, marginVertical: spacing.lg },
  exerciseImage: { width: "100%", height: "100%" },
  exerciseBody: { flex: 1, minWidth: 0, padding: spacing.lg },
  exerciseHeader: { flexDirection: "row", alignItems: "flex-start" },
  exerciseHeadingCopy: { flex: 1, minWidth: 0 },
  titleAndTag: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  exerciseTitle: { fontSize: 22, lineHeight: 28, fontWeight: "800", color: "#123E2D" },
  focusTag: { paddingHorizontal: spacing.sm, paddingVertical: 5, borderRadius: radius.pill, backgroundColor: "#E6EFE8" },
  focusTagText: { color: "#427454", fontSize: 12, lineHeight: 16, fontWeight: "700" },
  completeTag: { paddingHorizontal: spacing.sm, paddingVertical: 5, borderRadius: radius.pill, backgroundColor: "#E1F1E6" },
  completeTagText: { color: "#2C7543", fontSize: 12, lineHeight: 16, fontWeight: "800" },
  exerciseMeta: { marginTop: spacing.sm, fontSize: 16, lineHeight: 22, color: colors.brandPrimary, fontWeight: "700" },
  exerciseDescription: { marginTop: spacing.sm, fontSize: 15, lineHeight: 22, color: colors.onSurface },
  sessionScore: { marginTop: spacing.sm, fontSize: 12, lineHeight: 17, fontWeight: "700", color: colors.brandPrimary },
  rationalePanel: { marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider, gap: spacing.xs },
  rationaleRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.xs },
  rationaleText: { flex: 1, fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary },
  exerciseFooter: { marginTop: "auto", paddingTop: spacing.md, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  exerciseFooterNarrow: { flexDirection: "column", alignItems: "stretch" },
  purposeLink: { minHeight: 44, flexDirection: "row", alignItems: "center", gap: 4 },
  purposeLinkText: { fontSize: 14, lineHeight: 20, fontWeight: "700", color: colors.brandPrimary, textDecorationLine: "underline" },
  exerciseActions: { flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: spacing.md },
  exerciseActionsNarrow: { flexDirection: "column", alignItems: "stretch" },
  demoButton: { minWidth: 130, minHeight: 50, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, borderWidth: 1, borderColor: "#7C9C87", borderRadius: radius.sm, backgroundColor: "#FFFFFF" },
  demoButtonText: { color: colors.brandPrimary, fontSize: 15, lineHeight: 21, fontWeight: "800" },
  guidedBtn: { minWidth: 192, minHeight: 50, paddingHorizontal: spacing.lg, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, borderRadius: radius.sm, backgroundColor: colors.brandPrimary },
  guidedBtnText: { color: "#FFFFFF", fontSize: 15, lineHeight: 21, fontWeight: "800" },
  finishButton: { width: "100%", maxWidth: 390, minHeight: 68, alignSelf: "center", marginTop: spacing.xl, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg },
  finishButtonDisabled: { backgroundColor: "#E4E6E4" },
  finishButtonText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "800" },
  finishButtonTextDisabled: { color: "#A3A8A4" },
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
