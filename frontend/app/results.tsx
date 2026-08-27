import { useEffect, useMemo, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, useWindowDimensions } from "react-native";
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

function percentWidth(value: number): `${number}%` {
  return `${Math.max(2, Math.min(100, Math.round(value)))}%`;
}

const ANALYSIS_LABELS: Record<string, string> = {
  task_collection: "Tasks saved",
  musculoskeletal_analysis: "Movement model",
  patient_insights: "Insights",
  rehab_plan: "Plan decision",
};

export default function ResultsScreen() {
  const insets = useSafeAreaInsets();
  const { width: viewportWidth } = useWindowDimensions();
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
            refreshTimer = setTimeout(load, next.insights?.status === "processing" ? 5000 : 15000);
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
  const insights = data?.insights;

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
        <View style={[styles.report, { width: Math.min(Math.max(viewportWidth - 48, 280), 960) }]}>
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

        {insights && (
          <View testID="movement-insights">
            <View style={styles.insightHeadingRow}>
              <Text style={styles.sectionTitle}>Your movement insights</Text>
              <View style={[
                styles.insightBadge,
                insights.status === "needs_review" && styles.insightBadgeWarning,
                insights.status === "validated" && styles.insightBadgeValidated,
              ]}>
                <Text style={styles.insightBadgeText}>{insights.badge}</Text>
              </View>
            </View>

            <View style={styles.analysisPath} testID="analysis-path">
              {insights.analysis_order.map((stage, index) => {
                const stageComplete = stage === "task_collection"
                  || (stage === "musculoskeletal_analysis" && ["research_ready", "validated"].includes(insights.status))
                  || (stage === "patient_insights" && ["research_ready", "validated"].includes(insights.status))
                  || (stage === "rehab_plan" && !awaitingAnalysis);
                const stageActive = !stageComplete && (
                  (stage === "musculoskeletal_analysis" && insights.status === "processing")
                  || (stage === "patient_insights" && insights.status === "needs_review")
                  || (stage === "rehab_plan" && ["research_ready", "validated"].includes(insights.status))
                );
                return (
                  <View key={stage} style={styles.analysisStep}>
                    <View style={styles.analysisMarkerRow}>
                      <View style={[
                        styles.analysisDot,
                        stageComplete && styles.analysisDotComplete,
                        stageActive && styles.analysisDotActive,
                      ]}>
                        {stageComplete
                          ? <Ionicons name="checkmark" size={13} color={colors.onBrandPrimary} />
                          : <Text style={styles.analysisDotText}>{index + 1}</Text>}
                      </View>
                      {index < insights.analysis_order.length - 1 && (
                        <View style={[styles.analysisLine, stageComplete && styles.analysisLineComplete]} />
                      )}
                    </View>
                    <Text style={[styles.analysisLabel, (stageComplete || stageActive) && styles.analysisLabelActive]}>
                      {ANALYSIS_LABELS[stage] || stage}
                    </Text>
                  </View>
                );
              })}
            </View>

            <View style={styles.insightIntro}>
              <Ionicons
                name={insights.status === "processing" ? "analytics-outline" : "sparkles-outline"}
                size={24}
                color={colors.brandPrimary}
              />
              <View style={styles.insightIntroCopy}>
                <Text style={styles.insightHeadline}>{insights.headline}</Text>
                <Text style={styles.insightSummary}>{insights.summary}</Text>
              </View>
            </View>

            <View style={styles.chartCard} testID="domain-completion-chart">
              <Text style={styles.chartTitle}>Guided task completion by area</Text>
              <Text style={styles.chartSubtitle}>This shows collection completeness, not a clinical function score.</Text>
              {insights.domain_metrics.map((domain) => (
                <View key={domain.domain} style={styles.domainChartRow}>
                  <View style={styles.chartLabelRow}>
                    <Text style={styles.chartLabel}>{domain.label}</Text>
                    <Text style={styles.chartValue}>{domain.completion_percent}%</Text>
                  </View>
                  <View style={styles.chartTrack}>
                    <View style={[styles.chartFill, { width: percentWidth(domain.completion_percent) }]} />
                  </View>
                </View>
              ))}
            </View>

            {insights.activation_profile.length > 0 && (
              <View style={styles.chartCard} testID="activation-profile-chart">
                <Text style={styles.chartTitle}>Modeled muscle demand</Text>
                <Text style={styles.chartSubtitle}>
                  Mean activation estimated during the walking task. Peak values are shown at right.
                </Text>
                <View style={styles.legendRow}>
                  <View style={styles.legendItem}><View style={styles.legendModel} /><Text style={styles.legendText}>Patient model</Text></View>
                  <View style={styles.legendItem}><View style={styles.legendReference} /><Text style={styles.legendText}>Matched template</Text></View>
                </View>
                {insights.activation_profile.map((activation) => (
                  <View key={`${activation.task_id}-${activation.muscle}`} style={styles.activationRow}>
                    <View style={styles.chartLabelRow}>
                      <Text style={styles.activationLabel} numberOfLines={2}>{activation.label}</Text>
                      <Text style={styles.activationPeak}>Peak {Math.round(activation.peak * 100)}%</Text>
                    </View>
                    <View style={styles.activationTrack}>
                      <View style={[styles.activationBar, { width: percentWidth(activation.mean * 100) }]} />
                    </View>
                    {activation.template_mean !== null && (
                      <View style={styles.activationTrack}>
                        <View style={[
                          styles.activationBar,
                          styles.activationReference,
                          { width: percentWidth(activation.template_mean * 100) },
                        ]} />
                      </View>
                    )}
                  </View>
                ))}
                <Text style={styles.coverageNote}>
                  Current muscle modeling coverage: {insights.modeled_domains.map((domain) => domain.replace("_", " ")).join(", ") || "pending"}.
                  Upper-limb and hand results remain camera-derived until equivalent validated models are available.
                </Text>
              </View>
            )}

            {insights.observations.length > 0 && (
              <View style={styles.observations} testID="notable-observations">
                <Text style={styles.chartTitle}>What stood out</Text>
                {insights.observations.map((observation, index) => (
                  <View key={`${observation.title}-${index}`} style={styles.observationRow}>
                    <View style={styles.observationNumber}><Text style={styles.observationNumberText}>{index + 1}</Text></View>
                    <View style={styles.observationCopy}>
                      <Text style={styles.observationTitle}>{observation.title}</Text>
                      <Text style={styles.observationDetail}>{observation.detail}</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}

            <View style={styles.reportingNote}>
              <Ionicons name="information-circle-outline" size={20} color={colors.onSurfaceTertiary} />
              <Text style={styles.reportingText}>{insights.reporting_rule}</Text>
            </View>
          </View>
        )}

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
        </View>
      </ScrollView>

      <View style={[styles.ctaBar, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable
          onPress={canViewPlan ? goPlan : () => router.replace("/")}
          style={[styles.cta, { width: Math.min(Math.max(viewportWidth - 32, 280), 960) }]}
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
  content: { alignItems: "center", paddingVertical: spacing.lg, paddingBottom: 140 },
  report: { alignSelf: "center" },
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
  insightHeadingRow: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  insightBadge: { maxWidth: "100%", backgroundColor: colors.brandTertiary, borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 6, marginBottom: spacing.md },
  insightBadgeWarning: { backgroundColor: "#FFF0E1" },
  insightBadgeValidated: { backgroundColor: "#DDEEDF" },
  insightBadgeText: { color: colors.onBrandTertiary, fontSize: 12, lineHeight: 16, fontWeight: "700" },
  analysisPath: { flexDirection: "row", marginBottom: spacing.lg },
  analysisStep: { flex: 1, minWidth: 0 },
  analysisMarkerRow: { flexDirection: "row", alignItems: "center" },
  analysisDot: { width: 25, height: 25, borderRadius: 13, alignItems: "center", justifyContent: "center", backgroundColor: colors.surfaceTertiary },
  analysisDotComplete: { backgroundColor: colors.success },
  analysisDotActive: { borderWidth: 2, borderColor: colors.brandSecondary, backgroundColor: colors.surface },
  analysisDotText: { color: colors.onSurfaceTertiary, fontSize: 11, fontWeight: "800" },
  analysisLine: { flex: 1, height: 3, backgroundColor: colors.surfaceTertiary },
  analysisLineComplete: { backgroundColor: colors.success },
  analysisLabel: { color: colors.onSurfaceTertiary, fontSize: 10, lineHeight: 14, marginTop: 6, paddingRight: 5 },
  analysisLabelActive: { color: colors.onSurface, fontWeight: "700" },
  insightIntro: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md, backgroundColor: colors.brandTertiary, borderRadius: radius.sm, padding: spacing.md, marginBottom: spacing.md },
  insightIntroCopy: { flex: 1 },
  insightHeadline: { color: colors.onBrandTertiary, fontSize: 17, lineHeight: 22, fontWeight: "800" },
  insightSummary: { color: colors.onBrandTertiary, fontSize: 14, lineHeight: 20, marginTop: 4 },
  chartCard: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary, padding: spacing.md, marginBottom: spacing.md },
  chartTitle: { color: colors.onSurface, fontSize: 17, lineHeight: 22, fontWeight: "800" },
  chartSubtitle: { color: colors.onSurfaceSecondary, fontSize: 13, lineHeight: 18, marginTop: 4, marginBottom: spacing.md },
  domainChartRow: { marginBottom: spacing.md },
  chartLabelRow: { flexDirection: "row", alignItems: "flex-end", justifyContent: "space-between", gap: spacing.sm },
  chartLabel: { flex: 1, color: colors.onSurface, fontSize: 14, lineHeight: 19, fontWeight: "700" },
  chartValue: { color: colors.brandPrimary, fontSize: 14, lineHeight: 19, fontWeight: "800" },
  chartTrack: { height: 12, borderRadius: 6, backgroundColor: colors.surfaceTertiary, overflow: "hidden", marginTop: 7 },
  chartFill: { height: "100%", borderRadius: 6, backgroundColor: colors.brandPrimary },
  legendRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginBottom: spacing.md },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  legendModel: { width: 18, height: 7, borderRadius: 4, backgroundColor: colors.brandPrimary },
  legendReference: { width: 18, height: 7, borderRadius: 4, backgroundColor: colors.brandSecondary },
  legendText: { color: colors.onSurfaceSecondary, fontSize: 12 },
  activationRow: { marginBottom: spacing.md },
  activationLabel: { flex: 1, color: colors.onSurface, fontSize: 14, lineHeight: 18, fontWeight: "700", paddingRight: spacing.sm },
  activationPeak: { color: colors.onSurfaceSecondary, fontSize: 12, lineHeight: 17, fontWeight: "700" },
  activationTrack: { height: 8, borderRadius: 4, backgroundColor: colors.surfaceTertiary, overflow: "hidden", marginTop: 5 },
  activationBar: { height: "100%", borderRadius: 4, backgroundColor: colors.brandPrimary },
  activationReference: { backgroundColor: colors.brandSecondary },
  coverageNote: { color: colors.onSurfaceSecondary, fontSize: 12, lineHeight: 18, marginTop: spacing.xs },
  observations: { gap: spacing.sm, marginBottom: spacing.md },
  observationRow: { flexDirection: "row", gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider, paddingVertical: spacing.sm },
  observationNumber: { width: 28, height: 28, borderRadius: 14, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary },
  observationNumberText: { color: colors.brandPrimary, fontSize: 12, fontWeight: "800" },
  observationCopy: { flex: 1 },
  observationTitle: { color: colors.onSurface, fontSize: 15, lineHeight: 20, fontWeight: "800" },
  observationDetail: { color: colors.onSurfaceSecondary, fontSize: 13, lineHeight: 19, marginTop: 3 },
  reportingNote: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, marginBottom: spacing.xl, padding: spacing.md, backgroundColor: colors.surfaceTertiary, borderRadius: radius.sm },
  reportingText: { flex: 1, color: colors.onSurfaceTertiary, fontSize: 12, lineHeight: 18 },
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
    alignSelf: "center",
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
