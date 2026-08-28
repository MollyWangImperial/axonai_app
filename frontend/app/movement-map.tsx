import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Assessment, fetchAssessment, fetchPatientAssessmentSummary, PatientAssessmentSummary } from "@/src/api";
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
  return `${side} leg`;
}

function domainIcon(domain: DomainId) {
  if (domain === "lower_limb") return "walk-outline" as const;
  if (domain === "hand") return "hand-left-outline" as const;
  return "body-outline" as const;
}

export default function MovementMapScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<PatientAssessmentSummary | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [selected, setSelected] = useState<DomainId>("upper_limb");
  const [loading, setLoading] = useState(true);
  const [profileAgeBand, setProfileAgeBand] = useState<string | null>(null);

  const isDemo = id === DEMO_ASSESSMENT_ID;
  const isWide = width >= 860;
  const pageWidth = Math.min(Math.max(width - 32, 296), 1120);
  const anatomyHeight = isWide ? 760 : Math.min(580, Math.max(430, width * 1.34));

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
  const canViewPlan = data?.rehab_plan_ready === true && reviewGate?.rehab_access === "allowed";
  const noRehabNeeded = reviewGate?.rehab_access === "not_needed" || reviewGate?.status === "no_rehab_needed";
  const ageBand = assessment?.patient_parameters?.age_band || profileAgeBand || (isDemo ? "70-79" : null);
  const ageAnatomy = getAgeAnatomyPresentation(ageBand);
  const selectedAreaTitle = areaTitle(selected, affectedSide);

  const selectedSummary = useMemo(() => {
    const domain = data?.body_function_summary.domains.find((item) => item.domain === selected);
    if (!domain) return "This area was not observed in the completed assessment.";
    return domain.summary;
  }, [data?.body_function_summary.domains, selected]);

  const cycleDomain = () => {
    const available = domains.map((domain) => domain.domain);
    if (!available.length) return;
    const current = available.indexOf(selected);
    setSelected(available[(current + 1) % available.length]);
  };

  const openPlan = () => {
    if (canViewPlan && id) router.push({ pathname: "/rehab-plan", params: { id } });
    else router.replace("/");
  };

  if (loading) {
    return <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /><Text style={styles.loadingText}>Building your movement map...</Text></View>;
  }

  if (!data) {
    return <View style={styles.center}><Text style={styles.errorText}>We could not load your movement map.</Text><Pressable onPress={() => router.replace("/")} style={styles.planButton}><Text style={styles.planButtonText}>Return home</Text></Pressable></View>;
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.headerButton} accessibilityLabel="Go back" testID="movement-map-back">
          <Ionicons name="chevron-back" size={26} color="#154B34" />
        </Pressable>
        <Text style={[styles.headerTitle, !isWide && styles.headerTitleNarrow]}>Movement map</Text>
        <View style={styles.headerButton} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={[styles.page, { width: pageWidth }]}>
          {isDemo && (
            <View style={styles.demoBanner} testID="movement-map-demo-banner">
              <Ionicons name="sparkles" size={23} color="#675080" />
              <Text style={styles.demoBannerText}>Sample movement map. Your real map will use your completed assessment.</Text>
            </View>
          )}

          <View style={[styles.mapPanel, !isWide && styles.mapPanelNarrow]}>
            <View style={[styles.panelLead, !isWide && styles.panelLeadNarrow]}>
              <Text style={styles.panelInstruction}>Select a highlighted area to view its details.</Text>
            </View>

            <View style={[styles.legend, isWide && styles.legendWide]}>
              {[
                { color: "#F05F4C", soft: "#FCE7E3", label: "Needs attention", icon: "alert" as const },
                { color: "#DEA128", soft: "#FFF3D8", label: "Building strength", icon: "barbell-outline" as const },
                { color: "#3E8256", soft: "#E5F1E8", label: "Moving well", icon: "checkmark" as const },
              ].map((item) => (
                <View key={item.label} style={[styles.legendItem, !isWide && styles.legendItemNarrow]}>
                  <View style={[styles.legendIcon, !isWide && styles.legendIconNarrow, { borderColor: item.color, backgroundColor: item.soft }]}>
                    <Ionicons name={item.icon} size={27} color={item.color} />
                  </View>
                  <Text style={[styles.legendText, !isWide && styles.legendTextNarrow]}>{item.label}</Text>
                </View>
              ))}
            </View>

            <View style={styles.panelDivider} />

            <View style={[styles.workspace, isWide && styles.workspaceWide]}>
                <View style={[styles.anatomyColumn, isWide && styles.anatomyColumnWide]}>
                  <View style={[styles.mapCanvas, { height: anatomyHeight }]}>
                    <Image source={ageAnatomy.source} resizeMode="contain" style={styles.anatomyImage} accessibilityLabel={ageAnatomy.viewLabel} />
                    {domains.map((domain) => {
                      const x = domain.domain === "upper_limb" ? ageAnatomy.shoulderX : domain.domain === "hand" ? ageAnatomy.handX : ageAnatomy.lowerLimbX;
                      const y = domain.domain === "upper_limb" ? ageAnatomy.shoulderY : domain.domain === "hand" ? ageAnatomy.handY : ageAnatomy.lowerLimbY;
                      const status = statusColor(domain.findings_count, domain.completion_percent);
                      const active = selected === domain.domain;
                      return (
                        <Pressable
                          key={domain.domain}
                          onPress={() => setSelected(domain.domain)}
                          accessibilityLabel={`View ${areaTitle(domain.domain, affectedSide)}`}
                          testID={`movement-map-marker-${domain.domain}`}
                          style={[
                            styles.mapMarker,
                            {
                              top: `${y}%` as `${number}%`,
                              left: `${affectedSide === "right" ? x : 100 - x}%` as `${number}%`,
                              borderColor: status.color,
                              backgroundColor: status.soft,
                            },
                            active && styles.mapMarkerActive,
                          ]}
                        >
                          <View style={styles.mapMarkerInner}>
                            <Ionicons name={status.icon} size={25} color={status.color} />
                          </View>
                          {active && (
                            <View style={[styles.markerLabel, affectedSide === "right" ? styles.markerLabelRight : styles.markerLabelLeft, { borderColor: status.color }]}>
                              <Text style={[styles.markerLabelText, { color: status.color }]}>{selectedAreaTitle}</Text>
                            </View>
                          )}
                        </Pressable>
                      );
                    })}
                  </View>
                </View>

                <View style={[styles.detailPanel, isWide && styles.detailPanelWide]} testID="movement-map-detail-panel">
                  <View style={styles.detailHeader}>
                    <View style={[styles.detailIcon, { backgroundColor: selectedStatus.soft }]}>
                      <Ionicons name={domainIcon(selected)} size={31} color={selectedStatus.color} />
                    </View>
                    <View style={styles.detailHeadingCopy}>
                      <Text style={styles.detailTitle}>{selectedAreaTitle}</Text>
                      <View style={[styles.statusPill, { backgroundColor: selectedStatus.soft }]}>
                        <Text style={[styles.statusPillText, { color: selectedStatus.color }]}>{selectedStatus.label}</Text>
                      </View>
                    </View>
                  </View>

                  <Text style={styles.detailSummary}>{selectedSummary}</Text>
                  <View style={styles.detailDivider} />

                  <View style={styles.metricList}>
                    <View style={styles.metricRow}>
                      <View style={styles.metricIcon}><Ionicons name="clipboard-outline" size={25} color={colors.brandPrimary} /></View>
                      <Text style={styles.metricValue}>{selectedDomain?.completion_percent ?? 0}%</Text>
                      <Text style={styles.metricLabel}>Task coverage</Text>
                    </View>
                    <View style={styles.metricRow}>
                      <View style={styles.metricIcon}><Ionicons name="document-text-outline" size={25} color={colors.brandPrimary} /></View>
                      <Text style={styles.metricValue}>{selectedDomain?.findings_count ?? 0}</Text>
                      <Text style={styles.metricLabel}>Finding{selectedDomain?.findings_count === 1 ? "" : "s"} to review</Text>
                    </View>
                    <View style={styles.metricRow}>
                      <View style={styles.metricIcon}><Ionicons name="stats-chart" size={25} color={colors.brandPrimary} /></View>
                      <Text style={styles.metricValue}>{ratio !== null ? `${ratio.toFixed(1)}×` : "—"}</Text>
                      <Text style={styles.metricLabel}>Matched demand</Text>
                    </View>
                  </View>

                  <Pressable onPress={cycleDomain} style={[styles.selectButton, isWide && styles.selectButtonWide]} testID="movement-map-select-another">
                    <Text style={styles.selectButtonText}>Select another area</Text>
                  </Pressable>
                </View>
            </View>
          </View>

          <View style={styles.planSection}>
            <Text style={styles.planEyebrow}>NEXT STEP</Text>
            <Text style={styles.planTitle}>{canViewPlan ? "Your rehab plan is ready" : noRehabNeeded ? "No rehab plan is needed" : "Your plan is waiting for review"}</Text>
            <Text style={styles.planText}>{canViewPlan ? "Your plan focuses on the movement areas that need support." : reviewGate?.patient_message}</Text>
            <Pressable onPress={openPlan} style={styles.planButton} testID={canViewPlan ? "movement-map-view-plan" : "movement-map-return-home"}>
              <Ionicons name={canViewPlan ? "clipboard-outline" : "home-outline"} size={23} color="#FFFFFF" />
              <Text style={styles.planButtonText}>{canViewPlan ? "View your rehab plan" : "Return home"}</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FFFEFB" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.lg, backgroundColor: "#FFFEFB" },
  loadingText: { color: colors.onSurfaceSecondary },
  errorText: { color: colors.error, textAlign: "center" },
  header: { minHeight: 76, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, backgroundColor: "#FFFEFB" },
  headerButton: { width: 46, height: 46, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 38, lineHeight: 46, fontWeight: "800", color: "#123E2D" },
  headerTitleNarrow: { fontSize: 24, lineHeight: 30 },
  content: { alignItems: "center", paddingBottom: spacing.xl },
  page: { alignSelf: "center" },
  demoBanner: { minHeight: 72, flexDirection: "row", alignItems: "center", gap: spacing.md, borderRadius: radius.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, marginBottom: spacing.lg, backgroundColor: "#F3EDFA", borderWidth: 1, borderColor: "#D9C8ED" },
  demoBannerText: { flex: 1, fontSize: 16, lineHeight: 23, color: "#5C486F" },
  mapPanel: { borderWidth: 1, borderColor: "#C9CEC9", borderRadius: radius.sm, backgroundColor: "#FFFFFF", padding: spacing.xl },
  mapPanelNarrow: { padding: spacing.md },
  panelLead: { minHeight: 58, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.lg },
  panelLeadNarrow: { flexDirection: "column", alignItems: "stretch", gap: spacing.md },
  panelInstruction: { flex: 1, fontSize: 17, lineHeight: 24, fontWeight: "800", color: "#174833" },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.md },
  legendWide: { justifyContent: "space-between", paddingRight: 80 },
  legendItem: { minWidth: 180, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  legendItemNarrow: { minWidth: 0, flexBasis: "46%", flexGrow: 1, gap: spacing.xs },
  legendIcon: { width: 54, height: 54, borderRadius: 27, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  legendIconNarrow: { width: 46, height: 46, borderRadius: 23 },
  legendText: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  legendTextNarrow: { fontSize: 13 },
  panelDivider: { height: 1, backgroundColor: colors.divider, marginTop: spacing.lg },
  workspace: { paddingTop: spacing.lg },
  workspaceWide: { flexDirection: "row", alignItems: "center", gap: spacing.xl },
  anatomyColumn: { alignItems: "center", justifyContent: "center", minWidth: 0 },
  anatomyColumnWide: { flex: 1.05 },
  mapCanvas: { aspectRatio: 866 / 1816, position: "relative" },
  anatomyImage: { ...StyleSheet.absoluteFillObject, width: "100%", height: "100%" },
  mapMarker: { position: "absolute", width: 60, height: 60, marginLeft: -30, marginTop: -30, borderRadius: 30, borderWidth: 2, alignItems: "center", justifyContent: "center", zIndex: 3 },
  mapMarkerActive: { borderWidth: 4, transform: [{ scale: 1.08 }], zIndex: 5 },
  mapMarkerInner: { width: 42, height: 42, borderRadius: 21, backgroundColor: "rgba(255,255,255,0.92)", alignItems: "center", justifyContent: "center" },
  markerLabel: { position: "absolute", top: 12, width: 132, minHeight: 36, justifyContent: "center", paddingHorizontal: spacing.sm, borderWidth: 1, borderRadius: radius.sm, backgroundColor: "#FFFFFF" },
  markerLabelRight: { left: 66 },
  markerLabelLeft: { right: 66 },
  markerLabelText: { fontSize: 12, fontWeight: "800", textAlign: "center" },
  detailPanel: { marginTop: spacing.md, borderWidth: 1, borderColor: "#CDD3CE", borderRadius: radius.sm, backgroundColor: "#FFFEFB", padding: spacing.lg },
  detailPanelWide: { width: 430, minHeight: 700, marginTop: 0, padding: spacing.xl },
  detailHeader: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  detailIcon: { width: 72, height: 72, borderRadius: 36, alignItems: "center", justifyContent: "center" },
  detailHeadingCopy: { flex: 1, minWidth: 0 },
  detailTitle: { fontSize: 27, lineHeight: 33, fontWeight: "800", color: "#155039" },
  statusPill: { alignSelf: "flex-start", marginTop: 6, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 6 },
  statusPillText: { fontSize: 13, fontWeight: "800" },
  detailSummary: { marginTop: spacing.lg, fontSize: 18, lineHeight: 28, color: colors.onSurfaceSecondary },
  detailDivider: { height: 1, backgroundColor: colors.divider, marginVertical: spacing.lg },
  metricList: { gap: spacing.lg },
  metricRow: { minHeight: 60, flexDirection: "row", alignItems: "center", gap: spacing.md },
  metricIcon: { width: 54, height: 54, borderRadius: 27, alignItems: "center", justifyContent: "center", backgroundColor: "#EDF4EF", borderWidth: 1, borderColor: "#D9E5DC" },
  metricValue: { minWidth: 92, fontSize: 34, lineHeight: 40, fontWeight: "800", color: "#07543B" },
  metricLabel: { flex: 1, fontSize: 15, lineHeight: 20, color: colors.onSurfaceSecondary },
  selectButton: { minHeight: 54, marginTop: spacing.xl, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  selectButtonWide: { marginTop: "auto" },
  selectButtonText: { color: colors.brandPrimary, fontSize: 16, fontWeight: "800" },
  planSection: { marginTop: spacing.xl, borderWidth: 1, borderColor: "#BFD2C4", borderRadius: radius.sm, backgroundColor: "#F7FAF7", padding: spacing.xl },
  planEyebrow: { fontSize: 13, fontWeight: "900", color: colors.brandPrimary },
  planTitle: { marginTop: spacing.sm, fontSize: 31, lineHeight: 38, fontWeight: "800", color: "#164631" },
  planText: { marginTop: spacing.sm, fontSize: 16, lineHeight: 23, color: colors.onSurfaceSecondary },
  planButton: { minHeight: 64, marginTop: spacing.lg, borderRadius: radius.sm, backgroundColor: "#07543B", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.lg },
  planButtonText: { color: "#FFFFFF", fontSize: 18, fontWeight: "800" },
});
