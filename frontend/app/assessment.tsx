import { useRef, useState, useEffect } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform, ScrollView } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { AssessmentPackageId, POSE_RUNNER_URL } from "@/src/api";
import { cacheAssessmentActivity, completedTasksKey, getAccountGeneration, getUserId, savedTaskVideosKey } from "@/src/auth";
import { storage } from "@/src/utils/storage";
import { SafetyStopStrip } from "@/src/components/SafetyStopStrip";
import { loadUserPreferences } from "@/src/userPreferences";

type GaitScoreComponent = {
  score: number | null;
  weight: number;
};

type WalkingTestResult = {
  status: "scored" | "unscorable";
  score: number | null;
  rough_estimate?: boolean;
  reason_codes?: string[];
  components?: Record<string, GaitScoreComponent>;
  summary?: { step_count?: number };
};

const GAIT_COMPONENTS = [
  ["step_length_proxy", "Step length"],
  ["step_length_proxy_symmetry", "Step length symmetry"],
  ["step_time_symmetry", "Step timing symmetry"],
  ["rhythm_regularity", "Rhythm regularity"],
  ["swing_clearance_proxy", "Swing and knee movement"],
  ["trunk_stability", "Trunk stability"],
] as const;

const GAIT_RETRY_MESSAGES: Record<string, string> = {
  walking_pattern_not_detected: "The walking pattern could not be detected in this video.",
  walking_analysis_temporarily_unavailable: "The movement model could not finish reading this video. Please try the same video again.",
  camera_motion_not_compensated: "The camera movement could not be separated from the walking motion.",
  too_few_tracked_frames: "Too few clear walking frames were found.",
  insufficient_pose_tracking: "The body was not visible clearly enough throughout the clip.",
  feet_not_visible_enough: "Keep both feet and the whole body visible throughout the clip.",
  multiple_people_in_frame: "Keep one walking person in the frame.",
  too_few_alternating_steps: "The clip needs at least three clear alternating steps.",
  insufficient_gait_components: "There was not enough measurable walking information for a score.",
};

function parseCompletedTasks(raw: string | null): Record<string, boolean> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

async function markTaskComplete(userId: string, packageId: AssessmentPackageId, taskId: string) {
  const key = completedTasksKey(userId, packageId);
  const completed = parseCompletedTasks(await storage.getItem(key, ""));
  completed[taskId] = true;
  await storage.setItem(key, JSON.stringify(completed));
}

async function markTaskVideoSaved(userId: string, packageId: AssessmentPackageId, taskId: string, cloudSaved: boolean) {
  const key = savedTaskVideosKey(userId, packageId);
  const current = parseCompletedTasks(await storage.getItem(key, ""));
  current[taskId] = cloudSaved;
  await storage.setItem(key, JSON.stringify(current));
}

