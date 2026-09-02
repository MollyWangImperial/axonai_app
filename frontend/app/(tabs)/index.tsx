import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Animated,
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
import Svg, { Circle, G, Line, Polyline, Text as SvgText } from "react-native-svg";
import * as Haptics from "expo-haptics";

import { Assessment, fetchHistory } from "@/src/api";
import {
  authedFetch,
  cacheAssessmentActivity,
  cacheDailyCheckInActivity,
  getCachedPatientActivity,
  getCachedUser,
  preferredNameKey,
} from "@/src/auth";
import { PointsCelebration, PointsCelebrationEvent, celebrationEvent } from "@/src/components/PointsCelebration";
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
  requires_helper?: boolean;
  helper_confirmation_required?: boolean;
};

type HomeCarePlan = {
  account_state?: {
    has_completed_initial_assessment?: boolean;
    initial_assessment_completed_at?: string | null;
    latest_assessment_id?: string | null;
  };
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
  date: string;
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
  initialAssessmentCompletedAt: string;
  latestAssessmentId: string;
  latestAssessmentCreatedAt: string;
};

type TrendDefinition = {
  id: "reach" | "hand" | "walking";
  label: string;
  icon: React.ComponentProps<typeof Ionicons>["name"];
  values: number[];
  dates: string[];
  message: string;
};

const EMPTY_CHECK_IN: DailyCheckInState = { date: "", status: "not_checked_in", days: [] };
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
  if (["some_movement", "help_only", "no_movement", "not_sure"].includes(arm)) goals.push("Eating & dressing");
  if (["some_finger_movement", "very_little_movement", "no_movement", "not_sure"].includes(hand)) goals.push("Grooming & hand tasks");
  if (["person_assist", "wheelchair", "unable_walk", "not_cleared", "unsure"].includes(mobility)) goals.push("Safer mobility");
  return goals.join(" • ");
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

const AnimatedCircle = Animated.createAnimatedComponent(Circle);

