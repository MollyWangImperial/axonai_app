import { useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

export default function ExerciseScreen() {
  const router = useRouter();
  const { exercise_id, name } = useLocalSearchParams<{ exercise_id: string; name?: string }>();
  const webRef = useRef<WebView>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [doneInfo, setDoneInfo] = useState<{ reps: number } | null>(null);

  const url = `${BASE}/api/rehab/runner?exercise_id=${encodeURIComponent(exercise_id || "ex_maintenance")}`;

  const onMessage = (e: WebViewMessageEvent) => {
    try {
      const msg = JSON.parse(e.nativeEvent.data);
      if (msg.type === "ready") setLoading(false);
      else if (msg.type === "rep_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      } else if (msg.type === "exercise_complete") {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setDoneInfo({ reps: msg.reps || 0 });
        setTimeout(() => router.back(), 2200);
      } else if (msg.type === "camera_error") {
        setError("Camera unavailable. Please grant camera permission in your phone settings and try again.");
      } else if (msg.type === "exit") {
        router.back();
      }
    } catch {/* */}
  };

  return (
    <View style={styles.container}>
      <WebView
        ref={webRef}
        testID="exercise-webview"
        source={{ uri: url }}
        style={styles.web}
        originWhitelist={["*"]}
        javaScriptEnabled
        domStorageEnabled
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        {...(Platform.OS === "ios" ? { mediaCapturePermissionGrantType: "grant" as any } : {})}
        onPermissionRequest={(event: any) => { try { event?.grant(event?.resources || []); } catch {} }}
        onMessage={onMessage}
        onLoadEnd={() => setLoading(false)}
        onError={(e) => setError(String(e.nativeEvent.description || e.nativeEvent))}
      />
      {loading && (
        <View style={styles.overlay} pointerEvents="none">
          <ActivityIndicator size="large" color={colors.brandSecondary} />
          <Text style={styles.overlayText}>Preparing {name || "exercise"}…</Text>
        </View>
      )}
      {doneInfo && (
        <View style={styles.overlay} testID="exercise-done-overlay">
          <Ionicons name="checkmark-circle" size={56} color={colors.success} />
          <Text style={styles.doneTitle}>Exercise complete!</Text>
          <Text style={styles.doneSub}>Returning to your plan…</Text>
        </View>
      )}
      {error && (
        <View style={styles.errorWrap} testID="exercise-error">
          <Ionicons name="alert-circle" size={42} color={colors.brandSecondary} />
          <Text style={styles.errorTitle}>{error}</Text>
          <Pressable onPress={() => router.back()} style={styles.errorBtn} testID="exercise-error-back">
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
  doneTitle: { color: colors.onSurfaceInverse, fontSize: 22, fontWeight: "800" },
  doneSub: { color: colors.onSurfaceTertiary, fontSize: 15 },
  errorWrap: { ...StyleSheet.absoluteFillObject, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: spacing.md, backgroundColor: "#0c100eEE" },
  errorTitle: { color: colors.onSurfaceInverse, fontSize: 16, textAlign: "center", lineHeight: 22 },
  errorBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.lg },
  errorBtnText: { color: "#fff", fontWeight: "700" },
});
