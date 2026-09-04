import { useEffect, useMemo, useRef, useState } from "react";
import { Animated, Easing, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { formatLocalDate, parseLocalDate } from "@/src/appDate";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { colors, radius, spacing } from "@/src/theme";

// The daily flow on Home: Alira's reminder message, the re-assessment-day
// prompt, the medal for finishing today's exercises, the calendar that shows
// the medals and the next assessment date, and (testing phase) the date
// stepper that lets a tester walk through the days.

export type CalendarDay = { status: string; medal?: boolean };

const WEEKDAY_LABELS = ["M", "T", "W", "T", "F", "S", "S"];

function longDate(value: string): string {
  const date = parseLocalDate(value);
  return date.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
}

function shortDate(value: string): string {
  const date = parseLocalDate(value);
  return date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });
}

// ---------------------------------------------------------------- date stepper

type AppDateStepperProps = {
  date: string;
  overridden: boolean;
  onShift: (days: number) => void;
  onReset: () => void;
  compact?: boolean;
};

export function AppDateStepper({ date, overridden, onShift, onReset, compact }: AppDateStepperProps) {
  const { palette } = useDisplayPreferences();
  return (
    <View style={styles.stepperWrap} testID="home-app-date-stepper">
      <View style={[styles.stepper, { borderColor: overridden ? "#B65C09" : palette.border, backgroundColor: palette.surface }]}>
        <Pressable accessibilityLabel="Previous day" testID="home-app-date-previous" onPress={() => onShift(-1)} hitSlop={6} style={({ pressed }) => [styles.stepperButton, pressed && styles.pressed]}>
          <Ionicons name="chevron-back" size={20} color={palette.text} />
        </Pressable>
        <View style={styles.stepperCentre}>
          <Text style={[styles.stepperDate, { color: palette.text }]} numberOfLines={1} testID="home-app-date-value">{compact ? shortDate(date) : longDate(date)}</Text>
          <Text style={[styles.stepperCaption, { color: overridden ? "#B65C09" : palette.muted }]} numberOfLines={1}>
            {overridden ? "Testing date - not today" : "Testing date - step days with the arrows"}
          </Text>
        </View>
        <Pressable accessibilityLabel="Next day" testID="home-app-date-next" onPress={() => onShift(1)} hitSlop={6} style={({ pressed }) => [styles.stepperButton, pressed && styles.pressed]}>
          <Ionicons name="chevron-forward" size={20} color={palette.text} />
        </Pressable>
      </View>
      {overridden ? (
        <Pressable testID="home-app-date-reset" onPress={onReset} style={({ pressed }) => [styles.stepperReset, pressed && styles.pressed]}>
          <Ionicons name="refresh" size={14} color="#B65C09" />
          <Text style={styles.stepperResetText}>Back to today</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

// ---------------------------------------------------------------- Alira message

type AliraMessageModalProps = {
  visible: boolean;
  text: string;
  onOpenPlan: () => void;
  onOpenChat: () => void;
  onLater: () => void;
};

export function AliraMessageModal({ visible, text, onOpenPlan, onOpenChat, onLater }: AliraMessageModalProps) {
  const { palette } = useDisplayPreferences();
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onLater}>
      <View style={styles.backdrop}>
        <View style={[styles.card, { backgroundColor: palette.surface }]} testID="alira-daily-reminder">
          <View style={styles.aliraHeader}>
            <View style={styles.aliraAvatar}><Ionicons name="heart" size={22} color="#FFFFFF" /></View>
            <View style={styles.aliraHeaderCopy}>
              <Text style={[styles.aliraName, { color: palette.text }]}>Alira</Text>
              <Text style={[styles.aliraKicker, { color: palette.brand }]}>NEW MESSAGE</Text>
            </View>
          </View>
          <View style={[styles.aliraBubble, { backgroundColor: palette.soft }]}>
            <Text style={[styles.aliraText, { color: palette.text }]} testID="alira-daily-reminder-text">{text}</Text>
          </View>
          <Pressable testID="alira-daily-reminder-open-plan" onPress={onOpenPlan} style={({ pressed }) => [styles.primary, pressed && styles.pressed]}>
            <Ionicons name="fitness-outline" size={19} color="#FFFFFF" />
            <Text style={styles.primaryText}>Open today&apos;s exercises</Text>
          </Pressable>
          <Pressable testID="alira-daily-reminder-open-chat" onPress={onOpenChat} style={({ pressed }) => [styles.secondary, { borderColor: palette.border }, pressed && styles.pressed]}>
            <Text style={[styles.secondaryText, { color: palette.text }]}>Reply to Alira</Text>
          </Pressable>
          <Pressable testID="alira-daily-reminder-later" onPress={onLater} style={styles.later}>
            <Text style={[styles.laterText, { color: palette.muted }]}>Later</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

// ---------------------------------------------------------------- re-assessment day

type ReassessmentDayModalProps = {
  visible: boolean;
  date: string;
  onStart: () => void;
  onLater: () => void;
};

export function ReassessmentDayModal({ visible, date, onStart, onLater }: ReassessmentDayModalProps) {
  const { palette } = useDisplayPreferences();
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onLater}>
      <View style={styles.backdrop}>
        <View style={[styles.card, { backgroundColor: palette.surface }]} testID="reassessment-day-prompt">
          <View style={[styles.badge, { backgroundColor: palette.soft }]}>
            <Ionicons name="clipboard-outline" size={34} color={palette.brand} />
          </View>
          <Text style={[styles.kicker, { color: palette.brand }]}>TODAY IS YOUR RE-ASSESSMENT DAY</Text>
          <Text style={[styles.title, { color: palette.text }]}>Let&apos;s measure your progress</Text>
          <Text style={[styles.body, { color: palette.muted }]}>
            {longDate(date)}. You have completed a round of daily exercises, so today Alira repeats the movement assessment to see how far you have come and to refresh your plan for the next round.
          </Text>
          <Pressable testID="reassessment-day-start" onPress={onStart} style={({ pressed }) => [styles.primary, pressed && styles.pressed]}>
            <Ionicons name="videocam-outline" size={19} color="#FFFFFF" />
            <Text style={styles.primaryText}>Start the assessment</Text>
          </Pressable>
          <Pressable testID="reassessment-day-later" onPress={onLater} style={styles.later}>
            <Text style={[styles.laterText, { color: palette.muted }]}>Later today</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

// ---------------------------------------------------------------- daily medal

type MedalAwardModalProps = {
  visible: boolean;
  date: string;
  collecting: boolean;
  onCollect: () => void;
  onLater: () => void;
};

function MedalArt({ size = 150 }: { size?: number }) {
  return (
    <View style={{ width: size, height: size * 1.22, alignItems: "center" }} testID="daily-medal-art">
      <View style={styles.ribbonRow}>
        <View style={[styles.ribbon, styles.ribbonLeft, { height: size * 0.38, width: size * 0.2 }]} />
        <View style={[styles.ribbon, styles.ribbonRight, { height: size * 0.38, width: size * 0.2 }]} />
      </View>
      <View style={[styles.medalOuter, { width: size, height: size, borderRadius: size / 2, marginTop: -size * 0.16 }]}>
        <View style={[styles.medalInner, { width: size * 0.78, height: size * 0.78, borderRadius: size * 0.39 }]}>
          <Ionicons name="star" size={size * 0.42} color="#FFF4C2" />
        </View>
      </View>
    </View>
  );
}

export function MedalAwardModal({ visible, date, collecting, onCollect, onLater }: MedalAwardModalProps) {
  const { palette } = useDisplayPreferences();
  const pop = useRef(new Animated.Value(0.5)).current;
  const shine = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!visible) { pop.setValue(0.5); shine.setValue(0); return; }
    Animated.spring(pop, { toValue: 1, friction: 4, tension: 60, useNativeDriver: true }).start();
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(shine, { toValue: 1, duration: 900, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      Animated.timing(shine, { toValue: 0, duration: 900, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [pop, shine, visible]);
  const glow = shine.interpolate({ inputRange: [0, 1], outputRange: [0.35, 0.9] });
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onLater}>
      <View style={styles.backdrop}>
        <View style={[styles.card, styles.medalCard, { backgroundColor: palette.surface }]} testID="daily-medal-award">
          <Text style={[styles.kicker, { color: palette.brand }]}>TODAY&apos;S EXERCISES COMPLETE</Text>
          <Animated.View style={[styles.medalGlow, { opacity: glow }]} />
          <Animated.View style={{ transform: [{ scale: pop }] }}>
            <MedalArt />
          </Animated.View>
          <Text style={[styles.title, { color: palette.text }]}>You earned today&apos;s medal</Text>
          <Text style={[styles.body, { color: palette.muted }]}>
            {longDate(date)}. Every completed day is a step your recovery can build on. Collect the medal to add it to your calendar.
          </Text>
          <Pressable testID="daily-medal-collect" disabled={collecting} onPress={onCollect} style={({ pressed }) => [styles.primary, styles.collectButton, (pressed || collecting) && styles.pressed]}>
            <Ionicons name="medal-outline" size={20} color="#FFFFFF" />
            <Text style={styles.primaryText}>{collecting ? "Collecting..." : "Collect medal"}</Text>
          </Pressable>
          <Pressable testID="daily-medal-later" onPress={onLater} style={styles.later}>
            <Text style={[styles.laterText, { color: palette.muted }]}>Later</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

// ---------------------------------------------------------------- calendar

type MedalCalendarModalProps = {
  visible: boolean;
  today: string;
  days: Record<string, CalendarDay>;
  assessmentDate?: string;
  highlightMedalDate?: string;
  onClose: () => void;
};

export function MedalCalendarModal({ visible, today, days, assessmentDate, highlightMedalDate, onClose }: MedalCalendarModalProps) {
  const { palette } = useDisplayPreferences();
  const [monthOffset, setMonthOffset] = useState(0);
  useEffect(() => { if (visible) setMonthOffset(0); }, [visible, today]);
  const shownMonth = useMemo(() => {
    const base = parseLocalDate(today);
    return new Date(base.getFullYear(), base.getMonth() + monthOffset, 1);
  }, [monthOffset, today]);
  const monthLabel = shownMonth.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  const daysInMonth = new Date(shownMonth.getFullYear(), shownMonth.getMonth() + 1, 0).getDate();
  const firstWeekday = (new Date(shownMonth.getFullYear(), shownMonth.getMonth(), 1).getDay() + 6) % 7; // Monday-first
  const cells: { key: string; day?: number; date?: string }[] = [];
  for (let index = 0; index < firstWeekday; index += 1) cells.push({ key: `blank-${index}` });
  for (let day = 1; day <= daysInMonth; day += 1) {
    const date = formatLocalDate(new Date(shownMonth.getFullYear(), shownMonth.getMonth(), day, 12));
    cells.push({ key: date, day, date });
  }
  const medalCount = Object.values(days).filter((day) => day.medal).length;
  const assessmentLabel = assessmentDate ? longDate(assessmentDate) : "";
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={[styles.card, styles.calendarCard, { backgroundColor: palette.surface }]} testID="medal-calendar">
          <View style={styles.calendarHeader}>
            <View style={[styles.badgeSmall, { backgroundColor: palette.soft }]}><Ionicons name="calendar-outline" size={22} color={palette.brand} /></View>
            <View style={styles.calendarHeaderCopy}>
              <Text style={[styles.calendarTitle, { color: palette.text }]}>Your calendar</Text>
              <Text style={[styles.calendarSubtitle, { color: palette.muted }]}>{medalCount} medal{medalCount === 1 ? "" : "s"} collected</Text>
            </View>
            <Pressable testID="medal-calendar-close" accessibilityLabel="Close calendar" onPress={onClose} hitSlop={8} style={({ pressed }) => [styles.closeButton, { borderColor: palette.border }, pressed && styles.pressed]}>
              <Ionicons name="close" size={20} color={palette.text} />
            </Pressable>
          </View>
          <View style={styles.monthRow}>
            <Pressable accessibilityLabel="Previous month" testID="medal-calendar-previous" onPress={() => setMonthOffset((value) => value - 1)} style={styles.monthNav}><Ionicons name="chevron-back" size={20} color={palette.muted} /></Pressable>
            <Text style={[styles.monthLabel, { color: palette.text }]} testID="medal-calendar-month">{monthLabel}</Text>
            <Pressable accessibilityLabel="Next month" testID="medal-calendar-next" onPress={() => setMonthOffset((value) => value + 1)} style={styles.monthNav}><Ionicons name="chevron-forward" size={20} color={palette.muted} /></Pressable>
          </View>
          <View style={styles.weekHeader}>
            {WEEKDAY_LABELS.map((label, index) => <Text key={`${label}-${index}`} style={[styles.weekday, { color: palette.muted }]}>{label}</Text>)}
          </View>
          <View style={styles.grid}>
            {cells.map((cell) => {
              if (!cell.date) return <View key={cell.key} style={styles.dayCell} />;
              const record = days[cell.date];
              const isToday = cell.date === today;
              const isAssessment = Boolean(assessmentDate) && cell.date === assessmentDate;
              const hasMedal = Boolean(record?.medal);
              const isComplete = record?.status === "complete";
              const isInProgress = record?.status === "in_progress";
              const justCollected = hasMedal && cell.date === highlightMedalDate;
              return (
                <View key={cell.key} style={styles.dayCell} testID={`medal-calendar-day-${cell.date}`}>
                  <View
                    style={[
                      styles.dayInner,
                      isComplete && !hasMedal && styles.dayComplete,
                      isInProgress && styles.dayInProgress,
                      hasMedal && styles.dayMedal,
                      justCollected && styles.dayMedalNew,
                      isAssessment && styles.dayAssessment,
                      isToday && { borderColor: palette.brand, borderWidth: 2 },
                    ]}
                  >
                    {hasMedal ? (
                      <Ionicons name="medal" size={19} color="#8A5A00" testID={`medal-calendar-medal-${cell.date}`} />
                    ) : isAssessment ? (
                      <Ionicons name="clipboard" size={16} color="#FFFFFF" />
                    ) : isComplete ? (
                      <Ionicons name="checkmark" size={15} color="#FFFFFF" />
                    ) : isInProgress ? (
                      <Ionicons name="ellipsis-horizontal" size={14} color="#8A5A00" />
                    ) : (
                      <Text style={[styles.dayNumber, { color: palette.muted }]}>{cell.day}</Text>
                    )}
                  </View>
                  {hasMedal || isAssessment ? <Text style={[styles.dayUnder, { color: palette.muted }]}>{cell.day}</Text> : null}
                </View>
              );
            })}
          </View>
          <View style={styles.legend}>
            <View style={styles.legendItem}><Ionicons name="medal" size={15} color="#8A5A00" /><Text style={[styles.legendText, { color: palette.muted }]}>Medal - exercises finished</Text></View>
            <View style={styles.legendItem}><View style={[styles.legendDot, styles.dayAssessment]}><Ionicons name="clipboard" size={9} color="#FFFFFF" /></View><Text style={[styles.legendText, { color: palette.muted }]}>Re-assessment day</Text></View>
            <View style={styles.legendItem}><View style={[styles.legendDot, styles.dayInProgress]} /><Text style={[styles.legendText, { color: palette.muted }]}>Checked in</Text></View>
          </View>
          {assessmentLabel ? (
            <View style={[styles.assessmentNote, { backgroundColor: palette.soft }]} testID="medal-calendar-assessment-note">
              <Ionicons name="clipboard-outline" size={18} color={palette.brand} />
              <Text style={[styles.assessmentNoteText, { color: palette.text }]}>Next assessment: {assessmentLabel}</Text>
            </View>
          ) : null}
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  pressed: { opacity: 0.7 },
  backdrop: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, backgroundColor: "rgba(10,22,16,0.62)" },
  card: { width: "100%", maxWidth: 440, borderRadius: radius.md, padding: spacing.lg, alignItems: "center", gap: spacing.xs },
  badge: { width: 66, height: 66, borderRadius: 33, alignItems: "center", justifyContent: "center", marginBottom: 4 },
  badgeSmall: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  kicker: { fontSize: 11, fontWeight: "900", letterSpacing: 0.5, textAlign: "center" },
  title: { fontSize: 22, lineHeight: 28, fontWeight: "900", textAlign: "center" },
  body: { fontSize: 14, lineHeight: 21, textAlign: "center" },
  primary: { alignSelf: "stretch", minHeight: 52, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, marginTop: spacing.sm },
  primaryText: { color: "#FFFFFF", fontSize: 16, fontWeight: "900" },
  secondary: { alignSelf: "stretch", minHeight: 46, borderRadius: radius.sm, borderWidth: 1.5, alignItems: "center", justifyContent: "center", marginTop: 4 },
  secondaryText: { fontSize: 15, fontWeight: "800" },
  later: { minHeight: 40, alignSelf: "stretch", alignItems: "center", justifyContent: "center" },
  laterText: { fontSize: 14, fontWeight: "700" },
  // date stepper
  stepperWrap: { alignItems: "center", gap: 4, flexShrink: 1 },
  stepper: { minHeight: 52, maxWidth: 420, borderWidth: 1.5, borderRadius: radius.pill, paddingHorizontal: 6, flexDirection: "row", alignItems: "center", gap: 2 },
  stepperButton: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center" },
  stepperCentre: { minWidth: 120, maxWidth: 300, alignItems: "center", paddingHorizontal: 4 },
  stepperDate: { fontSize: 15, lineHeight: 20, fontWeight: "900", textAlign: "center" },
  stepperCaption: { fontSize: 11, lineHeight: 14, fontWeight: "700", textAlign: "center" },
  stepperReset: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 26, paddingHorizontal: 8 },
  stepperResetText: { color: "#B65C09", fontSize: 12, fontWeight: "800" },
  // Alira message
  aliraHeader: { alignSelf: "stretch", flexDirection: "row", alignItems: "center", gap: spacing.sm },
  aliraAvatar: { width: 46, height: 46, borderRadius: 23, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  aliraHeaderCopy: { flex: 1 },
  aliraName: { fontSize: 18, fontWeight: "900" },
  aliraKicker: { fontSize: 11, fontWeight: "900", letterSpacing: 0.5 },
  aliraBubble: { alignSelf: "stretch", borderRadius: radius.md, padding: spacing.md, marginTop: 4 },
  aliraText: { fontSize: 15, lineHeight: 23, fontWeight: "500" },
  // medal
  medalCard: { paddingTop: spacing.lg + 4 },
  medalGlow: { position: "absolute", top: 54, width: 230, height: 230, borderRadius: 115, backgroundColor: "#FFD86B" },
  ribbonRow: { flexDirection: "row", gap: 6 },
  ribbon: { borderRadius: 6 },
  ribbonLeft: { backgroundColor: "#0B7A3A", transform: [{ rotate: "16deg" }] },
  ribbonRight: { backgroundColor: "#16A34A", transform: [{ rotate: "-16deg" }] },
  medalOuter: { backgroundColor: "#E1A61E", borderWidth: 6, borderColor: "#B77A0E", alignItems: "center", justifyContent: "center", shadowColor: "#7A4E00", shadowOpacity: 0.35, shadowRadius: 14, shadowOffset: { width: 0, height: 8 }, elevation: 8 },
  medalInner: { backgroundColor: "#F2BF3B", borderWidth: 3, borderColor: "#FFE28A", alignItems: "center", justifyContent: "center" },
  collectButton: { backgroundColor: "#B77A0E" },
  // calendar
  calendarCard: { maxWidth: 480, alignItems: "stretch" },
  calendarHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  calendarHeaderCopy: { flex: 1 },
  calendarTitle: { fontSize: 19, fontWeight: "900" },
  calendarSubtitle: { fontSize: 13, marginTop: 2 },
  closeButton: { width: 40, height: 40, borderRadius: 20, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  monthRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  monthNav: { width: 42, height: 42, alignItems: "center", justifyContent: "center" },
  monthLabel: { fontSize: 16, fontWeight: "900" },
  weekHeader: { flexDirection: "row", marginTop: 4 },
  weekday: { flex: 1, textAlign: "center", fontSize: 11, fontWeight: "800" },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  dayCell: { width: `${100 / 7}%`, aspectRatio: 1, alignItems: "center", justifyContent: "center", paddingVertical: 2 },
  dayInner: { width: 36, height: 36, borderRadius: 18, alignItems: "center", justifyContent: "center" },
  dayComplete: { backgroundColor: colors.success },
  dayInProgress: { backgroundColor: "#F5D48F" },
  dayMedal: { backgroundColor: "#FFE28A", borderWidth: 2, borderColor: "#E1A61E" },
  dayMedalNew: { backgroundColor: "#FFD86B", borderColor: "#B77A0E", transform: [{ scale: 1.12 }] },
  dayAssessment: { backgroundColor: "#0B7A3A" },
  dayNumber: { fontSize: 13, fontWeight: "600" },
  dayUnder: { fontSize: 9, fontWeight: "800", marginTop: -1 },
  legend: { flexDirection: "row", flexWrap: "wrap", justifyContent: "center", gap: spacing.sm, marginTop: spacing.xs },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 5 },
  legendDot: { width: 14, height: 14, borderRadius: 7, alignItems: "center", justifyContent: "center" },
  legendText: { fontSize: 12 },
  assessmentNote: { flexDirection: "row", alignItems: "center", gap: 8, borderRadius: radius.sm, padding: spacing.sm, marginTop: spacing.xs },
  assessmentNoteText: { fontSize: 14, fontWeight: "800", flex: 1 },
});
