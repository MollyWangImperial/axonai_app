import { useCallback, useState } from "react";
import { StyleSheet, Text, View } from "react-native";
import { useFocusEffect } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { authedFetch } from "@/src/auth";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { colors, radius, spacing } from "@/src/theme";

// Spec section 6: after an assessment, the FIRST thing the patient sees is
// what it means for daily life - activities and the help needed - with honest
// complete / estimated / not-assessed labels, never raw biomechanics.

type ActivityMetric = {
  activity: string;
  status: "complete" | "estimated" | "not_assessed";
  observed?: string | null;
  reported_assistance_level?: string | null;
  change_from_baseline?: string | null;
};

const ASSISTANCE_LABELS: Record<string, string> = {
  unable: "Unable / not safely attempted",
  maximum_assistance: "Maximum assistance",
  moderate_assistance: "Moderate assistance",
  minimum_assistance: "Minimum assistance",
  supervision_only: "Supervision only",
  fully_independent: "Fully independent",
};

const STATUS_PRESENTATION = {
  complete: { label: "Observed", color: "#1F7047", background: "#E2F1E7", icon: "checkmark-circle" as const },
  estimated: { label: "Estimated from your answers", color: "#6B4A0B", background: "#FFF4DA", icon: "ellipse-outline" as const },
  not_assessed: { label: "Not assessed", color: "#5D6962", background: "#EAEDEA", icon: "remove-circle-outline" as const },
};

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

  return (
    <View style={styles.card} testID="daily-activities-panel">
      <Text style={styles.title}>What this means for daily life</Text>
      <Text style={styles.subtitle}>Your results as everyday activities and the help needed. Anything not assessed stays honestly blank - it is never turned into a low score.</Text>
      {activities.map((item) => {
        const presentation = STATUS_PRESENTATION[item.status] ?? STATUS_PRESENTATION.not_assessed;
        const detail = item.observed
          || (item.reported_assistance_level ? `Reported level of help: ${ASSISTANCE_LABELS[item.reported_assistance_level] || item.reported_assistance_level}` : "No observation or report yet.");
        return (
          <View key={item.activity} style={styles.row}>
            <View style={styles.rowTop}>
              <Text style={styles.activity}>{item.activity}</Text>
              <View style={[styles.badge, { backgroundColor: presentation.background }]}>
                <Ionicons name={presentation.icon} size={13} color={presentation.color} />
                <Text style={[styles.badgeText, { color: presentation.color }]}>{presentation.label}</Text>
              </View>
            </View>
            <Text style={styles.detail}>{detail}</Text>
            {item.change_from_baseline ? (
              <Text style={styles.change}>
                <Ionicons name="trending-up-outline" size={13} color={colors.success} /> {item.change_from_baseline}
              </Text>
            ) : null}
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#D9DEDA", borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, marginBottom: spacing.md },
  title: { fontSize: 19, lineHeight: 25, fontWeight: "800", color: "#17211B" },
  subtitle: { fontSize: 13, lineHeight: 19, color: "#5D6962" },
  row: { borderTopWidth: 1, borderTopColor: "#ECEFEC", paddingTop: spacing.sm, gap: 4 },
  rowTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  activity: { fontSize: 15, fontWeight: "800", color: "#17211B", flexShrink: 1 },
  badge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill },
  badgeText: { fontSize: 11, fontWeight: "800" },
  detail: { fontSize: 14, lineHeight: 20, color: "#35443C" },
  change: { fontSize: 13, lineHeight: 18, color: colors.success, fontWeight: "700" },
});
