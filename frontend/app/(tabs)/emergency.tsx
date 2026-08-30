import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import * as Haptics from "expo-haptics";

import { authedFetch, getCachedUser } from "@/src/auth";
import { API_BASE } from "@/src/config";
import { colors } from "@/src/theme";

export default function EmergencyFastScreen() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [patientName, setPatientName] = useState("");

  useEffect(() => {
    void getCachedUser().then((user) => setPatientName((user?.name || "").split(" ")[0] || ""));
  }, []);

  const recordResult = async (message: Record<string, unknown>) => {
    try {
      await authedFetch("/api/emergency/fast-check", {
        method: "POST",
        body: JSON.stringify({
          answers: message.answers,
          automated: message.automated,
          onset_time: message.onset_time || undefined,
          source: "guided_fast",
        }),
      });
    } catch {
      // An emergency result is shown immediately and never waits for audit logging.
    }
  };

  const onMessage = (event: WebViewMessageEvent) => {
    try {
      const message = JSON.parse(event.nativeEvent.data) as Record<string, unknown>;
      if (message.type === "fast_check_result") {
        const result = message.result as { call_999?: boolean } | undefined;
        void Haptics.notificationAsync(
          result?.call_999
            ? Haptics.NotificationFeedbackType.Error
            : Haptics.NotificationFeedbackType.Success,
        );
        void recordResult(message);
      } else if (message.type === "demo_911_started") {
        void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      } else if (message.type === "exit") {
        router.back();
      }
    } catch {
      // Ignore non-Rehyn iframe messages.
    }
  };

  const query = patientName ? `?name=${encodeURIComponent(patientName)}` : "";

  return (
    <View style={styles.container} testID="emergency-fast-screen">
      <WebView
        testID="emergency-fast-webview"
        source={{ uri: `${API_BASE}/api/emergency/fast-runner${query}` }}
        style={styles.webview}
        originWhitelist={["*"]}
        javaScriptEnabled
        domStorageEnabled
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        {...(Platform.OS === "ios" ? { mediaCapturePermissionGrantType: "grant" as const } : {})}
        {...({ onPermissionRequest: (event: any) => { try { event?.grant(event?.resources || []); } catch {} } } as any)}
        onMessage={onMessage}
        onLoadEnd={() => setReady(true)}
      />
      {!ready ? (
        <View style={styles.loading} pointerEvents="none">
          <ActivityIndicator size="large" color={colors.error} />
          <Text style={styles.loadingText}>Opening emergency FAST check...</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F7F8F6" },
  webview: { flex: 1, backgroundColor: "#F7F8F6" },
  loading: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    backgroundColor: "#F7F8F6",
  },
  loadingText: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
});
