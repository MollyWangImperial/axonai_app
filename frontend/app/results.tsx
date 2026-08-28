import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Image, Pressable, ScrollView, Share, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";

import { Assessment, fetchAssessment, fetchPatientAssessmentSummary, PatientAssessmentSummary } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

const anatomyImage = require("@/assets/images/rehyn-anatomy-front.png");

function formatDuration(durationMs: number) {
  return `${Math.max(1, Math.round(durationMs / 60000))} min`;
}

function formatAverageTaskTime(durationMs: number) {
  if (durationMs < 60000) return `${Math.max(1, Math.round(durationMs / 1000))} sec`;
  return `${Math.max(1, Math.round(durationMs / 60000))} min`;
}

function domainStatusLabel(status: string) {
  if (status === "no_observable_difficulty") return "Moving well";
  if (status === "review_recommended") return "Needs attention";
  if (status === "not_observed") return "Not observed";
  return "Analysis in progress";
}

function getMeasurement(assessment: Assessment | null, code: string) {
  for (const domain of assessment?.measurement_form?.domains || []) {
    const match = domain.rows.find((row) => row.code === code && typeof row.value === "number");
    if (match) return { value: match.value as number, unit: match.unit || "" };
  }
  return null;
}

export default function ResultsScreen() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<PatientAssessmentSummary | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [showDetails, setShowDetails] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        if (!id) return;
        const [summary, raw] = await Promise.all([
          fetchPatientAssessmentSummary(id),
          fetchAssessment(id).catch(() => null),
        ]);
        if (cancelled) return;
        setData(summary);
        setAssessment(raw);
        if (summary.clinical_review_gate?.status === "awaiting_model_analysis") {
          refreshTimer = setTimeout(load, summary.insights?.status === "processing" ? 5000 : 15000);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void load();
    return () => {
      cancelled = true;
      if (refreshTimer) clearTimeout(refreshTimer);
    };
  }, [id]);

  const reviewGate = data?.clinical_review_gate;
  const rehabBlocked = reviewGate?.rehab_access === "blocked";
  const noRehabNeeded = reviewGate?.rehab_access === "not_needed" || reviewGate?.status === "no_rehab_needed";
  const awaitingAnalysis = reviewGate?.status === "awaiting_model_analysis";
  const canViewPlan = data?.rehab_plan_ready === true && reviewGate?.rehab_access === "allowed";
  const affectedSide = assessment?.affected_side?.toLowerCase() === "left" ? "left" : "right";
  const activation = data?.insights.activation_profile.find((item) => item.template_mean !== null && item.template_mean > 0);
  const activationRatio = activation?.template_mean ? activation.mean / activation.template_mean : null;
  const trunkMetric = getMeasurement(assessment, "UL_TRUNK_COMPENSATION");
  const armMetric = getMeasurement(assessment, "UL_SHOULDER_ELEVATION");
  const walkingDomain = data?.body_function_summary.domains.find((domain) => domain.domain === "lower_limb");
  const topObservation = data?.insights.observations[0];
  const reportWidth = Math.min(Math.max(width - 32, 288), 720);

  const mainTitle = useMemo(() => {
    if (activationRatio !== null && activationRatio > 1.1) return `Your ${affectedSide} shoulder worked harder`;
    if (activationRatio !== null && activationRatio < 0.9) return `Your ${affectedSide} shoulder showed lower demand`;
    if (topObservation?.title) return topObservation.title;
    return "Your movement collection is ready";
  }, [activationRatio, affectedSide, topObservation?.title]);

  const shareSnapshot = () => {
    void Share.share({
      title: "My Rehyn movement snapshot",
      message: `${data?.insights.headline || "My movement assessment is complete."} ${mainTitle}.`,
    });
  };

  const goMap = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({ pathname: "/movement-map", params: { id } });
  };

  if (loading) {
    return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brandPrimary} /><Text style={styles.loadingText}>Preparing your movement snapshot...</Text></View>;
  }

  if (!data) {
    return (
      <View style={[styles.container, styles.center]}>
        <Text style={styles.errorText}>We could not load your movement snapshot.</Text>
        <Pressable onPress={() => router.replace("/")} style={[styles.cta, { marginTop: spacing.md }]}><Text style={styles.ctaText}>Back home</Text></Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.xs }]}>
        <Pressable onPress={() => router.replace("/")} style={styles.headerButton} testID="results-home"><Ionicons name="home-outline" size={23} color="#174834" /></Pressable>
        <View style={styles.headerCopy}>
          <Text style={styles.headerTitle}>Your movement snapshot</Text>
          <Text style={styles.headerDate}>{new Date(data.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</Text>
        </View>
        <Pressable onPress={shareSnapshot} style={styles.headerButton} accessibilityLabel="Share movement snapshot"><Ionicons name="share-outline" size={23} color="#174834" /></Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={[styles.report, { width: reportWidth }]}>
          <Text style={styles.lead}>{data.insights.headline || "Your completed tasks have been summarized below."}</Text>

          <View style={styles.anatomyStage}>
            <Image source={anatomyImage} resizeMode="contain" style={styles.anatomyImage} />
            <View style={[styles.bodyMarker, affectedSide === "right" ? styles.markerPatientRight : styles.markerPatientLeft]}>
              <View style={styles.markerCore} />
            </View>
            <View style={[styles.findingPill, affectedSide === "right" ? styles.findingRight : styles.findingLeft]}><Text style={styles.findingPillText}>Main finding</Text></View>
          </View>

          <View style={styles.mainInsight} testID="results-summary">
            <View style={styles.insightIcon}><Ionicons name="body-outline" size={28} color="#19553A" /></View>
            <View style={styles.insightCopy}>
              <Text style={styles.mainInsightTitle}>{mainTitle}</Text>
              {activationRatio !== null ? (
                <View style={styles.ratioRow}>
                  <Text style={styles.ratioValue}>{activationRatio.toFixed(1)}×</Text>
                  <Text style={styles.ratioLabel}>matched movement pattern</Text>
                </View>
              ) : (
                <Text style={styles.insightDescription}>{topObservation?.detail || data.insights.summary}</Text>
              )}
              <Text style={styles.disclaimer}>Modeled estimate, not measured EMG.</Text>
            </View>
          </View>

          <View style={styles.metricSection}>
            <View style={styles.metricCopy}>
              <Text style={styles.metricHeading}>Walking task captured</Text>
              <Text style={styles.metricLarge}>{walkingDomain?.step_completion_percent ?? 0}<Text style={styles.metricPercent}>%</Text></Text>
              <Text style={styles.metricCaption}>of guided walking steps</Text>
            </View>
            <View style={styles.stepGraphic}>
              {[0, 1, 2, 3, 4, 5].map((step) => <Ionicons key={step} name="footsteps" size={25} color={step % 2 ? "#CFE4D2" : "#79BC8A"} />)}
            </View>
          </View>

          <View style={styles.inlineMetrics}>
            <View style={styles.inlineMetricIcon}><Ionicons name="accessibility-outline" size={28} color="#19553A" /></View>
            <View style={styles.inlineMetricCopy}>
              <Text style={styles.inlineMetricLabel}>Arm elevation</Text>
              <Text style={styles.inlineMetricValue}>{armMetric ? `${Math.round(armMetric.value)}${armMetric.unit === "deg" ? "°" : ` ${armMetric.unit}`}` : "Captured"}</Text>
            </View>
            <View style={styles.inlineDivider} />
            <View style={styles.inlineMetricCopy}>
              <Text style={styles.inlineMetricLabel}>Trunk movement</Text>
              <Text style={styles.inlineMetricValue}>{trunkMetric ? `${Math.round(trunkMetric.value)}${trunkMetric.unit === "deg" ? "°" : ` ${trunkMetric.unit}`}` : "Captured"}</Text>
            </View>
          </View>

          <View style={styles.summaryNote}>
            <Ionicons name="leaf-outline" size={23} color="#74AD80" />
            <Text style={styles.summaryNoteText}>{data.insights.summary}</Text>
          </View>

          {(rehabBlocked || noRehabNeeded) && (
            <View style={styles.reviewCard} testID={noRehabNeeded ? "no-rehab-needed" : "clinical-review-hold"}>
              <Ionicons name={noRehabNeeded ? "checkmark-circle-outline" : awaitingAnalysis ? "hourglass-outline" : "people-outline"} size={25} color={colors.brandPrimary} />
              <View style={styles.reviewCopy}>
                <Text style={styles.reviewTitle}>{reviewGate?.patient_title}</Text>
                <Text style={styles.reviewText}>{reviewGate?.patient_message}</Text>
                {!!reviewGate?.next_step && <Text style={styles.reviewNext}>{reviewGate.next_step}</Text>}
              </View>
            </View>
          )}

          <Pressable onPress={goMap} style={styles.cta} testID={canViewPlan ? "results-view-plan" : "results-return-home"}>
            <Text style={styles.ctaText}>Explore your movement map</Text>
            <Ionicons name="arrow-forward" size={23} color="#FFFFFF" />
          </Pressable>

          <Pressable onPress={() => setShowDetails((current) => !current)} style={styles.detailToggle}>
            <Text style={styles.detailToggleText}>{showDetails ? "Hide measurements" : "View all measurements"}</Text>
            <Ionicons name={showDetails ? "chevron-up" : "chevron-down"} size={19} color={colors.brandPrimary} />
          </Pressable>

          {showDetails && (
            <View style={styles.details}>
              <Text style={styles.sectionTitle}>Body function summary</Text>
              {data.body_function_summary.domains.map((domain) => (
                <View key={domain.domain} style={styles.functionCard} testID={`body-function-${domain.domain}`}>
                  <View style={styles.functionHeader}>
                    <Text style={styles.functionTitle}>{domain.label}</Text>
                    <Text style={styles.functionStatus}>{domainStatusLabel(domain.status)}</Text>
                  </View>
                  <Text style={styles.functionSummary}>{domain.summary}</Text>
                  <View style={styles.functionMetrics}>
                    <View style={styles.functionMetric}><Text style={styles.functionMetricValue}>{domain.tasks_completed}/{domain.tasks_observed}</Text><Text style={styles.functionMetricLabel}>Tasks completed</Text></View>
                    <View style={styles.functionMetric}><Text style={styles.functionMetricValue}>{domain.step_completion_percent}%</Text><Text style={styles.functionMetricLabel}>Guided steps</Text></View>
                    <View style={styles.functionMetric}><Text style={styles.functionMetricValue}>{formatAverageTaskTime(domain.average_task_duration_ms)}</Text><Text style={styles.functionMetricLabel}>Average task</Text></View>
                    <View style={styles.functionMetric}><Text style={styles.functionMetricValue}>{domain.findings_count}</Text><Text style={styles.functionMetricLabel}>Findings to review</Text></View>
                  </View>
                </View>
              ))}

              <Text style={styles.sectionTitle}>Task collection</Text>
              <View style={styles.collectionRow} testID="collection-metrics">
                <View style={styles.collectionMetric}><Text style={styles.collectionValue}>{data.collection.tasks_collected}/{data.collection.tasks_expected}</Text><Text style={styles.collectionLabel}>Tasks collected</Text></View>
                <View style={styles.collectionMetric}><Text style={styles.collectionValue}>{data.collection.completion_percent}%</Text><Text style={styles.collectionLabel}>Guided steps completed</Text></View>
                <View style={styles.collectionMetric}><Text style={styles.collectionValue}>{formatDuration(data.collection.duration_ms)}</Text><Text style={styles.collectionLabel}>Collection time</Text></View>
              </View>
            </View>
          )}

          <View style={styles.bottomSpace} />
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FFFEFB" },
  center: { alignItems: "center", justifyContent: "center", padding: spacing.lg },
  loadingText: { marginTop: spacing.md, color: colors.onSurfaceSecondary },
  errorText: { color: colors.error, textAlign: "center" },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headerCopy: { alignItems: "center" },
  headerTitle: { fontSize: 18, lineHeight: 23, fontWeight: "800", color: "#164631" },
  headerDate: { marginTop: 2, fontSize: 13, color: colors.onSurfaceTertiary },
  content: { alignItems: "center", paddingTop: spacing.md },
  report: { alignSelf: "center" },
  lead: { fontSize: 17, lineHeight: 24, color: colors.onSurface, textAlign: "center", paddingHorizontal: spacing.sm },
  anatomyStage: { height: 390, marginTop: spacing.sm, alignItems: "center", justifyContent: "center" },
  anatomyImage: { width: "100%", height: "100%" },
  bodyMarker: { position: "absolute", top: 79, width: 66, height: 66, borderRadius: 33, borderWidth: 2, borderColor: "#F28270", backgroundColor: "rgba(241,108,90,0.22)", alignItems: "center", justifyContent: "center" },
  markerPatientRight: { left: "31%" },
  markerPatientLeft: { right: "31%" },
  markerCore: { width: 16, height: 16, borderRadius: 8, backgroundColor: "#F06B58", borderWidth: 3, borderColor: "#FFFFFF" },
  findingPill: { position: "absolute", top: 90, borderWidth: 1, borderColor: "#F2A090", borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 6, backgroundColor: "rgba(255,254,251,0.94)" },
  findingRight: { right: 6 },
  findingLeft: { left: 6 },
  findingPillText: { color: "#E55F4B", fontWeight: "700", fontSize: 12 },
  mainInsight: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start", paddingVertical: spacing.lg, borderBottomWidth: 1, borderBottomColor: colors.divider },
  insightIcon: { width: 54, height: 54, borderRadius: 27, borderWidth: 1, borderColor: "#B9D8C0", backgroundColor: "#F5FAF4", alignItems: "center", justifyContent: "center" },
  insightCopy: { flex: 1 },
  mainInsightTitle: { fontSize: 25, lineHeight: 31, fontWeight: "800", color: "#155039" },
  ratioRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, marginTop: spacing.xs },
  ratioValue: { fontSize: 44, lineHeight: 49, fontWeight: "800", color: "#07543B" },
  ratioLabel: { flex: 1, fontSize: 15, lineHeight: 20, color: colors.onSurfaceTertiary, marginBottom: 5 },
  insightDescription: { fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary, marginTop: spacing.xs },
  disclaimer: { marginTop: 5, fontSize: 12, color: "#8D938E" },
  metricSection: { flexDirection: "row", alignItems: "center", minHeight: 135, borderBottomWidth: 1, borderBottomColor: colors.divider },
  metricCopy: { width: "44%" },
  metricHeading: { fontSize: 15, fontWeight: "800", color: "#155039" },
  metricLarge: { fontSize: 40, lineHeight: 46, fontWeight: "800", color: "#07543B", marginTop: 4 },
  metricPercent: { fontSize: 24 },
  metricCaption: { fontSize: 12, color: colors.onSurfaceTertiary },
  stepGraphic: { flex: 1, flexDirection: "row", flexWrap: "wrap", justifyContent: "center", gap: 5 },
  inlineMetrics: { minHeight: 92, flexDirection: "row", alignItems: "center", gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  inlineMetricIcon: { width: 48, height: 48, borderRadius: 24, backgroundColor: "#F1F7EF", alignItems: "center", justifyContent: "center" },
  inlineMetricCopy: { flex: 1 },
  inlineMetricLabel: { fontSize: 12, color: colors.onSurfaceTertiary },
  inlineMetricValue: { fontSize: 20, fontWeight: "800", color: "#155039", marginTop: 2 },
  inlineDivider: { width: 1, height: 45, backgroundColor: colors.divider },
  summaryNote: { flexDirection: "row", gap: spacing.sm, paddingVertical: spacing.lg, alignItems: "flex-start" },
  summaryNoteText: { flex: 1, fontSize: 14, lineHeight: 21, color: colors.onSurfaceSecondary },
  reviewCard: { flexDirection: "row", gap: spacing.sm, borderWidth: 1, borderColor: "#BED6C2", borderRadius: radius.md, padding: spacing.md, backgroundColor: "#F2F8F1", marginBottom: spacing.md },
  reviewCopy: { flex: 1 },
  reviewTitle: { fontSize: 16, fontWeight: "800", color: "#174834" },
  reviewText: { marginTop: 4, fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary },
  reviewNext: { marginTop: 7, fontSize: 13, lineHeight: 19, fontWeight: "700", color: "#174834" },
  cta: { minHeight: 58, borderRadius: radius.md, backgroundColor: "#07543B", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.lg },
  ctaText: { color: "#FFFFFF", fontSize: 17, fontWeight: "800" },
  detailToggle: { minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 5 },
  detailToggleText: { color: colors.brandPrimary, fontSize: 14, fontWeight: "700" },
  details: { gap: spacing.sm, marginTop: spacing.sm },
  sectionTitle: { fontSize: 19, fontWeight: "800", color: colors.onSurface, marginTop: spacing.md },
  functionCard: { padding: spacing.md, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, backgroundColor: colors.surface },
  functionHeader: { flexDirection: "row", gap: spacing.sm, justifyContent: "space-between" },
  functionTitle: { flex: 1, fontSize: 16, fontWeight: "800", color: colors.onSurface },
  functionStatus: { fontSize: 12, fontWeight: "700", color: colors.brandPrimary },
  functionSummary: { marginTop: 5, fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary },
  functionMetrics: { flexDirection: "row", flexWrap: "wrap", marginTop: spacing.sm, rowGap: spacing.sm },
  functionMetric: { width: "50%" },
  functionMetricValue: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  functionMetricLabel: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2 },
  collectionRow: { flexDirection: "row", gap: spacing.xs },
  collectionMetric: { flex: 1, minHeight: 92, padding: spacing.sm, borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  collectionValue: { fontSize: 19, fontWeight: "800", color: colors.onSurface },
  collectionLabel: { marginTop: 4, fontSize: 11, lineHeight: 15, color: colors.onSurfaceTertiary },
  bottomSpace: { height: 40 },
});
