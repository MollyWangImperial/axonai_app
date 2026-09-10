import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { API_BASE } from "@/src/config";
import { getCachedPatientProfile, getUserId } from "@/src/auth";
import { colors } from "@/src/theme";

export function CameraSetup({ purpose, onReady, onExit }: {
  purpose: "assessment" | "exercise";
  onReady: () => void;
  onExit: () => void;
}) {
  const insets = useSafeAreaInsets();
  const [uri, setUri] = useState("");
  const [failed, setFailed] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    void (async () => {
      const uid = await getUserId();
      const profile = uid ? await getCachedPatientProfile(uid) : null;
      const query = new URLSearchParams({ purpose });
      if (Array.isArray(profile?.camera_devices)) query.set("devices", profile.camera_devices.join(","));
      if (active) setUri(`${API_BASE}/camera-setup/index.html?${query}`);
    })().catch(() => {
      if (active) setUri(`${API_BASE}/camera-setup/index.html?purpose=${purpose}`);
    });
    return () => { active = false; };
  }, [purpose]);

  function onMessage(event: WebViewMessageEvent) {
    try {
      const message = JSON.parse(event.nativeEvent.data);
      if (message.type === "camera_setup_ready") onReady();
      if (message.type === "camera_setup_exit") onExit();
    } catch { /* Ignore messages from model internals. */ }
  }

  if (failed) return <View style={styles.fallback}>
    <Text style={styles.message}>Camera setup could not load. Check your connection and try again.</Text>
    <Pressable onPress={() => { setFailed(false); setRevision((value) => value + 1); }}><Text style={styles.action}>Try again</Text></Pressable>
    <Pressable onPress={onExit}><Text style={styles.action}>Go back</Text></Pressable>
  </View>;
  if (!uri) return <View style={styles.fallback}><ActivityIndicator color={colors.brandPrimary} accessibilityLabel="Loading camera setup" /></View>;
  return <View style={{ flex: 1, paddingTop: insets.top, paddingBottom: insets.bottom, backgroundColor: "#fcfcfa" }}><WebView key={revision} source={{ uri }} style={styles.webview} testID="camera-setup"
    onMessage={onMessage} onError={() => setFailed(true)} javaScriptEnabled domStorageEnabled
    allowsInlineMediaPlayback mediaPlaybackRequiresUserAction={false} mediaCapturePermissionGrantType="grantIfSameHostElsePrompt"
    {...(Platform.OS === "android" ? { onPermissionRequest: (event: any) => event.grant(event.resources) } : {})}
  /></View>;
}

const styles = StyleSheet.create({
  webview: { flex: 1, backgroundColor: "#fcfcfa" },
  fallback: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, gap: 24 },
  message: { color: colors.onSurface, textAlign: "center", fontSize: 18 },
  action: { color: colors.brandPrimary, fontSize: 18, fontWeight: "700", padding: 12 },
});
