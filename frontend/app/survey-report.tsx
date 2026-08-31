import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { authedFetch } from "@/src/auth";
import { ActivityMetric, DailyActivitiesBoard } from "@/src/components/DailyActivitiesPanel";
import { getAgeAnatomyPresentation, loadPatientAgeBand } from "@/src/ageAnatomy";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { colors, radius, spacing } from "@/src/theme";

// The three-page assessment report. When Alira cannot assign any camera
// tasks, this report is built from the survey alone and is the patient's
// first stop: page 1 daily-activity scores, page 2 the anatomy map with
// pin-pointed problems, page 3 the rehab plan. Viewing it hands the Home
// next step over to the rehab plan.


type FunctionalPin = {
  domain: "upper_limb" | "hand" | "lower_limb";
  title: string;
  affected_side: "left" | "right";
  tier: number;
  severity: "needs_attention" | "building_strength" | "moving_well";
  problem: string;
};

type CaregiverProgrammeSummary = {
  id: string;
  domain: string;
  goal: string;
  muscle_groups: string[];
  dose: string;
};

type SurveyReport = {
  source: "survey_only" | "survey_and_tasks";
  daily_activities: { activities: ActivityMetric[] };
  functional_problems: { affected_side: "left" | "right"; pins: FunctionalPin[]; reason: string };
  rehab_plan: {
    type: "caregiver_delivered" | "camera_guided" | "pending_assessment";
    caregiver_plan?: { programmes: CaregiverProgrammeSummary[] };
    exercises?: { id: string; name?: string; title?: string }[];
    message?: string;
  };
};

const SEVERITY_PRESENTATION = {
  needs_attention: { color: "#F05F4C", soft: "#FCE7E3", label: "Needs attention", icon: "alert" as const },
  building_strength: { color: "#DEA128", soft: "#FFF3D8", label: "Building strength", icon: "barbell-outline" as const },
  moving_well: { color: "#3E8256", soft: "#E5F1E8", label: "Moving well", icon: "checkmark" as const },
};

const PAGE_TITLES = ["Daily life", "Where the problems are", "Your rehab plan"];
const CACHE_KEY = "survey-report";
const ANATOMY_ASPECT_RATIO = 866 / 1816;

