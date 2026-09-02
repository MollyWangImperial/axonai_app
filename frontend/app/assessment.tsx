import { useRef, useState, useEffect } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { AssessmentPackageId, POSE_RUNNER_URL } from "@/src/api";
import { cacheAssessmentActivity, completedTasksKey, getUserId, savedTaskVideosKey } from "@/src/auth";
import { storage } from "@/src/utils/storage";
import { SafetyStopStrip } from "@/src/components/SafetyStopStrip";
import { loadUserPreferences } from "@/src/userPreferences";

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
  const params = useLocalSearchParams<{ package?: string; start_task?: string; completed_tasks?: string; affected_side?: string; task_ids?: string; library_test?: string }>();
  const packageParam = params["package"];
  const startTaskParam = params["start_task"];
  const affectedSideParam = params["affected_side"];
  const completedTasksParam = params["completed_tasks"];
  const assignedTaskIdsParam = params["task_ids"];
  const isLibraryTest = params["library_test"] === "1";
  const webRef = useRef<WebView>(null);
  const userIdRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runnerUri, setRunnerUri] = useState<string | null>(null);
  const [testComplete, setTestComplete] = useState(false);

  useEffect(() => {
    (async () => {
      const uid = await getUserId();
      const preferences = await loadUserPreferences();
      userIdRef.current = uid;
      const selectedPackage = (typeof packageParam === "string" ? packageParam : "upper_limb") as AssessmentPackageId;
      const selectedStartTask = typeof startTaskParam === "string" ? startTaskParam : "";
      const query = new URLSearchParams();
      if (uid) query.set("uid", uid);
      query.set("package", selectedPackage);
      query.set("affected_side", affectedSideParam === "left" ? "left" : "right");
      query.set("voice_guidance", preferences.voiceGuidance ? "1" : "0");
      if (selectedStartTask) query.set("start_task", selectedStartTask);
      if (typeof completedTasksParam === "string" && completedTasksParam) query.set("completed_tasks", completedTasksParam);
      if (typeof assignedTaskIdsParam === "string" && assignedTaskIdsParam) query.set("task_ids", assignedTaskIdsParam);
      if (isLibraryTest) query.set("library_test", "1");
      setRunnerUri(`${POSE_RUNNER_URL}?${query.toString()}`);
    })();
  }, [packageParam, startTaskParam, completedTasksParam, affectedSideParam, assignedTaskIdsParam, isLibraryTest]);

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

  return (
    <View style={styles.container}>
      {runnerUri ? (
      <WebView
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
        onPermissionRequest={(event: any) => {
          try { event?.grant(event?.resources || []); } catch {}
        }}
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
});