function MiniTrendChart({ values, shiny }: { values: number[]; shiny?: boolean }) {
  const { palette } = useDisplayPreferences();
  const width = 300;
  const height = 92;
  const axisX = 30; // left gutter reserved for the y-axis value labels
  const padX = 12;
  const padY = 16;
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!shiny || values.length === 0) return;
    // Once today's assessment is complete the points shimmer gently so the
    // latest progress feels alive rather than static.
    const loop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 850, useNativeDriver: false }),
        Animated.timing(pulse, { toValue: 0, duration: 850, useNativeDriver: false }),
      ]),
    );
    loop.start();
    return () => loop.stop();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shiny, values.length]);

  if (values.length === 0) {
    return (
      <View style={styles.emptyChart}>
        <Ionicons name="analytics-outline" size={24} color={palette.muted} />
        <Text style={[styles.emptyChartText, { color: palette.muted }]}>No measurements yet</Text>
      </View>
    );
  }
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const spread = Math.max(12, maximum - minimum);
  const low = minimum - (spread - (maximum - minimum)) / 2;
  const high = low + spread;
  const plotLeft = axisX + padX;
  const plotY = (value: number) => height - padY - ((value - low) / spread) * (height - padY * 2);
  const points = values.map((value, index) => {
    const x = values.length === 1
      ? plotLeft + (width - plotLeft - padX) / 2
      : plotLeft + (index * (width - plotLeft - padX)) / (values.length - 1);
    return { x, y: plotY(value), value };
  });
  const last = points[points.length - 1];
  const axisTicks = [high, (low + high) / 2, low];
  const haloRadius = pulse.interpolate({ inputRange: [0, 1], outputRange: [5.5, 12] });
  const lastHaloRadius = pulse.interpolate({ inputRange: [0, 1], outputRange: [8, 17] });
  const haloOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.38, 0.04] });
  const sparkleOpacity = pulse.interpolate({ inputRange: [0, 1], outputRange: [0.2, 0.95] });
  return (
    <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} testID="home-trend-chart">
      <Line x1={axisX} y1={padY - 6} x2={axisX} y2={height - padY + 6} stroke={palette.border} strokeWidth={1} />
      {axisTicks.map((tick) => (
        <G key={`tick-${tick}`}>
          <Line x1={axisX} y1={plotY(tick)} x2={width - padX} y2={plotY(tick)} stroke={palette.border} strokeWidth={1} strokeDasharray="4 5" />
          <SvgText x={axisX - 5} y={plotY(tick) + 3.5} fontSize={9} fontWeight="600" fill={palette.muted} textAnchor="end" testID="home-trend-axis-label">
            {Math.round(tick)}
          </SvgText>
        </G>
      ))}
      {points.length > 1 ? (
        <Polyline points={points.map((point) => `${point.x},${point.y}`).join(" ")} fill="none" stroke={palette.brand} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
      ) : null}
      {!shiny ? (
        <G>
          <Circle cx={last.x} cy={last.y} r={14} fill="#5AC77D" opacity={0.12} />
          <Circle cx={last.x} cy={last.y} r={9} fill="#48BE70" opacity={0.18} />
        </G>
      ) : null}
      {points.map((point, index) => {
        const isLast = index === points.length - 1;
        const labelY = point.y - 9 < 9 ? point.y + 17 : point.y - 9;
        return (
          <G key={`point-${index}`}>
            {shiny ? (
              <AnimatedCircle cx={point.x} cy={point.y} r={isLast ? lastHaloRadius : haloRadius} fill={isLast ? "#48BE70" : "#5AC77D"} opacity={haloOpacity} />
            ) : null}
            <Circle cx={point.x} cy={point.y} r={isLast ? 4.5 : 3.4} fill={palette.brand} />
            {shiny ? (
              <AnimatedCircle cx={point.x + 5} cy={point.y - 6} r={1.6} fill="#7FE0A4" opacity={sparkleOpacity} />
            ) : null}
            <SvgText x={point.x} y={labelY} fontSize={10} fontWeight="700" fill={palette.brand} textAnchor="middle" testID="home-trend-point-value">
              {Math.round(point.value)}
            </SvgText>
          </G>
        );
      })}
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
  const { palette, preferences } = useDisplayPreferences();
  const percentage = progress?.total ? Math.min(100, Math.round((progress.completed / progress.total) * 100)) : 0;
  const titleColor = preferences.darkMode ? palette.brand : palette.text;
  return (
    <View style={styles.dayStep}>
      <View style={[styles.dayStepIcon, active && styles.dayStepIconActive]}>
        <Ionicons name={icon} size={28} color={active ? palette.brand : palette.muted} />
      </View>
      <Text style={[styles.dayStepTitle, { color: titleColor }]}>{title}</Text>
      {badge}
      <Text style={[styles.dayStepDescription, { color: palette.muted }]}>{description}</Text>
      {progress ? (
        <View style={styles.stepProgressWrap}>
          <Text style={[styles.stepProgressLabel, { color: palette.brand }]}>{progress.completed} of {progress.total} activities complete</Text>
          <View style={[styles.stepProgressTrack, { backgroundColor: palette.soft }]}><View style={[styles.stepProgressFill, { width: `${percentage}%`, backgroundColor: palette.brand }]} /></View>
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
  const [checkIn, setCheckIn] = useState<DailyCheckInState>(cached?.checkIn ?? EMPTY_CHECK_IN);
  const [rewards, setRewards] = useState<RewardsSummary | null>(cached?.rewards ?? null);
  const [progress, setProgress] = useState<ProgressSummary>(cached?.progress ?? EMPTY_PROGRESS);
  const [initialAssessmentCompletedAt, setInitialAssessmentCompletedAt] = useState(cached?.initialAssessmentCompletedAt ?? "");
  const [latestAssessmentId, setLatestAssessmentId] = useState(cached?.latestAssessmentId ?? "");
  const [latestAssessmentCreatedAt, setLatestAssessmentCreatedAt] = useState(cached?.latestAssessmentCreatedAt ?? "");
  const [loading, setLoading] = useState(!cached);
  const [checkingIn, setCheckingIn] = useState(false);
  const [showWeek, setShowWeek] = useState(false);
  const [showSurveyPreface, setShowSurveyPreface] = useState(false);
  const [celebration, setCelebration] = useState<PointsCelebrationEvent | null>(null);

  const load = useCallback(async () => {
    if (!getScreenCache<HomeScreenCache>("home")) setLoading(true);
    const user = await getCachedUser();
    const requestedDate = localDateString();
    // Rebind a cached account before parallel state requests. Without this,
    // an expired backend fallback session can make history look empty during
    // the same render in which another request is restoring the account.
    if (user?.id) await authedFetch("/api/users/consent").catch(() => null);
    const cachedActivity = user?.id ? await getCachedPatientActivity(user.id) : {};
    const [assessments, preferredName, carePlanPayload, onboarding, checkInPayload, rewardsPayload, progressPayload] = await Promise.all([
      fetchHistory().catch(() => []),
      user?.id ? storage.getItem(preferredNameKey(user.id), "") : Promise.resolve(""),
      authedFetch("/api/alira/care-plan").then(async (response) => response.ok ? response.json() : null).catch(() => null),
      authedFetch("/api/users/onboarding").then(async (response) => response.ok ? response.json() : null).catch(() => null),
      authedFetch(`/api/users/daily-checkin?date=${encodeURIComponent(requestedDate)}`).then(async (response) => response.ok ? response.json() : null).catch(() => null),
      authedFetch("/api/users/rewards").then(async (response) => response.ok ? response.json() : null).catch(() => null),
      authedFetch("/api/progress/summary").then(async (response) => response.ok ? response.json() : null).catch(() => null),
    ]);
    const nextHistory = Array.isArray(assessments) ? assessments : [];
    const nextName = preferredName || user?.name?.split(" ")[0] || "there";
    const nextOwnGoal = String(onboarding?.profile?.primary_goal || "").trim();
    const nextDailyGoal = deriveFunctionalGoal(onboarding?.profile) || nextOwnGoal;
    const serverCheckIn = checkInPayload
      ? { date: checkInPayload.date || requestedDate, status: checkInPayload.status || "not_checked_in", days: checkInPayload.days || [] }
      : EMPTY_CHECK_IN;
    const cachedCheckInStatus = cachedActivity.daily_check_ins?.[requestedDate];
    const nextCheckIn: DailyCheckInState = serverCheckIn.status !== "not_checked_in" || !cachedCheckInStatus
      ? serverCheckIn
      : {
          date: requestedDate,
          status: cachedCheckInStatus,
          days: [
            ...serverCheckIn.days.filter((day: { date: string }) => day.date !== requestedDate),
            { date: requestedDate, status: cachedCheckInStatus },
          ].sort((a: { date: string }, b: { date: string }) => a.date.localeCompare(b.date)),
        };
    if (user?.id && nextCheckIn.status !== "not_checked_in") {
      await cacheDailyCheckInActivity(user.id, requestedDate, nextCheckIn.status);
      if (serverCheckIn.status === "not_checked_in") {
        const repairPath = nextCheckIn.status === "complete" ? "/api/users/daily-checkin/complete" : "/api/users/daily-checkin";
        void authedFetch(repairPath, { method: "POST", body: JSON.stringify({ date: requestedDate }) });
      }
    }
    const newestAssessment = nextHistory[0];
    const nextInitialAssessmentCompletedAt = String(
      carePlanPayload?.account_state?.initial_assessment_completed_at
      || (nextHistory.length ? nextHistory[nextHistory.length - 1]?.created_at : "")
      || cachedActivity.initial_assessment_completed_at
      || "",
    );
    const nextLatestAssessmentId = String(
      newestAssessment?.id
      || carePlanPayload?.account_state?.latest_assessment_id
      || cachedActivity.latest_assessment_id
      || "",
    );
    const nextLatestAssessmentCreatedAt = String(
      newestAssessment?.created_at
      || cachedActivity.latest_assessment_created_at
      || "",
    );
    if (user?.id && nextLatestAssessmentId) {
      await cacheAssessmentActivity(
        user.id,
        nextLatestAssessmentId,
        nextLatestAssessmentCreatedAt,
        Boolean(nextInitialAssessmentCompletedAt || nextHistory.length),
      );
    }
    const nextProgress = progressPayload?.assessments ? progressPayload : EMPTY_PROGRESS;
    // Returning to Home after earning points (finishing the assessment or an
    // exercise elsewhere) pops a congratulation for the newly earned points;
    // the day board itself refreshes automatically on every focus.
    const previousHome = getScreenCache<HomeScreenCache>("home");
    const nextPoints = Number(rewardsPayload?.points ?? 0);
    const lastCelebratedPoints = getScreenCache<number>("celebrated-points");
    if (lastCelebratedPoints == null) {
      setScreenCache<number>("celebrated-points", nextPoints);
    } else if (nextPoints > lastCelebratedPoints) {
      const previousIds = new Set((previousHome?.history || []).map((item) => item.id));
      const finishedAssessmentToday = nextHistory.some(
        (item) => !previousIds.has(item.id) && String(item.created_at || "").slice(0, 10) === localDateString(),
      );
      setCelebration(celebrationEvent(
        nextPoints - lastCelebratedPoints,
        finishedAssessmentToday ? "Assessment complete - amazing work!" : "Points earned - keep it up!",
      ));
      setScreenCache<number>("celebrated-points", nextPoints);
    }
    setHistory(nextHistory);
    setGreetName(nextName);
    setCarePlan(carePlanPayload);
    setDailyGoal(nextDailyGoal);
    setCheckIn(nextCheckIn);
    setRewards(rewardsPayload);
    setProgress(nextProgress);
    setInitialAssessmentCompletedAt(nextInitialAssessmentCompletedAt);
    setLatestAssessmentId(nextLatestAssessmentId);
    setLatestAssessmentCreatedAt(nextLatestAssessmentCreatedAt);
    setScreenCache<HomeScreenCache>("home", {
      history: nextHistory,
      greetName: nextName,
      carePlan: carePlanPayload,
      dailyGoal: nextDailyGoal,
      ownGoal: nextOwnGoal,
      checkIn: nextCheckIn,
      rewards: rewardsPayload,
      progress: nextProgress,
      initialAssessmentCompletedAt: nextInitialAssessmentCompletedAt,
      latestAssessmentId: nextLatestAssessmentId,
      latestAssessmentCreatedAt: nextLatestAssessmentCreatedAt,
    });
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  useEffect(() => {
    if (carePlan) void loadSettings().then((settings) => rescheduleReminders(settings, carePlan));
  }, [carePlan]);

  const latest = history[0];
  const hasInitialAssessment = Boolean(
    carePlan?.account_state?.has_completed_initial_assessment
    || history.length > 0
    || initialAssessmentCompletedAt,
  );
  const isInitialAssessment = !hasInitialAssessment;
  const carePlanAssessment = carePlan?.assessment || null;
  const followUpDue = Boolean(carePlanAssessment?.due && carePlanAssessment?.can_start);
  const nextStep = carePlan?.next_step || null;
  const savedExerciseIds = (latest?.rehab_plan || []).map((exercise) => exercise.id).filter(Boolean);
  const carePlanExerciseIds = carePlan?.daily_monitoring?.active_exercise_ids?.length
    ? carePlan.daily_monitoring.active_exercise_ids
    : carePlan?.exercise_plan?.approved_exercise_ids || [];
  const activeExerciseIds = carePlanExerciseIds.length ? carePlanExerciseIds : savedExerciseIds;
  const completedExerciseIds = carePlan?.daily_monitoring?.completed_exercise_ids_today || [];
  const remainingExerciseIds = carePlan?.daily_monitoring?.remaining_exercise_ids_today || nextStep?.remaining_exercise_ids || [];
  const missingDomains = carePlanAssessment?.missing_domains || nextStep?.missing_domains || [];
  const missingTaskIds = carePlanAssessment?.missing_task_ids || [];
  const walkingOutstanding = missingDomains.includes("lower_limb") || missingTaskIds.includes("L6");
  // Keep the Home summary scannable while the underlying survey retains the
  // patient's full functional detail.
  const displayGoal = dailyGoal || "building everyday independence";
  const trends = useMemo(() => buildTrends(progress), [progress]);
  const assessmentDueLabel = formatShortDate(carePlanAssessment?.due_at);
  const surveyDueLabel = formatShortDate(carePlan?.survey?.due_at);
  const hour = new Date().getHours();
  const greeting = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const todayLabel = new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const recentCheckIns = checkIn.days.slice(-7);
  const todayIso = localDateString();
  const checkedInToday = checkIn.date === todayIso && checkIn.status !== "not_checked_in";
  const todayCheckInStatus = checkedInToday ? checkIn.status : "not_checked_in";

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
        if (latest?.id || latestAssessmentId) router.push({ pathname: "/rehab-plan" as never, params: { id: latest?.id || latestAssessmentId } });
        else router.push("/(tabs)/journey" as never);
        return;
      case "caregiver_plan": router.push("/caregiver-plan" as never); return;
      case "survey_report": router.push("/survey-report" as never); return;
      case "emergency": router.push("/(tabs)/emergency" as never); return;
      case "alira": router.push({ pathname: "/(tabs)/chat" as never, params: { prompt: "Please guide me through my next safe step." } }); return;
      case "progress": router.push("/progress" as never); return;
      default: router.push("/progress" as never);
    }
  }, [latest, latestAssessmentId, router, startNextSession]);

  const checkInForToday = useCallback(async () => {
    if (checkingIn || checkedInToday) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    setCheckingIn(true);
    const response = await authedFetch("/api/users/daily-checkin", {
      method: "POST",
      body: JSON.stringify({ date: todayIso }),
    }).catch(() => null);
    if (response?.ok) {
      const payload = await response.json().catch(() => null);
      if (payload) {
        const status = payload.status === "complete" ? "complete" : "in_progress";
        setCheckIn({ date: payload.date || todayIso, status, days: payload.days || [] });
        const user = await getCachedUser();
        if (user?.id) await cacheDailyCheckInActivity(user.id, todayIso, status);
      }
      // Checking in earns points (2 per day): celebrate briefly, then the
      // toast fades out on its own, and the badge refreshes right away.
      setCelebration(celebrationEvent(2, "Checked in - great start to today!"));
      const rewardsResponse = await authedFetch("/api/users/rewards").catch(() => null);
      if (rewardsResponse?.ok) {
        const rewardsPayload = await rewardsResponse.json().catch(() => null);
        if (rewardsPayload) {
          setRewards(rewardsPayload);
          setScreenCache<number>("celebrated-points", Number(rewardsPayload.points ?? 0));
        }
      }
    }
    setCheckingIn(false);
  }, [checkedInToday, checkingIn, todayIso]);

  const openExercisePlan = () => {
    if (nextStep?.destination === "caregiver_plan") openDestination("caregiver_plan");
    else if (latest?.id || latestAssessmentId) router.push({ pathname: "/rehab-plan" as never, params: { id: latest?.id || latestAssessmentId } });
    else openDestination(nextStep?.destination);
  };

  // Once today's assessment is finished, the middle step celebrates it and
  // the third step becomes today's exercises.
  const assessmentCompletedToday = Boolean(
    (latest?.created_at || latestAssessmentCreatedAt)
    && String(latest?.created_at || latestAssessmentCreatedAt).slice(0, 10) === localDateString(),
  );

  // Progressive disclosure: the next step is revealed by checking in, and the
  // third step only after the initial assessment exists.
  const stepTwoRevealed = checkedInToday;
  const stepThreeRevealed = checkedInToday && (assessmentCompletedToday || !isInitialAssessment);

  const primaryTitle = isInitialAssessment
    ? "Initial assessment"
    : nextStep?.destination === "caregiver_plan"
      ? "Today's routines"
      : activeExerciseIds.length
        ? "Today's exercises"
        : nextStep?.title || "Your next step";
  const primaryDescription = isInitialAssessment
    ? carePlanAssessment?.requires_helper
      ? "Alira selected suitable tasks. Please start with a carer or family member nearby."
      : "Alira selected suitable tasks from your readiness answers."
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
                  <Text style={[styles.goalLine, { color: palette.muted }]} testID="home-goal-line">Your goal: <Text style={[styles.goalStrong, { color: palette.brand }]}>{displayGoal}</Text></Text>
                  <Text style={[styles.dateLine, { color: palette.muted }]}>{todayLabel}</Text>
                </View>
                <View style={[styles.pointsBadge, { backgroundColor: palette.soft, borderColor: palette.brand }]} testID="home-points-badge">
                  <Ionicons name="ribbon-outline" size={28} color={palette.brand} />
                  <Text style={[styles.pointsValue, { color: palette.text }]}>{rewards?.points ?? 0}</Text>
                  <Text style={[styles.pointsLabel, { color: palette.brand }]}>points</Text>
                </View>
              </View>

              <View style={styles.sectionHeadingRow}>
                <Text style={[styles.sectionTitle, { color: palette.text }]}>Your day</Text>
                <Text style={[styles.sectionSubtitle, { color: palette.muted }]}>One step at a time.</Text>
              </View>

              <View style={[styles.dayBoard, { backgroundColor: palette.surface, borderColor: palette.border }, !isWide && styles.dayBoardCompact]} testID="home-your-day">
                {isWide ? (
                  <>
                    <View style={[styles.dayConnectorSegment, styles.dayConnectorLeft, !checkedInToday && styles.dayConnectorInactive]} />
                    <View
                      testID="home-day-connector-right"
                      style={[
                        styles.dayConnectorSegment,
                        styles.dayConnectorRight,
                        !stepThreeRevealed && styles.dayConnectorInactive,
                      ]}
                    />
                  </>
                ) : null}
                <DayStep
                  icon={todayCheckInStatus === "not_checked_in" ? "sunny-outline" : "checkmark"}
                  title="Check in"
                  active={todayCheckInStatus !== "not_checked_in"}
                  badge={todayCheckInStatus === "not_checked_in" ? <StatusPill icon="ellipse-outline" label="Ready" tone="grey" /> : <StatusPill icon="checkmark-circle-outline" label={todayCheckInStatus === "complete" ? "Complete" : "Checked in"} />}
                  description={todayCheckInStatus === "not_checked_in" ? "Start today's recovery plan. Checking in earns 2 points." : todayCheckInStatus === "complete" ? "Today's plan is complete." : "Daily check-in complete. +2 points earned."}
                  button={todayCheckInStatus === "not_checked_in" ? { label: checkingIn ? "Checking in..." : "Check in", icon: "hand-right-outline", onPress: checkInForToday, testID: "daily-checkin-button" } : undefined}
                />
                {!stepTwoRevealed ? (
                  <DayStep
                    icon="lock-closed-outline"
                    title="Your next step"
                    badge={<StatusPill icon="lock-closed-outline" label="Locked" tone="grey" />}
                    description="Check in first to see today's next step."
                  />
                ) : (
                  <DayStep
                    icon={isInitialAssessment ? "clipboard-outline" : primaryComplete ? "checkmark" : "fitness-outline"}
                    title={primaryTitle}
                    active
                    badge={<StatusPill icon={primaryComplete ? "checkmark-circle-outline" : "ellipse-outline"} label={primaryComplete ? "Complete" : "In progress"} />}
                    description={primaryDescription}
                    progress={activeExerciseIds.length ? { completed: completedExerciseIds.length, total: activeExerciseIds.length } : undefined}
                    button={{ label: primaryButton.label, icon: "arrow-forward-circle-outline", onPress: () => primaryButton.destination === "rehab_plan" ? openExercisePlan() : openDestination(primaryButton.destination), primary: true, testID: "home-primary-action" }}
                  />
                )}
                {!stepThreeRevealed ? (
                  <DayStep
                    icon="lock-closed-outline"
                    title="Later today"
                    badge={<StatusPill icon="lock-closed-outline" label="Locked" tone="grey" />}
                    description={!checkedInToday
                      ? "Check in to unlock your day."
                      : "Complete the initial assessment to see what comes next."}
                  />
                ) : (
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
                )}
              </View>

              <View style={styles.recoveryHeader}>
                <Text style={[styles.recoveryTitle, { color: palette.text }]}>Your recovery at a glance</Text>
              </View>
              <View style={[styles.recoveryBoard, { backgroundColor: palette.surface, borderColor: palette.border }, !isWide && styles.recoveryBoardCompact]} testID="home-recovery-glance">
                {trends.map((trend, index) => (
                  <View key={trend.id} style={[styles.trendCard, isWide && index > 0 && { borderLeftWidth: 1, borderLeftColor: palette.border }]} testID={`home-trend-${trend.id}`}>
                    <View style={styles.trendHeader}>
                      <View style={[styles.trendIcon, { backgroundColor: palette.soft }]}><Ionicons name={trend.icon} size={28} color={palette.brand} /></View>
                      <View style={styles.trendCopy}>
                        <Text style={[styles.trendTitle, { color: palette.text }]}>{trend.label}</Text>
                        <Text style={[styles.trendMessage, { color: palette.muted }]}>{trend.message}</Text>
                      </View>
                    </View>
                    <MiniTrendChart values={trend.values} shiny={assessmentCompletedToday} />
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
                <Text style={[styles.progressLinkText, { color: palette.brand }]}>See full progress</Text>
                <Ionicons name="chevron-forward" size={18} color={palette.brand} />
              </Pressable>

              <View style={[styles.weekPanel, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="home-week-panel">
                <View style={styles.weekSummaryRow}>
                  <View style={[styles.weekIcon, { backgroundColor: palette.soft }]}><Ionicons name="calendar-outline" size={21} color={palette.brand} /></View>
                  <Text style={[styles.weekTitle, { color: palette.text }]}>Your week</Text>
                  <Text style={[styles.weekSummary, { color: palette.muted }]}>
                    {todayCheckInStatus === "complete" ? "Daily plan complete" : todayCheckInStatus === "in_progress" ? "Daily check-in complete" : "Check in when ready"}
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
      <PointsCelebration event={celebration} onDone={() => setCelebration(null)} />
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
  goalStrong: { fontWeight: "900" },
  dateLine: { marginTop: 9, fontSize: 15, lineHeight: 21 },
  pointsBadge: { width: 138, height: 138, borderRadius: 69, borderWidth: 1.5, borderColor: "#2B8A53", alignItems: "center", justifyContent: "center" },
  pointsValue: { marginTop: -2, fontSize: 44, lineHeight: 48, fontWeight: "900" },
  pointsLabel: { fontSize: 16, lineHeight: 21, fontWeight: "900" },
  sectionHeadingRow: { marginTop: spacing.xs, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 29, lineHeight: 35, fontWeight: "900" },
  sectionSubtitle: { marginTop: 2, fontSize: 15, lineHeight: 21 },
  dayBoard: { minHeight: 318, borderWidth: 1, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.md, flexDirection: "row", position: "relative", overflow: "hidden" },
  dayBoardCompact: { flexDirection: "column", gap: spacing.lg },
  dayConnectorSegment: { position: "absolute", top: 61, height: 3, backgroundColor: "#15803D" },
  dayConnectorLeft: { left: "16%", right: "50%" },
  dayConnectorRight: { left: "50%", right: "16%" },
  dayConnectorInactive: { backgroundColor: "#D4DDD7" },
  dayStep: { flex: 1, minWidth: 0, alignItems: "center", paddingHorizontal: spacing.md, zIndex: 1 },
  dayStepIcon: { width: 62, height: 62, borderRadius: 31, borderWidth: 1.5, borderColor: "#667169", backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  dayStepIconActive: { borderWidth: 3, borderColor: "#0B7A3A" },
  dayStepTitle: { marginTop: 12, fontSize: 19, lineHeight: 24, fontWeight: "900", textAlign: "center" },
  statusPill: { minHeight: 31, marginTop: 8, paddingHorizontal: 11, borderRadius: radius.pill, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 },
  statusPillText: { fontSize: 12, lineHeight: 17, fontWeight: "700" },
  dayStepDescription: { minHeight: 38, marginTop: 12, maxWidth: 310, fontSize: 13, lineHeight: 19, textAlign: "center" },
  stepProgressWrap: { width: "100%", maxWidth: 330, marginTop: 4, alignItems: "center" },
  stepProgressLabel: { fontSize: 17, lineHeight: 23, fontWeight: "900", textAlign: "center" },
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
  emptyChartText: { fontSize: 12, fontWeight: "700" },
  trendDates: { marginTop: -2, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  trendDate: { fontSize: 11, lineHeight: 16, fontWeight: "600" },
  progressLink: { minHeight: 42, alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 3 },
  progressLinkText: { fontSize: 14, lineHeight: 20, fontWeight: "900" },
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
