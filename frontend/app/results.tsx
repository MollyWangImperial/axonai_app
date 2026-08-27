import { useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { fetchPatientAssessmentSummary, PatientAssessmentSummary } from "@/src/api";

function formatDuration(durationMs: number) {
  const totalMinutes = Math.max(1, Math.round(durationMs / 60000));
  return `${totalMinutes} min`;
}

function formatAverageTaskTime(durationMs: number) {
  if (durationMs < 60000) return `${Math.max(1, Math.round(durationMs / 1000))} sec`;
  return `${Math.max(1, Math.round(durationMs / 60000))} min`;
}

function domainStatusLabel(status: string) {
  if (status === "no_observable_difficulty") return "No difficulty observed";
  if (status === "review_recommended") return "Review recommended";
  if (status === "not_observed") return "Not observed";
  return "Analysis in progress";
}

export default function ResultsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<PatientAssessmentSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        if (id) {
          const next = await fetchPatientAssessmentSummary(id);
          if (cancelled) return;
          setData(next);
          if (next.clinical_review_gate?.status === "awaiting_model_analysis") {
            refreshTimer = setTimeout(load, 5000);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
      if (refreshTimer) clearTimeout(refreshTimer);
    };
  }, [id]);

  const areaLabel = useMemo(() => {
    if (!data?.collection.domains.length) return "Movement";
    return data.collection.domains.map((domain) => domain.label).join(", ");
  }, [data]);

  const goPlan = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({ pathname: "/designing-plan", params: { id } });
  };

  const reviewGate = data?.clinical_review_gate;
  const rehabBlocked = reviewGate?.rehab_access === "blocked";
  const noRehabNeeded = reviewGate?.rehab_access === "not_needed" || reviewGate?.status === "no_rehab_needed";
  const awaitingAnalysis = reviewGate?.status === "awaiting_model_analysis";
  const canViewPlan = data?.rehab_plan_ready === true && reviewGate?.rehab_access === "allowed";

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
        <Text style={styles.loadingText}>Saving your assessment...</Text>
      </View>
    );
  }

  if (!data) {
    return (
      <View style={[styles.container, styles.center]}>
        <Text style={styles.errorText}>We could not load your summary.</Text>
        <Pressable onPress={() => router.replace("/")} style={[styles.cta, { marginTop: spacing.md }]}>
          <Text style={styles.ctaText}>Back home</Text>
        </Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.replace("/")} style={styles.headerButton} testID="results-home">
          <Ionicons name="home-outline" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Assessment Summary</Text>
        <View style={styles.headerButton} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.heroCard} testID="results-summary">
          <View style={styles.completeIcon}>
            <Ionicons name="checkmark" size={30} color={colors.onBrandPrimary} />
          </View>
          <Text style={styles.heroTitle}>Your task collection is complete</Text>
          <Text style={styles.heroSub}>
            {noRehabNeeded
              ? "Your movement summary is ready. No rehabilitation plan is recommended from this assessment."
              : awaitingAnalysis
                ? "Your recordings are saved. Your movement metrics are ready while the validated analysis finishes."
                : "Your movement summary is ready. Review each area before opening your rehabilitation plan."}
          </Text>
        </View>

        <Text style={styles.sectionTitle}>Body function summary</Text>
        <View style={styles.functionList} testID="body-function-summary">
          {data.body_function_summary.domains.map((domain) => {
            const normal = domain.status === "no_observable_difficulty";
            const review = domain.status === "review_recommended";
            return (
              <View key={domain.domain} style={styles.functionCard} testID={`body-function-${domain.domain}`}>
                <View style={styles.functionHeader}>
                  <Text style={styles.functionTitle}>{domain.label}</Text>
                  <View style={[styles.statusBadge, normal && styles.statusBadgeNormal, review && styles.statusBadgeReview]}>
                    <Text style={[styles.statusText, normal && styles.statusTextNormal, review && styles.statusTextReview]}>
                      {domainStatusLabel(domain.status)}
                    </Text>
                  </View>
                </View>
                <Text style={styles.functionSummary}>{domain.summary}</Text>
                <View style={styles.functionMetrics}>
                  <View style={styles.functionMetric}>
                    <Text style={styles.functionMetricValue}>{domain.tasks_completed}/{domain.tasks_observed}</Text>
                    <Text style={styles.functionMetricLabel}>Tasks completed</Text>
                  </View>
                  <View style={styles.functionMetric}>
                    <Text style={styles.functionMetricValue}>{domain.step_completion_percent}%</Text>
                    <Text style={styles.functionMetricLabel}>Guided steps</Text>
                  </View>
                  <View style={styles.functionMetric}>
                    <Text style={styles.functionMetricValue}>{formatAverageTaskTime(domain.average_task_duration_ms)}</Text>
                    <Text style={styles.functionMetricLabel}>Average task</Text>
                  </View>
                  <View style={styles.functionMetric}>
                    <Text style={styles.functionMetricValue}>{domain.findings_count}</Text>
                    <Text style={styles.functionMetricLabel}>Findings to review</Text>
                  </View>
                </View>
              </View>
            );
          })}
        </View>

        <Text style={styles.sectionTitle}>Task collection</Text>
        <View style={styles.metricsGrid} testID="collection-metrics">
          <View style={styles.metricCard}>
            <Ionicons name="videocam-outline" size={22} color={colors.brandPrimary} />
            <Text style={styles.metricValue}>
              {data.collection.tasks_collected}/{data.collection.tasks_expected}
            </Text>
            <Text style={styles.metricLabel}>Tasks collected</Text>
          </View>
          <View style={styles.metricCard}>
            <Ionicons name="checkmark-done-outline" size={22} color={colors.brandPrimary} />
            <Text style={styles.metricValue}>{data.collection.completion_percent}%</Text>
            <Text style={styles.metricLabel}>Guided steps completed</Text>
          </View>
          <View style={styles.metricCard}>
            <Ionicons name="time-outline" size={22} color={colors.brandPrimary} />
            <Text style={styles.metricValue}>{formatDuration(data.collection.duration_ms)}</Text>
            <Text style={styles.metricLabel}>Collection time</Text>
          </View>
          <View style={styles.metricCard}>
            <Ionicons name="body-outline" size={22} color={colors.brandPrimary} />
            <Text style={styles.metricValue}>{data.collection.domains.length}</Text>
            <Text style={styles.metricLabel}>Areas observed</Text>
          </View>
        </View>

        <View style={styles.observedCard} testID="collection-areas">
          <View style={styles.observedIcon}>
            <Ionicons name="eye-outline" size={22} color={colors.brandPrimary} />
          </View>
          <View style={styles.observedCopy}>
            <Text style={styles.observedTitle}>Movement areas collected</Text>
            <Text style={styles.observedText}>{areaLabel}</Text>
          </View>
        </View>

        <View style={styles.nextCard}>
          <Ionicons name="shield-checkmark-outline" size={24} color={colors.brandPrimary} />
          <View style={styles.nextCopy}>
            <Text style={styles.nextTitle}>What happens next</Text>
            <Text style={styles.nextText}>
              {noRehabNeeded
                ? "No exercises are being generated because no observable difficulty was detected in the assessed tasks. Contact your therapist if symptoms continue or your function changes."
                : awaitingAnalysis
                  ? "We will not generate a rehabilitation plan until the validated movement analysis is complete."
                  : "A rehabilitation plan is generated only for movement findings that need support."}
            </Text>
          </View>
        </View>

        {(rehabBlocked || noRehabNeeded) && (
          <View style={styles.reviewCard} testID={noRehabNeeded ? "no-rehab-needed" : "clinical-review-hold"}>
            <View style={styles.reviewIcon}>
              <Ionicons
                name={noRehabNeeded ? "checkmark-circle-outline" : awaitingAnalysis ? "hourglass-outline" : "people-outline"}
                size={24}
                color={colors.brandPrimary}
              />
            </View>
            <View style={styles.nextCopy}>
              <Text style={styles.reviewTitle}>{reviewGate?.patient_title}</Text>
              <Text style={styles.reviewText}>{reviewGate?.patient_message}</Text>
              <Text style={styles.reviewNext}>{reviewGate?.next_step}</Text>
            </View>
          </View>
        )}
      </ScrollView>

      <View style={[styles.ctaBar, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable
          onPress={canViewPlan ? goPlan : () => router.replace("/")}
          style={styles.cta}
          testID={canViewPlan ? "results-view-plan" : "results-return-home"}
        >
          <Ionicons name={canViewPlan ? "clipboard-outline" : "home-outline"} size={22} color={colors.onBrandPrimary} />
          <Text style={styles.ctaText}>{canViewPlan ? "View Rehab Plan" : "Return Home"}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center", padding: spacing.lg },
  loadingText: { marginTop: spacing.md, color: colors.onSurfaceSecondary },
  errorText: { color: colors.error, textAlign: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.sm,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
  },
  headerButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  content: { padding: spacing.lg, paddingBottom: 140 },
  heroCard: {
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.md,
    padding: spacing.lg,
    alignItems: "center",
    marginBottom: spacing.xl,
  },
  completeIcon: {
    width: 58,
    height: 58,
    borderRadius: 29,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.success,
    marginBottom: spacing.md,
  },
  heroTitle: { fontSize: 23, fontWeight: "800", color: colors.onBrandTertiary, textAlign: "center" },
  heroSub: { color: colors.onBrandTertiary, fontSize: 15, textAlign: "center", lineHeight: 22, marginTop: spacing.sm },
  sectionTitle: { fontSize: 20, fontWeight: "800", color: colors.onSurface, marginBottom: spacing.md },
  functionList: { gap: spacing.md, marginBottom: spacing.xl },
  functionCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
  },
  functionHeader: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.sm },
  functionTitle: { flex: 1, fontSize: 18, fontWeight: "800", color: colors.onSurface },
  statusBadge: { maxWidth: "55%", backgroundColor: colors.brandTertiary, borderRadius: radius.sm, paddingHorizontal: 9, paddingVertical: 5 },
  statusBadgeNormal: { backgroundColor: colors.brandTertiary },
  statusBadgeReview: { backgroundColor: "#FFF0E1" },
  statusText: { color: colors.brandPrimary, fontSize: 11, lineHeight: 15, fontWeight: "700", textAlign: "center" },
  statusTextNormal: { color: colors.success },
  statusTextReview: { color: colors.warning },
  functionSummary: { color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 20, marginTop: spacing.sm },
  functionMetrics: { flexDirection: "row", flexWrap: "wrap", marginTop: spacing.md, rowGap: spacing.md },
  functionMetric: { width: "50%", paddingRight: spacing.sm },
  functionMetricValue: { color: colors.onSurface, fontSize: 18, lineHeight: 23, fontWeight: "800" },
  functionMetricLabel: { color: colors.onSurfaceSecondary, fontSize: 12, lineHeight: 17, marginTop: 2 },
  metricsGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.lg },
  metricCard: {
    width: "48%",
    minHeight: 132,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.md,
    justifyContent: "space-between",
  },
  metricValue: { fontSize: 24, fontWeight: "800", color: colors.onSurface, marginTop: spacing.sm },
  metricLabel: { fontSize: 13, lineHeight: 18, color: colors.onSurfaceSecondary },
  observedCard: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.divider,
    paddingVertical: spacing.lg,
  },
  observedIcon: {
    width: 46,
    height: 46,
    borderRadius: 23,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brandTertiary,
  },
  observedCopy: { flex: 1 },
  observedTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  observedText: { fontSize: 14, lineHeight: 20, color: colors.onSurfaceSecondary, marginTop: 3 },
  nextCard: {
    flexDirection: "row",
    gap: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.sm,
    padding: spacing.md,
    marginTop: spacing.xl,
  },
  nextCopy: { flex: 1 },
  nextTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: 4 },
  nextText: { color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 20 },
  reviewCard: {
    flexDirection: "row",
    gap: spacing.md,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.sm,
    padding: spacing.md,
    marginTop: spacing.lg,
  },
  reviewIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
  },
  reviewTitle: { fontSize: 17, fontWeight: "800", color: colors.onBrandTertiary, marginBottom: 6 },
  reviewText: { color: colors.onBrandTertiary, fontSize: 14, lineHeight: 20 },
  reviewNext: { color: colors.onBrandTertiary, fontSize: 14, lineHeight: 20, fontWeight: "700", marginTop: spacing.sm },
  ctaBar: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    padding: spacing.md,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  cta: {
    flexDirection: "row",
    gap: spacing.sm,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.md,
    padding: spacing.md,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 56,
  },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "700" },
});
