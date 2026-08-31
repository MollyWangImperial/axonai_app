import { useCallback, useState } from "react";
import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { authedFetch } from "@/src/auth";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { resolveAliraNavigation } from "@/src/aliraNavigation";
import { colors, radius, spacing } from "@/src/theme";

// Daily check-in loop: the patient taps "Check in" after signing in, which
// marks today as in progress on the calendar. The day only earns its green
// check mark once the day's exercises are completed (exercise.tsx reports
// completion to /api/users/daily-checkin/complete).

export type DailyCheckInStatus = "not_checked_in" | "in_progress" | "complete";
type DayRecord = { date: string; status: string };
type CheckInState = { todayStatus: DailyCheckInStatus; days: Record<string, string> };

export function localDateString(date = new Date()): string {
  const y = date.getFullYear();
  const m = `${date.getMonth() + 1}`.padStart(2, "0");
  const d = `${date.getDate()}`.padStart(2, "0");
  return `${y}-${m}-${d}`;
}

const WEEKDAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];

type NextStep = {
  action?: string;
  title?: string;
  message?: string;
  cta?: string;
  destination?: string;
  secondary_action?: (NextStep & { defer_domains?: string[] }) | null;
};

// The care plan's next_step destinations mapped onto the app's navigation map.
const NEXT_STEP_NAVIGATION: Record<string, string> = {
  rehab_plan: "rehab_plan",
  caregiver_plan: "caregiver_plan",
  survey_report: "survey_report",
  progress: "progress",
  survey: "alira_chat",
  alira: "alira_chat",
  assessment: "next_assessment",
  initial_assessment: "initial_assessment",
  emergency: "emergency_fast_check",
};

