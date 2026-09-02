import { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Animated, Image, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Assessment, fetchAssessment, fetchPatientAssessmentSummary, PatientAssessmentSummary } from "@/src/api";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { getAgeAnatomyPresentation, loadPatientAgeBand } from "@/src/ageAnatomy";
import { colors, radius, spacing } from "@/src/theme";
import { DEMO_ASSESSMENT_ID, demoAssessment, demoPatientAssessmentSummary } from "@/src/demoAssessment";

type DomainId = "upper_limb" | "hand" | "lower_limb";

function statusColor(findings: number, completion: number) {
  if (findings > 0) return { color: "#F05F4C", soft: "#FCE7E3", label: "Needs attention", icon: "alert" as const };
  if (completion < 100) return { color: "#DEA128", soft: "#FFF3D8", label: "Building strength", icon: "barbell-outline" as const };
  return { color: "#3E8256", soft: "#E5F1E8", label: "Moving well", icon: "checkmark" as const };
}

function areaTitle(domain: DomainId, affectedSide: "left" | "right") {
  const side = affectedSide === "left" ? "Left" : "Right";
  if (domain === "upper_limb") return `${side} shoulder`;
  if (domain === "hand") return `${side} hand`;
  return `${side} knee`;
}

type ShinyMapMarkerProps = {
  active: boolean;
  label: string;
  labelSide: "left" | "right";
  onPress: () => void;
  status: ReturnType<typeof statusColor>;
  testID: string;
  x: number;
  y: number;
};

function ShinyMapMarker({ active, label, labelSide, onPress, status, testID, x, y }: ShinyMapMarkerProps) {
  const pulse = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const animation = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, { toValue: 1, duration: 1500, useNativeDriver: true }),
        Animated.timing(pulse, { toValue: 0, duration: 1500, useNativeDriver: true }),
      ]),
    );
    animation.start();
    return () => animation.stop();
  }, [pulse]);

  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`View ${label}`}
      testID={testID}
      style={[
        styles.markerAnchor,
        {
          top: `${y}%` as `${number}%`,
          left: `${x}%` as `${number}%`,
          transform: [{ scale: active ? 1.08 : 1 }],
        },
      ]}
    >
      <Animated.View
        testID={`${testID}-shine`}
        style={[
          styles.markerGlow,
          {
            backgroundColor: status.soft,
            borderColor: status.color,
            opacity: pulse.interpolate({ inputRange: [0, 1], outputRange: [0.3, 0.08] }),
            transform: [{ scale: pulse.interpolate({ inputRange: [0, 1], outputRange: [1, 1.34] }) }],
          },
        ]}
      />
      <View style={[styles.markerOuter, { borderColor: status.color, shadowColor: status.color }]}>
        <View style={[styles.markerMiddle, { borderColor: status.color }]}>
          <View style={[styles.markerCore, { backgroundColor: status.color }]} />
          <Animated.View
            style={[
              styles.markerGlint,
              { opacity: pulse.interpolate({ inputRange: [0, 0.45, 1], outputRange: [0.35, 1, 0.35] }) },
            ]}
          />
        </View>
      </View>
      <Text
        pointerEvents="none"
        style={[
          styles.markerText,
          labelSide === "left" ? styles.markerTextLeft : styles.markerTextRight,
          active && styles.markerTextActive,
        ]}
      >
        {label}
      </Text>
    </Pressable>
  );
}

