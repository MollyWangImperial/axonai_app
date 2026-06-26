import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { fetchAssessment, Assessment } from "@/src/api";

const SEVERITY_COLORS: Record<string, string> = {
  mild: colors.warning,
  moderate: colors.brandSecondary,
  severe: colors.error,
};

export default function ResultsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        if (id) setData(await fetchAssessment(id));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const goPlan = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({ pathname: "/designing-plan", params: { id } });
  };

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
        <Text style={{ marginTop: spacing.md, color: colors.onSurfaceSecondary }}>Analyzing your movement…</Text>
      </View>
    );
  }
  if (!data) {
    return (
      <View style={[styles.container, styles.center]}>
        <Text style={{ color: colors.error }}>No results found.</Text>
        <Pressable onPress={() => router.replace("/")} style={[styles.cta, { marginTop: 16 }]}>
          <Text style={styles.ctaText}>Back home</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.replace("/")} style={styles.backBtn} testID="results-home">
          <Ionicons name="home" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Your Results</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }}>
        <View style={styles.heroCard} testID="results-summary">
          <Ionicons name="checkmark-circle" size={32} color={colors.success} />
          <Text style={styles.heroTitle}>Assessment complete</Text>
          <Text style={styles.heroSub}>
            We identified {data.functional_issues.length} focus area{data.functional_issues.length === 1 ? "" : "s"} for your recovery.
          </Text>
        </View>

        <Text style={styles.sectionTitle}>Functional issues identified</Text>
        {data.functional_issues.map((iss) => (
          <View key={iss.code} style={styles.issueCard} testID={`issue-${iss.code}`}>
            <View style={styles.issueHead}>
              <View style={[styles.sevDot, { backgroundColor: SEVERITY_COLORS[iss.severity] || colors.brandPrimary }]} />
              <Text style={styles.issueLabel}>{iss.label}</Text>
              <Text style={styles.issueSeverity}>{iss.severity}</Text>
            </View>
            <Text style={styles.issueDesc}>{iss.description}</Text>
            <Text style={styles.issueSource}>Source: {iss.source} · Task {iss.related_task}</Text>
          </View>
        ))}

        <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>What's next</Text>
        <View style={styles.nextCard}>
          <Ionicons name="medical" size={20} color={colors.brandPrimary} />
          <Text style={styles.nextText}>
            Your personalized rehabilitation plan includes {data.rehab_plan.length} evidence-based exercises drawn from established stroke rehabilitation sources.
          </Text>
        </View>
      </ScrollView>

      <View style={[styles.ctaBar, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable onPress={goPlan} style={styles.cta} testID="results-view-plan">
          <Ionicons name="clipboard" size={22} color={colors.onBrandPrimary} />
          <Text style={styles.ctaText}>View Rehab Plan</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  heroCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, alignItems: "center", marginBottom: spacing.lg, gap: spacing.xs },
  heroTitle: { fontSize: 22, fontWeight: "800", color: colors.onBrandTertiary, marginTop: spacing.xs },
  heroSub: { color: colors.onBrandTertiary, fontSize: 15, textAlign: "center", lineHeight: 22 },
  sectionTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  issueCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.sm, gap: 6 },
  issueHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  sevDot: { width: 10, height: 10, borderRadius: 5 },
  issueLabel: { flex: 1, fontSize: 16, fontWeight: "700", color: colors.onSurface },
  issueSeverity: { fontSize: 11, fontWeight: "700", color: colors.onSurfaceTertiary, textTransform: "uppercase" },
  issueDesc: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
  issueSource: { fontSize: 12, color: colors.onSurfaceTertiary, fontStyle: "italic", marginTop: 4 },
  nextCard: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, alignItems: "flex-start" },
  nextText: { flex: 1, color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 20 },
  ctaBar: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  cta: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.md, alignItems: "center", justifyContent: "center", minHeight: 56 },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "700" },
});
