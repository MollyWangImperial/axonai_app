import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import {
  createAudioPlayer,
  RecordingPresets,
  requestRecordingPermissionsAsync,
  setAudioModeAsync,
  useAudioRecorder,
} from "expo-audio";

import { authedFetch, getUserId } from "@/src/auth";
import { API_BASE as BASE } from "@/src/config";
import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";

type CallPhase = "ready" | "listening" | "processing" | "speaking" | "error";

const SESSION_KEY = "alira_session_id";

function makeSessionId() {
  return "s_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

export default function AliraCallScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const recorder = useAudioRecorder(RecordingPresets.HIGH_QUALITY);
  const playerRef = useRef<ReturnType<typeof createAudioPlayer> | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [phase, setPhase] = useState<CallPhase>("ready");
  const [heard, setHeard] = useState("");
  const [reply, setReply] = useState("I'm ready when you are. Tap the microphone and speak naturally.");
  const [error, setError] = useState("");

  useEffect(() => {
    void (async () => {
      const saved = await storage.getItem<string>(SESSION_KEY, "");
      const id = saved || makeSessionId();
      if (!saved) await storage.setItem(SESSION_KEY, id);
      setSessionId(id);
    })();
    return () => {
      try { playerRef.current?.pause(); } catch { /* no-op */ }
    };
  }, []);

  const playReply = async (text: string) => {
    setPhase("speaking");
    try {
      const response = await fetch(`${BASE}/api/tts/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) throw new Error("Voice playback is unavailable.");
      const audio = await response.json();
      try { playerRef.current?.pause(); } catch { /* no-op */ }
      const player = createAudioPlayer({ uri: `data:audio/mpeg;base64,${audio.audio_b64}` });
      playerRef.current = player;
      player.play();
    } catch {
      setError("Alira replied in text, but her voice could not play. You can still read the response below.");
    } finally {
      setPhase("ready");
    }
  };

  const uploadRecording = async (uri: string) => {
    const form = new FormData();
    if (Platform.OS === "web") {
      const recording = await fetch(uri);
      const blob = await recording.blob();
      form.append("file", blob, `alira-${Date.now()}.webm`);
    } else {
      form.append("file", {
        uri,
        name: `alira-${Date.now()}.m4a`,
        type: "audio/m4a",
      } as unknown as Blob);
    }
    const userId = await getUserId();
    const response = await fetch(`${BASE}/api/stt/transcribe`, {
      method: "POST",
      headers: userId ? { "X-User-Id": userId } : undefined,
      body: form,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || "I could not understand that recording.");
    return String(data.text || "").trim();
  };

  const startListening = async () => {
    setError("");
    const permission = await requestRecordingPermissionsAsync();
    if (!permission.granted) {
      setError("Microphone access is needed for a voice call. Enable it in your browser or device settings.");
      setPhase("error");
      return;
    }
    await setAudioModeAsync({ allowsRecording: true, playsInSilentMode: true });
    await recorder.prepareToRecordAsync();
    recorder.record({ forDuration: 60 });
    setPhase("listening");
  };

  const stopAndRespond = async () => {
    if (phase !== "listening") return;
    setPhase("processing");
    setError("");
    try {
      await recorder.stop();
      await setAudioModeAsync({ allowsRecording: false, playsInSilentMode: true });
      if (!recorder.uri) throw new Error("No recording was captured. Please try again.");
      const transcript = await uploadRecording(recorder.uri);
      setHeard(transcript);
      const response = await authedFetch("/api/chat/message", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, text: transcript }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || "Alira is unavailable right now.");
      const answer = String(data.text || "I'm here with you.");
      setReply(answer);
      await playReply(answer);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The call could not continue. Please try again.");
      setPhase("error");
    }
  };

  const busy = phase === "processing" || phase === "speaking";
  const status = phase === "listening"
    ? "Listening... tap again when you finish"
    : phase === "processing"
      ? "Understanding what you said..."
      : phase === "speaking"
        ? "Alira is speaking..."
        : "Tap the microphone to speak";

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.headerButton} accessibilityLabel="End call" testID="alira-call-back">
          <Ionicons name="close" size={26} color={colors.onSurface} />
        </Pressable>
        <View style={styles.headerCopy}>
          <Text style={styles.title}>Alira voice call</Text>
          <Text style={styles.subtitle}>AI stroke-recovery companion</Text>
        </View>
        <View style={styles.livePill}><View style={styles.liveDot} /><Text style={styles.liveText}>Available</Text></View>
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.avatar}><Ionicons name="heart" size={46} color="#FFFFFF" /></View>
        <Text style={styles.aliraName}>Alira</Text>
        <Text style={styles.safety}>Alira can support reflection and recovery questions. She cannot diagnose or replace your therapist. This is not an emergency service.</Text>

        <View style={styles.conversationCard}>
          {heard ? <><Text style={styles.label}>You said</Text><Text style={styles.heard}>{heard}</Text></> : null}
          <Text style={[styles.label, heard && { marginTop: spacing.md }]}>Alira</Text>
          <Text style={styles.reply}>{reply}</Text>
        </View>

        {error ? <View style={styles.errorCard}><Ionicons name="alert-circle-outline" size={20} color={colors.error} /><Text style={styles.errorText}>{error}</Text></View> : null}

        <View style={styles.controls}>
          <Pressable
            testID="alira-call-microphone"
            disabled={busy || !sessionId}
            onPress={phase === "listening" ? stopAndRespond : startListening}
            style={[styles.micButton, phase === "listening" && styles.micListening, (busy || !sessionId) && styles.disabled]}
            accessibilityLabel={phase === "listening" ? "Stop listening" : "Speak to Alira"}
          >
            {busy ? <ActivityIndicator size="large" color="#FFFFFF" /> : <Ionicons name={phase === "listening" ? "stop" : "mic"} size={38} color="#FFFFFF" />}
          </Pressable>
          <Text style={styles.status}>{status}</Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F8FBF8" },
  header: { minHeight: 72, flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider, backgroundColor: colors.surface },
  headerButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headerCopy: { flex: 1, alignItems: "center" },
  title: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  subtitle: { marginTop: 2, fontSize: 11, color: colors.onSurfaceTertiary },
  livePill: { minWidth: 70, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 5 },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.success },
  liveText: { fontSize: 11, fontWeight: "700", color: colors.brandPrimary },
  content: { flexGrow: 1, alignItems: "center", padding: spacing.lg, paddingBottom: spacing.xxl },
  avatar: { width: 104, height: 104, borderRadius: 52, alignItems: "center", justifyContent: "center", backgroundColor: "#4C8A5A", marginTop: spacing.lg },
  aliraName: { marginTop: spacing.sm, fontSize: 27, fontWeight: "900", color: colors.onSurface },
  safety: { maxWidth: 520, marginTop: spacing.sm, fontSize: 12, lineHeight: 18, textAlign: "center", color: colors.onSurfaceTertiary },
  conversationCard: { width: "100%", maxWidth: 620, minHeight: 150, marginTop: spacing.lg, padding: spacing.lg, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  label: { fontSize: 11, fontWeight: "800", color: colors.brandPrimary, textTransform: "uppercase" },
  heard: { marginTop: 5, fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary },
  reply: { marginTop: 5, fontSize: 17, lineHeight: 25, color: colors.onSurface, fontWeight: "600" },
  errorCard: { width: "100%", maxWidth: 620, flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: "#FFF1EF" },
  errorText: { flex: 1, fontSize: 13, lineHeight: 19, color: colors.error },
  controls: { flex: 1, justifyContent: "flex-end", alignItems: "center", minHeight: 190, paddingTop: spacing.xl },
  micButton: { width: 92, height: 92, borderRadius: 46, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  micListening: { backgroundColor: colors.brandSecondary },
  disabled: { opacity: 0.55 },
  status: { marginTop: spacing.md, fontSize: 14, fontWeight: "700", color: colors.onSurfaceSecondary, textAlign: "center" },
});