export default function MovementMapScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<PatientAssessmentSummary | null>(getScreenCache<{ summary: PatientAssessmentSummary; raw: Assessment | null }>(`movement-map:${id}`)?.summary ?? null);
  const [assessment, setAssessment] = useState<Assessment | null>(getScreenCache<{ summary: PatientAssessmentSummary; raw: Assessment | null }>(`movement-map:${id}`)?.raw ?? null);
  const [selected, setSelected] = useState<DomainId>("upper_limb");
  const [detailsExpanded, setDetailsExpanded] = useState(false);
  const [loading, setLoading] = useState(!getScreenCache(`movement-map:${id}`));
  const [profileAgeBand, setProfileAgeBand] = useState<string | null>(null);

  const isDemo = id === DEMO_ASSESSMENT_ID;
  const isWide = width >= 860;
  const pageWidth = Math.min(Math.max(width - 32, 296), 1120);
  const anatomyHeight = isWide ? 650 : Math.min(570, Math.max(430, width * 1.32));

  useEffect(() => {
    let active = true;
    void loadPatientAgeBand().then((savedAgeBand) => {
      if (active && savedAgeBand) setProfileAgeBand(savedAgeBand);
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!id) return;
    if (id === DEMO_ASSESSMENT_ID) {
      setData(demoPatientAssessmentSummary);
      setAssessment(demoAssessment);
      setSelected("upper_limb");
      setLoading(false);
      return;
    }
    Promise.all([fetchPatientAssessmentSummary(id), fetchAssessment(id).catch(() => null)])
      .then(([summary, raw]) => {
        setData(summary);
        setAssessment(raw);
        setScreenCache(`movement-map:${id}`, { summary, raw });
        const firstFinding = summary.insights.domain_metrics.find((domain) => domain.findings_count > 0)?.domain;
        if (firstFinding) setSelected(firstFinding);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const affectedSide: "left" | "right" = assessment?.affected_side?.toLowerCase() === "left" ? "left" : "right";
  const domains = data?.insights.domain_metrics || [];
  const selectedDomain = domains.find((domain) => domain.domain === selected) || domains[0];
  const selectedStatus = statusColor(selectedDomain?.findings_count || 0, selectedDomain?.completion_percent || 0);
  const activation = data?.insights.activation_profile.find((item) => item.domain === selected);
  const ratio = activation?.template_mean ? activation.mean / activation.template_mean : null;
  const reviewGate = data?.clinical_review_gate;
  const planAccessAllowed = reviewGate?.rehab_access === "allowed" || reviewGate?.rehab_access === "interim";
  const interimPlan = reviewGate?.rehab_access === "interim";
  const surveyBasedPlan = reviewGate?.rehab_plan_source === "survey_reported_problems";
  const canViewPlan = data?.rehab_plan_ready === true && planAccessAllowed;
  const noRehabNeeded = reviewGate?.rehab_access === "not_needed" || reviewGate?.status === "no_rehab_needed";
  const ageBand = assessment?.patient_parameters?.age_band || profileAgeBand || (isDemo ? "70-79" : null);
  const ageAnatomy = getAgeAnatomyPresentation(ageBand);
  const selectedAreaTitle = areaTitle(selected, affectedSide);

  const selectedSummary = useMemo(() => {
    const domain = data?.body_function_summary.domains.find((item) => item.domain === selected);
    if (!domain) return "This area was not observed in the completed assessment.";
    return domain.summary;
  }, [data?.body_function_summary.domains, selected]);

  const cycleDomain = (direction: -1 | 1) => {
    const available = domains.map((domain) => domain.domain);
    if (!available.length) return;
    const current = available.indexOf(selected);
    const next = current < 0 ? 0 : (current + direction + available.length) % available.length;
    setSelected(available[next]);
    setDetailsExpanded(false);
  };

  const openPlan = () => {
    if (canViewPlan && id) router.push({ pathname: "/rehab-plan", params: { id } });
    else router.dismissTo("/");
  };
  const selectedPosition = Math.max(0, domains.findIndex((domain) => domain.domain === selected));

  if (loading) {
    return <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /><Text style={styles.loadingText}>Building your movement map...</Text></View>;
  }

  if (!data) {
    return <View style={styles.center}><Text style={styles.errorText}>We could not load your movement map.</Text><Pressable onPress={() => router.dismissTo("/")} style={styles.planButton}><Text style={styles.planButtonText}>Return home</Text></Pressable></View>;
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.xs }]}>
        <Pressable onPress={() => router.back()} style={styles.headerButton} accessibilityLabel="Go back" testID="movement-map-back">
          <Ionicons name="chevron-back" size={26} color="#154B34" />
        </Pressable>
        <View style={styles.headerButton} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={[styles.page, { width: pageWidth }]}>
          <View style={[styles.mapPanel, !isWide && styles.mapPanelNarrow]} testID="movement-map-panel">
            <View style={[styles.panelHeader, !isWide && styles.panelHeaderNarrow]}>
              <View style={styles.panelHeadingCopy}>
                <View style={styles.panelTitleRow}>
                  <Text style={[styles.panelTitle, !isWide && styles.panelTitleNarrow]}>Movement map</Text>
                  {isDemo && (
                    <View style={styles.sampleBadge} testID="movement-map-demo-banner">
                      <Ionicons name="sparkles" size={14} color="#675080" />
                      <Text style={styles.sampleBadgeText}>Sample map</Text>
                    </View>
                  )}
                </View>
                <Text style={styles.panelSubtitle}>{domains.length} areas highlighted. Select one to see its details.</Text>
              </View>
              <View style={styles.frontViewBadge} testID="movement-map-front-view">
                <Ionicons name="body-outline" size={18} color={colors.brandPrimary} />
                <Text style={styles.frontViewText}>Front</Text>
              </View>
            </View>

            <View style={[styles.mapStage, { height: anatomyHeight }]}>
              <View style={[styles.mapCanvas, { height: anatomyHeight }]}>
                <Image source={ageAnatomy.source} resizeMode="contain" style={styles.anatomyImage} accessibilityLabel={ageAnatomy.viewLabel} />
                {domains.map((domain) => {
                  const sourceX = domain.domain === "upper_limb" ? ageAnatomy.shoulderX : domain.domain === "hand" ? ageAnatomy.handX : ageAnatomy.lowerLimbX;
                  const y = domain.domain === "upper_limb" ? ageAnatomy.shoulderY : domain.domain === "hand" ? ageAnatomy.handY : ageAnatomy.lowerLimbY;
                  const x = affectedSide === "right" ? sourceX : 100 - sourceX;
                  const status = statusColor(domain.findings_count, domain.completion_percent);
                  return (
                    <ShinyMapMarker
                      key={domain.domain}
                      active={selected === domain.domain}
                      label={areaTitle(domain.domain, affectedSide)}
                      labelSide={x < 50 ? "left" : "right"}
                      onPress={() => { setSelected(domain.domain); setDetailsExpanded(false); }}
                      status={status}
                      testID={`movement-map-marker-${domain.domain}`}
                      x={x}
                      y={y}
                    />
                  );
                })}
              </View>
            </View>

            <View style={[styles.detailsTray, !isWide && styles.detailsTrayNarrow]} testID="movement-map-detail-panel">
              <View style={[styles.selectedAreaBlock, !isWide && styles.selectedAreaBlockNarrow]}>
                <View style={[styles.detailIcon, { borderColor: selectedStatus.color, backgroundColor: selectedStatus.soft }]}>
                  <Ionicons name={selectedStatus.icon} size={26} color={selectedStatus.color} />
                </View>
                <View style={styles.detailHeadingCopy}>
                  <Text style={styles.detailTitle}>{selectedAreaTitle}</Text>
                  <Text style={[styles.detailStatus, { color: selectedStatus.color }]}>{selectedStatus.label}</Text>
                  <Text style={styles.detailSummary}>{selectedSummary}</Text>
                </View>
              </View>

              <Pressable
                onPress={() => setDetailsExpanded((value) => !value)}
                style={styles.detailsButton}
                accessibilityRole="button"
                testID="movement-map-view-details"
              >
                <Text style={styles.detailsButtonText}>{detailsExpanded ? "Hide details" : "View details"}</Text>
              </Pressable>

              <View style={styles.areaNavigator}>
                <Pressable onPress={() => cycleDomain(-1)} style={styles.areaArrow} accessibilityLabel="Previous highlighted area" testID="movement-map-previous-area">
                  <Ionicons name="chevron-back" size={28} color="#123E2D" />
                </Pressable>
                <Text style={styles.areaCount}>{domains.length ? selectedPosition + 1 : 0} of {domains.length} areas</Text>
                <Pressable onPress={() => cycleDomain(1)} style={styles.areaArrow} accessibilityLabel="Next highlighted area" testID="movement-map-next-area">
                  <Ionicons name="chevron-forward" size={28} color="#123E2D" />
                </Pressable>
              </View>
            </View>

            {detailsExpanded && (
              <View style={styles.expandedDetails} testID="movement-map-expanded-details">
                <View style={[styles.metricList, !isWide && styles.metricListNarrow]}>
                  <View style={styles.metricRow}>
                    <View style={styles.metricIcon}><Ionicons name="clipboard-outline" size={23} color={colors.brandPrimary} /></View>
                    <View><Text style={styles.metricValue}>{selectedDomain?.completion_percent ?? 0}%</Text><Text style={styles.metricLabel}>Task coverage</Text></View>
                  </View>
                  <View style={styles.metricRow}>
                    <View style={styles.metricIcon}><Ionicons name="document-text-outline" size={23} color={colors.brandPrimary} /></View>
                    <View><Text style={styles.metricValue}>{selectedDomain?.findings_count ?? 0}</Text><Text style={styles.metricLabel}>Finding{selectedDomain?.findings_count === 1 ? "" : "s"} to review</Text></View>
                  </View>
                  <View style={styles.metricRow}>
                    <View style={styles.metricIcon}><Ionicons name="stats-chart" size={23} color={colors.brandPrimary} /></View>
                    <View><Text style={styles.metricValue}>{ratio !== null ? `${ratio.toFixed(1)}×` : "—"}</Text><Text style={styles.metricLabel}>Matched demand</Text></View>
                  </View>
                </View>
                <View style={[styles.planSummary, !isWide && styles.planSummaryNarrow]}>
                  <View style={styles.planSummaryCopy}>
                    <Text style={styles.planEyebrow}>NEXT STEP</Text>
                    <Text style={styles.planTitle}>{canViewPlan ? (surveyBasedPlan ? "Your survey-based plan is ready" : "Your rehab plan is ready") : noRehabNeeded ? "No rehab plan is needed" : "Your plan is waiting for review"}</Text>
                    <Text style={styles.planText}>{canViewPlan ? (surveyBasedPlan ? "Selected only from the functional difficulties you reported; movement analysis will not replace the exercises." : "Your plan focuses on the movement areas that need support.") : reviewGate?.patient_message}</Text>
                  </View>
                  <Pressable onPress={openPlan} style={styles.planButton} testID={canViewPlan ? "movement-map-view-plan" : "movement-map-return-home"}>
                    <Ionicons name={canViewPlan ? "clipboard-outline" : "home-outline"} size={20} color="#FFFFFF" />
                    <Text style={styles.planButtonText}>{canViewPlan ? (interimPlan ? "View starting plan" : "View rehab plan") : "Return home"}</Text>
                  </Pressable>
                </View>
              </View>
            )}
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F8FAF8" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.lg, backgroundColor: "#F8FAF8" },
  loadingText: { color: colors.onSurfaceSecondary },
  errorText: { color: colors.error, textAlign: "center" },
  header: { minHeight: 58, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.xs, backgroundColor: "#F8FAF8" },
  headerButton: { width: 46, height: 46, alignItems: "center", justifyContent: "center" },
  content: { alignItems: "center", paddingBottom: spacing.xl },
  page: { alignSelf: "center" },
  mapPanel: { borderWidth: 1, borderColor: "#D3D8D3", borderRadius: radius.sm, backgroundColor: "#FFFEFC", padding: spacing.xl, overflow: "visible" },
  mapPanelNarrow: { padding: spacing.md },
  panelHeader: { minHeight: 72, flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.lg },
  panelHeaderNarrow: { flexDirection: "column", gap: spacing.sm },
  panelHeadingCopy: { flex: 1, minWidth: 0 },
  panelTitleRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  panelTitle: { fontSize: 38, lineHeight: 46, fontWeight: "800", color: "#123E2D" },
  panelTitleNarrow: { fontSize: 28, lineHeight: 34 },
  sampleBadge: { minHeight: 30, flexDirection: "row", alignItems: "center", gap: 6, borderRadius: radius.pill, paddingHorizontal: spacing.sm, backgroundColor: "#F3EDFA", borderWidth: 1, borderColor: "#D9C8ED" },
  sampleBadgeText: { fontSize: 12, lineHeight: 16, fontWeight: "700", color: "#5C486F" },
  panelSubtitle: { marginTop: 3, fontSize: 17, lineHeight: 24, color: colors.onSurfaceSecondary },
  frontViewBadge: { width: 132, minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, borderRadius: radius.sm, borderWidth: 1, borderColor: "#D4DED6", backgroundColor: "#ECF3ED" },
  frontViewText: { fontSize: 16, lineHeight: 22, fontWeight: "800", color: "#123E2D" },
  mapStage: { alignItems: "center", justifyContent: "center", overflow: "visible" },
  mapCanvas: { aspectRatio: 866 / 1816, position: "relative" },
  anatomyImage: { ...StyleSheet.absoluteFillObject, width: "100%", height: "100%" },
  markerAnchor: { position: "absolute", width: 72, height: 72, marginLeft: -36, marginTop: -36, alignItems: "center", justifyContent: "center", zIndex: 4 },
  markerGlow: { position: "absolute", width: 72, height: 72, borderRadius: 36, borderWidth: 2 },
  markerOuter: { width: 58, height: 58, borderRadius: 29, borderWidth: 3, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(255,255,255,0.94)", shadowOffset: { width: 0, height: 0 }, shadowOpacity: 0.42, shadowRadius: 11, elevation: 7 },
  markerMiddle: { width: 38, height: 38, borderRadius: 19, borderWidth: 2, alignItems: "center", justifyContent: "center", backgroundColor: "#FFFFFF" },
  markerCore: { width: 19, height: 19, borderRadius: 10 },
  markerGlint: { position: "absolute", top: 5, right: 7, width: 7, height: 7, borderRadius: 4, backgroundColor: "#FFFFFF" },
  markerText: { position: "absolute", top: 25, width: 150, fontSize: 14, lineHeight: 19, fontWeight: "700", color: "#123E2D" },
  markerTextLeft: { right: 70, textAlign: "right" },
  markerTextRight: { left: 70, textAlign: "left" },
  markerTextActive: { fontWeight: "900" },
  detailsTray: { minHeight: 154, flexDirection: "row", alignItems: "center", gap: spacing.xl, borderWidth: 1, borderColor: "#B8C0B9", borderRadius: radius.sm, backgroundColor: "#FFFEFC", padding: spacing.lg },
  detailsTrayNarrow: { flexDirection: "column", alignItems: "stretch", gap: spacing.md, padding: spacing.md },
  selectedAreaBlock: { flex: 1, minWidth: 0, flexDirection: "row", alignItems: "center", gap: spacing.md },
  selectedAreaBlockNarrow: { width: "100%", alignItems: "flex-start" },
  detailIcon: { width: 58, height: 58, borderRadius: 29, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  detailHeadingCopy: { flex: 1, minWidth: 0 },
  detailTitle: { fontSize: 26, lineHeight: 32, fontWeight: "800", color: "#123E2D" },
  detailStatus: { marginTop: 1, fontSize: 14, lineHeight: 20, fontWeight: "800" },
  detailSummary: { marginTop: 7, fontSize: 16, lineHeight: 23, color: colors.onSurfaceSecondary },
  detailsButton: { minWidth: 168, minHeight: 56, borderWidth: 1, borderColor: "#123E2D", borderRadius: radius.sm, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.lg },
  detailsButtonText: { fontSize: 16, lineHeight: 22, fontWeight: "800", color: "#123E2D" },
  areaNavigator: { minWidth: 230, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  areaArrow: { width: 48, height: 48, alignItems: "center", justifyContent: "center" },
  areaCount: { minWidth: 102, textAlign: "center", fontSize: 15, lineHeight: 21, color: colors.onSurface },
  expandedDetails: { marginTop: spacing.lg, paddingTop: spacing.lg, borderTopWidth: 1, borderTopColor: colors.divider },
  metricList: { flexDirection: "row", alignItems: "stretch", gap: spacing.lg },
  metricListNarrow: { flexDirection: "column", gap: spacing.sm },
  metricRow: { flex: 1, minHeight: 72, flexDirection: "row", alignItems: "center", gap: spacing.md },
  metricIcon: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center", backgroundColor: "#EDF4EF", borderWidth: 1, borderColor: "#D9E5DC" },
  metricValue: { fontSize: 27, lineHeight: 33, fontWeight: "800", color: "#07543B" },
  metricLabel: { fontSize: 13, lineHeight: 18, color: colors.onSurfaceSecondary },
  planSummary: { marginTop: spacing.lg, paddingTop: spacing.lg, borderTopWidth: 1, borderTopColor: colors.divider, flexDirection: "row", alignItems: "center", gap: spacing.lg },
  planSummaryNarrow: { flexDirection: "column", alignItems: "stretch" },
  planSummaryCopy: { flex: 1, minWidth: 0 },
  planEyebrow: { fontSize: 13, fontWeight: "900", color: colors.brandPrimary },
  planTitle: { marginTop: 4, fontSize: 23, lineHeight: 29, fontWeight: "800", color: "#164631" },
  planText: { marginTop: 4, fontSize: 14, lineHeight: 20, color: colors.onSurfaceSecondary },
  planButton: { minWidth: 216, minHeight: 56, borderRadius: radius.sm, backgroundColor: "#07543B", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.lg },
  planButtonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
});
