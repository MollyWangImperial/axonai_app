import { useCallback, useState } from "react";
import { Modal, Pressable, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";

import { authedFetch } from "@/src/auth";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { radius, spacing } from "@/src/theme";

export type ActivityMetric = {
  activity: string;
  status: "complete" | "estimated" | "not_assessed";
  observed?: string | null;
  qualitative_score?: "weak" | "medium" | "normal" | null;
  score?: number | null;
  score_source?: "observed" | "survey" | null;
  reported_assistance_level?: string | null;
  change_from_baseline?: string | null;
};

type HelpBandId = "full_help" | "a_lot_of_help" | "a_little_help" | "independent";

const HELP_BANDS: { id: HelpBandId; label: string }[] = [
  { id: "full_help", label: "Full help" },
  { id: "a_lot_of_help", label: "A lot of help" },
  { id: "a_little_help", label: "A little help" },
  { id: "independent", label: "Independent" },
];

const ASSISTANCE_TO_BAND: Record<string, HelpBandId> = {
  unable: "full_help",
  maximum_assistance: "full_help",
  moderate_assistance: "a_lot_of_help",
  minimum_assistance: "a_little_help",
  supervision_only: "a_little_help",
  fully_independent: "independent",
};

const QUALITATIVE_TO_BAND: Record<string, HelpBandId> = {
  weak: "a_lot_of_help",
  medium: "a_little_help",
  normal: "independent",
};

const BAND_DESCRIPTIONS: Record<HelpBandId, { estimated: string; observed: string }> = {
  full_help: {
    estimated: "Someone may need to help with most steps.",
    observed: "Most steps needed hands-on help in the assessment.",
  },
  a_lot_of_help: {
    estimated: "Hands-on support may be helpful for much of this activity.",
    observed: "Much of this activity needed hands-on support in the assessment.",
  },
  a_little_help: {
    estimated: "A little help or someone nearby may be useful.",
    observed: "Only a little help was needed in the assessment.",
  },
  independent: {
    estimated: "You reported managing this on your own.",
    observed: "You managed this on your own in the assessment.",
  },
};

const ACTIVITY_ICONS: Record<string, keyof typeof MaterialCommunityIcons.glyphMap> = {
  "Eating and drinking": "silverware-fork-knife",
  Dressing: "tshirt-crew-outline",
  "Grooming and self-care": "brush",
  "Moving around": "walk",
};

const NUMBER_WORDS = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten"];

function bandFor(item: ActivityMetric): HelpBandId | null {
  if (item.reported_assistance_level && ASSISTANCE_TO_BAND[item.reported_assistance_level]) {
    return ASSISTANCE_TO_BAND[item.reported_assistance_level];
  }
  if (item.qualitative_score && QUALITATIVE_TO_BAND[item.qualitative_score]) {
    return QUALITATIVE_TO_BAND[item.qualitative_score];
  }
  return null;
}

function countLabel(count: number) {
  return NUMBER_WORDS[count] || String(count);
}

function activitySummary(scored: ActivityMetric[]) {
  if (!scored.length) return "These activities have not been assessed yet.";
  const bands = scored.map((item) => ({ item, band: bandFor(item) as HelpBandId }));
  const independent = bands.filter(({ band }) => band === "independent");
  const fullHelp = bands.filter(({ band }) => band === "full_help");
  const aLot = bands.filter(({ band }) => band === "a_lot_of_help");
  const aLittle = bands.filter(({ band }) => band === "a_little_help");
  const messages: string[] = [];

  if (independent.length === scored.length) return "These everyday activities look independent.";
  if (independent.length === 1) messages.push(`${independent[0].item.activity} looks independent.`);
  if (independent.length > 1) messages.push(`${countLabel(independent.length)} activities look independent.`);
  if (fullHelp.length) messages.push(`${countLabel(fullHelp.length)} ${fullHelp.length === 1 ? "activity" : "activities"} may need full help.`);
  else if (aLot.length) messages.push(`${countLabel(aLot.length)} ${aLot.length === 1 ? "activity" : "activities"} may need a lot of help.`);
  else if (aLittle.length) messages.push(`${countLabel(aLittle.length)} ${aLittle.length === 1 ? "activity" : "activities"} may need a little help.`);

  return messages.join(" ") || "Your answers give an early picture of daily life.";
}

function toneFor(band: HelpBandId) {
  if (band === "full_help") return { accent: "#E2A000", text: "#995700", badge: "#FFE8B5", icon: "people-outline" as const };
  if (band === "a_lot_of_help") return { accent: "#D79A18", text: "#875900", badge: "#FFF0C9", icon: "people-outline" as const };
  if (band === "a_little_help") return { accent: "#78A06F", text: "#275D3E", badge: "#E5F0E5", icon: "person-outline" as const };
  return { accent: "#63966C", text: "#18533B", badge: "#DCECDF", icon: "person-outline" as const };
}

function descriptionFor(item: ActivityMetric, band: HelpBandId) {
  if (item.activity === "Grooming and self-care" && item.status !== "complete" && band === "full_help") {
    return "Hands-on support may be helpful.";
  }
  return item.observed && item.status === "complete"
    ? BAND_DESCRIPTIONS[band].observed
    : BAND_DESCRIPTIONS[band].estimated;
}

export function DailyActivitiesBoard({
  activities,
  title = "Daily life at a glance",
  sectionHeading = false,
}: {
  activities: ActivityMetric[];
  title?: string;
  sectionHeading?: boolean;
}) {
  const { width } = useWindowDimensions();
  const { palette } = useDisplayPreferences();
  const compact = width < 700;
  const [showMethodology, setShowMethodology] = useState(false);
  const scored = activities.filter((item) => item.status !== "not_assessed" && bandFor(item));
  const notAssessed = activities.filter((item) => item.status === "not_assessed" || !bandFor(item));
  const allObserved = scored.length > 0 && scored.every((item) => item.status === "complete");
  const anyObserved = scored.some((item) => item.status === "complete");
  const sourceBadge = anyObserved ? "Observed and estimated" : "Estimated from your answers";

  return (
    <View style={[styles.panel, compact && styles.panelCompact, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="daily-activities-panel">
      <View style={[styles.headerRow, compact && styles.headerRowCompact]}>
        <View style={styles.headerCopy}>
          <Text style={[styles.title, sectionHeading && styles.titleSection, compact && styles.titleCompact, { color: palette.text }]}>{title}</Text>
          <Text style={[styles.subtitle, compact && styles.subtitleCompact, { color: palette.muted }]}>How much help you may need with everyday activities.</Text>
        </View>
        {scored.length > 0 && !allObserved ? (
          <View style={styles.sourceBadge} testID="daily-activities-source-badge">
            <Ionicons name="information-circle-outline" size={compact ? 20 : 25} color="#915D05" />
            <Text style={[styles.sourceBadgeText, compact && styles.sourceBadgeTextCompact]}>{sourceBadge}</Text>
          </View>
        ) : null}
      </View>

      <View style={styles.summaryRow} testID="daily-activities-summary">
        <Ionicons name="checkmark-circle-outline" size={30} color="#145C43" />
        <Text style={[styles.summaryText, compact && styles.summaryTextCompact, { color: palette.text }]}>{activitySummary(scored)}</Text>
      </View>

      {scored.length > 0 ? (
        <View style={[styles.activityList, { borderColor: palette.border }]} testID="daily-activities-list">
          {scored.map((item, index) => {
            const band = bandFor(item) as HelpBandId;
            const tone = toneFor(band);
            const bandLabel = HELP_BANDS.find((candidate) => candidate.id === band)?.label || "Not assessed";
            const description = descriptionFor(item, band);
            return (
              <View
                key={item.activity}
                style={[
                  styles.activityRow,
                  compact && styles.activityRowCompact,
                  index < scored.length - 1 && { borderBottomWidth: 1, borderBottomColor: palette.border },
                ]}
                testID={`daily-activity-card-${item.activity}`}
              >
                <View style={[styles.activityRail, { backgroundColor: tone.accent }]} />
                <View style={styles.activityIcon}>
                  <MaterialCommunityIcons name={ACTIVITY_ICONS[item.activity] || "human"} size={compact ? 44 : 58} color={tone.text} />
                </View>
                <View style={styles.activityCopy}>
                  <Text style={[styles.activityName, compact && styles.activityNameCompact, { color: palette.text }]}>{item.activity}</Text>
                  <Text style={[styles.activityDetail, compact && styles.activityDetailCompact, { color: palette.muted }]}>{description}</Text>
                </View>
                <View
                  style={[styles.statusPill, compact && styles.statusPillCompact, { backgroundColor: tone.badge }]}
                  testID={`daily-activity-status-${item.activity}`}
                >
                  <Ionicons name={tone.icon} size={compact ? 25 : 31} color={tone.text} />
                  <Text style={[styles.statusPillText, compact && styles.statusPillTextCompact, { color: tone.text }]}>{bandLabel}</Text>
                </View>
              </View>
            );
          })}
        </View>
      ) : null}

      {notAssessed.length > 0 ? (
        <View style={[styles.notAssessedRow, { backgroundColor: palette.soft }]} testID="daily-activities-not-assessed">
          <Ionicons name="remove-circle-outline" size={20} color={palette.muted} />
          <Text style={[styles.notAssessedText, { color: palette.muted }]}>Not assessed yet: {notAssessed.map((item) => item.activity).join(", ")}</Text>
        </View>
      ) : null}

      <View style={[styles.footerRow, compact && styles.footerRowCompact]}>
        <Pressable
          accessibilityRole="button"
          onPress={() => setShowMethodology(true)}
          style={({ pressed }) => [styles.methodologyButton, pressed && styles.pressed]}
          testID="daily-activities-methodology"
        >
          <Ionicons name="open-outline" size={21} color="#175A43" />
          <Text style={styles.methodologyText}>How these results are estimated</Text>
        </Pressable>
        {!compact ? <View style={[styles.footerDivider, { backgroundColor: palette.border }]} /> : null}
        <Text style={[styles.footerText, { color: palette.muted }]}>Not assessed activities appear separately.</Text>
      </View>

      <Modal visible={showMethodology} transparent animationType="fade" onRequestClose={() => setShowMethodology(false)}>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="daily-activities-methodology-modal">
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: palette.text }]}>How these results are estimated</Text>
              <Pressable accessibilityLabel="Close estimation details" onPress={() => setShowMethodology(false)} style={({ pressed }) => [styles.closeButton, pressed && styles.pressed]}>
                <Ionicons name="close-outline" size={26} color={palette.text} />
              </Pressable>
            </View>
            <Text style={[styles.modalBody, { color: palette.muted }]}>Estimated results use your survey answers about movement and the help you receive. Observed results also use relevant completed assessment tasks.</Text>
            <Text style={[styles.modalBody, { color: palette.muted }]}>If Rehyn does not have enough information for an activity, it stays not assessed instead of being shown as a low result.</Text>
            <Pressable onPress={() => setShowMethodology(false)} style={({ pressed }) => [styles.modalDone, pressed && styles.pressed]}>
              <Text style={styles.modalDoneText}>Done</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const CACHE_KEY = "daily-activities";

export function DailyActivitiesPanel({ title, sectionHeading }: { title?: string; sectionHeading?: boolean } = {}) {
  const cached = getScreenCache<ActivityMetric[]>(CACHE_KEY);
  const [activities, setActivities] = useState<ActivityMetric[] | null>(cached ?? null);

  const load = useCallback(async () => {
    const response = await authedFetch("/api/progress/summary").catch(() => null);
    if (!response?.ok) return;
    const payload = await response.json().catch(() => null);
    const items = payload?.daily_activities?.activities as ActivityMetric[] | undefined;
    if (items) {
      setActivities(items);
      setScreenCache<ActivityMetric[]>(CACHE_KEY, items);
    }
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));
  if (!activities || activities.length === 0) return null;
  return <DailyActivitiesBoard activities={activities} title={title} sectionHeading={sectionHeading} />;
}

const styles = StyleSheet.create({
  panel: { borderWidth: 1.5, borderRadius: radius.md, padding: 36, gap: spacing.lg, marginBottom: spacing.md },
  panelCompact: { padding: spacing.lg, gap: spacing.md },
  headerRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.lg },
  headerRowCompact: { flexDirection: "column" },
  headerCopy: { flex: 1, minWidth: 0 },
  title: { fontSize: 44, lineHeight: 52, fontWeight: "900" },
  titleSection: { fontSize: 27, lineHeight: 34 },
  titleCompact: { fontSize: 30, lineHeight: 37 },
  subtitle: { marginTop: 8, fontSize: 21, lineHeight: 29 },
  subtitleCompact: { fontSize: 16, lineHeight: 23 },
  sourceBadge: { minHeight: 56, flexDirection: "row", alignItems: "center", gap: 9, paddingHorizontal: 20, borderRadius: radius.pill, backgroundColor: "#FFECC1" },
  sourceBadgeText: { fontSize: 18, lineHeight: 24, fontWeight: "900", color: "#8A5700" },
  sourceBadgeTextCompact: { fontSize: 14, lineHeight: 20 },
  summaryRow: { minHeight: 42, flexDirection: "row", alignItems: "center", gap: spacing.md },
  summaryText: { flex: 1, fontSize: 20, lineHeight: 28, fontWeight: "500" },
  summaryTextCompact: { fontSize: 16, lineHeight: 24 },
  activityList: { borderWidth: 1, borderRadius: radius.md, overflow: "hidden" },
  activityRow: { minHeight: 122, flexDirection: "row", alignItems: "center", gap: spacing.lg, paddingHorizontal: spacing.xl, paddingVertical: spacing.md, position: "relative" },
  activityRowCompact: { minHeight: 0, flexWrap: "wrap", gap: spacing.md, paddingHorizontal: spacing.md, paddingVertical: spacing.lg },
  activityRail: { position: "absolute", left: 0, top: 5, bottom: 5, width: 7 },
  activityIcon: { width: 104, alignItems: "center", justifyContent: "center" },
  activityCopy: { flex: 1, minWidth: 220 },
  activityName: { fontSize: 27, lineHeight: 34, fontWeight: "900" },
  activityNameCompact: { fontSize: 21, lineHeight: 27 },
  activityDetail: { marginTop: 4, fontSize: 19, lineHeight: 27 },
  activityDetailCompact: { fontSize: 15, lineHeight: 22 },
  statusPill: { width: 290, minHeight: 68, borderRadius: radius.pill, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.md },
  statusPillCompact: { width: "100%", minWidth: 0, minHeight: 48, marginLeft: 0 },
  statusPillText: { fontSize: 21, lineHeight: 27, fontWeight: "900" },
  statusPillTextCompact: { fontSize: 17, lineHeight: 23 },
  notAssessedRow: { minHeight: 48, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  notAssessedText: { flex: 1, fontSize: 14, lineHeight: 20, fontWeight: "600" },
  footerRow: { minHeight: 38, flexDirection: "row", alignItems: "center", gap: spacing.lg },
  footerRowCompact: { alignItems: "flex-start", flexDirection: "column", gap: spacing.sm },
  methodologyButton: { minHeight: 42, flexDirection: "row", alignItems: "center", gap: 9 },
  methodologyText: { color: "#154F3C", fontSize: 17, lineHeight: 23, fontWeight: "900", textDecorationLine: "underline" },
  footerDivider: { width: 1, height: 30 },
  footerText: { flex: 1, fontSize: 17, lineHeight: 23 },
  pressed: { opacity: 0.65 },
  modalBackdrop: { flex: 1, backgroundColor: "rgba(9, 22, 16, 0.46)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  modalCard: { width: "100%", maxWidth: 560, borderWidth: 1, borderRadius: radius.md, padding: spacing.lg, gap: spacing.md },
  modalHeader: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  modalTitle: { flex: 1, fontSize: 23, lineHeight: 29, fontWeight: "900" },
  closeButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  modalBody: { fontSize: 16, lineHeight: 24 },
  modalDone: { minHeight: 48, marginTop: spacing.sm, borderRadius: radius.sm, backgroundColor: "#0B6547", alignItems: "center", justifyContent: "center" },
  modalDoneText: { color: "#FFFFFF", fontSize: 16, fontWeight: "900" },
});