export default function AssessmentScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ package?: string; start_task?: string; completed_tasks?: string; affected_side?: string; task_ids?: string; library_test?: string; walking_test?: string }>();
  const packageParam = params["package"];
  const startTaskParam = params["start_task"];
  const affectedSideParam = params["affected_side"];
  const completedTasksParam = params["completed_tasks"];
  const assignedTaskIdsParam = params["task_ids"];
  const isLibraryTest = params["library_test"] === "1";
  const isWalkingTest = params["walking_test"] === "1";
  const webRef = useRef<WebView>(null);
  const userIdRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runnerUri, setRunnerUri] = useState<string | null>(null);
  const [testComplete, setTestComplete] = useState(false);
  const [walkingTestResult, setWalkingTestResult] = useState<WalkingTestResult | null>(null);
  const [runnerRevision, setRunnerRevision] = useState(0);

  useEffect(() => {
    (async () => {
      const uid = await getUserId();
      const preferences = await loadUserPreferences();
      userIdRef.current = uid;
      const selectedPackage = (typeof packageParam === "string" ? packageParam : "upper_limb") as AssessmentPackageId;
      const selectedStartTask = typeof startTaskParam === "string" ? startTaskParam : "";
      const query = new URLSearchParams();
      if (uid) query.set("uid", uid);
      if (uid) query.set("account_generation", String(await getAccountGeneration(uid)));
      query.set("package", selectedPackage);
      query.set("affected_side", affectedSideParam === "left" ? "left" : "right");
      query.set("voice_guidance", preferences.voiceGuidance ? "1" : "0");
      if (selectedStartTask) query.set("start_task", selectedStartTask);
      if (typeof completedTasksParam === "string" && completedTasksParam) query.set("completed_tasks", completedTasksParam);
      if (typeof assignedTaskIdsParam === "string" && assignedTaskIdsParam) query.set("task_ids", assignedTaskIdsParam);
      if (isLibraryTest) query.set("library_test", "1");
      if (isWalkingTest) query.set("walking_test", "1");
      setRunnerUri(`${POSE_RUNNER_URL}?${query.toString()}`);
    })();
  }, [packageParam, startTaskParam, completedTasksParam, affectedSideParam, assignedTaskIdsParam, isLibraryTest, isWalkingTest]);

  const onMessage = async (e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data);
      if (msg.type === "ready") {
        setLoading(false);
      } else if (msg.type === "step_start") {
        Haptics.selectionAsync();
      } else if (msg.type === "task_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        if (!isLibraryTest && msg.task_id && userIdRef.current) {
          const packageId = (msg.package_id || packageParam || "upper_limb") as AssessmentPackageId;
          void markTaskComplete(userIdRef.current, packageId, String(msg.task_id));
        }
      } else if (msg.type === "task_video_saved") {
        if (!isLibraryTest && msg.task_id && userIdRef.current) {
          const packageId = (msg.package_id || packageParam || "upper_limb") as AssessmentPackageId;
          void markTaskVideoSaved(userIdRef.current, packageId, String(msg.task_id), Boolean(msg.cloud_saved));
        }
      } else if (msg.type === "assessment_start_error") {
        const detail = typeof msg.message === "string"
          ? msg.message.replace(/^Could not load assessment tasks:\s*/, "")
          : "The assessment could not start. Check your connection and try again.";
        setError(detail);
      } else if (msg.type === "camera_error") {
        const detail = typeof msg.message === "string" ? msg.message : "";
        setError(detail.includes("secure HTTPS")
          ? "Camera setup requires the secure assessment connection. Please reopen the latest Expo QR code."
          : "Camera unavailable. Please grant camera permission in settings and reopen the assessment.");
      } else if (msg.type === "model_setup_error") {
        setError("The movement model could not finish loading. Check the connection and try again.");
      } else if (msg.type === "exit") {
        router.back();
      } else if (msg.type === "assessment_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        if (!isLibraryTest && userIdRef.current && msg.assessment?.id) {
          const completedPackage = String(msg.assessment.assessment_package || packageParam || "initial");
          await cacheAssessmentActivity(
            userIdRef.current,
            String(msg.assessment.id),
            String(msg.assessment.created_at || new Date().toISOString()),
            completedPackage === "initial",
          );
        }
        router.replace({ pathname: "/results", params: { id: msg.assessment.id, entry: "assessment_complete" } });
      } else if (msg.type === "library_test_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setTestComplete(true);
      } else if (msg.type === "walking_test_result") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setWalkingTestResult(msg.gait_analysis as WalkingTestResult);
      } else if (msg.type === "walking_video_error" && isWalkingTest) {
        setError("The walking video could not be scored. Please choose another video.");
      } else if (msg.type === "assessment_error") {
        setError("Could not save assessment. Please try again.");
      }
    } catch {
      /* noop */
    }
  };

  const injectedJS = `
    document.documentElement.style.backgroundColor='#0c100e';
    true;
  `;

  const retryWalkingTest = () => {
    setWalkingTestResult(null);
    setError(null);
    setLoading(true);
    setRunnerRevision((current) => current + 1);
  };

  const walkingComponents = walkingTestResult
    ? GAIT_COMPONENTS.map(([key, label]) => ({ key, label, value: walkingTestResult.components?.[key] }))
      .filter((item) => item.value)
    : [];

  return (
    <View style={styles.container}>
      {runnerUri ? (
      <WebView
        key={`assessment-runner-${runnerRevision}`}
        ref={webRef}
        testID="assessment-webview"
        source={{ uri: runnerUri }}
        style={styles.web}
        originWhitelist={["*"]}
        javaScriptEnabled
        domStorageEnabled
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        // iOS — grant camera permission inline (Expo Go limitations may apply on first load)
        {...(Platform.OS === "ios" ? { mediaCapturePermissionGrantType: "grant" as any } : {})}
        // Android — auto-grant camera permission requests
        {...(Platform.OS === "android" ? { onPermissionRequest: (event: any) => {
          try { event?.grant(event?.resources || []); } catch {}
        }} as any : {})}
        onLoadEnd={() => setLoading(false)}
        onMessage={onMessage}
        onError={(e) => setError(String(e.nativeEvent.description || e.nativeEvent))}
        injectedJavaScriptBeforeContentLoaded={injectedJS}
      />
      ) : (
        <View style={styles.overlay}>
          <ActivityIndicator size="large" color={colors.brandSecondary} />
          <Text style={styles.overlayText}>Loading…</Text>
        </View>
      )}

      {loading && (
        <View style={styles.overlay} pointerEvents="none">
          <ActivityIndicator size="large" color={colors.brandSecondary} />
          <Text style={styles.overlayText}>Preparing camera & pose model…</Text>
        </View>
      )}

      {error && (
        <View style={styles.errorWrap} testID="assessment-error">
          <Ionicons name="alert-circle" size={42} color={colors.brandSecondary} />
          <Text style={styles.errorTitle}>{error}</Text>
          <Pressable onPress={() => router.back()} style={styles.errorBtn} testID="assessment-error-back">
            <Text style={styles.errorBtnText}>Go back</Text>
          </Pressable>
        </View>
      )}

      {testComplete && (
        <View style={styles.testCompleteWrap} testID="assessment-library-test-complete">
          <Ionicons name="checkmark-circle" size={58} color={colors.success} />
          <Text style={styles.testCompleteTitle}>Task test complete</Text>
          <Text style={styles.testCompleteBody}>This test was not added to Assessment history, Progress, or your care plan.</Text>
          <Pressable onPress={() => router.back()} style={styles.testCompleteButton} testID="assessment-library-back">
            <Ionicons name="arrow-back" size={20} color="#FFFFFF" />
            <Text style={styles.testCompleteButtonText}>Back to library</Text>
          </Pressable>
        </View>
      )}

      {walkingTestResult && (
        <ScrollView style={styles.walkingResultOverlay} contentContainerStyle={styles.walkingResultWrap} testID="walking-video-test-result">
          <View style={styles.walkingResultPanel}>
            <Ionicons
              name={walkingTestResult.status === "scored" ? "checkmark-circle" : "alert-circle"}
              size={54}
              color={walkingTestResult.status === "scored" ? colors.success : colors.brandSecondary}
            />
            <Text style={styles.walkingResultTitle}>Walking video score</Text>
            {walkingTestResult.status === "scored" && walkingTestResult.score != null ? (
              <>
                <Text style={styles.walkingOverallScore}>{walkingTestResult.score}<Text style={styles.walkingScoreSuffix}> / 100</Text></Text>
                {walkingTestResult.rough_estimate ? (
                  <>
                    <Text style={styles.walkingEstimateLabel}>Rough test estimate</Text>
                    <Text style={styles.walkingResultBody}>The video was accepted, but a stable 2D walking pattern could not be measured. A testing fallback score was used.</Text>
                  </>
                ) : (
                  <>
                    <Text style={styles.walkingResultBody}>{walkingTestResult.summary?.step_count || 0} alternating steps measured</Text>
                    <View style={styles.walkingComponentList}>
                      {walkingComponents.map(({ key, label, value }) => (
                        <View key={key} style={styles.walkingComponentRow}>
                          <View style={styles.walkingComponentCopy}>
                            <Text style={styles.walkingComponentLabel}>{label}</Text>
                            <Text style={styles.walkingComponentWeight}>{value?.weight || 0}% of the overall score</Text>
                          </View>
                          <Text style={styles.walkingComponentScore}>{value?.score == null ? "Not measured" : `${value.score} / 100`}</Text>
                        </View>
                      ))}
                    </View>
                  </>
                )}
              </>
            ) : (
              <>
                <Text style={styles.walkingUnscorable}>No reliable score</Text>
                {(walkingTestResult.reason_codes || ["walking_pattern_not_detected"]).map((code) => (
                  <Text key={code} style={styles.walkingReason}>{GAIT_RETRY_MESSAGES[code] || "Try a clearer walking video."}</Text>
                ))}
              </>
            )}
            <Text style={styles.walkingTestingNote}>Testing only. This result was not saved to Assessment history or Progress.</Text>
            <View style={styles.walkingResultActions}>
              <Pressable onPress={retryWalkingTest} style={styles.walkingRetryButton} testID="walking-video-test-again">
                <Ionicons name="refresh" size={20} color="#FFFFFF" />
                <Text style={styles.walkingActionPrimary}>Test another video</Text>
              </Pressable>
              <Pressable onPress={() => router.back()} style={styles.walkingBackButton} testID="walking-video-test-back">
                <Ionicons name="arrow-back" size={20} color={colors.brandPrimary} />
                <Text style={styles.walkingActionSecondary}>Back to Settings</Text>
              </Pressable>
            </View>
          </View>
        </ScrollView>
      )}
      <SafetyStopStrip />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#0c100e" },
  web: { flex: 1, backgroundColor: "#0c100e" },
  overlay: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", backgroundColor: "#0c100e", gap: spacing.md },
  overlayText: { color: colors.onSurfaceInverse, fontSize: 16, fontWeight: "600" },
  errorWrap: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: spacing.md, backgroundColor: "#0c100eEE" },
  errorTitle: { color: colors.onSurfaceInverse, fontSize: 16, textAlign: "center", lineHeight: 22 },
  errorBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.lg },
  errorBtnText: { color: "#fff", fontWeight: "700" },
  testCompleteWrap: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", padding: spacing.xl, gap: spacing.md, backgroundColor: "#F8FBF8" },
  testCompleteTitle: { color: colors.onSurface, fontSize: 24, lineHeight: 30, fontWeight: "800", textAlign: "center" },
  testCompleteBody: { maxWidth: 420, color: colors.onSurfaceSecondary, fontSize: 15, lineHeight: 22, textAlign: "center" },
  testCompleteButton: { minHeight: 54, minWidth: 210, marginTop: spacing.sm, paddingHorizontal: spacing.lg, borderRadius: radius.md, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  testCompleteButtonText: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  walkingResultOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: "#F8FBF8" },
  walkingResultWrap: { flexGrow: 1, minHeight: "100%", alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md, paddingTop: spacing.xl, paddingBottom: 88, backgroundColor: "#F8FBF8" },
  walkingResultPanel: { width: "100%", maxWidth: 680, alignItems: "center", gap: spacing.sm },
  walkingResultTitle: { color: colors.onSurface, fontSize: 27, lineHeight: 34, fontWeight: "800", textAlign: "center" },
  walkingOverallScore: { color: colors.brandPrimary, fontSize: 52, lineHeight: 60, fontWeight: "900", textAlign: "center" },
  walkingScoreSuffix: { fontSize: 22, fontWeight: "800" },
  walkingEstimateLabel: { color: colors.brandSecondary, fontSize: 18, lineHeight: 24, fontWeight: "800", textAlign: "center" },
  walkingUnscorable: { color: colors.brandSecondary, fontSize: 30, lineHeight: 38, fontWeight: "900", textAlign: "center" },
  walkingResultBody: { color: colors.onSurfaceSecondary, fontSize: 15, lineHeight: 22, textAlign: "center" },
  walkingComponentList: { width: "100%", marginTop: spacing.sm, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: "#C9D4CC" },
  walkingComponentRow: { minHeight: 62, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md, paddingVertical: spacing.sm, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#C9D4CC" },
  walkingComponentCopy: { flex: 1 },
  walkingComponentLabel: { color: colors.onSurface, fontSize: 15, lineHeight: 21, fontWeight: "700" },
  walkingComponentWeight: { color: colors.onSurfaceSecondary, fontSize: 12, lineHeight: 17 },
  walkingComponentScore: { color: colors.brandPrimary, fontSize: 15, lineHeight: 21, fontWeight: "800", textAlign: "right" },
  walkingReason: { maxWidth: 540, color: colors.onSurfaceSecondary, fontSize: 15, lineHeight: 22, textAlign: "center" },
  walkingTestingNote: { maxWidth: 540, marginTop: spacing.sm, color: colors.onSurfaceSecondary, fontSize: 12, lineHeight: 18, textAlign: "center" },
  walkingResultActions: { width: "100%", maxWidth: 420, marginTop: spacing.sm, gap: spacing.sm },
  walkingRetryButton: { minHeight: 54, paddingHorizontal: spacing.lg, borderRadius: radius.md, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  walkingBackButton: { minHeight: 52, paddingHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.md, backgroundColor: "#FFFFFF", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  walkingActionPrimary: { color: "#FFFFFF", fontSize: 16, fontWeight: "800" },
  walkingActionSecondary: { color: colors.brandPrimary, fontSize: 16, fontWeight: "800" },
});
