import { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { AssessmentPackageId, fetchTaskProgress, fetchTaskVideos, fetchTasks, resetTaskProgress } from "@/src/api";
import { affectedSideKey, authedFetch, completedTasksKey, getUserId, savedTaskVideosKey } from "@/src/auth";
import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";

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
  "Ask a carer or family member to film the walking task from the side and keep your full body visible",
];

export default function TaskIntro() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ mode?: string }>();
  const isInitial = params.mode !== "followup";
  const packageId: AssessmentPackageId = "initial";
  const [completedTasks, setCompletedTasks] = useState<Record<string, boolean>>({});
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [userId, setUserId] = useState<string | null>(null);
  const [nextTaskId, setNextTaskId] = useState<string | null>(null);
  const [affectedSide, setAffectedSide] = useState<"left" | "right">("right");
  const [savedVideoCount, setSavedVideoCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const uid = await getUserId();
        if (!uid) throw new Error("Please sign in again.");
        setUserId(uid);
        const [taskResponse, rawCompleted, rawSavedVideos, profileResponse, savedVideos, serverProgress] = await Promise.all([
          fetchTasks(packageId),
          storage.getItem(completedTasksKey(uid, packageId), ""),
          storage.getItem(savedTaskVideosKey(uid, packageId), ""),
          authedFetch("/api/users/onboarding").then((r) => r.json()).catch(() => null),
          fetchTaskVideos(packageId).catch(() => []),
          fetchTaskProgress(packageId).catch(() => []),
        ]);
        const deviceCompleted = parseCompletedTasks(rawCompleted || "");
        const deviceSavedVideos = parseCompletedTasks(rawSavedVideos || "");
        const serverCompleted = Object.fromEntries(
          serverProgress
            .filter(Boolean)
            .map((taskId) => [taskId, true]),
        );
        const completed = { ...deviceCompleted, ...serverCompleted };
        if (Object.keys(serverCompleted).length > 0) {
          await storage.setItem(completedTasksKey(uid, packageId), JSON.stringify(completed));
        }
        const nextTask = taskResponse.tasks.find((task) => !completed[task.id]);
        const storedSide = await storage.getItem(affectedSideKey(uid), "");
        const profileSide = profileResponse?.profile?.side_affected;
        const resolvedSide = storedSide || profileSide;
        setTaskIds(taskResponse.tasks.reduce<string[]>((ids, task) => [...ids, task.id], []));
        setAffectedSide(resolvedSide === "left" ? "left" : "right");
        setCompletedTasks(completed);
        setNextTaskId(nextTask?.id || null);
        setSavedVideoCount(Math.max(savedVideos.length, Object.keys(deviceSavedVideos).length));
      } catch (e: any) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const onBegin = async () => {
    let taskToStart = nextTaskId;
    let completedTaskIds = Object.keys(completedTasks).filter((taskId) => completedTasks[taskId]);
    if (!isInitial && assessmentComplete && userId) {
      setLoading(true);
      try {
        await resetTaskProgress(packageId);
        await storage.removeItem(completedTasksKey(userId, packageId));
        await storage.removeItem(savedTaskVideosKey(userId, packageId));
        taskToStart = taskIds[0] || null;
        completedTaskIds = [];
      } catch (e: any) {
        setError(String(e));
        setLoading(false);
        return;
      }
      setLoading(false);
    }
    if (!taskToStart) {
      router.replace("/");
      return;
    }
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({
      pathname: "/assessment",
      params: {
        package: packageId,
        start_task: taskToStart,
        completed_tasks: completedTaskIds.join(","),
        affected_side: affectedSide,
      },
    });
  };

  const confirmStartOver = () => {
    if (!userId || taskIds.length === 0) return;
    Alert.alert(
      "Start the assessment again?",
      "Your saved results will remain in your history, but all seven collection tasks will be marked as incomplete.",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Start over",
          style: "destructive",
          onPress: () => {
            void (async () => {
              setLoading(true);
              try {
                await resetTaskProgress(packageId);
                await storage.removeItem(completedTasksKey(userId, packageId));
                await storage.removeItem(savedTaskVideosKey(userId, packageId));
                setCompletedTasks({});
                setNextTaskId(taskIds[0] || null);
              } catch (e: any) {
                setError(String(e));
              } finally {
                setLoading(false);
              }
            })();
          },
        },
      ],
    );
  };

  const completedCount = taskIds.filter((taskId) => completedTasks[taskId]).length;
  const assessmentComplete = taskIds.length > 0 && completedCount === taskIds.length;

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
                {assessmentComplete
                  ? isInitial ? "Your Initial Assessment is complete" : "Your next assessment is ready"
                  : completedCount > 0 ? "Continue where you left off" : isInitial ? "Your first guided task is ready" : "Your next guided task is ready"}
              </Text>
              <Text style={styles.sessionReadyText}>
                {assessmentComplete
                  ? isInitial
                    ? "You do not need to repeat these tasks. Your saved results are ready from the Home screen."
                    : "Your previous results will remain in Assessment history. Starting now creates a new movement check-in for progress comparison."
                  : `Alira will launch your next guided task automatically and continue through the remaining assessment. ${completedCount} of ${taskIds.length} tasks are already complete.`}
              </Text>
              {savedVideoCount > 0 && (
                <View style={styles.savedVideoRow} testID="saved-task-video-count">
                  <Ionicons name="cloud-done-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.savedVideoText}>
                    {savedVideoCount} task {savedVideoCount === 1 ? "video is" : "videos are"} saved for later review and reanalysis.
                  </Text>
                </View>
              )}
            </View>
          </View>
        )}
      </ScrollView>

      <View style={[styles.cta, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        {completedCount > 0 && (isInitial || !assessmentComplete) && (
          <Pressable testID="task-intro-start-over" disabled={loading} onPress={confirmStartOver} style={styles.startOverBtn}>
            <Ionicons name="refresh" size={18} color={colors.brandPrimary} />
            <Text style={styles.startOverText}>Start over</Text>
          </Pressable>
        )}
        <Pressable testID="task-intro-begin" disabled={loading} onPress={onBegin} style={[styles.ctaBtn, loading && { opacity: 0.4 }]}>
          <Ionicons name={assessmentComplete && isInitial ? "home" : "videocam"} size={21} color={colors.onBrandPrimary} />
          <Text style={styles.ctaText}>
            {assessmentComplete
              ? isInitial ? "Return Home" : "Start Next Assessment"
              : completedCount > 0 ? "Continue Assessment" : isInitial ? "Begin Initial Assessment" : "Begin Movement Check-in"}
          </Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 64, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border, backgroundColor: colors.surface },
  backBtn: { width: 48, height: 48, alignItems: "center", justifyContent: "center", borderRadius: 24, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  headerTitle: { fontSize: 18, lineHeight: 24, fontWeight: "800", color: colors.onSurface },
  scroll: { width: "100%", maxWidth: 620, alignSelf: "center", paddingHorizontal: 20, paddingTop: 28, paddingBottom: 200 },
  introIcon: { width: 64, height: 64, borderRadius: 32, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary, marginBottom: spacing.lg },
  title: { fontSize: 32, lineHeight: 40, fontWeight: "800", color: colors.onSurface },
  sub: { fontSize: 18, lineHeight: 27, color: colors.onSurfaceSecondary, marginTop: spacing.sm, marginBottom: spacing.lg },
  tipsCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: 20, marginBottom: spacing.lg },
  tipsHeader: { fontSize: 20, lineHeight: 26, fontWeight: "800", color: colors.onBrandTertiary, marginBottom: spacing.sm },
  tipRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, minHeight: 44, paddingVertical: 7 },
  tipText: { flex: 1, color: colors.onBrandTertiary, fontSize: 17, lineHeight: 25 },
  sessionReady: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md, padding: 20, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  sessionReadyIcon: { width: 48, height: 48, borderRadius: 24, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  sessionReadyCopy: { flex: 1, minWidth: 0 },
  sessionReadyTitle: { color: colors.onSurface, fontSize: 18, lineHeight: 24, fontWeight: "800" },
  sessionReadyText: { color: colors.onSurfaceSecondary, fontSize: 16, lineHeight: 24, marginTop: 4 },
  savedVideoRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.xs, marginTop: spacing.sm },
  savedVideoText: { flex: 1, color: colors.brandPrimary, fontSize: 16, lineHeight: 22, fontWeight: "700" },
  errorText: { color: colors.error, fontSize: 16, lineHeight: 23, marginVertical: spacing.md },
  cta: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.lg, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.border, gap: spacing.sm, shadowColor: colors.onSurface, shadowOpacity: 0.08, shadowRadius: 12, shadowOffset: { width: 0, height: -4 }, elevation: 5 },
  startOverBtn: { width: "100%", maxWidth: 620, alignSelf: "center", minHeight: 48, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, borderRadius: radius.md },
  startOverText: { color: colors.brandPrimary, fontSize: 16, lineHeight: 22, fontWeight: "800" },
  ctaBtn: { width: "100%", maxWidth: 620, alignSelf: "center", minHeight: 60, borderRadius: radius.md, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, shadowColor: colors.onBrandTertiary, shadowOpacity: 0.16, shadowRadius: 10, shadowOffset: { width: 0, height: 5 }, elevation: 3 },
  ctaText: { color: colors.onBrandPrimary, fontSize: 18, lineHeight: 24, fontWeight: "800" },
});
