import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Image, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Assessment, fetchAssessment, fetchPatientAssessmentSummary, PatientAssessmentSummary } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

const anatomyImage = require("@/assets/images/rehyn-anatomy-front.png");

type DomainId = "upper_limb" | "hand" | "lower_limb";

const domainPosition: Record<DomainId, { top: `${number}%`; leftRight: `${number}%`; leftLeft: `${number}%` }> = {
  upper_limb: { top: "22%", leftRight: "33%", leftLeft: "67%" },
  hand: { top: "43%", leftRight: "25%", leftLeft: "75%" },
  lower_limb: { top: "70%", leftRight: "41%", leftLeft: "59%" },
};

function statusColor(findings: number, completion: number) {
  if (findings > 0) return { color: "#EF6B5A", soft: "rgba(239,107,90,0.22)", label: "Needs attention" };
  if (completion < 100) return { color: "#D8A33B", soft: "rgba(216,163,59,0.20)", label: "Building strength" };
  return { color: "#609A6B", soft: "rgba(96,154,107,0.20)", label: "Moving well" };
}

export default function MovementMapScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<PatientAssessmentSummary | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [selected, setSelected] = useState<DomainId>("upper_limb");
  const [view, setView] = useState<"front" | "back">("front");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    Promise.all([fetchPatientAssessmentSummary(id), fetchAssessment(id).catch(() => null)])
      .then(([summary, raw]) => {
        setData(summary);
        setAssessment(raw);
        const firstFinding = summary.insights.domain_metrics.find((domain) => domain.findings_count > 0)?.domain;
        if (firstFinding) setSelected(firstFinding);
      })
      .finally(() => setLoading(false));
  }, [id]);

  const affectedSide = assessment?.affected_side?.toLowerCase() === "left" ? "left" : "right";
  const domains = data?.insights.domain_metrics || [];
  const selectedDomain = domains.find((domain) => domain.domain === selected) || domains[0];
  const selectedStatus = statusColor(selectedDomain?.findings_count || 0, selectedDomain?.completion_percent || 0);
  const activation = data?.insights.activation_profile.find((item) => item.domain === selected);
  const ratio = activation?.template_mean ? activation.mean / activation.template_mean : null;
  const pageWidth = Math.min(Math.max(width - 24, 296), 700);
  const reviewGate = data?.clinical_review_gate;
  const canViewPlan = data?.rehab_plan_ready === true && reviewGate?.rehab_access === "allowed";
  const noRehabNeeded = reviewGate?.rehab_access === "not_needed" || reviewGate?.status === "no_rehab_needed";

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
    if (canViewPlan) {
      router.push({ pathname: "/designing-plan", params: { id } });
    } else {
      router.replace("/");
    }
  };

  if (loading) {
    return <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /><Text style={styles.loadingText}>Building your movement map...</Text></View>;
  }

  if (!data) {
    return <View style={styles.center}><Text style={styles.errorText}>We could not load your movement map.</Text><Pressable onPress={() => router.replace("/")} style={styles.planButton}><Text style={styles.planButtonText}>Return home</Text></Pressable></View>;
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.xs }]}>
        <Pressable onPress={() => router.back()} style={styles.headerButton}><Ionicons name="arrow-back" size={23} color="#154B34" /></Pressable>
        <Text style={styles.headerTitle}>Your movement map</Text>
        <View style={styles.headerButton} />
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        <View style={[styles.page, { width: pageWidth }]}>
          <View style={styles.segmented}>
            <Pressable onPress={() => setView("front")} style={[styles.segment, view === "front" && styles.segmentActive]}><Text style={[styles.segmentText, view === "front" && styles.segmentTextActive]}>Front</Text></Pressable>
            <Pressable onPress={() => setView("back")} style={[styles.segment, view === "back" && styles.segmentActive]}><Text style={[styles.segmentText, view === "back" && styles.segmentTextActive]}>Back</Text></Pressable>
          </View>

          {view === "front" ? (
            <View style={styles.mapStage}>
              <Image source={anatomyImage} resizeMode="contain" style={styles.anatomyImage} />
              {domains.map((domain) => {
                const position = domainPosition[domain.domain];
                const status = statusColor(domain.findings_count, domain.completion_percent);
                const active = selected === domain.domain;
                return (
                  <Pressable
                    key={domain.domain}
                    onPress={() => setSelected(domain.domain)}
                    accessibilityLabel={`View ${domain.label}`}
                    style={[
                      styles.mapMarker,
                      { top: position.top, left: affectedSide === "right" ? position.leftRight : position.leftLeft, borderColor: status.color, backgroundColor: status.soft },
                      active && styles.mapMarkerActive,
                    ]}
                  >
                    <View style={[styles.mapMarkerCore, { backgroundColor: status.color }]} />
                  </Pressable>
                );
              })}
            </View>
          ) : (
            <View style={styles.backUnavailable}>
              <Ionicons name="body-outline" size={54} color={colors.brandPrimary} />
              <Text style={styles.backTitle}>Front-view map available</Text>
              <Text style={styles.backText}>This assessment did not collect a clinical back view, so we won’t infer one. Use the Front view for the captured findings.</Text>
              <Pressable onPress={() => setView("front")} style={styles.frontButton}><Text style={styles.frontButtonText}>Return to Front</Text></Pressable>
            </View>
          )}

          <View style={styles.legend}>
            {[
              { color: "#EF6B5A", label: "Needs attention" },
              { color: "#D8A33B", label: "Building strength" },
              { color: "#609A6B", label: "Moving well" },
            ].map((item) => <View key={item.label} style={styles.legendItem}><View style={[styles.legendDot, { backgroundColor: item.color }]} /><Text style={styles.legendText}>{item.label}</Text></View>)}
          </View>

          <View style={styles.detailPanel}>
            <View style={styles.detailHeader}>
              <View style={[styles.detailIcon, { backgroundColor: selectedStatus.soft }]}><Ionicons name={selected === "lower_limb" ? "walk-outline" : selected === "hand" ? "hand-left-outline" : "body-outline"} size={30} color={selectedStatus.color} /></View>
              <View style={styles.detailHeadingCopy}>
                <Text style={styles.detailTitle}>{selectedDomain?.label || "Movement area"}</Text>
                <View style={[styles.statusPill, { backgroundColor: selectedStatus.soft }]}><Text style={[styles.statusPillText, { color: selectedStatus.color }]}>{selectedStatus.label}</Text></View>
              </View>
            </View>
            <Text style={styles.detailSummary}>{selectedSummary}</Text>

            <View style={styles.dataRow}>
              <View style={styles.dataBlock}>
                <Text style={styles.dataValue}>{selectedDomain?.completion_percent ?? 0}%</Text>
                <Text style={styles.dataLabel}>task coverage</Text>
              </View>
              <View style={styles.dataDivider} />
              <View style={styles.dataBlock}>
                <Text style={styles.dataValue}>{selectedDomain?.findings_count ?? 0}</Text>
                <Text style={styles.dataLabel}>finding{selectedDomain?.findings_count === 1 ? "" : "s"} to review</Text>
              </View>
              {ratio !== null && <><View style={styles.dataDivider} /><View style={styles.dataBlock}><Text style={styles.dataValue}>{ratio.toFixed(1)}×</Text><Text style={styles.dataLabel}>matched demand</Text></View></>}
            </View>

            <Pressable onPress={cycleDomain} style={styles.exploreButton}>
              <Text style={styles.exploreButtonText}>Explore another area</Text>
              <Ionicons name="arrow-forward" size={21} color="#FFFFFF" />
            </Pressable>
          </View>

          <View style={styles.planSection}>
            <Text style={styles.planEyebrow}>NEXT STEP</Text>
            <Text style={styles.planTitle}>{canViewPlan ? "Your rehab plan is ready" : noRehabNeeded ? "No rehab plan is needed" : "Your plan is waiting for review"}</Text>
            <Text style={styles.planText}>{canViewPlan ? "Your plan follows the movement areas that need support in this assessment." : reviewGate?.patient_message}</Text>
            <Pressable onPress={openPlan} style={styles.planButton} testID={canViewPlan ? "movement-map-view-plan" : "movement-map-return-home"}>
              <Ionicons name={canViewPlan ? "clipboard-outline" : "home-outline"} size={22} color="#FFFFFF" />
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
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 20, fontWeight: "800", color: "#154B34" },
  content: { alignItems: "center", paddingVertical: spacing.sm, paddingBottom: spacing.xl },
  page: { alignSelf: "center" },
  segmented: { alignSelf: "flex-end", flexDirection: "row", borderWidth: 1, borderColor: "#CAD5CC", borderRadius: radius.pill, padding: 3, marginBottom: spacing.xs },
  segment: { minWidth: 76, minHeight: 36, alignItems: "center", justifyContent: "center", borderRadius: radius.pill },
  segmentActive: { backgroundColor: "#15543C" },
  segmentText: { color: "#244738", fontWeight: "700" },
  segmentTextActive: { color: "#FFFFFF" },
  mapStage: { height: 560, alignItems: "center", justifyContent: "center" },
  anatomyImage: { width: "100%", height: "100%" },
  mapMarker: { position: "absolute", width: 54, height: 54, marginLeft: -27, marginTop: -27, borderRadius: 27, borderWidth: 2, alignItems: "center", justifyContent: "center" },
  mapMarkerActive: { borderWidth: 4, transform: [{ scale: 1.12 }] },
  mapMarkerCore: { width: 14, height: 14, borderRadius: 7, borderWidth: 3, borderColor: "#FFFFFF" },
  backUnavailable: { minHeight: 420, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.xl },
  backTitle: { marginTop: spacing.md, fontSize: 22, fontWeight: "800", color: "#164631", textAlign: "center" },
  backText: { marginTop: spacing.sm, fontSize: 14, lineHeight: 21, color: colors.onSurfaceSecondary, textAlign: "center" },
  frontButton: { marginTop: spacing.lg, minHeight: 44, borderRadius: radius.pill, paddingHorizontal: spacing.lg, alignItems: "center", justifyContent: "center", backgroundColor: "#E7F1E5" },
  frontButtonText: { color: colors.brandPrimary, fontWeight: "800" },
  legend: { gap: spacing.xs, paddingHorizontal: spacing.sm, marginBottom: spacing.md },
  legendItem: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  legendDot: { width: 15, height: 15, borderRadius: 8, borderWidth: 2, borderColor: "#FFFFFF" },
  legendText: { fontSize: 13, color: "#163B2B" },
  detailPanel: { borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, borderWidth: 1, borderColor: "#D8DFD8", backgroundColor: "#FFFFFF", padding: spacing.lg },
  detailHeader: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  detailIcon: { width: 68, height: 68, borderRadius: 34, alignItems: "center", justifyContent: "center" },
  detailHeadingCopy: { flex: 1 },
  detailTitle: { fontSize: 25, lineHeight: 31, fontWeight: "800", color: "#155039" },
  statusPill: { alignSelf: "flex-start", marginTop: 5, borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 5 },
  statusPillText: { fontSize: 12, fontWeight: "800" },
  detailSummary: { marginTop: spacing.md, fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary },
  dataRow: { flexDirection: "row", alignItems: "stretch", marginVertical: spacing.lg },
  dataBlock: { flex: 1 },
  dataValue: { fontSize: 24, lineHeight: 29, fontWeight: "800", color: "#155039" },
  dataLabel: { marginTop: 3, fontSize: 11, lineHeight: 15, color: colors.onSurfaceTertiary },
  dataDivider: { width: 1, backgroundColor: colors.divider, marginHorizontal: spacing.sm },
  exploreButton: { minHeight: 56, borderRadius: radius.md, backgroundColor: "#07543B", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  exploreButtonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  planSection: { paddingVertical: spacing.xl, paddingHorizontal: spacing.sm },
  planEyebrow: { fontSize: 11, fontWeight: "900", color: colors.brandPrimary },
  planTitle: { marginTop: 5, fontSize: 23, lineHeight: 29, fontWeight: "800", color: "#164631" },
  planText: { marginTop: spacing.sm, fontSize: 14, lineHeight: 21, color: colors.onSurfaceSecondary },
  planButton: { minHeight: 56, marginTop: spacing.md, borderRadius: radius.md, backgroundColor: "#07543B", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.lg },
  planButtonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
});
