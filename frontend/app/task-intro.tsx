import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { AssessmentPackageId, fetchTasks } from "@/src/api";
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
  "Use a stable seat and clear a short, safe walking path",
  "Keep your phone propped up so your full body can be seen",
  "Use your usual walking aid and do not attempt walking if it is not normally safe",
  "Have someone nearby for safety if you need support",
];

export default function TaskIntro() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ mode?: string }>();
  const isInitial = params.mode !== "followup";
  const packageId: AssessmentPackageId = "initial";
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
            ? "Every new patient completes the same seven guided arm, hand, and comfortable-walking observations. This gives us a broad, consistent starting point before personalizing future sessions."
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

        {loading && <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.lg }} />}
        {error && <Text style={styles.errorText}>Could not load the assessment. {error}</Text>}

        {!loading && !error && (
          <View style={styles.sessionReady} testID="task-intro-session-ready">
            <View style={styles.sessionReadyIcon}>
              <Ionicons name="play" size={20} color={colors.onBrandPrimary} />
            </View>
            <View style={styles.sessionReadyCopy}>
              <Text style={styles.sessionReadyTitle}>
                {Object.keys(completedTasks).length > 0 ? "Continue where you left off" : "Your first guided task is ready"}
              </Text>
              <Text style={styles.sessionReadyText}>
                Alira will launch your next guided task automatically and continue through the assessment in order.
              </Text>
            </View>
          </View>
        )}
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
  sessionReady: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  sessionReadyIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  sessionReadyCopy: { flex: 1, minWidth: 0 },
  sessionReadyTitle: { color: colors.onSurface, fontSize: 16, lineHeight: 21, fontWeight: "800" },
  sessionReadyText: { color: colors.onSurfaceSecondary, fontSize: 13, lineHeight: 19, marginTop: 3 },
  errorText: { color: colors.error, fontSize: 14, lineHeight: 20, marginVertical: spacing.md },
  cta: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  ctaBtn: { width: "100%", maxWidth: 620, alignSelf: "center", minHeight: 56, borderRadius: radius.md, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "800" },
});
