import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Image, Pressable, ScrollView, Share, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";

import { Assessment, fetchAssessment, fetchPatientAssessmentSummary, FunctionalIssue, PatientAssessmentSummary } from "@/src/api";
import { authedFetch } from "@/src/auth";
import { ActivityMetric, DailyActivitiesBoard, DailyActivitiesPanel } from "@/src/components/DailyActivitiesPanel";
import { MovementScoresPanel } from "@/src/components/MovementScoresPanel";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { getAgeAnatomyPresentation, loadPatientAgeBand } from "@/src/ageAnatomy";
import { colors, radius, spacing } from "@/src/theme";
import { DEMO_ASSESSMENT_ID, demoAssessment, demoPatientAssessmentSummary } from "@/src/demoAssessment";
import { DisclaimerBanner } from "@/src/components/MedicalDisclaimer";

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

type SurveyPin = {
  domain: "upper_limb" | "hand" | "lower_limb";
  title: string;
  affected_side: "left" | "right";
  severity: "needs_attention" | "building_strength" | "moving_well";
  problem: string;
};

const ANATOMY_ASPECT_RATIO = 866 / 1816;

const DEMO_DAILY_ACTIVITIES: ActivityMetric[] = [
  { activity: "Eating and drinking", status: "complete", observed: "A little help", qualitative_score: "medium", score: 72, score_source: "observed" },
  { activity: "Dressing", status: "complete", observed: "A little help", qualitative_score: "medium", score: 70, score_source: "observed" },
  { activity: "Grooming and self-care", status: "complete", observed: "A little help", qualitative_score: "medium", score: 68, score_source: "observed" },
  { activity: "Moving around", status: "complete", observed: "Independent", qualitative_score: "normal", score: 88, score_source: "observed" },
];

