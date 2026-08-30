import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Image, Pressable, ScrollView, Share, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";

import { Assessment, fetchAssessment, fetchPatientAssessmentSummary, FunctionalIssue, PatientAssessmentSummary } from "@/src/api";
import { getAgeAnatomyPresentation, loadPatientAgeBand } from "@/src/ageAnatomy";
import { colors, radius, spacing } from "@/src/theme";
import { DEMO_ASSESSMENT_ID, demoAssessment, demoPatientAssessmentSummary } from "@/src/demoAssessment";
import { DisclaimerBanner } from "@/src/components/MedicalDisclaimer";

const webNoOutline = { outlineStyle: "none" } as const;

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

type PatientProblem = {
  title: string;
  dailyImpact: string;
  icon: "body-outline" | "hand-left-outline" | "walk-outline";
};

function toPatientProblem(issue: FunctionalIssue, affectedSide: "left" | "right"): PatientProblem {
  const text = `${issue.code} ${issue.label} ${issue.description}`.toLowerCase();
  const domain = issue.phenotype_domain || "";
  const isWalking = domain === "lower_limb" || /walk|gait|step|balance|lower limb/.test(text);
  const isHand = domain === "hand" || /hand|finger|grip|grasp|pinch/.test(text);
  const isShoulderOrReach = domain === "upper_limb" || /shoulder|reach|arm|deltoid/.test(text);

  if (isWalking) {
    return {
      title: /start/.test(text) ? "Starting to walk may need support" : /stop/.test(text) ? "Stopping after walking may need support" : "Walking may need support",
      dailyImpact: "This may affect walking confidence, balance, or how easily you move around.",
      icon: "walk-outline",
    };
  }
  if (isHand) {
    return {
      title: /open|extension/.test(text) ? `Opening your ${affectedSide} hand may need more effort` : `Using your ${affectedSide} hand may need support`,
      dailyImpact: "This may affect opening your hand, holding everyday objects, or letting them go.",
      icon: "hand-left-outline",
    };
  }
  if (isShoulderOrReach) {
    const higherEffort = /higher|harder|hyper|compens|effort/.test(text);
    return {
      title: higherEffort ? `Reaching may tire your ${affectedSide} shoulder` : `Reaching with your ${affectedSide} arm may need support`,
      dailyImpact: "This may make reaching for, lifting, or placing everyday objects feel harder.",
      icon: "body-outline",
    };
  }
  return {
    title: issue.label,
    dailyImpact: "This movement area may need extra support during everyday activities.",
    icon: "body-outline",
  };
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
  const [anatomyZoom, setAnatomyZoom] = useState(1);
  const isDemo = id === DEMO_ASSESSMENT_ID;
  const [profileAgeBand, setProfileAgeBand] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void loadPatientAgeBand().then((savedAgeBand) => {
      if (active && savedAgeBand) setProfileAgeBand(savedAgeBand);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;
    const load = async () => {
      try {
        if (!id) return;
        if (id === DEMO_ASSESSMENT_ID) {
          setData(demoPatientAssessmentSummary);
          setAssessment(demoAssessment);
          return;
        }
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
  const snapshotDecision = data?.movement_snapshot_decision || assessment?.movement_snapshot_decision;
  const findingsUnavailable = !assessment && !isDemo && !snapshotDecision;
  const canViewPlan = data?.rehab_plan_ready === true && reviewGate?.rehab_access === "allowed";
  const affectedSide = assessment?.affected_side?.toLowerCase() === "left" ? "left" : "right";
  const topObservation = data?.insights.observations[0];
  const isWide = width >= 820;
  const reportWidth = Math.min(Math.max(width - (isWide ? 64 : 24), 288), 1120);
  const ageBand = assessment?.patient_parameters?.age_band || profileAgeBand || (isDemo ? "70-79" : null);
  const ageAnatomy = getAgeAnatomyPresentation(ageBand);
  const patientProblems = useMemo(
    () => (assessment?.functional_issues || [])
      .filter((issue) => issue.code !== "NO_ISSUES")
      .map((issue) => toPatientProblem(issue, affectedSide)),
    [assessment?.functional_issues, affectedSide],
  );
  const primaryProblem = patientProblems.find((problem) => problem.icon === "body-outline") || patientProblems[0];
  const lowerLimbDomain = data?.body_function_summary.domains.find((domain) => domain.domain === "lower_limb");
  const hasShoulderFinding = snapshotDecision
    ? Boolean(snapshotDecision.anatomy_marker.visible && snapshotDecision.anatomy_marker.region?.endsWith("_shoulder"))
    : primaryProblem?.icon === "body-outline";

  const mainInsight = findingsUnavailable
      ? { eyebrow: "RESULT UNAVAILABLE", title: "We could not load this finding", text: "Please refresh the page. Missing analysis is not treated as normal movement.", tone: "pending" as const }
      : snapshotDecision?.presentation
        ? {
            eyebrow: snapshotDecision.presentation.eyebrow,
            title: snapshotDecision.presentation.title,
            text: snapshotDecision.presentation.summary,
            tone: snapshotDecision.presentation.tone,
          }
        : awaitingAnalysis
          ? { eyebrow: "ANALYSIS IN PROGRESS", title: "We are checking your movement", text: "Your recordings are still being reviewed before a functional finding is shown.", tone: "pending" as const }
      : primaryProblem
        ? {
            eyebrow: hasShoulderFinding ? `${affectedSide.toUpperCase()} SHOULDER` : primaryProblem.icon === "hand-left-outline" ? "HAND CONTROL" : "WALKING",
            title: hasShoulderFinding ? `Your ${affectedSide} shoulder may need support when reaching` : primaryProblem.title,
            text: hasShoulderFinding ? "Reaching, lifting, or placing everyday objects may require more effort." : primaryProblem.dailyImpact,
            tone: "attention" as const,
          }
        : { eyebrow: "MOVEMENT CHECK", title: "Your movement looked steady", text: "No clear functional problem stood out in the movements completed during this assessment.", tone: "well" as const };

  const walkingInsight = lowerLimbDomain?.status === "review_recommended"
    ? { eyebrow: "WALKING", title: "Walking may need support", text: "Your walking pattern showed an area that may benefit from review.", tone: "attention" as const }
  : lowerLimbDomain?.status === "analysis_pending"
      ? { eyebrow: "WALKING", title: "Walking results captured", text: "The walking observation is saved. Detailed movement analysis can add more information later.", tone: "pending" as const }
      : lowerLimbDomain?.status === "not_observed" || !lowerLimbDomain
        ? { eyebrow: "WALKING", title: "Walking was not observed", text: "No walking result is available from this assessment.", tone: "quiet" as const }
        : { eyebrow: "WALKING", title: "Walking appeared steady", text: "Your walking pattern looked consistent during this assessment.", tone: "well" as const };

  const mainTitle = useMemo(() => {
    if (snapshotDecision?.presentation.title) return snapshotDecision.presentation.title;
    if (primaryProblem?.title) return primaryProblem.title;
    if (topObservation?.title) return topObservation.title;
    return "Your movement collection is ready";
  }, [snapshotDecision?.presentation.title, primaryProblem?.title, topObservation?.title]);

  const shareSnapshot = () => {
    void Share.share({
      title: isDemo ? "Rehyn demo movement snapshot" : "My Rehyn movement snapshot",
      message: isDemo ? "This is a sample Rehyn movement snapshot, not a patient result." : `${data?.insights.headline || "My movement assessment is complete."} ${mainTitle}.`,
    });
  };

  const goMap = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({ pathname: "/movement-map", params: { id } });
  };

  const changeAnatomyZoom = (amount: number) => {
    setAnatomyZoom((current) => Math.min(2.25, Math.max(1, Number((current + amount).toFixed(2)))));
  };

  const focusAnatomyFinding = () => {
    setAnatomyZoom((current) => current < 1.75 ? 1.75 : current < 2.25 ? 2.25 : 1);
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
          <Text style={[styles.headerTitle, isWide && styles.headerTitleWide]}>Movement snapshot</Text>
          <Text style={[styles.headerDate, isWide && styles.headerDateWide]}>{new Date(data.created_at).toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" })}</Text>
          {isDemo && <View style={styles.samplePill}><Text style={styles.samplePillText}>Sample result</Text></View>}
        </View>
        <Pressable onPress={shareSnapshot} style={styles.headerButton} accessibilityLabel="Share movement snapshot"><Ionicons name="share-outline" size={23} color="#174834" /></Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={[styles.report, { width: reportWidth }]}>
          <DisclaimerBanner />
          {isDemo && <View style={styles.demoBanner}><Ionicons name="sparkles" size={20} color="#675080" /><Text style={styles.demoBannerText}>Sample data for preview only. This is not your assessment result.</Text></View>}
          <View style={[styles.snapshotPanel, isWide && styles.snapshotPanelWide]} testID="results-summary">
            <View style={[styles.anatomyPane, isWide && styles.anatomyPaneWide]}>
              <View style={[styles.anatomyStage, isWide && styles.anatomyStageWide]} testID="interactive-anatomy">
                <View
                  style={[
                    styles.anatomyCanvas,
                    {
                      transform: [{ scale: anatomyZoom }],
                      transformOrigin: `${affectedSide === "right" ? ageAnatomy.shoulderX : 100 - ageAnatomy.shoulderX}% ${ageAnatomy.shoulderY}%`,
                    },
                  ]}
                >
                  <Image source={ageAnatomy.source} resizeMode="stretch" style={styles.anatomyImage} />
                  {hasShoulderFinding && (
                    <Pressable
                      testID="anatomy-main-finding"
                      onPress={focusAnatomyFinding}
                      accessibilityLabel={`Focus on the ${affectedSide} shoulder finding`}
                      accessibilityHint="Activate to zoom into the highlighted shoulder"
                      style={[
                        styles.bodyMarker,
                        {
                          top: `${ageAnatomy.shoulderY}%` as `${number}%`,
                          left: `${affectedSide === "right" ? ageAnatomy.shoulderX : 100 - ageAnatomy.shoulderX}%` as `${number}%`,
                        },
                        webNoOutline as never,
                      ]}
                    >
                      <View style={styles.markerCore} />
                    </Pressable>
                  )}
                </View>

                {hasShoulderFinding && (
                  <View style={[styles.anatomyFindingLabel, isWide && styles.anatomyFindingLabelWide]} pointerEvents="none">
                    <Text style={styles.anatomyFindingText}>{affectedSide === "right" ? "Right" : "Left"} shoulder</Text>
                  </View>
                )}

                <View style={styles.zoomControls}>
                  <Pressable testID="anatomy-zoom-out" accessibilityLabel="Zoom anatomy out" disabled={anatomyZoom <= 1} onPress={() => changeAnatomyZoom(-0.25)} style={[styles.zoomButton, anatomyZoom <= 1 && styles.zoomButtonDisabled]}>
                    <Ionicons name="remove" size={21} color="#174834" />
                  </Pressable>
                  <Text style={styles.zoomValue}>{Math.round(anatomyZoom * 100)}%</Text>
                  <Pressable testID="anatomy-zoom-in" accessibilityLabel="Zoom anatomy in" disabled={anatomyZoom >= 2.25} onPress={() => changeAnatomyZoom(0.25)} style={[styles.zoomButton, anatomyZoom >= 2.25 && styles.zoomButtonDisabled]}>
                    <Ionicons name="add" size={21} color="#174834" />
                  </Pressable>
                  <Pressable testID="anatomy-zoom-reset" accessibilityLabel="Reset anatomy zoom" onPress={() => setAnatomyZoom(1)} style={styles.zoomButton}>
                    <Ionicons name="scan-outline" size={19} color="#174834" />
                  </Pressable>
                </View>
              </View>
            </View>

            <View style={[styles.insightPane, isWide && styles.insightPaneWide]}>
              <Text style={[styles.insightEyebrow, mainInsight.tone === "attention" && styles.insightEyebrowAttention]}>{mainInsight.eyebrow}</Text>
              <Text style={[styles.insightTitle, isWide && styles.insightTitleWide]}>{mainInsight.title}</Text>
              <Text style={[styles.insightText, isWide && styles.insightTextWide]}>{mainInsight.text}</Text>

              <View style={[styles.walkingCallout, walkingInsight.tone === "attention" && styles.walkingCalloutAttention, walkingInsight.tone === "pending" && styles.walkingCalloutPending]}>
                <View style={[styles.walkingIcon, walkingInsight.tone === "attention" && styles.walkingIconAttention, walkingInsight.tone === "pending" && styles.walkingIconPending, walkingInsight.tone === "quiet" && styles.walkingIconQuiet]}>
                  <Ionicons name={walkingInsight.tone === "well" ? "checkmark" : walkingInsight.tone === "pending" ? "hourglass-outline" : walkingInsight.tone === "attention" ? "alert" : "remove"} size={27} color="#FFFFFF" />
                </View>
                <View style={styles.walkingCopy}>
                  <Text style={styles.walkingEyebrow}>{walkingInsight.eyebrow}</Text>
                  <Text style={styles.walkingTitle}>{walkingInsight.title}</Text>
                  <Text style={styles.walkingText}>{walkingInsight.text}</Text>
                </View>
              </View>
            </View>
          </View>

          <View style={styles.summaryNote}>
            <View style={styles.storyIcon}><Ionicons name="leaf-outline" size={27} color="#2A744A" /></View>
            <View style={styles.storyCopy}>
              <Text style={styles.storyLabel}>MOVEMENT STORY</Text>
              <Text style={styles.summaryNoteText}>{data.insights.summary}</Text>
            </View>
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
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headerCopy: { alignItems: "center" },
  headerTitle: { fontSize: 18, lineHeight: 23, fontWeight: "800", color: "#164631" },
  headerTitleWide: { fontSize: 34, lineHeight: 42, fontWeight: "900" },
  headerDate: { marginTop: 2, fontSize: 13, color: colors.onSurfaceTertiary },
  headerDateWide: { marginTop: 6, fontSize: 16, lineHeight: 21, color: "#34423C" },
  samplePill: { marginTop: 9, paddingHorizontal: 16, paddingVertical: 6, borderRadius: radius.pill, backgroundColor: "#F0F1EF" },
  samplePillText: { color: "#34423C", fontSize: 13, lineHeight: 17, fontWeight: "700" },
  content: { alignItems: "center", paddingTop: spacing.lg, paddingHorizontal: spacing.sm },
  demoBanner: { minHeight: 66, flexDirection: "row", alignItems: "center", gap: spacing.sm, borderRadius: radius.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, marginBottom: spacing.lg, backgroundColor: "#F3ECF9", borderWidth: 1, borderColor: "#D8C7EA" },
  demoBannerText: { flex: 1, fontSize: 14, lineHeight: 20, fontWeight: "800", color: "#5C486F" },
  report: { alignSelf: "center" },
  lead: { fontSize: 17, lineHeight: 24, color: colors.onSurface, textAlign: "center", paddingHorizontal: spacing.sm },
  snapshotPanel: { overflow: "hidden", borderWidth: 1, borderColor: "#CDD6CE", borderRadius: radius.sm, backgroundColor: "#FFFFFF" },
  snapshotPanelWide: { flexDirection: "row", alignItems: "stretch" },
  anatomyPane: { backgroundColor: "#FFFCF8" },
  anatomyPaneWide: { width: "48%", borderRightWidth: 1, borderRightColor: "#D8DED8" },
  anatomyStage: { height: 430, alignItems: "center", justifyContent: "center", overflow: "hidden", backgroundColor: "#FFFCF8" },
  anatomyStageWide: { height: 680 },
  anatomyCanvas: { height: "100%", aspectRatio: 866 / 1817, position: "relative" },
  anatomyImage: { ...StyleSheet.absoluteFillObject, width: "100%", height: "100%" },
  bodyMarker: { position: "absolute", width: 68, height: 68, marginTop: -34, marginLeft: -34, borderRadius: 34, borderWidth: 2, borderColor: "#F26E5A", backgroundColor: "rgba(241,108,90,0.24)", alignItems: "center", justifyContent: "center", shadowColor: "#F06B58", shadowOpacity: 0.22, shadowRadius: 10, shadowOffset: { width: 0, height: 0 } },
  markerCore: { width: 16, height: 16, borderRadius: 8, backgroundColor: "#F06B58", borderWidth: 3, borderColor: "#FFFFFF" },
  anatomyFindingLabel: { position: "absolute", top: spacing.sm, right: spacing.sm, minHeight: 36, paddingHorizontal: spacing.sm, borderRadius: radius.pill, backgroundColor: "rgba(255,254,251,0.96)", borderWidth: 1, borderColor: "#F06B58", flexDirection: "row", alignItems: "center" },
  anatomyFindingLabelWide: { top: "18%", right: spacing.lg },
  anatomyFindingDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: "#F06B58" },
  anatomyFindingText: { color: "#D55340", fontSize: 13, fontWeight: "900" },
  zoomControls: { position: "absolute", right: spacing.sm, bottom: spacing.sm, minHeight: 48, padding: 3, borderRadius: radius.pill, backgroundColor: "rgba(255,255,255,0.97)", borderWidth: 1, borderColor: "#D7E1D9", flexDirection: "row", alignItems: "center", shadowColor: "#173D35", shadowOpacity: 0.1, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 2 },
  zoomButton: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center" },
  zoomButtonDisabled: { opacity: 0.3 },
  zoomValue: { width: 46, textAlign: "center", color: "#174834", fontSize: 11, fontWeight: "800" },
  insightPane: { padding: spacing.lg, backgroundColor: "#FFFFFF" },
  insightPaneWide: { flex: 1, justifyContent: "center", paddingHorizontal: 44, paddingVertical: 48 },
  insightEyebrow: { color: "#397753", fontSize: 13, lineHeight: 18, fontWeight: "900" },
  insightEyebrowAttention: { color: "#D65340" },
  insightTitle: { marginTop: spacing.sm, color: "#0F432F", fontSize: 27, lineHeight: 34, fontWeight: "900" },
  insightTitleWide: { marginTop: spacing.md, fontSize: 36, lineHeight: 46 },
  insightText: { marginTop: spacing.md, color: "#303A35", fontSize: 16, lineHeight: 24 },
  insightTextWide: { marginTop: spacing.lg, fontSize: 20, lineHeight: 31 },
  walkingCallout: { marginTop: 36, flexDirection: "row", alignItems: "flex-start", gap: spacing.md, padding: spacing.lg, borderWidth: 1, borderColor: "#C9D8CA", borderRadius: radius.sm, backgroundColor: "#F9FCF8" },
  walkingCalloutAttention: { borderColor: "#F0C0B7", backgroundColor: "#FFF8F5" },
  walkingCalloutPending: { borderColor: "#E5D5AC", backgroundColor: "#FFFBF0" },
  walkingIcon: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center", backgroundColor: "#338052" },
  walkingIconAttention: { backgroundColor: "#D75B48" },
  walkingIconPending: { backgroundColor: "#B9892B" },
  walkingIconQuiet: { backgroundColor: "#7A847D" },
  walkingCopy: { flex: 1, minWidth: 0 },
  walkingEyebrow: { color: "#397753", fontSize: 12, lineHeight: 17, fontWeight: "900" },
  walkingTitle: { marginTop: 5, color: "#174834", fontSize: 22, lineHeight: 28, fontWeight: "900" },
  walkingText: { marginTop: spacing.sm, color: "#4A5650", fontSize: 14, lineHeight: 21 },
  problemSection: { paddingVertical: spacing.lg, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  problemEyebrow: { fontSize: 11, lineHeight: 15, fontWeight: "900", color: "#8F4339" },
  problemCard: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md, padding: spacing.md, borderWidth: 1, borderColor: "#F0B6AB", borderRadius: radius.md, backgroundColor: "#FFF6F3" },
  problemCardSecondary: { borderColor: "#E7D6A8", backgroundColor: "#FFFBF0" },
  problemIcon: { width: 50, height: 50, borderRadius: 25, alignItems: "center", justifyContent: "center", backgroundColor: "#FFE7E1" },
  problemIconSecondary: { backgroundColor: "#F8EDCE" },
  problemCopy: { flex: 1, minWidth: 0 },
  problemHeadingRow: { alignItems: "flex-start" },
  problemTitle: { fontSize: 20, lineHeight: 26, fontWeight: "800", color: "#173E2F" },
  problemTitleTagged: { marginTop: 5 },
  problemTag: { borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 4, overflow: "hidden", backgroundColor: "#FCE0DA", color: "#B5483B", fontSize: 9, lineHeight: 12, fontWeight: "900" },
  problemTagSecondary: { backgroundColor: "#F4E6BC", color: "#795B16" },
  problemImpact: { marginTop: spacing.xs, fontSize: 15, lineHeight: 22, fontWeight: "700", color: "#315E4A" },
  problemText: { fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary },
  analysisState: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md, padding: spacing.md, borderWidth: 1, borderColor: "#C9DCCB", borderRadius: radius.md, backgroundColor: "#F4F8F3" },
  analysisIcon: { width: 50, height: 50, borderRadius: 25, alignItems: "center", justifyContent: "center", backgroundColor: "#E3F0E3" },
  unavailableState: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md, padding: spacing.md, borderWidth: 1, borderColor: "#E2CC9F", borderRadius: radius.md, backgroundColor: "#FFF9ED" },
  unavailableIcon: { width: 50, height: 50, borderRadius: 25, alignItems: "center", justifyContent: "center", backgroundColor: "#F6E9CC" },
  noProblemCard: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md, padding: spacing.md, borderWidth: 1, borderColor: "#BFDCC5", borderRadius: radius.md, backgroundColor: "#F3FAF3" },
  noProblemIcon: { width: 50, height: 50, borderRadius: 25, alignItems: "center", justifyContent: "center", backgroundColor: "#DCEEDD" },
  moreProblemsText: { fontSize: 12, lineHeight: 18, color: colors.onSurfaceTertiary, textAlign: "center" },
  summaryNote: { minHeight: 124, marginTop: spacing.lg, flexDirection: "row", gap: spacing.md, padding: spacing.lg, alignItems: "center", borderWidth: 1, borderColor: "#CDD8CE", borderRadius: radius.sm, backgroundColor: "#FBFDF9" },
  storyIcon: { width: 54, height: 54, borderRadius: 27, alignItems: "center", justifyContent: "center", backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: "#D3DFD5" },
  storyCopy: { flex: 1 },
  storyLabel: { marginBottom: 8, fontSize: 12, lineHeight: 17, fontWeight: "900", color: colors.brandPrimary },
  summaryNoteText: { fontSize: 15, lineHeight: 23, color: colors.onSurfaceSecondary },
  reviewCard: { flexDirection: "row", gap: spacing.sm, borderWidth: 1, borderColor: "#BED6C2", borderRadius: radius.md, padding: spacing.md, backgroundColor: "#F2F8F1", marginBottom: spacing.md },
  reviewCopy: { flex: 1 },
  reviewTitle: { fontSize: 16, fontWeight: "800", color: "#174834" },
  reviewText: { marginTop: 4, fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary },
  reviewNext: { marginTop: 7, fontSize: 13, lineHeight: 19, fontWeight: "700", color: "#174834" },
  cta: { minHeight: 70, marginTop: spacing.lg, borderRadius: radius.sm, backgroundColor: "#07543B", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.lg },
  ctaText: { color: "#FFFFFF", fontSize: 20, fontWeight: "900" },
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
