import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
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

type InitialAssessmentRecommendation = {
  status: "needs_answers" | "support_needed" | "clinical_review" | "ready";
  can_start: boolean;
  task_ids: string[];
  task_count: number;
  missing_answers: string[];
  requires_helper: boolean;
  requires_clinician_review: boolean;
  safety_notes: string[];
  message: string;
};

type AdaptiveAssessmentSelection = {
  due: boolean;
  due_at?: string;
  can_start: boolean;
  packages: AssessmentPackageId[];
  task_ids: string[];
  trigger?: "scheduled" | "new_functional_issue" | "initial" | "not_due";
};

export default function TaskIntro() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ mode?: string; package?: string; task_ids?: string }>();
  const isInitial = params.mode !== "followup";
  const allowedPackages: AssessmentPackageId[] = ["initial", "upper_limb", "hand", "lower_limb", "balance"];
  const packageId: AssessmentPackageId = allowedPackages.includes(params.package as AssessmentPackageId)
    ? params.package as AssessmentPackageId
    : "initial";
  const [completedTasks, setCompletedTasks] = useState<Record<string, boolean>>({});
  const [taskIds, setTaskIds] = useState<string[]>([]);
  const [userId, setUserId] = useState<string | null>(null);
  const [nextTaskId, setNextTaskId] = useState<string | null>(null);
  const [affectedSide, setAffectedSide] = useState<"left" | "right">("right");
  const [savedVideoCount, setSavedVideoCount] = useState(0);
  const [recommendation, setRecommendation] = useState<InitialAssessmentRecommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showStartOver, setShowStartOver] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        setLoading(true);
        const uid = await getUserId();
        if (!uid) throw new Error("Please sign in again.");
        setUserId(uid);
        const [profileResponse, recommendationResponse, adaptiveSelection] = await Promise.all([
          authedFetch("/api/users/onboarding").then((r) => r.json()).catch(() => null),
          isInitial
            ? authedFetch("/api/assessment/recommendation?package=initial")
              .then(async (response) => {
                const body = await response.json().catch(() => null);
                if (!response.ok) throw new Error(body?.detail || "Could not select suitable assessment tasks.");
                return body as InitialAssessmentRecommendation;
              })
            : Promise.resolve(null),
          !isInitial
            ? authedFetch("/api/alira/care-plan")
              .then(async (response) => {
                const body = await response.json().catch(() => null);
                if (!response.ok) throw new Error(body?.detail || "Could not verify the assessment schedule.");
                return body?.assessment as AdaptiveAssessmentSelection;
              })
            : Promise.resolve(null),
        ]);
        setRecommendation(recommendationResponse);
        const storedSide = await storage.getItem(affectedSideKey(uid), "");
        const profileSide = profileResponse?.profile?.side_affected;
        const resolvedSide = storedSide || profileSide;
        setAffectedSide(resolvedSide === "left" ? "left" : "right");
        if (recommendationResponse && !recommendationResponse.can_start) {
          setTaskIds([]);
          setCompletedTasks({});
          setNextTaskId(null);
          setSavedVideoCount(0);
          return;
        }
        if (adaptiveSelection && (!adaptiveSelection.due || !adaptiveSelection.can_start)) {
          const dueDate = String(adaptiveSelection.due_at || "").slice(0, 10);
          throw new Error(`Your next assessment is not due yet${dueDate ? `; it is scheduled for ${dueDate}` : ""}.`);
        }
        const selectedPackage = adaptiveSelection?.packages?.[0];
        if (selectedPackage && selectedPackage !== packageId) {
          throw new Error(`Alira selected the ${selectedPackage.replace("_", " ")} assessment for this check-in.`);
        }
        const assignedTaskIds = recommendationResponse?.task_ids || adaptiveSelection?.task_ids;
        const routeTaskIds = String(params.task_ids || "").split(",").map((item) => item.trim()).filter(Boolean);
        if (routeTaskIds.length && assignedTaskIds) {
          const expected = new Set(assignedTaskIds);
          if (new Set(routeTaskIds).size !== expected.size || routeTaskIds.some((taskId) => !expected.has(taskId))) {
            throw new Error("The assessment link no longer matches Alira's current task selection.");
          }
        }
        const [taskResponse, rawCompleted, rawSavedVideos, savedVideos, serverProgressResult] = await Promise.all([
          fetchTasks(packageId, assignedTaskIds),
          storage.getItem(completedTasksKey(uid, packageId), ""),
          storage.getItem(savedTaskVideosKey(uid, packageId), ""),
          fetchTaskVideos(packageId).catch(() => []),
          fetchTaskProgress(packageId)
            .then((completedTaskIds) => ({ available: true as const, completedTaskIds }))
            .catch(() => ({ available: false as const, completedTaskIds: [] as string[] })),
        ]);
        const deviceCompleted = parseCompletedTasks(rawCompleted || "");
        const deviceSavedVideos = parseCompletedTasks(rawSavedVideos || "");
        const serverCompleted = Object.fromEntries(
          serverProgressResult.completedTaskIds
            .filter(Boolean)
            .map((taskId) => [taskId, true]),
        );
        // A successful server response is authoritative, including an empty list.
        // Device state is used only when progress cannot be reached at all.
        const completed = serverProgressResult.available ? serverCompleted : deviceCompleted;
        if (serverProgressResult.available) {
          await storage.setItem(completedTasksKey(uid, packageId), JSON.stringify(completed));
        }
        const nextTask = taskResponse.tasks.find((task) => !completed[task.id]);
        const loadedTaskIds = taskResponse.tasks.reduce<string[]>((ids, task) => [...ids, task.id], []);
        const completedTaskIds = loadedTaskIds.filter((taskId) => completed[taskId]);
        const ignoredDeviceCompletedTaskIds = serverProgressResult.available
          ? loadedTaskIds.filter((taskId) => deviceCompleted[taskId] && !serverCompleted[taskId])
          : [];
        try {
          await authedFetch("/api/alira/assessment-resume-events", {
            method: "POST",
            body: JSON.stringify({
              package_id: packageId,
              task_ids: loadedTaskIds,
              completed_task_ids: completedTaskIds,
              next_task_id: nextTask?.id || null,
              progress_source: serverProgressResult.available ? "server" : "device_fallback",
              ignored_device_completed_task_ids: ignoredDeviceCompletedTaskIds,
            }),
          });
        } catch { /* action logging must not block the assessment */ }
        setTaskIds(loadedTaskIds);
        setCompletedTasks(completed);
        setNextTaskId(nextTask?.id || null);
        setSavedVideoCount(Math.max(savedVideos.length, Object.keys(deviceSavedVideos).length));
      } catch (e: any) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    })();
  }, [isInitial, packageId, params.task_ids]);

  const onBegin = async () => {
    if (isInitial && recommendation && !recommendation.can_start) {
      router.push("/onboarding?mode=assessment-readiness" as never);
      return;
    }
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
      pathname: "/camera-check",
      params: {
        package: packageId,
        start_task: taskToStart,
        completed_tasks: completedTaskIds.join(","),
        affected_side: affectedSide,
        task_ids: taskIds.join(","),
      },
    });
  };

  const confirmStartOver = () => {
    if (!userId || taskIds.length === 0) return;
    setShowStartOver(true);
  };

  const doStartOver = async () => {
    setShowStartOver(false);
    if (!userId) return;
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
  };

  const completedCount = taskIds.filter((taskId) => completedTasks[taskId]).length;
  const assessmentComplete = taskIds.length > 0 && completedCount === taskIds.length;
  const preparationTips = recommendation && !recommendation.task_ids.includes("L6")
    ? PREPARATION_TIPS.filter((tip) => !tip.toLowerCase().includes("walking"))
    : PREPARATION_TIPS;

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
            ? recommendation?.message || "Alira uses your saved movement-readiness answers to select only suitable approved arm, hand, and walking tasks."
            : "We have selected the next standardized movement session for you. Alira will guide each task in order."}
        </Text>

        <View style={styles.tipsCard} testID="task-intro-tips">
          <Text style={styles.tipsHeader}>Before we begin</Text>
          {preparationTips.map((tip) => (
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
                {recommendation && !recommendation.can_start
                  ? recommendation.status === "needs_answers" ? "A few readiness answers are needed" : "Camera tasks are paused"
                  : assessmentComplete
                  ? isInitial ? "Your Initial Assessment is complete" : "Your next assessment is ready"
                  : completedCount > 0 ? "Continue where you left off" : isInitial ? "Your first guided task is ready" : "Your next guided task is ready"}
              </Text>
              <Text style={styles.sessionReadyText}>
                {recommendation && !recommendation.can_start
                  ? recommendation.message
                  : assessmentComplete
                  ? isInitial
                    ? "You do not need to repeat these tasks. Your saved results are ready from the Home screen."
                    : "Your previous results will remain in Assessment history. Starting now creates a new movement check-in for progress comparison."
                  : `Alira will launch your next guided task automatically and continue through the remaining assessment. ${completedCount} of ${taskIds.length} tasks are already complete.`}
              </Text>
              {recommendation?.safety_notes?.map((note) => (
                <View key={note} style={styles.savedVideoRow}>
                  <Ionicons name="shield-checkmark-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.savedVideoText}>{note}</Text>
                </View>
              ))}
              {savedVideoCount > 0 && recommendation?.can_start !== false && (
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
          <Ionicons name={recommendation && !recommendation.can_start ? "clipboard" : assessmentComplete && isInitial ? "home" : "videocam"} size={21} color={colors.onBrandPrimary} />
          <Text style={styles.ctaText}>
            {recommendation && !recommendation.can_start
              ? recommendation.status === "needs_answers" ? "Answer readiness questions" : "Review readiness answers"
              : assessmentComplete
              ? isInitial ? "Return Home" : "Start Next Assessment"
              : completedCount > 0 ? "Continue Assessment" : isInitial ? "Begin Initial Assessment" : "Begin Movement Check-in"}
          </Text>
        </Pressable>
      </View>

      <Modal visible={showStartOver} transparent animationType="fade" onRequestClose={() => setShowStartOver(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard} testID="task-intro-startover-modal">
            <Text style={styles.modalTitle}>Start the assessment again?</Text>
            <Text style={styles.modalBody}>Your saved results will remain in your history, but all {taskIds.length} assigned collection tasks will be marked as incomplete.</Text>
            <View style={styles.modalActions}>
              <Pressable testID="startover-cancel" onPress={() => setShowStartOver(false)} style={styles.modalCancel}>
                <Text style={styles.modalCancelText}>Cancel</Text>
              </Pressable>
              <Pressable testID="startover-confirm" onPress={doStartOver} style={styles.modalConfirm}>
                <Text style={styles.modalConfirmText}>Start over</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  scroll: { width: "100%", maxWidth: 620, alignSelf: "center", padding: spacing.lg, paddingBottom: 180 },
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
  savedVideoRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.sm },
  savedVideoText: { flex: 1, color: colors.brandPrimary, fontSize: 12, lineHeight: 17, fontWeight: "700" },
  errorText: { color: colors.error, fontSize: 14, lineHeight: 20, marginVertical: spacing.md },
  cta: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider, gap: spacing.sm },
  startOverBtn: { width: "100%", maxWidth: 620, alignSelf: "center", minHeight: 42, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  startOverText: { color: colors.brandPrimary, fontSize: 15, fontWeight: "800" },
  ctaBtn: { width: "100%", maxWidth: 620, alignSelf: "center", minHeight: 56, borderRadius: radius.md, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "800" },
  modalBackdrop: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, backgroundColor: "rgba(10,22,16,0.6)" },
  modalCard: { width: "100%", maxWidth: 440, borderRadius: radius.md, backgroundColor: colors.surface, padding: spacing.lg },
  modalTitle: { fontSize: 20, lineHeight: 26, fontWeight: "800", color: colors.onSurface },
  modalBody: { fontSize: 14, lineHeight: 20, color: colors.onSurfaceSecondary, marginTop: spacing.sm },
  modalActions: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.lg },
  modalCancel: { minHeight: 46, minWidth: 96, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  modalCancelText: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  modalConfirm: { minHeight: 46, minWidth: 110, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md, borderRadius: radius.md, backgroundColor: colors.error },
  modalConfirmText: { color: "#FFFFFF", fontSize: 15, fontWeight: "800" },
});