export default function ResultsScreen() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<PatientAssessmentSummary | null>(getScreenCache<{ data: PatientAssessmentSummary; assessment: Assessment | null }>(`results:${id}`)?.data ?? null);
  const [assessment, setAssessment] = useState<Assessment | null>(getScreenCache<{ data: PatientAssessmentSummary; assessment: Assessment | null }>(`results:${id}`)?.assessment ?? null);
  const cachedResult = getScreenCache<{ data: PatientAssessmentSummary; assessment: Assessment | null }>(`results:${id}`);
  const [loading, setLoading] = useState(!cachedResult);
  const [showDetails, setShowDetails] = useState(false);
  const [surveyPins, setSurveyPins] = useState<SurveyPin[]>(getScreenCache<SurveyPin[]>("survey-problems") ?? []);
  const [selectedMapDomain, setSelectedMapDomain] = useState<"upper_limb" | "hand" | "lower_limb" | null>(null);
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
    // Survey-based weakness/spasticity highlights: while nothing has been
    // observed for a region, the anatomy shades areas the survey answers mark
    // as potentially weak, so the snapshot is never an unexplained blank.
    if (isDemo) return;
    let cancelled = false;
    void authedFetch("/api/assessment/survey-report")
      .then(async (response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (cancelled || !body) return;
        const pins = (body?.functional_problems?.pins || []) as SurveyPin[];
        setSurveyPins(pins);
        setScreenCache<SurveyPin[]>("survey-problems", pins);
      })
      .catch(() => null);
    return () => { cancelled = true; };
  }, [isDemo]);

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
        setScreenCache(`results:${id}`, { data: summary, assessment: raw });
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
  const planAccessAllowed = reviewGate?.rehab_access === "allowed" || reviewGate?.rehab_access === "interim";
  const canViewPlan = data?.rehab_plan_ready === true && planAccessAllowed;
  const affectedSide = assessment?.affected_side?.toLowerCase() === "left" ? "left" : "right";
  const topObservation = data?.insights.observations[0];
  const isWide = width >= 820;
  const reportWidth = Math.min(Math.max(width - (isWide ? 64 : 24), 288), 1120);
  const ageBand = assessment?.patient_parameters?.age_band || profileAgeBand || (isDemo ? "70-79" : null);
  const ageAnatomy = getAgeAnatomyPresentation(ageBand);
  const desiredMapAnatomyHeight = Math.min(520, Math.max(380, reportWidth * 0.62));
  const mapAnatomyWidth = Math.min(
    desiredMapAnatomyHeight * ANATOMY_ASPECT_RATIO,
    Math.max(120, reportWidth - spacing.md * 2),
  );
  const mapAnatomyHeight = mapAnatomyWidth / ANATOMY_ASPECT_RATIO;
  const patientProblems = useMemo(
    () => (assessment?.functional_issues || [])
      .filter((issue) => issue.code !== "NO_ISSUES")
      .map((issue) => toPatientProblem(issue, affectedSide)),
    [assessment?.functional_issues, affectedSide],
  );
  const primaryProblem = patientProblems.find((problem) => problem.icon === "body-outline") || patientProblems[0];

  const mainTitle = useMemo(() => {
    if (snapshotDecision?.presentation.title) return snapshotDecision.presentation.title;
    if (primaryProblem?.title) return primaryProblem.title;
    if (topObservation?.title) return topObservation.title;
    return "Your movement collection is ready";
  }, [snapshotDecision?.presentation.title, primaryProblem?.title, topObservation?.title]);

  // Inline movement map: observed domain results lead; survey answers fill in
  // any domain that has not been observed yet.
  const MAP_SEVERITIES = {
    needs_attention: { color: "#E84432", soft: "#FFF1EF", label: "May need support" },
    building_strength: { color: "#C88913", soft: "#FFF7E6", label: "Building strength" },
    moving_well: { color: "#3E8256", soft: "#F1F8F2", label: "Moving well" },
  };
  const MAP_TITLES: Record<string, string> = { upper_limb: "shoulder and arm", hand: "hand", lower_limb: "leg" };
  const MAP_DOMAIN_ICONS = {
    upper_limb: "body-outline",
    hand: "hand-left-outline",
    lower_limb: "walk-outline",
  } as const;
  const mapMarkers = (["upper_limb", "hand", "lower_limb"] as const).map((domain) => {
    const observed = data?.body_function_summary.domains.find((item) => item.domain === domain);
    const pin = surveyPins.find((item) => item.domain === domain);
    if (observed && observed.status !== "not_observed") {
      const severity = observed.findings_count > 0 || observed.status === "review_recommended"
        ? "needs_attention" as const
        : observed.status === "analysis_pending" || (observed.step_completion_percent ?? 0) < 100
          ? "building_strength" as const
          : "moving_well" as const;
      return {
        domain,
        severity,
        source: "observed" as const,
        coverage: observed.step_completion_percent ?? 0,
        findings: observed.findings_count ?? 0,
        detail: observed.findings_count > 0
          ? "This area showed a finding to review from the completed tasks."
          : observed.status === "analysis_pending"
            ? "The guided-task metrics are ready while the validated movement analysis is still in progress."
            : "This area moved steadily in the completed tasks.",
      };
    }
    if (pin) {
      return { domain, severity: pin.severity, source: "survey" as const, coverage: null, findings: null, detail: pin.problem };
    }
    return null;
  }).filter((marker): marker is NonNullable<typeof marker> => marker != null);
  const activeMapMarker = mapMarkers.find((marker) => marker.domain === selectedMapDomain)
    ?? mapMarkers.find((marker) => marker.severity === "needs_attention")
    ?? mapMarkers[0]
    ?? null;

  const shareSnapshot = () => {
    void Share.share({
      title: isDemo ? "Rehyn demo movement snapshot" : "My Rehyn movement snapshot",
      message: isDemo ? "This is a sample Rehyn movement snapshot, not a patient result." : `${data?.insights.headline || "My movement assessment is complete."} ${mainTitle}.`,
    });
  };

  const goPlan = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    if (canViewPlan && id) router.push({ pathname: "/rehab-plan", params: { id } });
    else router.dismissTo("/");
  };

  if (loading) {
    return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brandPrimary} /><Text style={styles.loadingText}>Preparing your movement snapshot...</Text></View>;
  }

  if (!data) {
    return (
      <View style={[styles.container, styles.center]}>
        <Text style={styles.errorText}>We could not load your movement snapshot.</Text>
        <Pressable onPress={() => router.dismissTo("/")} style={[styles.cta, { marginTop: spacing.md }]}><Text style={styles.ctaText}>Back home</Text></Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.xs }]}>
        <Pressable onPress={() => router.dismissTo("/")} style={styles.headerButton} testID="results-home"><Ionicons name="home-outline" size={23} color="#174834" /></Pressable>
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
          <MovementScoresPanel domains={data.body_function_summary.domains} metrics={data.functional_metrics} />
          {isDemo
            ? <DailyActivitiesBoard activities={DEMO_DAILY_ACTIVITIES} title="What this means for daily life" sectionHeading />
            : <DailyActivitiesPanel title="What this means for daily life" sectionHeading />}
          {mapMarkers.length > 0 && (
            <View style={[styles.mapPanel, !isWide && styles.mapPanelNarrow]} testID="results-movement-map">
              <Text style={[styles.mapHeading, !isWide && styles.mapHeadingNarrow]}>Your movement map</Text>
              <Text style={[styles.mapInstruction, !isWide && styles.mapInstructionNarrow]}>Choose a number to learn about that area.</Text>
              <View style={[styles.mapLayout, !isWide && styles.mapLayoutStacked]}>
                <View style={[styles.mapFigure, !isWide && styles.mapFigureStacked]}>
                  <View
                    style={[styles.mapCanvas, { width: mapAnatomyWidth, height: mapAnatomyHeight }]}
                    testID="results-map-coordinate-frame"
                  >
                    <Image source={ageAnatomy.source} resizeMode="contain" style={styles.anatomyImage} accessibilityLabel={ageAnatomy.viewLabel} />
                    {mapMarkers.map((marker, index) => {
                      const x = marker.domain === "upper_limb" ? ageAnatomy.shoulderX : marker.domain === "hand" ? ageAnatomy.handX : ageAnatomy.lowerLimbX;
                      const y = marker.domain === "upper_limb" ? ageAnatomy.shoulderY : marker.domain === "hand" ? ageAnatomy.handY : ageAnatomy.lowerLimbY;
                      const presentation = MAP_SEVERITIES[marker.severity];
                      const active = activeMapMarker?.domain === marker.domain;
                      const areaTitle = `${affectedSide === "left" ? "Left" : "Right"} ${MAP_TITLES[marker.domain]}`;
                      return (
                        <Pressable
                          key={marker.domain}
                          testID={`results-map-marker-${marker.domain}`}
                          accessibilityRole="button"
                          accessibilityLabel={`Area ${index + 1}, ${areaTitle}: ${presentation.label}.`}
                          accessibilityHint="Shows details for this movement area"
                          onPress={() => setSelectedMapDomain(marker.domain)}
                          style={[
                            styles.mapMarker,
                            {
                              top: `${y}%` as `${number}%`,
                              left: `${affectedSide === "right" ? x : 100 - x}%` as `${number}%`,
                              borderColor: presentation.color,
                              backgroundColor: active ? presentation.soft : "#FFFFFF",
                              shadowColor: presentation.color,
                            },
                            active && styles.mapMarkerActive,
                          ]}
                        >
                          <Text style={[styles.mapMarkerNumber, { color: presentation.color }]}>{index + 1}</Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </View>

                <View style={styles.mapAreasPanel} testID="results-map-areas">
                  <View style={styles.mapAreasHeader}>
                    <Text style={styles.mapAreasTitle}>Areas</Text>
                  </View>
                  {mapMarkers.map((marker, index) => {
                    const presentation = MAP_SEVERITIES[marker.severity];
                    const active = activeMapMarker?.domain === marker.domain;
                    const areaTitle = `${affectedSide === "left" ? "Left" : "Right"} ${MAP_TITLES[marker.domain]}`;
                    return (
                      <Pressable
                        key={marker.domain}
                        testID={`results-map-area-${marker.domain}`}
                        accessibilityRole="button"
                        accessibilityState={{ selected: active }}
                        accessibilityLabel={`Area ${index + 1}, ${areaTitle}, ${presentation.label}`}
                        accessibilityHint="Selects this area and shows its explanation"
                        onPress={() => setSelectedMapDomain(marker.domain)}
                        style={[
                          styles.mapAreaRow,
                          {
                            borderLeftColor: active ? presentation.color : "transparent",
                            backgroundColor: active ? presentation.soft : "#FFFFFF",
                          },
                        ]}
                      >
                        <View style={[styles.mapAreaNumber, { borderColor: presentation.color }]}>
                          <Text style={[styles.mapAreaNumberText, { color: presentation.color }]}>{index + 1}</Text>
                        </View>
                        <View style={styles.mapAreaIcon}>
                          <Ionicons name={MAP_DOMAIN_ICONS[marker.domain]} size={isWide ? 46 : 38} color={presentation.color} />
                        </View>
                        <View style={styles.mapAreaCopy}>
                          <Text style={[styles.mapAreaTitle, isWide && styles.mapAreaTitleWide]}>{areaTitle}</Text>
                          <Text style={[styles.mapAreaStatus, isWide && styles.mapAreaStatusWide, { color: presentation.color }]}>{presentation.label}</Text>
                          {active && (
                            <View testID="results-map-detail">
                              <Text style={[styles.mapAreaDetail, isWide && styles.mapAreaDetailWide]}>{marker.detail}</Text>
                              <Text style={[styles.mapAreaMeta, isWide && styles.mapAreaMetaWide]}>
                                {marker.source === "observed"
                                  ? `${marker.coverage}% task coverage · ${marker.findings} finding${marker.findings === 1 ? "" : "s"} to review`
                                  : "Based on your survey answers; completed camera tasks refine this area."}
                              </Text>
                            </View>
                          )}
                        </View>
                        <Ionicons name="chevron-forward" size={30} color="#0D4C35" />
                      </Pressable>
                    );
                  })}
                </View>
              </View>
            </View>
          )}
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

          <Pressable onPress={goPlan} style={styles.cta} testID={canViewPlan ? "results-view-plan" : "results-return-home"}>
            <Text style={styles.ctaText}>{canViewPlan ? "View your rehab plan" : "Return home"}</Text>
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
  mapPanel: { borderWidth: 1, borderColor: "#CBD2CC", borderRadius: radius.sm, backgroundColor: "#FFFEFC", padding: 32, marginBottom: spacing.md, overflow: "hidden" },
  mapPanelNarrow: { padding: spacing.md },
  mapHeading: { fontSize: 38, lineHeight: 47, fontWeight: "900", color: "#0C402E" },
  mapHeadingNarrow: { fontSize: 30, lineHeight: 38 },
  mapInstruction: { marginTop: 8, fontSize: 19, lineHeight: 27, color: "#243B32" },
  mapInstructionNarrow: { fontSize: 17, lineHeight: 24 },
  mapLayout: { marginTop: spacing.lg, flexDirection: "row", alignItems: "center", gap: 32 },
  mapLayoutStacked: { flexDirection: "column", gap: spacing.md },
  mapFigure: { flex: 0.42, minWidth: 250, alignItems: "center", justifyContent: "center", paddingVertical: spacing.sm },
  mapFigureStacked: { width: "100%", minWidth: 0 },
  mapCanvas: { position: "relative", alignSelf: "center" },
  mapMarker: { position: "absolute", width: 56, height: 56, marginLeft: -28, marginTop: -28, borderRadius: 28, borderWidth: 2, alignItems: "center", justifyContent: "center", zIndex: 3, shadowOpacity: 0.08, shadowRadius: 6, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  mapMarkerActive: { borderWidth: 3, transform: [{ scale: 1.08 }], shadowOpacity: 0.26, shadowRadius: 13, elevation: 5, zIndex: 5 },
  mapMarkerNumber: { fontSize: 22, lineHeight: 27, fontWeight: "900" },
  mapAreasPanel: { flex: 0.58, minWidth: 0, width: "100%", borderWidth: 1, borderColor: "#D4D9D5", borderRadius: radius.sm, backgroundColor: "#FFFFFF", overflow: "hidden" },
  mapAreasHeader: { minHeight: 72, justifyContent: "center", paddingHorizontal: spacing.lg, borderBottomWidth: 1, borderBottomColor: "#DDE2DE" },
  mapAreasTitle: { fontSize: 25, lineHeight: 31, fontWeight: "900", color: "#123F2F" },
  mapAreaRow: { minHeight: 142, flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderTopWidth: 1, borderTopColor: "#DDE2DE", borderLeftWidth: 6 },
  mapAreaNumber: { width: 52, height: 52, borderRadius: 26, borderWidth: 2, alignItems: "center", justifyContent: "center", backgroundColor: "#FFFFFF" },
  mapAreaNumberText: { fontSize: 22, lineHeight: 27, fontWeight: "900" },
  mapAreaIcon: { width: 58, alignItems: "center", justifyContent: "center" },
  mapAreaCopy: { flex: 1, minWidth: 0 },
  mapAreaTitle: { fontSize: 19, lineHeight: 25, fontWeight: "900", color: "#123F2F" },
  mapAreaTitleWide: { fontSize: 22, lineHeight: 29 },
  mapAreaStatus: { marginTop: 3, fontSize: 17, lineHeight: 23, fontWeight: "700" },
  mapAreaStatusWide: { fontSize: 19, lineHeight: 25 },
  mapAreaDetail: { marginTop: 7, fontSize: 15, lineHeight: 22, color: "#273D34" },
  mapAreaDetailWide: { fontSize: 17, lineHeight: 25 },
  mapAreaMeta: { marginTop: 5, fontSize: 13, lineHeight: 18, fontWeight: "700", color: "#617067" },
  mapAreaMetaWide: { fontSize: 14, lineHeight: 20 },
  snapshotPanelWide: { flexDirection: "row", alignItems: "stretch" },
  anatomyPane: { backgroundColor: "#FFFCF8" },
  anatomyPaneWide: { width: "48%", borderRightWidth: 1, borderRightColor: "#D8DED8" },
  anatomyStage: { height: 430, alignItems: "center", justifyContent: "center", overflow: "hidden", backgroundColor: "#FFFCF8" },
  anatomyStageWide: { height: 680 },
  anatomyCanvas: { height: "100%", aspectRatio: 866 / 1817, position: "relative" },
  anatomyImage: { ...StyleSheet.absoluteFillObject, width: "100%", height: "100%" },
  bodyMarker: { position: "absolute", width: 68, height: 68, marginTop: -34, marginLeft: -34, borderRadius: 34, borderWidth: 2, borderColor: "#F26E5A", backgroundColor: "rgba(241,108,90,0.24)", alignItems: "center", justifyContent: "center", shadowColor: "#F06B58", shadowOpacity: 0.22, shadowRadius: 10, shadowOffset: { width: 0, height: 0 } },
  markerCore: { width: 16, height: 16, borderRadius: 8, backgroundColor: "#F06B58", borderWidth: 3, borderColor: "#FFFFFF" },
  surveyHighlight: { position: "absolute", width: 56, height: 56, marginLeft: -28, marginTop: -28, borderRadius: 28, borderWidth: 2, zIndex: 2 },
  surveyHighlightNote: { marginTop: spacing.sm, paddingHorizontal: spacing.sm, fontSize: 12, lineHeight: 17, color: "#5D6962", fontWeight: "600" },
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
