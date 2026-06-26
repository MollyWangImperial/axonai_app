import { useRef, useState, useEffect } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { POSE_RUNNER_URL } from "@/src/api";
import { getUserId } from "@/src/auth";

export default function AssessmentScreen() {
  const router = useRouter();
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runnerUri, setRunnerUri] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      const uid = await getUserId();
      setRunnerUri(uid ? `${POSE_RUNNER_URL}?uid=${encodeURIComponent(uid)}` : POSE_RUNNER_URL);
    })();
  }, []);

  const onMessage = (e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data);
      if (msg.type === "ready") {
        setLoading(false);
      } else if (msg.type === "step_start") {
        Haptics.selectionAsync();
      } else if (msg.type === "task_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      } else if (msg.type === "camera_error") {
        setError("Camera unavailable. Please grant camera permission in settings and reload.");
      } else if (msg.type === "exit") {
        router.back();
      } else if (msg.type === "assessment_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        router.replace({ pathname: "/results", params: { id: msg.assessment.id } });
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
});
