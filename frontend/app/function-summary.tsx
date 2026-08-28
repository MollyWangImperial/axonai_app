import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";

import { BodyFunctionDomainSummary, fetchPatientAssessmentSummary, PatientAssessmentSummary } from "@/src/api";
import { DEMO_ASSESSMENT_ID, demoPatientAssessmentSummary } from "@/src/demoAssessment";
import { colors, radius, spacing } from "@/src/theme";

type DomainId = "upper_limb" | "hand" | "lower_limb";

type DomainPresentation = {
  id: DomainId;
  title: string;
  status: string;
  message: string;
  tone: "attention" | "well" | "pending" | "quiet";
};

const domainOrder: DomainId[] = ["upper_limb", "hand", "lower_limb"];

const tones = {
  attention: { strong: "#E86F5B", soft: "#FFF0EC", border: "#F5C4BA" },
  well: { strong: "#4B9362", soft: "#EDF7EF", border: "#C8E3CE" },
  pending: { strong: "#B88224", soft: "#FFF7E6", border: "#EAD5A7" },
  quiet: { strong: "#77817A", soft: "#F3F5F2", border: "#DCE1DD" },
} as const;

function presentationFor(domain: BodyFunctionDomainSummary | undefined, id: DomainId): DomainPresentation {
  const title = id === "upper_limb" ? "Reaching" : id === "hand" ? "Hand control" : "Walking";
  if (!domain || domain.status === "not_observed") {
    return { id, title, status: "Not observed", message: `${title} was not captured this time.`, tone: "quiet" };
  }
  if (domain.status === "analysis_pending") {
    return { id, title, status: "Reviewing", message: `${title} is still being analysed.`, tone: "pending" };
  }
  if (domain.status === "review_recommended") {
    const message = id === "upper_limb"
      ? "Reaching may take extra shoulder effort."
      : id === "hand"
        ? "Everyday hand use may need more support."
        : "Walking may need added support or review.";
    return { id, title, status: "Needs support", message, tone: "attention" };
  }
  const message = id === "upper_limb"
    ? "Reaching looked comfortable in these tasks."
    : id === "hand"
      ? "Hand control looked steady in these tasks."
      : "Walking looked steady in this assessment.";
  return { id, title, status: "Moving well", message, tone: "well" };
}

function DomainIcon({ domain, compact }: { domain: DomainPresentation; compact: boolean }) {
  const tone = tones[domain.tone];
  const iconSize = compact ? 72 : 104;

  if (domain.id === "lower_limb") {
    return (
      <View style={styles.footprintPair} accessibilityElementsHidden>
        <MaterialCommunityIcons name="shoe-print" size={compact ? 48 : 67} color={tone.strong} style={styles.leftFootprint} />
        <MaterialCommunityIcons name="shoe-print" size={compact ? 48 : 67} color={tone.strong} style={styles.rightFootprint} />
      </View>
    );
  }

  return (
    <MaterialCommunityIcons
      accessibilityElementsHidden
      name={domain.id === "upper_limb" ? "human-greeting" : "hand-back-left-outline"}
      size={iconSize}
      color={tone.strong}
    />
  );
}

function DomainFigure({ domain, compact }: { domain: DomainPresentation; compact: boolean }) {
  const tone = tones[domain.tone];
  return (
    <View
      style={[
        styles.domainCard,
        compact && styles.domainCardCompact,
        { borderColor: "#DFE4DF", borderTopColor: tone.strong },
      ]}
      testID={`function-summary-${domain.id}`}
    >
      <View style={[styles.iconCircle, compact && styles.iconCircleCompact, { backgroundColor: tone.soft }]}>
        <DomainIcon domain={domain} compact={compact} />
      </View>
      <Text style={[styles.domainTitle, compact && styles.domainTitleCompact]}>{domain.title}</Text>
      <View style={[styles.statusPill, { backgroundColor: tone.strong }]}><Text style={styles.statusText}>{domain.status}</Text></View>
      <Text style={[styles.domainMessage, compact && styles.domainMessageCompact]}>{domain.message}</Text>
    </View>
  );
}