export default function SurveyReportScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const cached = getScreenCache<SurveyReport>(CACHE_KEY);
  const [report, setReport] = useState<SurveyReport | null>(cached ?? null);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(!cached);
  const [error, setError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);
  const [selectedPin, setSelectedPin] = useState<FunctionalPin | null>(null);
  const [ageBand, setAgeBand] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void loadPatientAgeBand().then((saved) => { if (active) setAgeBand(saved); });
    return () => { active = false; };
  }, []);

  const load = useCallback(async () => {
    try {
      const response = await authedFetch("/api/assessment/survey-report");
      const body = await response.json().catch(() => null);
      if (!response.ok) throw new Error(body?.detail || "Could not load the assessment report.");
      setReport(body as SurveyReport);
      setScreenCache<SurveyReport>(CACHE_KEY, body as SurveyReport);
      setError(null);
    } catch (e: any) {
      setError(String(e?.message || e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const finishReport = async () => {
    if (finishing) return;
    setFinishing(true);
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    // Recording the view is what moves Alira's Home next step on to the plan.
    await authedFetch("/api/alira/survey-report-viewed", { method: "POST", body: JSON.stringify({}) }).catch(() => null);
    const planType = report?.rehab_plan?.type;
    if (planType === "caregiver_delivered") router.replace("/caregiver-plan" as never);
    else if (planType === "camera_guided") router.replace("/rehab-plan" as never);
    else router.replace("/");
  };

  const anatomy = getAgeAnatomyPresentation(ageBand);
  const desiredAnatomyHeight = Math.min(480, Math.max(360, width * 1.1));
  const anatomyWidth = Math.min(
    desiredAnatomyHeight * ANATOMY_ASPECT_RATIO,
    Math.max(120, width - spacing.lg * 2),
  );
  const anatomyHeight = anatomyWidth / ANATOMY_ASPECT_RATIO;
  const pins = report?.functional_problems?.pins ?? [];
  const affectedSide = report?.functional_problems?.affected_side ?? "right";
  const activePin = selectedPin ?? pins.find((pin) => pin.severity === "needs_attention") ?? pins[0] ?? null;

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable
          onPress={() => (page > 0 ? setPage(page - 1) : router.back())}
          style={styles.backBtn}
          testID="survey-report-back"
        >
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Assessment report</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.pagerRow} testID="survey-report-pager">
        {PAGE_TITLES.map((title, index) => (
          <View key={title} style={styles.pagerStep}>
            <View style={[styles.pagerDot, index === page && styles.pagerDotActive, index < page && styles.pagerDotDone]}>
              {index < page
                ? <Ionicons name="checkmark" size={13} color={colors.onBrandPrimary} />
                : <Text style={[styles.pagerDotText, index === page && styles.pagerDotTextActive]}>{index + 1}</Text>}
            </View>
            <Text style={[styles.pagerLabel, index === page && styles.pagerLabelActive]}>{title}</Text>
          </View>
        ))}
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {loading && !report && <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.lg }} />}
        {error && <Text style={styles.errorText}>{error}</Text>}

        {report && report.source === "survey_only" && (
          <View style={styles.sourceBanner} testID="survey-report-source">
            <Ionicons name="document-text-outline" size={16} color="#6B4A0B" />
            <Text style={styles.sourceBannerText}>
              This report is based only on your survey answers. A camera assessment, when it becomes suitable, will refine it.
            </Text>
          </View>
        )}

        {report && page === 0 && (
          <View testID="survey-report-page-activities">
            <DailyActivitiesBoard activities={report.daily_activities.activities} />
          </View>
        )}

        {report && page === 1 && (
          <View testID="survey-report-page-anatomy">
            <Text style={styles.pageTitle}>Where the problems are</Text>
            <Text style={styles.pageSub}>{report.functional_problems.reason}</Text>
            <View
              style={[styles.mapCanvas, { width: anatomyWidth, height: anatomyHeight }]}
              testID="survey-report-anatomy-coordinate-frame"
            >
              <Image source={anatomy.source} resizeMode="contain" style={styles.anatomyImage} accessibilityLabel={anatomy.viewLabel} />
              {pins.map((pin) => {
                const x = pin.domain === "upper_limb" ? anatomy.shoulderX : pin.domain === "hand" ? anatomy.handX : anatomy.lowerLimbX;
                const y = pin.domain === "upper_limb" ? anatomy.shoulderY : pin.domain === "hand" ? anatomy.handY : anatomy.lowerLimbY;
                const severity = SEVERITY_PRESENTATION[pin.severity];
                const active = activePin?.domain === pin.domain;
                return (
                  <Pressable
                    key={pin.domain}
                    testID={`survey-report-pin-${pin.domain}`}
                    accessibilityLabel={`${pin.title}: ${severity.label}`}
                    onPress={() => setSelectedPin(pin)}
                    style={[
                      styles.pin,
                      {
                        top: `${y}%` as `${number}%`,
                        left: `${affectedSide === "right" ? x : 100 - x}%` as `${number}%`,
                        borderColor: severity.color,
                        backgroundColor: severity.soft,
                      },
                      active && styles.pinActive,
                    ]}
                  >
                    <Ionicons name={severity.icon} size={20} color={severity.color} />
                  </Pressable>
                );
              })}
            </View>
            {activePin && (
              <View style={[styles.pinDetail, { borderColor: SEVERITY_PRESENTATION[activePin.severity].color }]} testID="survey-report-pin-detail">
                <View style={[styles.pinDetailBadge, { backgroundColor: SEVERITY_PRESENTATION[activePin.severity].soft }]}>
                  <Ionicons name={SEVERITY_PRESENTATION[activePin.severity].icon} size={14} color={SEVERITY_PRESENTATION[activePin.severity].color} />
                  <Text style={[styles.pinDetailBadgeText, { color: SEVERITY_PRESENTATION[activePin.severity].color }]}>
                    {SEVERITY_PRESENTATION[activePin.severity].label}
                  </Text>
                </View>
                <Text style={styles.pinDetailTitle}>
                  {(activePin.affected_side === "left" ? "Left " : "Right ") + activePin.title.toLowerCase()}
                </Text>
                <Text style={styles.pinDetailText}>{activePin.problem}</Text>
              </View>
            )}
          </View>
        )}

        {report && page === 2 && (
          <View testID="survey-report-page-plan">
            <Text style={styles.pageTitle}>Your rehab plan</Text>
            {report.rehab_plan.type === "caregiver_delivered" && (
              <>
                <Text style={styles.pageSub}>
                  Because camera tasks are not suitable right now, your plan is delivered by your carer: gentle strengthening and relaxation of the affected muscle groups, ticked off daily.
                </Text>
                {(report.rehab_plan.caregiver_plan?.programmes || []).map((programme) => (
                  <View key={programme.id} style={styles.planRow}>
                    <View style={styles.planIcon}><Ionicons name="hand-left-outline" size={18} color={colors.brandPrimary} /></View>
                    <View style={styles.planCopy}>
                      <Text style={styles.planGoal}>{programme.goal}</Text>
                      <Text style={styles.planMeta}>{programme.muscle_groups.join(", ")}</Text>
                      <Text style={styles.planDose}>{programme.dose}</Text>
                    </View>
                  </View>
                ))}
              </>
            )}
            {report.rehab_plan.type === "camera_guided" && (
              <>
                <Text style={styles.pageSub}>Your guided exercise plan from the completed assessment.</Text>
                {(report.rehab_plan.exercises || []).map((exercise) => (
                  <View key={exercise.id} style={styles.planRow}>
                    <View style={styles.planIcon}><Ionicons name="fitness-outline" size={18} color={colors.brandPrimary} /></View>
                    <View style={styles.planCopy}>
                      <Text style={styles.planGoal}>{exercise.name || exercise.title || exercise.id}</Text>
                    </View>
                  </View>
                ))}
              </>
            )}
            {report.rehab_plan.type === "pending_assessment" && (
              <Text style={styles.pageSub}>{report.rehab_plan.message}</Text>
            )}
          </View>
        )}
      </ScrollView>

      <View style={[styles.cta, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable
          testID="survey-report-next"
          disabled={loading || finishing || !report}
          onPress={() => {
            if (page < 2) { setPage(page + 1); return; }
            void finishReport();
          }}
          style={[styles.ctaBtn, (loading || finishing) && { opacity: 0.4 }]}
        >
          <Ionicons name={page < 2 ? "arrow-forward" : "clipboard-outline"} size={20} color={colors.onBrandPrimary} />
          <Text style={styles.ctaText}>{page < 2 ? "Next" : "Go to my rehab plan"}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  pagerRow: { flexDirection: "row", justifyContent: "space-around", paddingVertical: spacing.sm, paddingHorizontal: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  pagerStep: { alignItems: "center", gap: 4, flex: 1 },
  pagerDot: { width: 26, height: 26, borderRadius: 13, borderWidth: 2, borderColor: colors.border, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  pagerDotActive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  pagerDotDone: { borderColor: colors.brandPrimary, backgroundColor: colors.brandPrimary },
  pagerDotText: { fontSize: 12, fontWeight: "800", color: colors.onSurfaceSecondary },
  pagerDotTextActive: { color: colors.brandPrimary },
  pagerLabel: { fontSize: 11, lineHeight: 14, fontWeight: "700", color: colors.onSurfaceSecondary, textAlign: "center" },
  pagerLabelActive: { color: colors.brandPrimary },
  scroll: { width: "100%", maxWidth: 1724, alignSelf: "center", padding: spacing.lg, paddingBottom: 140 },
  sourceBanner: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, backgroundColor: "#FFF4DA", borderRadius: radius.sm, padding: spacing.sm, marginBottom: spacing.md },
  sourceBannerText: { flex: 1, fontSize: 12, lineHeight: 17, color: "#6B4A0B", fontWeight: "700" },
  pageTitle: { fontSize: 24, lineHeight: 30, fontWeight: "800", color: colors.onSurface },
  pageSub: { fontSize: 14, lineHeight: 20, color: colors.onSurfaceSecondary, marginTop: spacing.sm, marginBottom: spacing.md },
  activityRow: { borderTopWidth: 1, borderTopColor: "#ECEFEC", paddingVertical: spacing.sm, gap: 4 },
  activityTop: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  badgeGroup: { flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap", justifyContent: "flex-end" },
  activityName: { fontSize: 15, fontWeight: "800", color: colors.onSurface, flexShrink: 1 },
  badge: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill },
  badgeText: { fontSize: 11, fontWeight: "800" },
  activityDetail: { fontSize: 14, lineHeight: 20, color: "#35443C" },
  mapCanvas: { position: "relative", alignSelf: "center" },
  anatomyImage: { width: "100%", height: "100%" },
  pin: { position: "absolute", width: 44, height: 44, marginLeft: -22, marginTop: -22, borderRadius: 22, borderWidth: 2, alignItems: "center", justifyContent: "center", zIndex: 3 },
  pinActive: { borderWidth: 4, transform: [{ scale: 1.1 }], zIndex: 5 },
  pinDetail: { marginTop: spacing.md, borderWidth: 1, borderRadius: radius.md, padding: spacing.md, gap: 6, backgroundColor: colors.surfaceSecondary },
  pinDetailBadge: { alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 4, borderRadius: radius.pill },
  pinDetailBadgeText: { fontSize: 12, fontWeight: "800" },
  pinDetailTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  pinDetailText: { fontSize: 14, lineHeight: 20, color: "#35443C" },
  planRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", borderTopWidth: 1, borderTopColor: "#ECEFEC", paddingVertical: spacing.sm },
  planIcon: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  planCopy: { flex: 1, gap: 2 },
  planGoal: { fontSize: 15, lineHeight: 21, fontWeight: "800", color: colors.onSurface },
  planMeta: { fontSize: 13, lineHeight: 18, color: colors.onSurfaceSecondary },
  planDose: { fontSize: 12, lineHeight: 17, color: colors.onSurfaceSecondary, fontStyle: "italic" },
  errorText: { color: colors.error, fontSize: 14, lineHeight: 20, marginVertical: spacing.md },
  cta: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  ctaBtn: { width: "100%", maxWidth: 620, alignSelf: "center", minHeight: 54, borderRadius: radius.md, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  ctaText: { color: colors.onBrandPrimary, fontSize: 16, fontWeight: "800" },
});
