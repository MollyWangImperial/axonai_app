import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Svg, { Circle, Line, Polyline } from "react-native-svg";
import * as Haptics from "expo-haptics";

import { Assessment, fetchHistory } from "@/src/api";
import { authedFetch, getCachedUser, preferredNameKey } from "@/src/auth";
import { SurveyPrefaceModal } from "@/src/components/SurveyPrefaceModal";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { colors, radius, spacing } from "@/src/theme";
import { loadSettings, rescheduleReminders } from "@/src/utils/notifications";
import { storage } from "@/src/utils/storage";

type CarePlanNextStep = {
  action?: string;
  title?: string;
  message?: string;
  cta?: string;
  destination?: string;
  missing_domains?: string[];
  remaining_exercise_ids?: string[];
  secondary_action?: CarePlanNextStep | null;
};

type CarePlanAssessment = {
  due?: boolean;
  due_at?: string;
  can_start?: boolean;
  packages?: string[];
  recommended_packages?: string[];
  task_ids?: string[];
  trigger?: string;
  missing_domains?: string[];
  missing_task_ids?: string[];
};

type HomeCarePlan = {
  assessment?: CarePlanAssessment;
  survey?: { due?: boolean; due_at?: string; patient_prompt_enabled?: boolean };
  exercise_plan?: { action?: string; approved_exercise_ids?: string[] };
  daily_monitoring?: {
    active_exercise_ids?: string[];
    completed_exercise_ids_today?: string[];
    remaining_exercise_ids_today?: string[];
    current_round_complete?: boolean;
    sessions_last_7_days?: number;
  };
  next_step?: CarePlanNextStep;
};

type DailyCheckInState = {
  status: "not_checked_in" | "in_progress" | "complete";
  days: { date: string; status: string }[];
};

type RewardsSummary = {
  points: number;
  message?: string;
  streak?: { current_days?: number };
};

type ProgressPoint = {
  id: string;
  date: string;
  reach_completion: number | null;
  bilateral_symmetry: number | null;
  pinch_grip: number | null;
  hand_opening: number | null;
  walking_skipped?: boolean;
};

type ProgressSummary = { assessments: ProgressPoint[] };

type HomeScreenCache = {
  history: Assessment[];
  greetName: string;
  carePlan: HomeCarePlan | null;
  dailyGoal: string;
  ownGoal: string;
  checkIn: DailyCheckInState;
  rewards: RewardsSummary | null;
  progress: ProgressSummary;
};

type TrendDefinition = {
  id: "reach" | "hand" | "walking";
  label: string;
  icon: React.ComponentProps<typeof Ionicons>["name"];
  values: number[];
  dates: string[];
  message: string;
};

const EMPTY_CHECK_IN: DailyCheckInState = { status: "not_checked_in", days: [] };
const EMPTY_PROGRESS: ProgressSummary = { assessments: [] };

