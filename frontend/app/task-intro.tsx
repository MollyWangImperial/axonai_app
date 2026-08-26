import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { AssessmentPackageId, fetchTasks, Task } from "@/src/api";
import { authedFetch } from "@/src/auth";
import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";

const COMPLETED_TASKS_KEY = (packageId: AssessmentPackageId) => `assessment_completed_tasks_v1:${packageId}`;

function parseCompletedTasks(raw: string): Record<string, boolean> {
  try {
    const parsed = JSON.parse(raw || "{}");
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

const PREPARATION_TIPS = [
  "Wear short or fitted sleeves so your arms are visible",
  "Use a stable seat and clear the space around you",
  "Keep your phone propped up at chest height with good lighting",
  "Have someone nearby for safety if you need support",
];

export default function TaskIntro() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ mode?: string }>();
  const isInitial = params.mode !== "followup";
  const packageId: AssessmentPackageId = "upper_limb";
  const [tasks, setTasks] = useState<Task[]>([]);
  const [completedTasks, setCompletedTasks] = useState<Record<string, boolean>>({});
  const [nextTaskId, setNextTaskId] = useState<string | null>(null);
  const [affectedSide, setAffectedSide] = useState<"left" | "right">("right");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const [taskResponse, rawCompleted, profileResponse] = await Promise.all([
          fetchTasks(packageId),
          storage.getItem(COMPLETED_TASKS_KEY(packageId), ""),
          authedFetch("/api/users/onboarding").then((r) => r.json()).catch(() => null),
        ]);
        const completed = parseCompletedTasks(rawCompleted || "");
        const nextTask = taskResponse.tasks.find((task) => !completed[task.id]) || taskResponse.tasks[0];
        const storedSide = await storage.getItem("affected_side_v1", "");
        const profileSide = profileResponse?.profile?.side_affected;
        const resolvedSide = storedSide || profileSide;
        setAffectedSide(resolvedSide === "left" ? "left" : "right");
        setTasks(taskResponse.tasks);
        setCompletedTasks(completed);
        setNextTaskId(nextTask?.id || null);
      } catch (e: any) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const onBegin = () => {
    if (!nextTaskId) return;
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({ pathname: "/assessment", params: { package: packageId, start_task: nextTaskId, affected_side: affectedSide } });
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="task-intro-back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>{isInitial ? "Initial Assessment" : "Movement Check-in"}</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.introIcon}><Ionicons name="body-outline" size={30} color={colors.brandPrimary} /></View>
        <Text style={styles.title}>{isInitial ? "Your Initial Assessment" : "Your next movement check-in"}</Text>
        <Text style={styles.sub}>
          {isInitial
            ? "Every new patient completes the same seven upper-limb tasks. This gives us a broad, consistent starting point before personalizing future sessions."
            : "We have selected the next standardized movement session for you. Alira will guide each task in order."}
        </Text>

        <View style={styles.tipsCard} testID="task-intro-tips">
          <Text style={styles.tipsHeader}>Before we begin</Text>
          {PREPARATION_TIPS.map((tip) => (
            <View key={tip} style={styles.tipRow}>
              <Ionicons name="checkmark-circle" size={18} color={colors.brandPrimary} />
              <Text style={styles.tipText}>{tip}</Text>
            </View>
          ))}
        </View>

        <View style={styles.sectionHeader}>
          <Text style={styles.sectionTitle}>What you will complete</Text>
          <Text style={styles.taskCount}>{tasks.length || 7} tasks</Text>
        </View>
        <Text style={styles.readOnlyNote}>Tasks run automatically in this order, so there is nothing to choose.</Text>

        {loading && <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.lg }} />}
        {error && <Text style={styles.errorText}>Could not load the assessment. {error}</Text>}

        {tasks.map((task, index) => {
          const complete = !!completedTasks[task.id];
          const isNext = task.id === nextTaskId;
          return (
            <View key={task.id} style={[styles.taskRow, isNext && styles.taskRowNext]} testID={`task-row-${task.id}`}>
              <View style={[styles.taskNum, complete && styles.taskNumComplete]}>
                {complete ? <Ionicons name="checkmark" size={20} color={colors.onBrandPrimary} /> : <Text style={styles.taskNumText}>{index + 1}</Text>}
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <View style={styles.taskTitleRow}>
                  <Text style={styles.taskTitle} numberOfLines={2}>{task.title}</Text>
                  {complete && <Text style={styles.completeText}>Complete</Text>}
                  {isNext && !complete && <Text style={styles.nextText}>Next</Text>}
                </View>
                <Text style={styles.taskFocus} numberOfLines={2}>{task.focus}</Text>
              </View>
            </View>
          );
        })}
      </ScrollView>

      <View style={[styles.cta, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable testID="task-intro-begin" disabled={loading || !nextTaskId} onPress={onBegin} style={[styles.ctaBtn, (loading || !nextTaskId) && { opacity: 0.4 }]}>
          <Ionicons name="videocam" size={21} color={colors.onBrandPrimary} />
          <Text style={styles.ctaText}>{Object.keys(completedTasks).length > 0 ? "Continue Assessment" : "Begin Initial Assessment"}</Text>
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
  scroll: { width: "100%", maxWidth: 620, alignSelf: "center", padding: spacing.lg, paddingBottom: 130 },
  introIcon: { width: 56, height: 56, borderRadius: 28, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary, marginBottom: spacing.md },
  title: { fontSize: 28, lineHeight: 34, fontWeight: "800", color: colors.onSurface },
  sub: { fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary, marginTop: spacing.sm, marginBottom: spacing.lg },
  tipsCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.lg },
  tipsHeader: { fontSize: 16, fontWeight: "800", color: colors.onBrandTertiary, marginBottom: spacing.sm },
  tipRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 4 },
  tipText: { flex: 1, color: colors.onBrandTertiary, fontSize: 14, lineHeight: 19 },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  sectionTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  taskCount: { fontSize: 12, fontWeight: "800", color: colors.brandPrimary, backgroundColor: colors.brandTertiary, paddingHorizontal: spacing.sm, paddingVertical: 5, borderRadius: radius.pill },
  readOnlyNote: { fontSize: 13, lineHeight: 18, color: colors.onSurfaceTertiary, marginTop: 4, marginBottom: spacing.md },
  taskRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, marginBottom: spacing.sm, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, backgroundColor: colors.surface },
  taskRowNext: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  taskNum: { width: 40, height: 40, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandSecondary },
  taskNumComplete: { backgroundColor: colors.brandPrimary },
  taskNumText: { color: colors.onBrandSecondary, fontWeight: "800", fontSize: 17 },
  taskTitleRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.xs },
  taskTitle: { flexShrink: 1, fontSize: 15, lineHeight: 20, fontWeight: "800", color: colors.onSurface },
  taskFocus: { fontSize: 12, lineHeight: 17, color: colors.onSurfaceTertiary, marginTop: 2 },
  completeText: { fontSize: 10, fontWeight: "800", color: colors.brandPrimary },
  nextText: { fontSize: 10, fontWeight: "800", color: colors.onBrandPrimary, backgroundColor: colors.brandPrimary, paddingHorizontal: 7, paddingVertical: 3, borderRadius: radius.pill },
  errorText: { color: colors.error, fontSize: 14, lineHeight: 20, marginVertical: spacing.md },
  cta: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  ctaBtn: { width: "100%", maxWidth: 620, alignSelf: "center", minHeight: 56, borderRadius: radius.md, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "800" },
});
