import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { authedFetch } from "@/src/auth";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
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

export function DailyCheckInCalendar() {
  const { palette } = useDisplayPreferences();
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

  const load = useCallback(async () => {
    if (!getScreenCache<CheckInState>("daily-checkin")) setLoading(true);
    const response = await authedFetch("/api/users/daily-checkin").catch(() => null);
    if (response?.ok) applyResponse(await response.json().catch(() => null));
    setLoading(false);
  }, [applyResponse]);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const checkIn = async () => {
    if (saving || todayStatus !== "not_checked_in") return;
    setSaving(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    const response = await authedFetch("/api/users/daily-checkin", {
      method: "POST",
      body: JSON.stringify({ date: localDateString() }),
    }).catch(() => null);
    if (response?.ok) applyResponse(await response.json().catch(() => null));
    setSaving(false);
  };

  const shownMonth = (() => {
    const base = new Date();
    return new Date(base.getFullYear(), base.getMonth() + monthOffset, 1);
  })();
  const monthLabel = shownMonth.toLocaleDateString(undefined, { month: "long", year: "numeric" });
  const daysInMonth = new Date(shownMonth.getFullYear(), shownMonth.getMonth() + 1, 0).getDate();
  const firstWeekday = (new Date(shownMonth.getFullYear(), shownMonth.getMonth(), 1).getDay() + 6) % 7; // Monday-first
  const todayKey = localDateString();
  const cells: Array<{ key: string; day?: number; date?: string }> = [];
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
        <Pressable testID="daily-checkin-button" disabled={saving} onPress={checkIn} style={[styles.checkInButton, saving && styles.checkInButtonDisabled]}>
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
});