export default function FunctionSummaryScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<PatientAssessmentSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const isDemo = id === DEMO_ASSESSMENT_ID;
  const isWide = width >= 760;

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        if (!id) return;
        const summary = isDemo ? demoPatientAssessmentSummary : await fetchPatientAssessmentSummary(id);
        if (active) setData(summary);
      } catch {
        if (active) setData(null);
      } finally {
        if (active) setLoading(false);
      }
    };
    void load();
    return () => { active = false; };
  }, [id, isDemo]);

  const domains = useMemo(() => domainOrder.map((domainId) => (
    presentationFor(data?.body_function_summary.domains.find((domain) => domain.domain === domainId), domainId)
  )), [data?.body_function_summary.domains]);

  if (loading) {
    return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brandPrimary} /><Text style={styles.loadingText}>Preparing your function summary...</Text></View>;
  }

  if (!data) {
    return (
      <View style={[styles.container, styles.center]}>
        <Text style={styles.errorText}>We could not load this assessment.</Text>
        <Pressable onPress={() => router.replace("/(tabs)/journey")} style={styles.primaryButton}><Text style={styles.primaryButtonText}>Back to Journey</Text></Pressable>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.xs }]}>
        <Pressable accessibilityLabel="Back to Journey" onPress={() => router.replace("/(tabs)/journey")} style={styles.headerButton}><Ionicons name="arrow-back" size={24} color="#174834" /></Pressable>
        <View style={styles.headerCopy}>
          <Text style={styles.headerTitle}>{isDemo ? "Demo function summary" : "Your function summary"}</Text>
          <Text style={styles.headerDate}>{new Date(data.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" })}</Text>
        </View>
        <View style={styles.headerButton} />
      </View>

      <ScrollView contentContainerStyle={[styles.content, isWide && styles.contentWide]} showsVerticalScrollIndicator={false}>
        <View style={styles.page}>
          {isDemo && <View style={styles.demoBanner}><Ionicons name="sparkles" size={18} color="#675080" /><Text style={styles.demoBannerText}>Sample assessment preview</Text></View>}
          <View style={styles.intro}>
            <Text style={[styles.eyebrow, isWide && styles.eyebrowWide]}>FUNCTION AT A GLANCE</Text>
            <Text style={[styles.title, isWide && styles.titleWide]}>Three parts of everyday movement</Text>
          </View>

          <View style={[styles.domainList, isWide && styles.domainListWide]}>
            {domains.map((domain) => <DomainFigure key={domain.id} domain={domain} compact={!isWide} />)}
          </View>

          <Pressable testID="function-summary-view-snapshot" onPress={() => router.push({ pathname: "/results", params: { id } })} style={[styles.primaryButton, isWide && styles.primaryButtonWide]}>
            <Text style={[styles.primaryButtonText, isWide && styles.primaryButtonTextWide]}>View movement snapshot</Text>
            <Ionicons name="arrow-forward" size={22} color="#FFFFFF" />
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FFFEFB" },
  center: { alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.lg },
  loadingText: { color: colors.onSurfaceSecondary },
  errorText: { color: colors.error, textAlign: "center" },
  header: { minHeight: 66, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.sm, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerButton: { width: 48, height: 44, alignItems: "center", justifyContent: "center" },
  headerCopy: { flex: 1, alignItems: "center" },
  headerTitle: { fontSize: 18, lineHeight: 23, fontWeight: "800", color: "#164631", textAlign: "center" },
  headerDate: { marginTop: 2, fontSize: 12, color: colors.onSurfaceTertiary },
  content: { paddingVertical: spacing.lg, paddingHorizontal: spacing.sm, paddingBottom: 48 },
  contentWide: { paddingHorizontal: 48 },
  page: { width: "100%", maxWidth: 1160, alignSelf: "center" },
  demoBanner: { minHeight: 42, flexDirection: "row", alignItems: "center", gap: spacing.xs, paddingHorizontal: spacing.sm, borderWidth: 1, borderColor: "#DCCFEA", borderRadius: radius.sm, backgroundColor: "#F5EFFA" },
  demoBannerText: { color: "#675080", fontSize: 12, fontWeight: "800" },
  intro: { alignItems: "center", paddingVertical: 30 },
  eyebrow: { color: "#4A7856", fontSize: 11, lineHeight: 15, fontWeight: "900" },
  eyebrowWide: { fontSize: 16, lineHeight: 21 },
  title: { marginTop: 6, color: "#12392B", fontSize: 26, lineHeight: 32, fontWeight: "900", textAlign: "center" },
  titleWide: { marginTop: 10, fontSize: 44, lineHeight: 52 },
  domainList: { gap: spacing.sm },
  domainListWide: { flexDirection: "row", gap: spacing.md },
  domainCard: { flex: 1, minWidth: 0, minHeight: 540, alignItems: "center", paddingHorizontal: spacing.lg, paddingTop: 48, paddingBottom: spacing.lg, borderWidth: 1, borderTopWidth: 6, borderRadius: radius.sm, backgroundColor: "#FFFFFF", shadowColor: "#173E2F", shadowOffset: { width: 0, height: 5 }, shadowOpacity: 0.09, shadowRadius: 12, elevation: 2 },
  domainCardCompact: { minHeight: 320, paddingTop: spacing.lg, paddingHorizontal: spacing.md },
  iconCircle: { width: 208, height: 208, borderRadius: 104, alignItems: "center", justifyContent: "center" },
  iconCircleCompact: { width: 124, height: 124, borderRadius: 62 },
  footprintPair: { flexDirection: "row", alignItems: "center", justifyContent: "center", width: "100%" },
  leftFootprint: { transform: [{ rotate: "-12deg" }, { translateY: -6 }] },
  rightFootprint: { marginLeft: -10, transform: [{ rotate: "12deg" }, { translateY: 8 }] },
  domainTitle: { marginTop: 28, color: "#12392B", fontSize: 30, lineHeight: 37, fontWeight: "900", textAlign: "center" },
  domainTitleCompact: { marginTop: spacing.md, fontSize: 25, lineHeight: 31 },
  statusPill: { marginTop: 14, paddingHorizontal: 20, paddingVertical: 8, borderRadius: radius.pill },
  statusText: { color: "#FFFFFF", fontSize: 16, lineHeight: 20, fontWeight: "900" },
  domainMessage: { maxWidth: 272, marginTop: 18, color: "#303A35", fontSize: 17, lineHeight: 26, fontWeight: "500", textAlign: "center" },
  domainMessageCompact: { maxWidth: 310, marginTop: 14, fontSize: 15, lineHeight: 22 },
  primaryButton: { minHeight: 56, marginTop: spacing.lg, paddingHorizontal: spacing.lg, borderRadius: radius.sm, backgroundColor: "#15543C", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  primaryButtonWide: { minHeight: 84, marginTop: 36 },
  primaryButtonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  primaryButtonTextWide: { fontSize: 22 },
});
