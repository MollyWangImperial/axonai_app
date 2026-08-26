import { useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { AssessmentPackageId, fetchTasks, Task } from "@/src/api";
import { storage } from "@/src/utils/storage";

const COMPLETED_TASKS_KEY = (packageId: AssessmentPackageId) => `assessment_completed_tasks_v1:${packageId}`;

function parseCompletedTasks(raw: string | null): Record<string, boolean> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

const PACKAGE_OPTIONS: {
  id: AssessmentPackageId;
  title: string;
  subtitle: string;
  icon: keyof typeof Ionicons.glyphMap;
}[] = [
  {
    id: "upper_limb",
    title: "Upper Limb Function Package",
    subtitle: "Shoulder, elbow, reach, hand-to-mouth, and bilateral coordination",
    icon: "body-outline",
  },
  {
    id: "hand",
    title: "Hand Function Package",
    subtitle: "Open hand, fist, pinch, wrist control, and advanced grasp-release",
    icon: "hand-left-outline",
  },
  {
    id: "lower_limb",
    title: "Lower Limb Function Package",
    subtitle: "Seated control, transfers, supported stepping, and gait prerequisites",
    icon: "walk-outline",
  },
  {
    id: "balance",
    title: "Balance Function Package",
    subtitle: "Sitting, supported standing, weight shift, and step-stance control",
    icon: "swap-horizontal-outline",
  },
];

const PREPARATION_TIPS: Record<AssessmentPackageId, string[]> = {
  upper_limb: [
    "Wear short or fitted sleeves so your arms are visible",
    "Have someone nearby for safety if needed",
    "Stable seat, clear background, good lighting",
    "Keep your phone propped up at chest height, about 6 feet away",
  ],
  hand: [
    "Keep your affected hand and fingers fully visible",
    "Remove rings or anything that limits comfortable movement",
    "Use a stable seat, clear background, and good lighting",
    "Place your phone close enough to see the whole hand clearly",
  ],
  lower_limb: [
    "Use a stable chair and wear secure, non-slip footwear",
    "Keep the floor clear and a fixed support within reach",
    "Have a therapist or capable caregiver beside you for standing tasks",
    "Place your phone far enough away to show your shoulders, hips, knees, and both feet",
  ],
  balance: [
    "Use a stable chair and keep a fixed support within reach",
    "Have a therapist or capable caregiver beside you for standing tasks",
    "Keep the floor clear and wear secure, non-slip footwear",
    "Place your phone far enough away to show your full body and both feet",
  ],
};

export default function TaskIntro() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [selectedPackage, setSelectedPackage] = useState<AssessmentPackageId | null>(null);
  const [packageTitle, setPackageTitle] = useState("");
  const [packageSubtitle, setPackageSubtitle] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [completedTasks, setCompletedTasks] = useState<Record<string, boolean>>({});
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [affectedSide, setAffectedSide] = useState<"left" | "right">("right");

  const load = async (packageId: AssessmentPackageId) => {
    try {
      setSelectedPackage(packageId);
      setLoading(true);
      setError(null);
      const r = await fetchTasks(packageId);
      const completed = parseCompletedTasks(await storage.getItem(COMPLETED_TASKS_KEY(packageId), ""));
      setTasks(r.tasks);
      setCompletedTasks(completed);
      setSelectedTaskId(r.tasks.find((task) => !completed[task.id])?.id || r.tasks[0]?.id || null);
      setPackageTitle(r.package_title || PACKAGE_OPTIONS.find((p) => p.id === packageId)?.title || "");
      setPackageSubtitle(r.package_subtitle || PACKAGE_OPTIONS.find((p) => p.id === packageId)?.subtitle || "");
    } catch (e: any) {
      setError(String(e));
      setTasks([]);
    } finally {
      setLoading(false);
    }
  };

  const onBack = () => {
    if (selectedPackage) {
      setSelectedPackage(null);
      setTasks([]);
      setCompletedTasks({});
      setSelectedTaskId(null);
      setError(null);
      return;
    }
    router.back();
  };

  const onBegin = () => {
    if (!selectedPackage || !selectedTaskId) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({ pathname: "/assessment", params: { package: selectedPackage, start_task: selectedTaskId, affected_side: affectedSide } });
  };

  const renderPackageChoice = () => (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }}>
      <Text style={styles.title}>Choose assessment package</Text>
      <Text style={styles.sub}>Choose which function package you want to collect today. Each package shows its matching movement tasks.</Text>

      <Text style={styles.controlLabel}>Affected side</Text>
      <View style={styles.segmentedControl} testID="affected-side-control">
        {(["left", "right"] as const).map((side) => (
          <Pressable
            key={side}
            onPress={() => setAffectedSide(side)}
            style={[styles.segmentButton, affectedSide === side && styles.segmentButtonActive]}
            testID={`affected-side-${side}`}
          >
            <Text style={[styles.segmentText, affectedSide === side && styles.segmentTextActive]}>{side === "left" ? "Left" : "Right"}</Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.packageList}>
        {PACKAGE_OPTIONS.map((option) => (
          <Pressable
            key={option.id}
            onPress={() => load(option.id)}
            style={styles.packageRow}
            testID={`task-package-card-${option.id}`}
          >
            <View style={styles.packageIcon}>
              <Ionicons name={option.icon} size={26} color={colors.brandPrimary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.packageTitle}>{option.title}</Text>
              <Text style={styles.packageSubtitle}>{option.subtitle}</Text>
            </View>
            <Ionicons name="chevron-forward" size={22} color={colors.onSurfaceTertiary} />
          </Pressable>
        ))}
      </View>
    </ScrollView>
  );

  const renderTaskList = () => (
    <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }}>
      <Text style={styles.title}>{packageTitle || "Movement Assessment"}</Text>
      <Text style={styles.sub}>
        {tasks.length || 0} guided movement tasks. {packageSubtitle || "A warm voice will guide you through each task."}
      </Text>

      <View style={styles.tipsCard} testID="task-intro-tips">
        <Text style={styles.tipsHeader}>Before we begin</Text>
        {PREPARATION_TIPS[selectedPackage || "upper_limb"].map((t, i) => (
          <View key={i} style={styles.tipRow}>
            <Ionicons name="checkmark-circle" size={18} color={colors.brandPrimary} />
            <Text style={styles.tipText}>{t}</Text>
          </View>
        ))}
      </View>

      {loading && <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.lg }} />}
      {error && <Text style={styles.errorText}>Could not load tasks. {error}</Text>}

      {tasks.map((t, i) => {
        const isComplete = !!completedTasks[t.id];
        const isSelected = selectedTaskId === t.id;
        return (
        <Pressable
          key={t.id}
          onPress={() => {
            setSelectedTaskId(t.id);
            Haptics.selectionAsync();
          }}
          style={[styles.taskRow, isSelected && styles.taskRowSelected]}
          testID={`task-row-${t.id}`}
        >
          <View style={[styles.taskNum, isComplete && styles.taskNumComplete]}>
            {isComplete ? <Ionicons name="checkmark" size={22} color="#fff" /> : <Text style={styles.taskNumText}>{i + 1}</Text>}
          </View>
          <View style={{ flex: 1 }}>
            <View style={styles.taskTitleRow}>
              <Text style={styles.taskTitle}>{t.id} {t.title}</Text>
              {isComplete && (
                <View style={styles.completeBadge} testID={`task-complete-badge-${t.id}`}>
                  <Ionicons name="checkmark-circle" size={13} color={colors.onBrandTertiary} />
                  <Text style={styles.completeBadgeText}>Complete</Text>
                </View>
              )}
              {isSelected && !isComplete && (
                <View style={styles.selectedBadge} testID={`task-selected-badge-${t.id}`}>
                  <Text style={styles.selectedBadgeText}>Selected</Text>
                </View>
              )}
            </View>
            <Text style={styles.taskFocus}>{t.focus}</Text>
            <Text style={styles.taskView}>{t.view}</Text>
            {t.advanced_marker_required && (
              <View style={styles.markerBadge} testID={`task-marker-badge-${t.id}`}>
                <Ionicons name="pricetag" size={13} color={colors.onBrandTertiary} />
                <Text style={styles.markerBadgeText}>AxonAI marker for advanced grasp-release</Text>
              </View>
            )}
            {t.safety_note && (
              <View style={styles.safetyNote} testID={`task-safety-${t.id}`}>
                <Ionicons name={t.safety_tier === "spotter_required" ? "people" : "shield-checkmark"} size={13} color={colors.warning} />
                <Text style={styles.safetyText}>{t.safety_note}</Text>
              </View>
            )}
          </View>
        </Pressable>
      )})}
    </ScrollView>
  );

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={onBack} style={styles.backBtn} testID="task-intro-back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Movement Assessment</Text>
        <View style={{ width: 40 }} />
      </View>

      {selectedPackage ? renderTaskList() : renderPackageChoice()}

      {selectedPackage && (
        <View style={[styles.cta, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
          <Pressable onPress={onBegin} style={styles.ctaBtn} testID="task-intro-begin" disabled={loading || tasks.length === 0 || !selectedTaskId}>
            <Ionicons name="videocam" size={22} color={colors.onBrandPrimary} />
            <Text style={styles.ctaText}>{selectedTaskId ? `Open Camera & Collect ${selectedTaskId}` : "Open Camera & Begin"}</Text>
          </Pressable>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  title: { fontSize: 26, fontWeight: "800", color: colors.onSurface, marginBottom: spacing.sm },
  sub: { fontSize: 15, color: colors.onSurfaceSecondary, lineHeight: 22, marginBottom: spacing.lg },
  packageList: { gap: spacing.sm },
  controlLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurfaceSecondary, marginBottom: spacing.xs },
  segmentedControl: { flexDirection: "row", alignSelf: "flex-start", borderWidth: 1, borderColor: colors.divider, borderRadius: radius.md, padding: 3, marginBottom: spacing.lg },
  segmentButton: { minWidth: 78, minHeight: 38, alignItems: "center", justifyContent: "center", borderRadius: radius.sm },
  segmentButtonActive: { backgroundColor: colors.brandPrimary },
  segmentText: { fontSize: 14, fontWeight: "700", color: colors.onSurfaceSecondary },
  segmentTextActive: { color: colors.onBrandPrimary },
  packageRow: { flexDirection: "row", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, alignItems: "center" },
  packageIcon: { width: 50, height: 50, borderRadius: 16, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  packageTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, marginBottom: 3 },
  packageSubtitle: { fontSize: 13, color: colors.onSurfaceTertiary, lineHeight: 18 },
  tipsCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.lg },
  tipsHeader: { fontSize: 16, fontWeight: "700", color: colors.onBrandTertiary, marginBottom: spacing.sm },
  tipRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 4 },
  tipText: { color: colors.onBrandTertiary, fontSize: 14, flex: 1 },
  taskRow: { flexDirection: "row", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, marginBottom: spacing.sm, alignItems: "center", borderWidth: 2, borderColor: "transparent" },
  taskRowSelected: { borderColor: colors.brandPrimary, backgroundColor: colors.surface },
  taskNum: { width: 44, height: 44, borderRadius: 12, backgroundColor: colors.brandSecondary, alignItems: "center", justifyContent: "center" },
  taskNumComplete: { backgroundColor: colors.brandPrimary },
  taskNumText: { color: "#fff", fontWeight: "800", fontSize: 18 },
  taskTitleRow: { flexDirection: "row", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 2 },
  taskTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: 2 },
  completeBadge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandTertiary, borderRadius: radius.sm, paddingHorizontal: 8, paddingVertical: 4 },
  completeBadgeText: { color: colors.onBrandTertiary, fontSize: 11, fontWeight: "800" },
  selectedBadge: { backgroundColor: colors.brandPrimary, borderRadius: radius.sm, paddingHorizontal: 8, paddingVertical: 4 },
  selectedBadgeText: { color: colors.onBrandPrimary, fontSize: 11, fontWeight: "800" },
  taskFocus: { fontSize: 13, color: colors.onSurfaceTertiary, lineHeight: 18 },
  taskView: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", marginTop: 4 },
  safetyNote: { flexDirection: "row", alignItems: "flex-start", gap: 6, marginTop: 7 },
  safetyText: { flex: 1, fontSize: 12, lineHeight: 17, color: colors.onSurfaceSecondary },
  markerBadge: { marginTop: spacing.sm, alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: colors.brandTertiary, borderRadius: radius.sm, paddingHorizontal: spacing.sm, paddingVertical: 6 },
  markerBadgeText: { color: colors.onBrandTertiary, fontSize: 12, fontWeight: "700" },
  errorText: { color: colors.error, marginTop: spacing.md },
  cta: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  ctaBtn: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.md, alignItems: "center", justifyContent: "center", minHeight: 56 },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "700" },
});