export function DailyCheckInCalendar() {
  const { palette } = useDisplayPreferences();
  const router = useRouter();
  const [nextStep, setNextStep] = useState<NextStep | null>(null);
  const [showNextStep, setShowNextStep] = useState(false);
  const cached = getScreenCache<CheckInState>("daily-checkin");
  const [todayStatus, setTodayStatus] = useState<DailyCheckInStatus>(cached?.todayStatus ?? "not_checked_in");
  const [days, setDays] = useState<Record<string, string>>(cached?.days ?? {});
  const [loading, setLoading] = useState(!cached);
  const [saving, setSaving] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);
  const [monthOffset, setMonthOffset] = useState(0);

  const applyResponse = useCallback((payload: { status?: string; days?: DayRecord[] } | null) => {
    if (!payload) return;
    const today = localDateString();
    const dayMap: Record<string, string> = {};
    for (const day of payload.days || []) dayMap[day.date] = day.status;
    const status = (dayMap[today] as DailyCheckInStatus) || "not_checked_in";
    setDays(dayMap);
    setTodayStatus(status);
    setScreenCache<CheckInState>("daily-checkin", { todayStatus: status, days: dayMap });
  }, []);

  const cachedNextStep = (): NextStep | null => {
    // The Home screen already fetches the care plan into the shared cache, so
    // the next step can be shown instantly with no extra network wait.
    const home = getScreenCache<{ carePlan?: { next_step?: NextStep } | null }>("home");
    return home?.carePlan?.next_step ?? null;
  };

  const openNextStep = useCallback(async () => {
    const instant = cachedNextStep();
    setNextStep(instant);
    setShowNextStep(true);
    setScreenCache("daily-checkin-prompted", localDateString());
    if (!instant) {
      const plan = await authedFetch("/api/alira/care-plan")
        .then((planResponse) => (planResponse.ok ? planResponse.json() : null))
        .catch(() => null);
      setNextStep((plan?.next_step as NextStep) || {
        title: "You're checked in",
        message: "Complete today's exercises to earn your check mark on the calendar.",
        cta: "OK",
      });
    }
  }, []);

  const checkIn = useCallback(async (automatic = false) => {
    if (!automatic) Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    setSaving(true);
    // Show Alira's next step immediately - the check-in itself saves in the
    // background rather than making the patient wait on the network.
    void openNextStep();
    const response = await authedFetch("/api/users/daily-checkin", {
      method: "POST",
      body: JSON.stringify({ date: localDateString() }),
    }).catch(() => null);
    if (response?.ok) applyResponse(await response.json().catch(() => null));
    setSaving(false);
  }, [applyResponse, openNextStep]);

  const load = useCallback(async () => {
    if (!getScreenCache<CheckInState>("daily-checkin")) setLoading(true);
    const response = await authedFetch("/api/users/daily-checkin").catch(() => null);
    const payload = response?.ok ? await response.json().catch(() => null) : null;
    if (payload) applyResponse(payload);
    setLoading(false);
    // Spec 2/3: the session starts with Alira routing the patient - the next
    // step appears automatically once per day, without waiting for a tap.
    const today = localDateString();
    const alreadyPrompted = getScreenCache<string>("daily-checkin-prompted") === today;
    if (payload && !alreadyPrompted) {
      if (payload.status === "not_checked_in") void checkIn(true);
      else void openNextStep();
    }
  }, [applyResponse, checkIn, openNextStep]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const onSecondaryAction = async () => {
    const secondary = nextStep?.secondary_action;
    setShowNextStep(false);
    if (!secondary) return;
    // "I can't do this today" - record the deferral without penalty, then
    // continue with the plan that is already active.
    for (const domain of secondary.defer_domains || []) {
      await authedFetch("/api/alira/assessment-deferral", {
        method: "POST",
        body: JSON.stringify({ domain, reason: "not_possible_today" }),
      }).catch(() => null);
    }
    const destination = NEXT_STEP_NAVIGATION[secondary.destination || ""];
    if (!destination) return;
    try {
      const resolution = await resolveAliraNavigation(destination);
      if (resolution.success && resolution.path) router.push(resolution.path as never);
    } catch {
      // Staying on Home is a safe fallback.
    }
  };

  const goToNextStep = async () => {
    setShowNextStep(false);
    const destination = NEXT_STEP_NAVIGATION[nextStep?.destination || ""];
    if (!destination) return;
    try {
      const resolution = await resolveAliraNavigation(destination);
      if (resolution.success && resolution.path) router.push(resolution.path as never);
    } catch {
      // Staying on Home is a safe fallback; the cards above show the same step.
    }
  };

  const shownMonth = (() => {
    const base = new Date();
    return new Date(base.getFullYear(), base.getMonth() + monthOffset, 1);
  })();
  const monthLabel = shownMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const daysInMonth = new Date(shownMonth.getFullYear(), shownMonth.getMonth() + 1, 0).getDate();
  const firstWeekday = (new Date(shownMonth.getFullYear(), shownMonth.getMonth(), 1).getDay() + 6) % 7; // Monday-first
  const todayKey = localDateString();
  const cells: { key: string; day?: number; date?: string }[] = [];
  for (let i = 0; i < firstWeekday; i++) cells.push({ key: `blank-${i}` });
  for (let day = 1; day <= daysInMonth; day++) {
    const date = localDateString(new Date(shownMonth.getFullYear(), shownMonth.getMonth(), day));
    cells.push({ key: date, day, date });
  }

  return (
    <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="daily-checkin-card">
      <View style={styles.headerRow}>
        <View style={[styles.icon, { backgroundColor: palette.soft }]}>
          <Ionicons name={todayStatus === "complete" ? "checkmark-circle" : todayStatus === "in_progress" ? "time-outline" : "sunny-outline"} size={24} color={todayStatus === "complete" ? colors.success : palette.brand} />
        </View>
        <View style={styles.copy}>
          <Text style={[styles.title, { color: palette.text }]}>Daily check-in</Text>
          <Text style={[styles.subtitle, { color: palette.muted }]}>
            {todayStatus === "complete"
              ? "Day complete - today's check mark is earned."
              : todayStatus === "in_progress"
                ? "Checked in. Complete today's exercises to earn your check mark."
                : "Tap check in to start your day."}
          </Text>
        </View>
        <Pressable testID="daily-checkin-calendar-toggle" accessibilityLabel="Show check-in calendar" onPress={() => { setMonthOffset(0); setShowCalendar((value) => !value); }} style={[styles.calendarButton, { borderColor: palette.border, backgroundColor: showCalendar ? palette.soft : "transparent" }]}>
          <Ionicons name="calendar-outline" size={22} color={palette.brand} />
        </Pressable>
      </View>

      {loading ? (
        <View style={styles.loadingRow}><ActivityIndicator color={palette.brand} /></View>
      ) : todayStatus === "not_checked_in" ? (
        <Pressable testID="daily-checkin-button" disabled={saving} onPress={() => { if (!saving && todayStatus === "not_checked_in") void checkIn(); }} style={[styles.checkInButton, saving && styles.checkInButtonDisabled]}>
          {saving ? <ActivityIndicator color="#FFFFFF" /> : <><Ionicons name="hand-right-outline" size={19} color="#FFFFFF" /><Text style={styles.checkInText}>Check in for today</Text></>}
        </Pressable>
      ) : (
        <View style={[styles.statusBadge, { backgroundColor: palette.soft }]} testID={todayStatus === "complete" ? "daily-checkin-complete-badge" : "daily-checkin-progress-badge"}>
          <Ionicons name={todayStatus === "complete" ? "checkmark-circle" : "ellipsis-horizontal-circle-outline"} size={20} color={todayStatus === "complete" ? colors.success : colors.warning} />
          <Text style={[styles.statusText, { color: palette.text }]}>{todayStatus === "complete" ? "Completed today" : "In progress today"}</Text>
        </View>
      )}

      {showCalendar ? (
        <View style={[styles.calendar, { borderColor: palette.border }]} testID="daily-checkin-calendar">
          <View style={styles.monthRow}>
            <Pressable accessibilityLabel="Previous month" onPress={() => setMonthOffset((value) => value - 1)} style={styles.monthNav}><Ionicons name="chevron-back" size={19} color={palette.muted} /></Pressable>
            <Text style={[styles.monthLabel, { color: palette.text }]}>{monthLabel}</Text>
            <Pressable accessibilityLabel="Next month" onPress={() => setMonthOffset((value) => Math.min(0, value + 1))} style={styles.monthNav}><Ionicons name="chevron-forward" size={19} color={monthOffset >= 0 ? "transparent" : palette.muted} /></Pressable>
          </View>
          <View style={styles.weekHeader}>
            {WEEKDAY_LABELS.map((label, index) => <Text key={`${label}-${index}`} style={[styles.weekday, { color: palette.muted }]}>{label}</Text>)}
          </View>
          <View style={styles.grid}>
            {cells.map((cell) => {
              if (!cell.date) return <View key={cell.key} style={styles.dayCell} />;
              const status = days[cell.date];
              const isToday = cell.date === todayKey;
              return (
                <View key={cell.key} style={styles.dayCell}>
                  <View style={[styles.dayInner, isToday && { borderColor: palette.brand, borderWidth: 2 }, status === "complete" && styles.dayComplete, status === "in_progress" && styles.dayInProgress]}>
                    {status === "complete" ? (
                      <Ionicons name="checkmark" size={15} color="#FFFFFF" />
                    ) : status === "in_progress" ? (
                      <Ionicons name="ellipsis-horizontal" size={14} color="#8A5A00" />
                    ) : (
                      <Text style={[styles.dayNumber, { color: palette.muted }]}>{cell.day}</Text>
                    )}
                  </View>
                </View>
              );
            })}
          </View>
          <View style={styles.legendRow}>
            <View style={styles.legendItem}><View style={[styles.legendDot, styles.dayComplete]} /><Text style={[styles.legendText, { color: palette.muted }]}>Exercises complete</Text></View>
            <View style={styles.legendItem}><View style={[styles.legendDot, styles.dayInProgress]} /><Text style={[styles.legendText, { color: palette.muted }]}>Checked in</Text></View>
          </View>
        </View>
      ) : null}

      <Modal visible={showNextStep} transparent animationType="fade" onRequestClose={() => setShowNextStep(false)}>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { backgroundColor: palette.surface }]} testID="daily-checkin-next-step">
            <View style={[styles.modalBadge, { backgroundColor: palette.soft }]}>
              <Ionicons name="checkmark-circle" size={30} color={colors.success} />
            </View>
            <Text style={[styles.modalKicker, { color: palette.brand }]}>{"CHECKED IN - HERE'S YOUR NEXT STEP"}</Text>
            <Text style={[styles.modalTitle, { color: palette.text }]}>{nextStep?.title || "You're checked in"}</Text>
            <Text style={[styles.modalBody, { color: palette.muted }]}>{nextStep ? (nextStep.message || "Complete today's exercises to earn your check mark.") : "One moment - Alira is checking your plan..."}</Text>
            <Pressable testID="daily-checkin-next-step-go" onPress={goToNextStep} style={styles.modalPrimary}>
              <Text style={styles.modalPrimaryText}>{nextStep?.cta || "Let's go"}</Text>
            </Pressable>
            {nextStep?.secondary_action ? (
              <Pressable testID="daily-checkin-next-step-secondary" onPress={onSecondaryAction} style={[styles.modalSecondary, { borderColor: palette.border }]}>
                <Text style={[styles.modalSecondaryText, { color: palette.text }]}>{nextStep.secondary_action.title || "I can't do this today"}</Text>
              </Pressable>
            ) : null}
            <Pressable testID="daily-checkin-next-step-later" onPress={() => setShowNextStep(false)} style={styles.modalLater}>
              <Text style={[styles.modalLaterText, { color: palette.muted }]}>Later</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, marginBottom: spacing.md },
  headerRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  icon: { width: 46, height: 46, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  copy: { flex: 1 },
  title: { fontSize: 17, lineHeight: 23, fontWeight: "800" },
  subtitle: { fontSize: 13, lineHeight: 19, marginTop: 2 },
  calendarButton: { width: 44, height: 44, borderRadius: radius.sm, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  loadingRow: { minHeight: 48, alignItems: "center", justifyContent: "center" },
  checkInButton: { minHeight: 50, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs },
  checkInButtonDisabled: { opacity: 0.6 },
  checkInText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  statusBadge: { minHeight: 44, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, paddingHorizontal: spacing.sm },
  statusText: { fontSize: 14, fontWeight: "700" },
  calendar: { borderTopWidth: 1, paddingTop: spacing.sm, gap: spacing.xs },
  monthRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  monthNav: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  monthLabel: { fontSize: 15, fontWeight: "800" },
  weekHeader: { flexDirection: "row" },
  weekday: { flex: 1, textAlign: "center", fontSize: 11, fontWeight: "800" },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  dayCell: { width: `${100 / 7}%`, aspectRatio: 1.15, alignItems: "center", justifyContent: "center", paddingVertical: 2 },
  dayInner: { width: 32, height: 32, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  dayComplete: { backgroundColor: colors.success },
  dayInProgress: { backgroundColor: "#F5D48F" },
  dayNumber: { fontSize: 13, fontWeight: "600" },
  legendRow: { flexDirection: "row", gap: spacing.md, justifyContent: "center", paddingTop: 2 },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendDot: { width: 12, height: 12, borderRadius: 6 },
  legendText: { fontSize: 12 },
  modalBackdrop: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, backgroundColor: "rgba(10,22,16,0.6)" },
  modalCard: { width: "100%", maxWidth: 420, borderRadius: radius.md, padding: spacing.lg, alignItems: "center", gap: spacing.xs },
  modalBadge: { width: 56, height: 56, borderRadius: 28, alignItems: "center", justifyContent: "center", marginBottom: 2 },
  modalKicker: { fontSize: 11, fontWeight: "900", letterSpacing: 0.4 },
  modalTitle: { fontSize: 20, lineHeight: 26, fontWeight: "800", textAlign: "center" },
  modalBody: { fontSize: 14, lineHeight: 21, textAlign: "center" },
  modalPrimary: { alignSelf: "stretch", minHeight: 50, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginTop: spacing.sm },
  modalPrimaryText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  modalSecondary: { alignSelf: "stretch", minHeight: 48, borderRadius: radius.sm, borderWidth: 1, alignItems: "center", justifyContent: "center", marginTop: 2 },
  modalSecondaryText: { fontSize: 15, fontWeight: "700" },
  modalLater: { minHeight: 40, alignItems: "center", justifyContent: "center", alignSelf: "stretch" },
  modalLaterText: { fontSize: 14, fontWeight: "700" },
});