function localDateString(date = new Date()) {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function deriveFunctionalGoal(profile: any): string {
  const arm = String(profile?.affected_arm_movement || "").toLowerCase();
  const hand = String(profile?.affected_hand_movement || "").toLowerCase();
  const mobility = String(profile?.mobility_level || "").toLowerCase();
  const goals: string[] = [];
  if (["some_movement", "help_only", "no_movement", "not_sure"].includes(arm)) goals.push("eating and dressing with your arm");
  if (["some_finger_movement", "very_little_movement", "no_movement", "not_sure"].includes(hand)) goals.push("grooming and small hand tasks");
  if (["person_assist", "wheelchair", "unable_walk", "not_cleared", "unsure"].includes(mobility)) goals.push("moving around more safely");
  if (goals.length === 0) return "";
  const joined = goals.length === 1
    ? goals[0]
    : goals.length === 2
      ? `${goals[0]} and ${goals[1]}`
      : `${goals[0]}, ${goals[1]}, and ${goals[2]}`;
  return `Manage ${joined} with less help`;
}

function normalizeMetric(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  const normalized = Math.abs(value) <= 1.5 ? value * 100 : value;
  return Math.max(0, Math.min(100, normalized));
}

function formatShortDate(value?: string) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function trendMessage(label: TrendDefinition["label"], values: number[], walkingSkipped: boolean) {
  if (label === "Walking" && walkingSkipped) return "Walking has not been observed yet.";
  if (values.length === 0) return "Complete an assessment to start this trend.";
  if (values.length === 1) return `${label} baseline recorded.`;
  const change = values[values.length - 1] - values[0];
  if (change >= 2) return label === "Reaching" ? "Reaching is becoming easier." : `${label} looks steadier.`;
  if (change <= -2) return `${label} is ready for review.`;
  return `${label} looks steady.`;
}

function buildTrends(summary: ProgressSummary): TrendDefinition[] {
  const points = summary.assessments || [];
  const dates = points.map((point) => point.date);
  const collect = (reader: (point: ProgressPoint) => number | null) => points
    .map(reader)
    .filter((value): value is number => value != null);
  const reach = collect((point) => normalizeMetric(point.reach_completion));
  const hand = collect((point) => {
    const values = [normalizeMetric(point.hand_opening), normalizeMetric(point.pinch_grip)]
      .filter((value): value is number => value != null);
    return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
  });
  const walking = collect((point) => normalizeMetric(point.bilateral_symmetry));
  const walkingSkipped = Boolean(points[points.length - 1]?.walking_skipped);
  return [
    { id: "reach", label: "Reaching", icon: "accessibility-outline", values: reach, dates, message: trendMessage("Reaching", reach, false) },
    { id: "hand", label: "Hand control", icon: "hand-left-outline", values: hand, dates, message: trendMessage("Hand control", hand, false) },
    { id: "walking", label: "Walking", icon: "walk-outline", values: walking, dates, message: trendMessage("Walking", walking, walkingSkipped) },
  ];
}

function MiniTrendChart({ values }: { values: number[] }) {
  const width = 300;
  const height = 84;
  const padX = 10;
  const padY = 12;
  if (values.length === 0) {
    return (
      <View style={styles.emptyChart}>
        <Ionicons name="analytics-outline" size={24} color="#9AABA0" />
        <Text style={styles.emptyChartText}>No measurements yet</Text>
      </View>
    );
  }
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const spread = Math.max(12, maximum - minimum);
  const points = values.map((value, index) => {
    const x = values.length === 1 ? width / 2 : padX + (index * (width - padX * 2)) / (values.length - 1);
    const y = height - padY - ((value - minimum + (spread - (maximum - minimum)) / 2) / spread) * (height - padY * 2);
    return { x, y };
  });
  const last = points[points.length - 1];
  return (
    <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} testID="home-trend-chart">
      <Line x1={padX} y1={height - 4} x2={width - padX} y2={height - 4} stroke="#D4DDD7" strokeWidth={1} strokeDasharray="5 5" />
      {points.length > 1 ? (
        <Polyline points={points.map((point) => `${point.x},${point.y}`).join(" ")} fill="none" stroke="#0A7A3B" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
      ) : null}
      {points.map((point, index) => <Circle key={`${point.x}-${point.y}`} cx={point.x} cy={point.y} r={index === points.length - 1 ? 4.5 : 3.4} fill="#0A7A3B" />)}
      <Circle cx={last.x} cy={last.y} r={14} fill="#5AC77D" opacity={0.12} />
      <Circle cx={last.x} cy={last.y} r={9} fill="#48BE70" opacity={0.18} />
      <Circle cx={last.x} cy={last.y} r={4.5} fill="#087435" />
    </Svg>
  );
}

function StatusPill({ icon, label, tone = "green" }: { icon: React.ComponentProps<typeof Ionicons>["name"]; label: string; tone?: "green" | "amber" | "grey" }) {
  const presentation = tone === "green"
    ? { background: "#E8F3EB", color: "#155D3C" }
    : tone === "amber"
      ? { background: "#FFF1D8", color: "#7B5107" }
      : { background: "#F0F2F0", color: "#5D6660" };
  return (
    <View style={[styles.statusPill, { backgroundColor: presentation.background }]}>
      <Ionicons name={icon} size={15} color={presentation.color} />
      <Text style={[styles.statusPillText, { color: presentation.color }]}>{label}</Text>
    </View>
  );
}

type DayStepProps = {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  title: string;
  badge: React.ReactNode;
  description: string;
  active?: boolean;
  progress?: { completed: number; total: number };
  button?: { label: string; icon: React.ComponentProps<typeof Ionicons>["name"]; onPress: () => void; primary?: boolean; testID: string };
};

