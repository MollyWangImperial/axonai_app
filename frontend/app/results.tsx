import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Linking } from "react-native";
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

const ANOMALY_COLORS: Record<string, string> = {
  hypoactivation: colors.brandSecondary,
  hyperactivation: colors.warning,
  timing_disorder: colors.brandPrimary,
  co_contraction: colors.error,
};

const ANOMALY_SHORT: Record<string, string> = {
  hypoactivation: "Hypoactivation",
  hyperactivation: "Hyperactivation",
  timing_disorder: "Timing disorder",
  co_contraction: "Co-contraction",
};

function formatEvidence(metrics: Record<string, unknown>) {
  const parts = Object.entries(metrics)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${k}=${typeof v === "number" ? Number(v.toFixed ? v.toFixed(3) : v) : String(v)}`);
  return parts.join(" · ");
}

function formatEstimateValue(value: unknown, unit?: string | null) {
  if (value === null || value === undefined) return "Not available";
  if (typeof value === "object") return JSON.stringify(value);
  return `${String(value)}${unit ? ` ${unit}` : ""}`;
}

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
            We identified {data.functional_issues.length} movement phenotype{data.functional_issues.length === 1 ? "" : "s"} from the steps you could not complete.
          </Text>
        </View>

        {!!data.domain_assessments?.length && (
          <>
            <Text style={styles.sectionTitle}>Functional domain screening</Text>
            {data.domain_assessments.map((domain) => (
              <View key={domain.domain} style={styles.domainRow} testID={`domain-${domain.domain}`}>
                <View style={styles.domainHead}>
                  <Text style={styles.domainLabel}>{domain.label}</Text>
                  <Text style={styles.domainScore}>{domain.completion_percent}% steps completed</Text>
                </View>
                <Text style={styles.issueDesc}>{domain.interpretation}</Text>
                <Text style={styles.issueSource}>{domain.method} · Screening result</Text>
              </View>
            ))}
          </>
        )}

        <Text style={styles.sectionTitle}>Movement phenotypes identified</Text>
        {data.functional_issues.map((iss) => (
          <View key={iss.code} style={styles.issueCard} testID={`issue-${iss.code}`}>
            <View style={styles.issueHead}>
              <View style={[styles.sevDot, { backgroundColor: SEVERITY_COLORS[iss.severity] || colors.brandPrimary }]} />
              <Text style={styles.issueLabel}>{iss.label}</Text>
              <Text style={styles.issueSeverity}>{iss.severity}</Text>
            </View>
            <Text style={styles.issueDesc}>{iss.description}</Text>
            <Text style={styles.issueSource}>
              Source: {iss.source} · Task {iss.related_task}{iss.related_step ? ` · Step ${iss.related_step}` : ""}
            </Text>
          </View>
        ))}

        {!!data.muscle_activation_diagnosis && (
          <>
            <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Muscle activation screening</Text>
            <Text style={styles.formRule}>
              These findings are inferred from movement patterns. They do not directly measure muscle activity and should be reviewed by a clinician.
            </Text>
            {data.muscle_activation_diagnosis.findings.length === 0 && (
              <View style={styles.issueCard} testID="muscle-screening-empty">
                <Text style={styles.issueLabel}>No muscle activation patterns were flagged</Text>
                <Text style={styles.issueDesc}>
                  This assessment did not cross the current screening thresholds. It does not rule out weakness, spasticity, fatigue, or coordination problems.
                </Text>
              </View>
            )}
            {data.muscle_activation_diagnosis.findings.map((finding) => (
              <View key={finding.code} style={styles.issueCard} testID={`muscle-finding-${finding.code}`}>
                <View style={styles.issueHead}>
                  <View
                    style={[
                      styles.anomalyBadge,
                      { backgroundColor: ANOMALY_COLORS[finding.anomaly_type] || colors.brandPrimary },
                    ]}
                  >
                    <Text style={styles.anomalyBadgeText}>{ANOMALY_SHORT[finding.anomaly_type] || finding.anomaly_type}</Text>
                  </View>
                  <Text style={styles.issueSeverity}>{finding.severity}</Text>
                </View>
                <Text style={styles.issueLabel}>{finding.label}</Text>
                <Text style={styles.issueDesc}>{finding.interpretation}</Text>
                <Text style={styles.muscleTargets}>Target muscles: {finding.muscles}</Text>
                {!!Object.keys(finding.evidence_metrics || {}).length && (
                  <Text style={styles.issueSource}>Evidence: {formatEvidence(finding.evidence_metrics)}</Text>
                )}
                <Text style={styles.issueSource}>
                  Pipeline {finding.pipeline_route}: {finding.pipeline_route_label} · Tasks {finding.related_tasks.join(", ")}
                </Text>
                <Text style={styles.citationText}>{finding.citation}</Text>
              </View>
            ))}
            <Text style={styles.formRule}>{data.muscle_activation_diagnosis.reporting_rule}</Text>
          </>
        )}

        {!!data.biomechanical_estimates?.length && (
          <>
            <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Biomechanics and measurement status</Text>
            {data.biomechanical_estimates.map((estimate) => (
              <View key={estimate.code} style={styles.metricRow} testID={`estimate-${estimate.code}`}>
                <View style={styles.domainHead}>
                  <Text style={styles.domainLabel}>{estimate.label}</Text>
                  <Text style={styles.metricValue}>{formatEstimateValue(estimate.value, estimate.unit)}</Text>
                </View>
                <Text style={styles.issueDesc}>{estimate.interpretation}</Text>
                <Text style={styles.issueSource}>{estimate.method} · {estimate.confidence}</Text>
              </View>
            ))}
          </>
        )}

        {!!data.measurement_form?.domains?.length && (
          <>
            <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Clinical measurement form</Text>
            <View style={styles.formSummary} testID="measurement-form-summary">
              <Text style={styles.formSummaryValue}>{data.measurement_form.summary.auto_filled}</Text>
              <Text style={styles.formSummaryLabel}>camera-filled</Text>
              <Text style={styles.formSummaryValue}>{data.measurement_form.summary.model_filled}</Text>
              <Text style={styles.formSummaryLabel}>model-filled</Text>
              <Text style={styles.formSummaryValue}>{data.measurement_form.summary.clinician_filled}</Text>
              <Text style={styles.formSummaryLabel}>clinician-filled</Text>
              <Text style={styles.formSummaryValue}>{data.measurement_form.summary.tool_filled}</Text>
              <Text style={styles.formSummaryLabel}>tool-filled</Text>
              <Text style={styles.formSummaryValue}>{data.measurement_form.summary.pending}</Text>
              <Text style={styles.formSummaryLabel}>pending clinical measurement</Text>
            </View>
            <Text style={styles.formRule}>{data.measurement_form.reporting_rule}</Text>
            {data.measurement_form.domains.map((domain) => {
              const visibleRows = domain.rows.filter((row) => row.applicable_to_submitted_tasks);
              if (!visibleRows.length) return null;
              return (
                <View key={domain.domain} style={styles.formDomain} testID={`measurement-domain-${domain.domain}`}>
                  <Text style={styles.formDomainTitle}>{domain.label}</Text>
                  {visibleRows.map((row) => (
                    <View key={row.code} style={styles.formRow} testID={`measurement-${row.code}`}>
                      <View style={styles.domainHead}>
                        <Text style={styles.domainLabel}>{row.label}</Text>
                        <Text style={row.status.endsWith("filled") ? styles.metricValue : styles.pendingValue}>
                          {row.status.endsWith("filled")
                            ? formatEstimateValue(row.value, row.unit)
                            : "Pending"}
                        </Text>
                      </View>
                      <Text style={styles.issueSource}>{row.source_label} · {row.method}</Text>
                      {!!row.requirement && !row.status.endsWith("filled") && (
                        <Text style={styles.formRequirement}>{row.requirement}</Text>
                      )}
                    </View>
                  ))}
                </View>
              );
            })}
          </>
        )}

        {!!data.rehabilitation_goals?.short_term?.length && (
          <>
            <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Short-term goals</Text>
            {data.rehabilitation_goals.short_term.map((goal) => (
              <View key={goal.id} style={styles.goalRow} testID={`goal-${goal.id}`}>
                <View style={styles.domainHead}>
                  <Text style={styles.goalDomain}>{goal.domain_label}</Text>
                  <Text style={styles.goalTime}>{goal.timeframe}</Text>
                </View>
                <Text style={styles.goalStatement}>{goal.statement}</Text>
                <Text style={styles.goalMeta}>Baseline: {goal.baseline}</Text>
                <Text style={styles.goalMeta}>Review: {goal.outcome_measure}</Text>
                <View style={styles.goalFlags}>
                  {goal.patient_agreement_required && <Text style={styles.goalFlag}>Patient priority to confirm</Text>}
                  {goal.clinician_confirmation_required && <Text style={styles.goalFlag}>Clinician review required</Text>}
                </View>
                {!!goal.evidence[0] && (
                  <Pressable onPress={() => Linking.openURL(goal.evidence[0].url)} accessibilityRole="link">
                    <Text style={styles.evidenceLink}>{goal.evidence[0].organization} · {goal.evidence[0].year}</Text>
                  </Pressable>
                )}
              </View>
            ))}

            <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Long-term goals</Text>
            {data.rehabilitation_goals.long_term.map((goal) => (
              <View key={goal.id} style={styles.goalRow} testID={`goal-${goal.id}`}>
                <View style={styles.domainHead}>
                  <Text style={styles.goalDomain}>{goal.domain_label}</Text>
                  <Text style={styles.goalTime}>{goal.timeframe}</Text>
                </View>
                <Text style={styles.goalStatement}>{goal.statement}</Text>
                <Text style={styles.goalMeta}>Target: {goal.target}</Text>
                <Text style={styles.goalMeta}>Review: {goal.outcome_measure}</Text>
                <View style={styles.goalFlags}>
                  {goal.patient_agreement_required && <Text style={styles.goalFlag}>Patient priority to confirm</Text>}
                  {goal.clinician_confirmation_required && <Text style={styles.goalFlag}>Clinician review required</Text>}
                </View>
                {!!goal.evidence[0] && (
                  <Pressable onPress={() => Linking.openURL(goal.evidence[0].url)} accessibilityRole="link">
                    <Text style={styles.evidenceLink}>{goal.evidence[0].organization} · {goal.evidence[0].year}</Text>
                  </Pressable>
                )}
              </View>
            ))}

            {!!data.rehabilitation_goals.missing_information.length && (
              <View style={styles.missingInfo} testID="goal-missing-information">
                <Text style={styles.missingTitle}>Required before goals are agreed</Text>
                {data.rehabilitation_goals.missing_information.map((item) => (
                  <Text key={item} style={styles.missingText}>• {item}</Text>
                ))}
              </View>
            )}
          </>
        )}

        <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>What&apos;s next</Text>
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
  anomalyBadge: { borderRadius: radius.sm, paddingHorizontal: 8, paddingVertical: 4, alignSelf: "flex-start" },
  anomalyBadgeText: { color: "#fff", fontSize: 11, fontWeight: "800" },
  muscleTargets: { fontSize: 13, fontWeight: "600", color: colors.onSurfaceSecondary, lineHeight: 18 },
  citationText: { fontSize: 12, lineHeight: 17, color: colors.brandPrimary, fontStyle: "italic" },
  issueDesc: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
  issueSource: { fontSize: 12, color: colors.onSurfaceTertiary, fontStyle: "italic", marginTop: 4 },
  domainRow: { paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: 5, marginBottom: spacing.xs },
  metricRow: { paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: 5 },
  domainHead: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.md },
  domainLabel: { flex: 1, fontSize: 15, fontWeight: "700", color: colors.onSurface },
  domainScore: { fontSize: 12, fontWeight: "700", color: colors.brandPrimary },
  metricValue: { maxWidth: "42%", fontSize: 12, fontWeight: "700", color: colors.brandPrimary, textAlign: "right" },
  pendingValue: { maxWidth: "42%", fontSize: 12, fontWeight: "700", color: colors.warning, textAlign: "right" },
  formSummary: { flexDirection: "row", flexWrap: "wrap", alignItems: "baseline", gap: spacing.xs, paddingVertical: spacing.sm },
  formSummaryValue: { fontSize: 18, fontWeight: "800", color: colors.brandPrimary, marginLeft: spacing.sm },
  formSummaryLabel: { fontSize: 12, color: colors.onSurfaceSecondary, marginRight: spacing.sm },
  formRule: { fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary, marginBottom: spacing.md },
  formDomain: { marginBottom: spacing.lg },
  formDomainTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, paddingBottom: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.divider },
  formRow: { paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: 3 },
  formRequirement: { fontSize: 12, lineHeight: 17, color: colors.warning },
  goalRow: { paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: 6 },
  goalDomain: { flex: 1, fontSize: 15, fontWeight: "800", color: colors.onSurface },
  goalTime: { fontSize: 12, fontWeight: "700", color: colors.brandPrimary },
  goalStatement: { fontSize: 14, lineHeight: 21, color: colors.onSurface },
  goalMeta: { fontSize: 12, lineHeight: 18, color: colors.onSurfaceSecondary },
  goalFlags: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  goalFlag: { fontSize: 11, fontWeight: "700", color: colors.warning },
  evidenceLink: { fontSize: 12, fontWeight: "700", color: colors.brandPrimary, textDecorationLine: "underline" },
  missingInfo: { marginTop: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, gap: 4 },
  missingTitle: { fontSize: 13, fontWeight: "800", color: colors.onSurface },
  missingText: { fontSize: 12, lineHeight: 18, color: colors.onSurfaceSecondary },
  nextCard: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, alignItems: "flex-start" },
  nextText: { flex: 1, color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 20 },
  ctaBar: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  cta: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.md, alignItems: "center", justifyContent: "center", minHeight: 56 },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "700" },
});
