import { useCallback, useState } from "react";
import { StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { authedFetch } from "@/src/auth";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { radius, spacing } from "@/src/theme";

// Spec section 6, presented as "Daily life at a glance": a simple card per
// activity with a four-band help meter - Full help, A lot of help, A little
// help, Independent. Anything not assessed appears separately underneath,
// never as a low score.

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

const BAND_INDEX: Record<HelpBandId, number> = {
  full_help: 0,
  a_lot_of_help: 1,
  a_little_help: 2,
  independent: 3,
};

// The six-level reported assistance scale folds into the four patient-facing
// help bands; an observed row without a report falls back to its qualitative
// weak / medium / normal score.
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

const HELP_TONE = { text: "#B06A00", border: "#E4C388", cardBackground: "#FBF3E2", fill: "#D98A00" };
const WELL_TONE = { text: "#1F6A4A", border: "#BFD6C6", cardBackground: "#EAF2EC", fill: "#2E7D57" };

const BAND_DESCRIPTIONS: Record<HelpBandId, { estimated: string; observed: string }> = {
  full_help: {
    estimated: "Someone may need to help with most of this activity.",
    observed: "Most of this activity needed hands-on help in the assessment.",
  },
  a_lot_of_help: {
    estimated: "Hands-on support may be needed for much of this activity.",
    observed: "Much of this activity needed hands-on support in the assessment.",
  },
  a_little_help: {
    estimated: "A little help or someone nearby may be needed.",
    observed: "Only a little help was needed in the assessment.",
  },
  independent: {
    estimated: "You reported managing this activity on your own.",
    observed: "You managed this activity on your own in the assessment.",
  },
};

const ACTIVITY_ICONS: Record<string, keyof typeof Ionicons.glyphMap> = {
  "Eating and drinking": "restaurant-outline",
  "Dressing": "shirt-outline",
  "Grooming and self-care": "brush-outline",
  "Moving around": "walk-outline",
};

function bandFor(item: ActivityMetric): HelpBandId | null {
  if (item.reported_assistance_level && ASSISTANCE_TO_BAND[item.reported_assistance_level]) {
    return ASSISTANCE_TO_BAND[item.reported_assistance_level];
  }
  if (item.qualitative_score && QUALITATIVE_TO_BAND[item.qualitative_score]) {
    return QUALITATIVE_TO_BAND[item.qualitative_score];
  }
  return null;
}

export function DailyActivitiesBoard({ activities }: { activities: ActivityMetric[] }) {
  const { width } = useWindowDimensions();
  const twoColumns = width >= 700;
  const scored = activities.filter((item) => item.status !== "not_assessed" && bandFor(item));
  const notAssessed = activities.filter((item) => item.status === "not_assessed" || !bandFor(item));
  const allObserved = scored.length > 0 && scored.every((item) => item.status === "complete");
  const anyObserved = scored.some((item) => item.status === "complete");
  const sourceBadge = allObserved
    ? "Observed in your assessment"
    : anyObserved
      ? "Observed and estimated"
      : "Estimated from your answers";

  return (
    <View style={styles.card} testID="daily-activities-panel">
      <View style={styles.headerRow}>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>Daily life at a glance</Text>
          <Text style={styles.subtitle}>A simple view of where you may need help.</Text>
        </View>
        {scored.length > 0 && (
          <View style={styles.sourceBadge} testID="daily-activities-source-badge">
            <Ionicons name="ellipse-outline" size={12} color="#6B4A0B" />
            <Text style={styles.sourceBadgeText}>{sourceBadge}</Text>
          </View>
        )}
      </View>

      <View style={styles.legendRow} testID="daily-activities-legend">
        {HELP_BANDS.map((band) => {
          const helping = band.id === "full_help" || band.id === "a_lot_of_help";
          const tone = helping ? HELP_TONE : WELL_TONE;
          return (
            <View key={band.id} style={styles.legendItem}>
              <View
                style={[
                  styles.legendSwatch,
                  { borderColor: band.id === "independent" ? tone.text : tone.border },
                  band.id === "full_help" && { backgroundColor: HELP_TONE.fill, borderColor: HELP_TONE.fill },
                  band.id === "a_little_help" && { backgroundColor: WELL_TONE.cardBackground },
                ]}
              />
              <Text style={styles.legendLabel}>{band.label}</Text>
            </View>
          );
        })}
      </View>

      <View style={[styles.grid, twoColumns && styles.gridWide]}>
        {scored.map((item) => {
          const band = bandFor(item) as HelpBandId;
          const bandIndex = BAND_INDEX[band];
          const helping = band === "full_help" || band === "a_lot_of_help";
          const tone = helping ? HELP_TONE : WELL_TONE;
          const bandLabel = HELP_BANDS[bandIndex].label;
          const description = item.observed && item.status === "complete"
            ? BAND_DESCRIPTIONS[band].observed
            : BAND_DESCRIPTIONS[band].estimated;
          return (
            <View
              key={item.activity}
              style={[styles.activityCard, { backgroundColor: tone.cardBackground, borderColor: tone.border }, twoColumns && styles.activityCardWide]}
              testID={`daily-activity-card-${item.activity}`}
            >
              <View style={styles.activityIcon}>
                <Ionicons name={ACTIVITY_ICONS[item.activity] || "body-outline"} size={44} color={tone.text} />
              </View>
              <View style={styles.activityCopy}>
                <Text style={styles.activityName}>{item.activity}</Text>
                <View style={styles.bandRow}>
                  <Text style={[styles.activityBand, { color: tone.text }]}>{bandLabel}</Text>
                  {typeof item.score === "number" && (
                    <View style={[styles.scorePill, { borderColor: tone.border }]} testID={`daily-activity-score-${item.activity}`}>
                      <Text style={[styles.scorePillText, { color: tone.text }]}>{item.score}</Text>
                      <Text style={styles.scorePillScale}>/ 100</Text>
                    </View>
                  )}
                </View>
                <Text style={styles.activityDetail}>{description}</Text>
                <View style={styles.meterRow} testID={`daily-activity-meter-${item.activity}`}>
                  {HELP_BANDS.map((meterBand, index) => (
                    <View
                      key={meterBand.id}
                      style={[
                        styles.meterSegment,
                        { borderColor: tone.border },
                        index === bandIndex && { backgroundColor: tone.fill, borderColor: tone.fill },
                      ]}
                    />
                  ))}
                </View>
                <Text style={[styles.meterLabel, { color: tone.text }]}>{bandLabel}</Text>
                {item.change_from_baseline ? (
                  <Text style={styles.change}>
                    <Ionicons name="trending-up-outline" size={13} color={WELL_TONE.text} /> {item.change_from_baseline}
                  </Text>
                ) : null}
              </View>
            </View>
          );
        })}
      </View>

      {notAssessed.length > 0 && (
        <View style={styles.notAssessedRow} testID="daily-activities-not-assessed">
          <Ionicons name="remove-circle-outline" size={15} color="#5D6962" />
          <Text style={styles.notAssessedText}>
            Not assessed yet: {notAssessed.map((item) => item.activity).join(", ")}
          </Text>
        </View>
      )}

      <View style={styles.footerRow}>
        <Ionicons name="leaf-outline" size={14} color="#3E5C4A" />
        <Text style={styles.footerText}>Not assessed appears separately — never as a low score.</Text>
      </View>
    </View>
  );
}

const CACHE_KEY = "daily-activities";

export function DailyActivitiesPanel() {
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

  return <DailyActivitiesBoard activities={activities} />;
}

const styles = StyleSheet.create({
  card: { backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#D9DEDA", borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, marginBottom: spacing.md },
  headerRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.sm, flexWrap: "wrap" },
  headerCopy: { flexShrink: 1, minWidth: 200 },
  title: { fontSize: 22, lineHeight: 28, fontWeight: "800", color: "#17211B" },
  subtitle: { fontSize: 13, lineHeight: 19, color: "#5D6962", marginTop: 2 },
  sourceBadge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 10, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: "#FFF4DA" },
  sourceBadgeText: { fontSize: 11, fontWeight: "800", color: "#6B4A0B" },
  legendRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, flexWrap: "wrap" },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendSwatch: { width: 26, height: 14, borderRadius: 5, borderWidth: 1.5, backgroundColor: "#FFFFFF" },
  legendLabel: { fontSize: 12, fontWeight: "700", color: "#35443C" },
  grid: { gap: spacing.sm },
  gridWide: { flexDirection: "row", flexWrap: "wrap" },
  activityCard: { flexDirection: "row", gap: spacing.md, alignItems: "center", borderWidth: 1, borderRadius: radius.md, padding: spacing.md },
  activityCardWide: { flexBasis: "48.5%", flexGrow: 1 },
  activityIcon: { width: 72, alignItems: "center", justifyContent: "center" },
  activityCopy: { flex: 1, minWidth: 0 },
  activityName: { fontSize: 15, fontWeight: "800", color: "#17211B" },
  activityBand: { fontSize: 26, lineHeight: 32, fontWeight: "900" },
  bandRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" },
  scorePill: { flexDirection: "row", alignItems: "baseline", gap: 2, borderWidth: 1.5, borderRadius: radius.pill, paddingHorizontal: 10, paddingVertical: 2, backgroundColor: "#FFFFFF" },
  scorePillText: { fontSize: 17, fontWeight: "900" },
  scorePillScale: { fontSize: 11, fontWeight: "700", color: "#5D6962" },
  activityDetail: { fontSize: 13, lineHeight: 18, color: "#35443C", marginTop: 2 },
  meterRow: { flexDirection: "row", gap: 6, marginTop: spacing.sm },
  meterSegment: { flex: 1, maxWidth: 64, height: 18, borderRadius: 9, borderWidth: 1.5, backgroundColor: "#FFFFFF" },
  meterLabel: { fontSize: 12, fontWeight: "800", marginTop: 4 },
  change: { fontSize: 13, lineHeight: 18, color: "#2E7D57", fontWeight: "700", marginTop: 4 },
  notAssessedRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingTop: 2 },
  notAssessedText: { flex: 1, fontSize: 13, lineHeight: 18, color: "#5D6962", fontWeight: "600" },
  footerRow: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingTop: 2 },
  footerText: { fontSize: 12, lineHeight: 17, color: "#3E5C4A", fontWeight: "700" },
});