function DayStep({ icon, title, badge, description, active, progress, button }: DayStepProps) {
  const percentage = progress?.total ? Math.min(100, Math.round((progress.completed / progress.total) * 100)) : 0;
  return (
    <View style={styles.dayStep}>
      <View style={[styles.dayStepIcon, active && styles.dayStepIconActive]}>
        <Ionicons name={icon} size={28} color={active ? "#0B7338" : "#5E6861"} />
      </View>
      <Text style={styles.dayStepTitle}>{title}</Text>
      {badge}
      <Text style={styles.dayStepDescription}>{description}</Text>
      {progress ? (
        <View style={styles.stepProgressWrap}>
          <Text style={styles.stepProgressLabel}>{progress.completed} of {progress.total} activities complete</Text>
          <View style={styles.stepProgressTrack}><View style={[styles.stepProgressFill, { width: `${percentage}%` }]} /></View>
        </View>
      ) : null}
      {button ? (
        <Pressable
          testID={button.testID}
          accessibilityRole="button"
          onPress={button.onPress}
          style={({ pressed }) => [styles.stepButton, button.primary ? styles.stepButtonPrimary : styles.stepButtonSecondary, pressed && styles.pressed]}
        >
          <Ionicons name={button.icon} size={18} color={button.primary ? "#FFFFFF" : "#145C3B"} />
          <Text style={[styles.stepButtonText, button.primary ? styles.stepButtonTextPrimary : styles.stepButtonTextSecondary]}>{button.label}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { palette } = useDisplayPreferences();
  const { width } = useWindowDimensions();
  const isWide = width >= 900;
  const cached = getScreenCache<HomeScreenCache>("home");
  const [history, setHistory] = useState<Assessment[]>(cached?.history ?? []);
  const [greetName, setGreetName] = useState(cached?.greetName ?? "");
  const [carePlan, setCarePlan] = useState<HomeCarePlan | null>(cached?.carePlan ?? null);
  const [dailyGoal, setDailyGoal] = useState(cached?.dailyGoal ?? "");
  const [ownGoal, setOwnGoal] = useState(cached?.ownGoal ?? "");
  const [checkIn, setCheckIn] = useState<DailyCheckInState>(cached?.checkIn ?? EMPTY_CHECK_IN);
  const [rewards, setRewards] = useState<RewardsSummary | null>(cached?.rewards ?? null);
  const [progress, setProgress] = useState<ProgressSummary>(cached?.progress ?? EMPTY_PROGRESS);
  const [loading, setLoading] = useState(!cached);
  const [checkingIn, setCheckingIn] = useState(false);
  const [showWeek, setShowWeek] = useState(false);
  const [showSurveyPreface, setShowSurveyPreface] = useState(false);

  const load = useCallback(async () => {
    if (!getScreenCache<HomeScreenCache>("home")) setLoading(true);
    const user = await getCachedUser();
    const [assessments, preferredName, carePlanPayload, onboarding, checkInPayload, rewardsPayload, progressPayload] = await Promise.all([
      fetchHistory().catch(() => []),
      user?.id ? storage.getItem(preferredNameKey(user.id), "") : Promise.resolve(""),
      authedFetch("/api/alira/care-plan").then(async (response) => response.ok ? response.json() : null).catch(() => null),
      authedFetch("/api/users/onboarding").then(async (response) => response.ok ? response.json() : null).catch(() => null),
      authedFetch("/api/users/daily-checkin").then(async (response) => response.ok ? response.json() : null).catch(() => null),
      authedFetch("/api/users/rewards").then(async (response) => response.ok ? response.json() : null).catch(() => null),
      authedFetch("/api/progress/summary").then(async (response) => response.ok ? response.json() : null).catch(() => null),
    ]);
    const nextName = preferredName || user?.name?.split(" ")[0] || "there";
    const nextOwnGoal = String(onboarding?.profile?.primary_goal || "").trim();
    const nextDailyGoal = deriveFunctionalGoal(onboarding?.profile) || nextOwnGoal;
    const nextCheckIn = checkInPayload
      ? { status: checkInPayload.status || "not_checked_in", days: checkInPayload.days || [] }
      : EMPTY_CHECK_IN;
    const nextProgress = progressPayload?.assessments ? progressPayload : EMPTY_PROGRESS;
    setHistory(assessments);
    setGreetName(nextName);
    setCarePlan(carePlanPayload);
    setDailyGoal(nextDailyGoal);
    setOwnGoal(nextOwnGoal);
    setCheckIn(nextCheckIn);
    setRewards(rewardsPayload);
    setProgress(nextProgress);
    setScreenCache<HomeScreenCache>("home", {
      history: assessments,
      greetName: nextName,
      carePlan: carePlanPayload,
      dailyGoal: nextDailyGoal,
      ownGoal: nextOwnGoal,
      checkIn: nextCheckIn,
      rewards: rewardsPayload,
      progress: nextProgress,
    });
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  useEffect(() => {
    if (carePlan) void loadSettings().then((settings) => rescheduleReminders(settings, carePlan));
  }, [carePlan]);

  const latest = history[0];
  const hasInitialAssessment = history.some((item) => item.assessment_package === "initial");
  const isInitialAssessment = !hasInitialAssessment;
  const carePlanAssessment = carePlan?.assessment || null;
  const followUpDue = Boolean(carePlanAssessment?.due && carePlanAssessment?.can_start);
  const nextStep = carePlan?.next_step || null;
  const activeExerciseIds = carePlan?.daily_monitoring?.active_exercise_ids || carePlan?.exercise_plan?.approved_exercise_ids || [];
  const completedExerciseIds = carePlan?.daily_monitoring?.completed_exercise_ids_today || [];
  const remainingExerciseIds = carePlan?.daily_monitoring?.remaining_exercise_ids_today || nextStep?.remaining_exercise_ids || [];
  const missingDomains = carePlanAssessment?.missing_domains || nextStep?.missing_domains || [];
  const missingTaskIds = carePlanAssessment?.missing_task_ids || [];
  const walkingOutstanding = missingDomains.includes("lower_limb") || missingTaskIds.includes("L6");
  const displayGoal = ownGoal || dailyGoal || "building everyday independence";
  const trends = useMemo(() => buildTrends(progress), [progress]);
  const assessmentDueLabel = formatShortDate(carePlanAssessment?.due_at);
  const surveyDueLabel = formatShortDate(carePlan?.survey?.due_at);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const todayLabel = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const recentCheckIns = checkIn.days.slice(-7);

  const startNextSession = useCallback((taskIds?: string[]) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const selectedPackage = isInitialAssessment
      ? "initial"
      : carePlanAssessment?.packages?.[0] || carePlanAssessment?.recommended_packages?.[0] || latest?.assessment_package || "initial";
    router.push({
      pathname: "/session-check" as never,
      params: {
        target: "assessment",
        mode: taskIds?.length ? "initial" : isInitialAssessment ? "initial" : "followup",
        package: selectedPackage,
        task_ids: (taskIds?.length ? taskIds : carePlanAssessment?.task_ids || []).join(","),
      },
    });
  }, [carePlanAssessment, isInitialAssessment, latest?.assessment_package, router]);

  const openSurveyChat = () => {
    setShowSurveyPreface(false);
    router.push({ pathname: "/(tabs)/chat" as never, params: { prompt: "Please begin my scheduled short recovery check-in." } });
  };

  const openDestination = useCallback((destination?: string) => {
    Haptics.selectionAsync();
    switch (destination) {
      case "survey": setShowSurveyPreface(true); return;
      case "initial_assessment": startNextSession(); return;
      case "assessment": startNextSession(); return;
      case "rehab_plan":
        if (latest) router.push({ pathname: "/rehab-plan" as never, params: { id: latest.id } });
        else router.push("/(tabs)/journey" as never);
        return;
      case "caregiver_plan": router.push("/caregiver-plan" as never); return;
      case "survey_report": router.push("/survey-report" as never); return;
      case "emergency": router.push("/(tabs)/emergency" as never); return;
      case "alira": router.push({ pathname: "/(tabs)/chat" as never, params: { prompt: "Please guide me through my next safe step." } }); return;
      case "progress": router.push("/progress" as never); return;
      default: router.push("/progress" as never);
    }
  }, [latest, router, startNextSession]);

  const checkInForToday = useCallback(async () => {
    if (checkingIn || checkIn.status !== "not_checked_in") return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setCheckingIn(true);
    const response = await authedFetch("/api/users/daily-checkin", {
      method: "POST",
      body: JSON.stringify({ date: localDateString() }),
    }).catch(() => null);
    if (response?.ok) {
      const payload = await response.json().catch(() => null);
      if (payload) setCheckIn({ status: payload.status || "in_progress", days: payload.days || [] });
    }
    setCheckingIn(false);
  }, [checkIn.status, checkingIn]);

  const openExercisePlan = () => {
    if (nextStep?.destination === "caregiver_plan") openDestination("caregiver_plan");
    else if (latest) router.push({ pathname: "/rehab-plan" as never, params: { id: latest.id } });
    else openDestination(nextStep?.destination);
  };

  const primaryTitle = isInitialAssessment
    ? "Initial assessment"
    : nextStep?.destination === "caregiver_plan"
      ? "Today's routines"
      : activeExerciseIds.length
        ? "Today's exercises"
        : nextStep?.title || "Your next step";
  const primaryDescription = isInitialAssessment
    ? "Alira selected suitable tasks from your readiness answers."
    : activeExerciseIds.length
      ? remainingExerciseIds.length
        ? "Continue the plan Alira selected for this recovery stage."
        : "Today's planned activities are complete."
      : nextStep?.message || "Your care plan is up to date.";
  const primaryComplete = activeExerciseIds.length > 0 && remainingExerciseIds.length === 0;
  const initialWalkingAssigned = Boolean(isInitialAssessment && carePlanAssessment?.task_ids?.includes("L6"));
  const primaryButton = isInitialAssessment
    ? { label: "Start Initial Assessment", destination: "initial_assessment" }
    : activeExerciseIds.length
      ? { label: primaryComplete ? "Review exercises" : "Continue exercises", destination: nextStep?.destination === "caregiver_plan" ? "caregiver_plan" : "rehab_plan" }
      : { label: nextStep?.cta || "Open next step", destination: nextStep?.destination };

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <ScrollView contentContainerStyle={[styles.page, { paddingTop: insets.top + spacing.sm }]} showsVerticalScrollIndicator={false}>
        <View style={styles.inner}>
          <View style={styles.header}>
            <View style={styles.brandRow}>
              <View style={styles.brandIcon}><Ionicons name="pulse" size={22} color="#FFFFFF" /></View>
              <Text style={[styles.brand, { color: palette.text }]}>Rehyn</Text>
            </View>
            <View style={styles.headerActions}>
              <Pressable testID="home-emergency-fast" accessibilityLabel="Stroke warning signs" onPress={() => router.push("/(tabs)/emergency" as never)} style={({ pressed }) => [styles.headerButton, { borderColor: palette.border, backgroundColor: palette.surface }, pressed && styles.pressed]}>
                <Ionicons name="warning-outline" size={20} color="#E44C36" />
                {isWide ? <Text style={[styles.headerButtonText, { color: palette.text }]}>Stroke warning signs</Text> : null}
              </Pressable>
              <Pressable testID="home-open-settings" accessibilityLabel="Settings" onPress={() => router.push("/settings" as never)} style={({ pressed }) => [styles.headerButton, { borderColor: palette.border, backgroundColor: palette.surface }, pressed && styles.pressed]}>
                <Ionicons name="settings-outline" size={21} color={palette.text} />
                {isWide ? <Text style={[styles.headerButtonText, { color: palette.text }]}>Settings</Text> : null}
              </Pressable>
              <Pressable testID="home-open-profile" accessibilityLabel="Profile" onPress={() => router.push("/profile" as never)} style={({ pressed }) => [styles.avatar, { backgroundColor: palette.soft }, pressed && styles.pressed]}>
                <Text style={[styles.avatarText, { color: palette.text }]}>{greetName.slice(0, 1).toUpperCase()}</Text>
              </Pressable>
            </View>
          </View>

          {loading ? (
            <View style={styles.loadingState}><ActivityIndicator size="large" color={colors.brandPrimary} /></View>
          ) : (
            <>
              <View style={[styles.welcomeRow, !isWide && styles.welcomeRowCompact]}>
                <View style={styles.welcomeCopy}>
                  <Text style={[styles.welcomeTitle, { color: palette.text }]}>{greeting}, {greetName}</Text>
                  <Text style={[styles.goalLine, { color: palette.muted }]} testID="home-goal-line">Working towards your goal: <Text style={styles.goalStrong}>{displayGoal}</Text></Text>
                  <Text style={[styles.dateLine, { color: palette.muted }]}>{todayLabel}</Text>
                </View>
                <View style={[styles.pointsBadge, { backgroundColor: palette.soft }]} testID="home-points-badge">
                  <Ionicons name="ribbon-outline" size={28} color="#276C47" />
                  <Text style={[styles.pointsValue, { color: palette.text }]}>{rewards?.points ?? 0}</Text>
                  <Text style={styles.pointsLabel}>points</Text>
                </View>
              </View>

              <View style={styles.sectionHeadingRow}>
                <Text style={[styles.sectionTitle, { color: palette.text }]}>Your day</Text>
                <Text style={[styles.sectionSubtitle, { color: palette.muted }]}>One step at a time.</Text>
              </View>

              <View style={[styles.dayBoard, { backgroundColor: palette.surface, borderColor: palette.border }, !isWide && styles.dayBoardCompact]} testID="home-your-day">
                {isWide ? <View style={styles.dayConnector} /> : null}
                <DayStep
                  icon={checkIn.status === "not_checked_in" ? "sunny-outline" : "checkmark"}
                  title="Check in"
                  active={checkIn.status !== "not_checked_in"}
                  badge={checkIn.status === "not_checked_in" ? <StatusPill icon="ellipse-outline" label="Ready" tone="grey" /> : <StatusPill icon="checkmark-circle-outline" label={checkIn.status === "complete" ? "Complete" : "Checked in"} />}
                  description={checkIn.status === "not_checked_in" ? "Start today's recovery plan." : checkIn.status === "complete" ? "Today's plan is complete." : "Daily check-in complete."}
                  button={checkIn.status === "not_checked_in" ? { label: checkingIn ? "Checking in..." : "Check in", icon: "hand-right-outline", onPress: checkInForToday, testID: "daily-checkin-button" } : undefined}
                />
                <DayStep
                  icon={isInitialAssessment ? "clipboard-outline" : primaryComplete ? "checkmark" : "fitness-outline"}
                  title={primaryTitle}
                  active
                  badge={<StatusPill icon={primaryComplete ? "checkmark-circle-outline" : "ellipse-outline"} label={primaryComplete ? "Complete" : "In progress"} />}
                  description={primaryDescription}
                  progress={activeExerciseIds.length ? { completed: completedExerciseIds.length, total: activeExerciseIds.length } : undefined}
                  button={{ label: primaryButton.label, icon: "arrow-forward-circle-outline", onPress: () => primaryButton.destination === "rehab_plan" ? openExercisePlan() : openDestination(primaryButton.destination), primary: true, testID: "home-primary-action" }}
                />
                <DayStep
                  icon={isInitialAssessment || walkingOutstanding ? "videocam-outline" : carePlan?.survey?.due ? "chatbubble-ellipses-outline" : "calendar-outline"}
                  title={isInitialAssessment ? "Walking observation" : walkingOutstanding ? "Walking video" : carePlan?.survey?.due ? "Short check-in" : "Next assessment"}
                  active={Boolean(initialWalkingAssigned || carePlan?.survey?.due || followUpDue)}
                  badge={isInitialAssessment
                    ? initialWalkingAssigned
                      ? <StatusPill icon="checkmark-circle-outline" label="Selected if safe" />
                      : <StatusPill icon="remove-circle-outline" label="Not assigned" tone="grey" />
                    : walkingOutstanding
                      ? <StatusPill icon="people-circle-outline" label="When a helper is available" tone="grey" />
                      : carePlan?.survey?.due
                        ? <StatusPill icon="time-outline" label="Due" tone="amber" />
                        : <StatusPill icon="calendar-outline" label={assessmentDueLabel || "Scheduled"} tone="grey" />}
                  description={isInitialAssessment
                    ? initialWalkingAssigned
                      ? "Included because your readiness answers indicate walking can be observed safely."
                      : "Not included because your readiness answers did not support a walking task."
                    : walkingOutstanding
                      ? "Record the walking video so your plan can cover that area."
                      : carePlan?.survey?.due
                        ? "A few short questions help Alira adjust your plan."
                        : assessmentDueLabel ? `Your next meaningful progress check is ${assessmentDueLabel}.` : "Alira will schedule this when enough recovery time has passed."}
                  button={isInitialAssessment
                    ? undefined
                    : walkingOutstanding
                      ? { label: "Record later", icon: "camera-outline", onPress: () => startNextSession(missingTaskIds.length ? missingTaskIds : ["L6"]), testID: "home-walking-action" }
                      : carePlan?.survey?.due
                        ? { label: "Start check-in", icon: "chatbubble-outline", onPress: () => setShowSurveyPreface(true), testID: "home-survey-action" }
                        : followUpDue
                          ? { label: "Start assessment", icon: "clipboard-outline", onPress: () => startNextSession(), testID: "home-assessment-action" }
                          : undefined}
                />
              </View>

              <View style={styles.recoveryHeader}>
                <Text style={[styles.recoveryTitle, { color: palette.text }]}>Your recovery at a glance</Text>
              </View>
              <View style={[styles.recoveryBoard, { backgroundColor: palette.surface, borderColor: palette.border }, !isWide && styles.recoveryBoardCompact]} testID="home-recovery-glance">
                {trends.map((trend, index) => (
                  <View key={trend.id} style={[styles.trendCard, isWide && index > 0 && { borderLeftWidth: 1, borderLeftColor: palette.border }]} testID={`home-trend-${trend.id}`}>
                    <View style={styles.trendHeader}>
                      <View style={[styles.trendIcon, { backgroundColor: palette.soft }]}><Ionicons name={trend.icon} size={28} color="#176642" /></View>
                      <View style={styles.trendCopy}>
                        <Text style={[styles.trendTitle, { color: palette.text }]}>{trend.label}</Text>
                        <Text style={[styles.trendMessage, { color: palette.muted }]}>{trend.message}</Text>
                      </View>
                    </View>
                    <MiniTrendChart values={trend.values} />
                    {trend.values.length ? (
                      <View style={styles.trendDates}>
                        <Text style={[styles.trendDate, { color: palette.muted }]}>{formatShortDate(trend.dates[0])}</Text>
                        <Text style={[styles.trendDate, { color: palette.muted }]}>{formatShortDate(trend.dates[trend.dates.length - 1])}</Text>
                      </View>
                    ) : null}
                  </View>
                ))}
              </View>
              <Pressable testID="home-see-full-progress" onPress={() => router.push("/progress" as never)} style={({ pressed }) => [styles.progressLink, pressed && styles.pressed]}>
                <Text style={styles.progressLinkText}>See full progress</Text>
                <Ionicons name="chevron-forward" size={18} color="#0B653A" />
              </Pressable>

              <View style={[styles.weekPanel, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="home-week-panel">
                <View style={styles.weekSummaryRow}>
                  <View style={[styles.weekIcon, { backgroundColor: palette.soft }]}><Ionicons name="calendar-outline" size={21} color="#176642" /></View>
                  <Text style={[styles.weekTitle, { color: palette.text }]}>Your week</Text>
                  <Text style={[styles.weekSummary, { color: palette.muted }]}>
                    {checkIn.status === "complete" ? "Daily plan complete" : checkIn.status === "in_progress" ? "Daily check-in complete" : "Check in when ready"}
                    {isInitialAssessment ? "   •   Initial assessment ready" : assessmentDueLabel ? `   •   Next assessment ${assessmentDueLabel}` : ""}
                  </Text>
                  <Pressable testID="home-week-toggle" onPress={() => setShowWeek((value) => !value)} style={styles.weekToggle}>
                    <Text style={[styles.weekToggleText, { color: palette.text }]}>{showWeek ? "Hide details" : "Show details"}</Text>
                    <Ionicons name={showWeek ? "chevron-up" : "chevron-down"} size={20} color={palette.text} />
                  </Pressable>
                </View>
                {showWeek ? (
                  <View style={[styles.weekDetails, { borderTopColor: palette.border }]}>
                    <View style={styles.weekDays}>
                      {recentCheckIns.length ? recentCheckIns.map((day) => (
                        <View key={day.date} style={[styles.weekDay, { backgroundColor: day.status === "complete" ? "#E5F2E9" : palette.soft }]}>
                          <Ionicons name={day.status === "complete" ? "checkmark-circle" : "ellipse-outline"} size={17} color={day.status === "complete" ? "#1A7045" : palette.muted} />
                          <Text style={[styles.weekDayText, { color: palette.text }]}>{formatShortDate(day.date)}</Text>
                        </View>
                      )) : <Text style={[styles.weekEmpty, { color: palette.muted }]}>Your check-in history will appear here.</Text>}
                    </View>
                    <View style={styles.weekFacts}>
                      <Text style={[styles.weekFact, { color: palette.muted }]}>{completedExerciseIds.length} of {activeExerciseIds.length || 0} planned activities complete today</Text>
                      <Text style={[styles.weekFact, { color: palette.muted }]}>Survey {carePlan?.survey?.due ? "due now" : surveyDueLabel ? `scheduled ${surveyDueLabel}` : "scheduled by Alira when needed"}</Text>
                    </View>
                  </View>
                ) : null}
              </View>
            </>
          )}
        </View>
      </ScrollView>
      <SurveyPrefaceModal visible={showSurveyPreface} onBegin={openSurveyChat} onClose={() => setShowSurveyPreface(false)} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  page: { paddingHorizontal: spacing.md, paddingBottom: 112 },
  inner: { width: "100%", maxWidth: 1420, alignSelf: "center" },
  header: { minHeight: 72, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  brandIcon: { width: 43, height: 43, borderRadius: 8, backgroundColor: "#07593E", alignItems: "center", justifyContent: "center" },
  brand: { fontSize: 25, lineHeight: 31, fontWeight: "900" },
  headerActions: { flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: spacing.sm, flexShrink: 1 },
  headerButton: { minHeight: 46, minWidth: 46, borderRadius: radius.md, borderWidth: 1, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 9 },
  headerButtonText: { fontSize: 14, fontWeight: "800" },
  avatar: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center" },
  avatarText: { fontSize: 18, fontWeight: "900" },
  pressed: { opacity: 0.68 },
  loadingState: { minHeight: 560, alignItems: "center", justifyContent: "center" },
  welcomeRow: { minHeight: 174, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.xl, paddingVertical: spacing.md },
  welcomeRowCompact: { minHeight: 0, alignItems: "flex-start", gap: spacing.md },
  welcomeCopy: { flex: 1, minWidth: 0 },
  welcomeTitle: { fontSize: 31, lineHeight: 38, fontWeight: "900" },
  goalLine: { marginTop: 7, fontSize: 16, lineHeight: 23, fontWeight: "500" },
  goalStrong: { color: "#0A5D3A", fontWeight: "900" },
  dateLine: { marginTop: 9, fontSize: 15, lineHeight: 21 },
  pointsBadge: { width: 138, height: 138, borderRadius: 69, borderWidth: 1.5, borderColor: "#2B8A53", alignItems: "center", justifyContent: "center" },
  pointsValue: { marginTop: -2, fontSize: 44, lineHeight: 48, fontWeight: "900" },
  pointsLabel: { fontSize: 16, lineHeight: 21, fontWeight: "900", color: "#0B653A" },
  sectionHeadingRow: { marginTop: spacing.xs, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 29, lineHeight: 35, fontWeight: "900" },
  sectionSubtitle: { marginTop: 2, fontSize: 15, lineHeight: 21 },
  dayBoard: { minHeight: 318, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.md, flexDirection: "row", position: "relative", overflow: "hidden" },
  dayBoardCompact: { flexDirection: "column", gap: spacing.lg },
  dayConnector: { position: "absolute", left: "16%", right: "16%", top: 61, height: 3, backgroundColor: "#15803D" },
  dayStep: { flex: 1, minWidth: 0, alignItems: "center", paddingHorizontal: spacing.md, zIndex: 1 },
  dayStepIcon: { width: 62, height: 62, borderRadius: 31, borderWidth: 1.5, borderColor: "#667169", backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  dayStepIconActive: { borderWidth: 3, borderColor: "#0B7A3A" },
  dayStepTitle: { marginTop: 12, fontSize: 19, lineHeight: 24, fontWeight: "900", color: "#134D37", textAlign: "center" },
  statusPill: { minHeight: 31, marginTop: 8, paddingHorizontal: 11, borderRadius: radius.pill, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 },
  statusPillText: { fontSize: 12, lineHeight: 17, fontWeight: "700" },
  dayStepDescription: { minHeight: 38, marginTop: 12, maxWidth: 310, fontSize: 13, lineHeight: 19, color: "#35433B", textAlign: "center" },
  stepProgressWrap: { width: "100%", maxWidth: 330, marginTop: 4, alignItems: "center" },
  stepProgressLabel: { fontSize: 17, lineHeight: 23, fontWeight: "900", color: "#155D3B", textAlign: "center" },
  stepProgressTrack: { width: "100%", height: 13, marginTop: 10, borderRadius: 7, backgroundColor: "#DDE6DF", overflow: "hidden" },
  stepProgressFill: { height: "100%", borderRadius: 7, backgroundColor: "#0B7B3A" },
  stepButton: { minHeight: 46, minWidth: 170, maxWidth: 330, marginTop: 16, borderRadius: radius.md, paddingHorizontal: 18, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 9 },
  stepButtonPrimary: { width: "100%", backgroundColor: "#05603F" },
  stepButtonSecondary: { borderWidth: 1.5, borderColor: "#137040", backgroundColor: "#FFFFFF" },
  stepButtonText: { fontSize: 14, lineHeight: 20, fontWeight: "900" },
  stepButtonTextPrimary: { color: "#FFFFFF" },
  stepButtonTextSecondary: { color: "#145C3B" },
  recoveryHeader: { marginTop: 22, marginBottom: spacing.sm },
  recoveryTitle: { fontSize: 20, lineHeight: 26, fontWeight: "900" },
  recoveryBoard: { minHeight: 190, borderWidth: 1, borderRadius: radius.md, paddingVertical: spacing.md, flexDirection: "row" },
  recoveryBoardCompact: { flexDirection: "column", gap: spacing.md },
  trendCard: { flex: 1, minWidth: 0, paddingHorizontal: spacing.lg },
  trendHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  trendIcon: { width: 54, height: 54, borderRadius: 27, alignItems: "center", justifyContent: "center" },
  trendCopy: { flex: 1, minWidth: 0 },
  trendTitle: { fontSize: 18, lineHeight: 23, fontWeight: "900" },
  trendMessage: { marginTop: 2, fontSize: 13, lineHeight: 18 },
  emptyChart: { height: 84, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 },
  emptyChartText: { fontSize: 12, color: "#7B887F", fontWeight: "700" },
  trendDates: { marginTop: -2, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  trendDate: { fontSize: 11, lineHeight: 16, fontWeight: "600" },
  progressLink: { minHeight: 42, alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 3 },
  progressLinkText: { fontSize: 14, lineHeight: 20, fontWeight: "900", color: "#0B653A" },
  weekPanel: { marginTop: spacing.sm, borderWidth: 1, borderRadius: radius.md, overflow: "hidden" },
  weekSummaryRow: { minHeight: 66, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  weekIcon: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center" },
  weekTitle: { fontSize: 17, lineHeight: 22, fontWeight: "900" },
  weekSummary: { flex: 1, minWidth: 0, marginLeft: spacing.md, fontSize: 13, lineHeight: 19 },
  weekToggle: { minHeight: 42, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, paddingHorizontal: spacing.sm },
  weekToggleText: { fontSize: 13, fontWeight: "800" },
  weekDetails: { borderTopWidth: 1, padding: spacing.md, gap: spacing.md },
  weekDays: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  weekDay: { minHeight: 34, paddingHorizontal: 10, borderRadius: radius.pill, flexDirection: "row", alignItems: "center", gap: 5 },
  weekDayText: { fontSize: 12, fontWeight: "800" },
  weekEmpty: { fontSize: 13, lineHeight: 19 },
  weekFacts: { gap: 4 },
  weekFact: { fontSize: 13, lineHeight: 19, fontWeight: "600" },
});
