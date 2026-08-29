import { useCallback, useEffect, useRef, useState } from "react";
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
import { resolveAliraNavigation } from "@/src/aliraNavigation";
import type { AliraNavigationResolution } from "@/src/aliraNavigation";

type CallPhase = "ready" | "listening" | "processing" | "speaking" | "error";
type RealtimePhase = "idle" | "connecting" | "listening" | "thinking" | "speaking" | "ended" | "error";
type TranscriptTurn = { id: string; role: "user" | "assistant"; text: string };
type PendingNavigation = AliraNavigationResolution & {
  originResponseId?: string;
  acknowledgementResponseId?: string;
  acknowledgementDone?: boolean;
  audioStopped?: boolean;
};

const SESSION_KEY = "alira_session_id";
const MAX_CALL_MS = 20 * 60 * 1000;

function makeSessionId() {
  return "s_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

export default function AliraCallScreen() {
  return Platform.OS === "web" ? <RealtimeWebCall /> : <TurnBasedAliraCallScreen />;
}

function TurnBasedAliraCallScreen() {
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

function RealtimeWebCall() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const peerRef = useRef<any>(null);
  const dataChannelRef = useRef<any>(null);
  const mediaStreamRef = useRef<any>(null);
  const remoteAudioRef = useRef<any>(null);
  const callTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const navigationTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingNavigationRef = useRef<PendingNavigation | null>(null);
  const handledToolCallsRef = useRef<Set<string>>(new Set());
  const closedByUserRef = useRef(false);
  const [phase, setPhase] = useState<RealtimePhase>("idle");
  const [turns, setTurns] = useState<TranscriptTurn[]>([]);
  const [liveReply, setLiveReply] = useState("");
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState("");

  const releaseConnection = useCallback(() => {
    if (callTimerRef.current) clearTimeout(callTimerRef.current);
    if (navigationTimerRef.current) clearTimeout(navigationTimerRef.current);
    callTimerRef.current = null;
    navigationTimerRef.current = null;
    pendingNavigationRef.current = null;
    handledToolCallsRef.current.clear();
    try { dataChannelRef.current?.close(); } catch { /* no-op */ }
    try { peerRef.current?.close(); } catch { /* no-op */ }
    try { mediaStreamRef.current?.getTracks()?.forEach((track: any) => track.stop()); } catch { /* no-op */ }
    try {
      if (remoteAudioRef.current) {
        remoteAudioRef.current.pause?.();
        remoteAudioRef.current.srcObject = null;
      }
    } catch { /* no-op */ }
    dataChannelRef.current = null;
    peerRef.current = null;
    mediaStreamRef.current = null;
    remoteAudioRef.current = null;
  }, []);

  useEffect(() => releaseConnection, [releaseConnection]);

  const addTurn = useCallback((role: TranscriptTurn["role"], rawText: unknown, id?: string) => {
    const text = String(rawText || "").trim();
    if (!text) return;
    setTurns((current) => {
      if (current.some((turn) => turn.role === role && turn.text === text)) return current;
      return [...current, { id: id || `${role}-${Date.now()}`, role, text }].slice(-8);
    });
  }, []);

  const completeNavigation = useCallback((pending = pendingNavigationRef.current) => {
    if (!pending || pendingNavigationRef.current !== pending) return;
    const { action, path } = pending;
    pendingNavigationRef.current = null;
    if (navigationTimerRef.current) clearTimeout(navigationTimerRef.current);
    navigationTimerRef.current = null;
    closedByUserRef.current = true;
    releaseConnection();
    if (action === "back") router.back();
    else if (path) router.push(path as never);
  }, [releaseConnection, router]);

  const handleNavigationTool = useCallback(async (event: any) => {
    if (event.name !== "navigate_app") return;
    const callId = String(event.call_id || event.item_id || "");
    if (!callId || handledToolCallsRef.current.has(callId)) return;
    handledToolCallsRef.current.add(callId);

    let destination = "";
    try {
      const parsed = JSON.parse(String(event.arguments || "{}"));
      destination = String(parsed.destination || "");
    } catch { /* validated below */ }

    let resolution: AliraNavigationResolution;
    try {
      resolution = destination
        ? await resolveAliraNavigation(destination)
        : { success: false, destination: "", label: "that page", message: "I could not identify which page to open. Ask the patient to name the page again." };
    } catch {
      resolution = { success: false, destination, label: "that page", message: "I could not check that page right now. Ask the patient to try again." };
    }

    const channel = dataChannelRef.current;
    if (!channel || channel.readyState !== "open") return;
    channel.send(JSON.stringify({
      type: "conversation.item.create",
      item: {
        type: "function_call_output",
        call_id: callId,
        output: JSON.stringify({
          success: resolution.success,
          destination: resolution.destination,
          label: resolution.label,
          message: resolution.message,
        }),
      },
    }));

    if (resolution.success && (resolution.path || resolution.action)) {
      const pending: PendingNavigation = { ...resolution, originResponseId: event.response_id };
      pendingNavigationRef.current = pending;
      if (navigationTimerRef.current) clearTimeout(navigationTimerRef.current);
      navigationTimerRef.current = setTimeout(() => completeNavigation(pending), 9000);
      setPhase("thinking");
      channel.send(JSON.stringify({
        type: "response.create",
        response: {
          tool_choice: "none",
          instructions: `Confirm warmly in one very short sentence that you are opening ${resolution.label}. Do not ask another question.`,
        },
      }));
      return;
    }

    channel.send(JSON.stringify({
      type: "response.create",
      response: {
        tool_choice: "none",
        instructions: `Explain this in one or two short spoken sentences: ${resolution.message}`,
      },
    }));
  }, [completeNavigation]);

  const handleServerEvent = useCallback((message: any) => {
    let event: any;
    try { event = JSON.parse(String(message.data || "{}")); } catch { return; }

    if (event.type === "response.function_call_arguments.done") {
      void handleNavigationTool(event);
      return;
    }
    if (event.type === "input_audio_buffer.speech_started") {
      setLiveReply("");
      setPhase("listening");
      return;
    }
    if (event.type === "input_audio_buffer.speech_stopped") {
      setPhase("thinking");
      return;
    }
    if (event.type === "conversation.item.input_audio_transcription.completed") {
      addTurn("user", event.transcript, event.item_id);
      return;
    }
    if (event.type === "response.created") {
      const pending = pendingNavigationRef.current;
      const responseId = String(event.response?.id || event.response_id || "");
      if (pending && responseId && responseId !== pending.originResponseId && !pending.acknowledgementResponseId) {
        pending.acknowledgementResponseId = responseId;
      }
      setPhase("speaking");
      return;
    }
    if (event.type === "output_audio_buffer.started") {
      setPhase("speaking");
      return;
    }
    if (event.type === "response.output_audio_transcript.delta" || event.type === "response.audio_transcript.delta") {
      setLiveReply((current) => current + String(event.delta || ""));
      return;
    }
    if (event.type === "response.output_audio_transcript.done" || event.type === "response.audio_transcript.done") {
      addTurn("assistant", event.transcript, event.item_id || event.response_id);
      setLiveReply("");
      return;
    }
    if (event.type === "response.done") {
      const output = Array.isArray(event.response?.output) ? event.response.output : [];
      output.forEach((item: any) => {
        const content = Array.isArray(item?.content) ? item.content : [];
        content.forEach((part: any) => addTurn("assistant", part?.transcript || part?.text, item?.id));
      });
      setLiveReply("");
      const pending = pendingNavigationRef.current;
      const responseId = String(event.response?.id || event.response_id || "");
      if (pending && responseId === pending.acknowledgementResponseId) {
        pending.acknowledgementDone = true;
        if (pending.audioStopped) completeNavigation(pending);
        else setPhase("speaking");
      } else {
        setPhase(pending ? "thinking" : "listening");
      }
      return;
    }
    if (event.type === "output_audio_buffer.stopped") {
      const pending = pendingNavigationRef.current;
      const responseId = String(event.response_id || "");
      if (pending && (!responseId || responseId === pending.acknowledgementResponseId)) {
        pending.audioStopped = true;
        if (pending.acknowledgementDone) completeNavigation(pending);
      } else if (!pending) {
        setPhase("listening");
      }
      return;
    }
    if (event.type === "error") {
      setError("The live conversation had a connection problem. End the call and try again.");
      setPhase("error");
    }
  }, [addTurn, completeNavigation, handleNavigationTool]);

  const endCall = useCallback((message = "Call ended") => {
    closedByUserRef.current = true;
    releaseConnection();
    setLiveReply("");
    setPhase("ended");
    setError(message === "Call ended" ? "" : message);
  }, [releaseConnection]);

  const startCall = useCallback(async () => {
    const browser = globalThis as any;
    const PeerConnection = browser.RTCPeerConnection;
    const mediaDevices = browser.navigator?.mediaDevices;
    if (!PeerConnection || !mediaDevices?.getUserMedia) {
      setError("This browser does not support live voice calls. Please use a current version of Chrome, Edge, Firefox, or Safari.");
      setPhase("error");
      return;
    }

    releaseConnection();
    closedByUserRef.current = false;
    setError("");
    setTurns([]);
    setLiveReply("");
    setMuted(false);
    setPhase("connecting");

    try {
      const peer = new PeerConnection();
      peerRef.current = peer;
      const remoteAudio = browser.document.createElement("audio");
      remoteAudio.autoplay = true;
      remoteAudio.setAttribute("playsinline", "true");
      remoteAudioRef.current = remoteAudio;
      peer.ontrack = (event: any) => {
        remoteAudio.srcObject = event.streams[0];
        void remoteAudio.play().catch(() => setError("Tap the screen once if your browser has blocked Alira's audio."));
      };

      const stream = await mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      mediaStreamRef.current = stream;
      stream.getAudioTracks().forEach((track: any) => peer.addTrack(track, stream));

      const dataChannel = peer.createDataChannel("oai-events");
      dataChannelRef.current = dataChannel;
      dataChannel.addEventListener("message", handleServerEvent);
      dataChannel.addEventListener("open", () => {
        setPhase("speaking");
        dataChannel.send(JSON.stringify({
          type: "response.create",
          response: {
            instructions: "Greet the patient warmly in one short sentence, introduce yourself as Alira, then ask what they would like support with today.",
          },
        }));
      });
      dataChannel.addEventListener("close", () => {
        if (!closedByUserRef.current) {
          setError("The live call disconnected. You can start a new call.");
          setPhase("ended");
        }
      });

      peer.onconnectionstatechange = () => {
        if (peer.connectionState === "failed") {
          closedByUserRef.current = true;
          releaseConnection();
          setError("The live call could not stay connected. Please check your internet connection and try again.");
          setPhase("error");
        }
      };

      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      const response = await authedFetch("/api/realtime/session", {
        method: "POST",
        body: JSON.stringify({ sdp: offer.sdp }),
      });
      const answerSdp = await response.text();
      if (!response.ok) {
        let detail = "Alira could not start a live call. Please try again.";
        try { detail = JSON.parse(answerSdp).detail || detail; } catch { /* use fallback */ }
        throw new Error(detail);
      }
      await peer.setRemoteDescription({ type: "answer", sdp: answerSdp });
      callTimerRef.current = setTimeout(
        () => endCall("The 20-minute call limit was reached. You can start another call whenever you are ready."),
        MAX_CALL_MS,
      );
    } catch (caught) {
      closedByUserRef.current = true;
      releaseConnection();
      const message = caught instanceof Error ? caught.message : "Alira could not start a live call. Please try again.";
      setError(message.includes("Permission") || message.includes("NotAllowed")
        ? "Microphone access is needed. Allow it in your browser settings, then try again."
        : message);
      setPhase("error");
    }
  }, [endCall, handleServerEvent, releaseConnection]);

  const toggleMute = () => {
    setMuted((current) => {
      const next = !current;
      mediaStreamRef.current?.getAudioTracks()?.forEach((track: any) => { track.enabled = !next; });
      return next;
    });
  };

  const leaveScreen = () => {
    if (peerRef.current) endCall();
    router.back();
  };

  const active = ["connecting", "listening", "thinking", "speaking"].includes(phase);
  const status = phase === "connecting"
    ? "Connecting securely..."
    : phase === "listening"
      ? muted ? "Microphone muted" : "Listening - speak naturally"
      : phase === "thinking"
        ? "Alira is thinking..."
        : phase === "speaking"
          ? "Alira is speaking - you can interrupt at any time"
          : phase === "ended"
            ? "Call ended"
            : phase === "error"
              ? "Live call unavailable"
              : "Ready for a real-time conversation";

  return (
    <View style={[realtimeStyles.container, { paddingTop: insets.top }]}>
      <View style={realtimeStyles.header}>
        <Pressable onPress={leaveScreen} style={realtimeStyles.headerButton} accessibilityLabel="Close Alira call" testID="alira-call-back">
          <Ionicons name="close" size={26} color={colors.onSurface} />
        </Pressable>
        <View style={realtimeStyles.headerCopy}>
          <Text style={realtimeStyles.title}>Call Alira</Text>
          <Text style={realtimeStyles.subtitle}>Live AI recovery companion</Text>
        </View>
        <View style={realtimeStyles.livePill}>
          <View style={[realtimeStyles.liveDot, active && realtimeStyles.liveDotActive]} />
          <Text style={realtimeStyles.liveText}>{active ? "Live" : "Ready"}</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={realtimeStyles.content}>
        <View style={[realtimeStyles.avatar, phase === "speaking" && realtimeStyles.avatarSpeaking]}>
          <Ionicons name="heart" size={42} color="#FFFFFF" />
        </View>
        <Text style={realtimeStyles.aliraName}>Alira</Text>
        <Text style={realtimeStyles.status}>{status}</Text>
        <Text style={realtimeStyles.safety}>Alira is an AI recovery companion, not a therapist or emergency service. She cannot diagnose or replace your clinical team.</Text>

        <View style={realtimeStyles.liveHint}>
          <Ionicons name="sparkles-outline" size={20} color={colors.brandPrimary} />
          <Text style={realtimeStyles.liveHintText}>No recording or send button. Talk naturally, pause when you are done, and Alira will answer.</Text>
        </View>

        <View style={realtimeStyles.conversationCard}>
          {turns.length === 0 && !liveReply ? (
            <View style={realtimeStyles.emptyConversation}>
              <Ionicons name="chatbubbles-outline" size={30} color={colors.brandPrimary} />
              <Text style={realtimeStyles.emptyTitle}>{active ? "Alira will greet you in a moment" : "Start when you feel ready"}</Text>
              <Text style={realtimeStyles.emptyText}>Your conversation captions will appear here.</Text>
            </View>
          ) : (
            turns.map((turn) => (
              <View key={turn.id} style={[realtimeStyles.turn, turn.role === "user" ? realtimeStyles.userTurn : realtimeStyles.aliraTurn]}>
                <Text style={realtimeStyles.turnLabel}>{turn.role === "user" ? "You" : "Alira"}</Text>
                <Text style={realtimeStyles.turnText}>{turn.text}</Text>
              </View>
            ))
          )}
          {liveReply ? (
            <View style={[realtimeStyles.turn, realtimeStyles.aliraTurn]}>
              <Text style={realtimeStyles.turnLabel}>Alira</Text>
              <Text style={realtimeStyles.turnText}>{liveReply}</Text>
            </View>
          ) : null}
        </View>

        {error ? (
          <View style={realtimeStyles.errorCard}>
            <Ionicons name="alert-circle-outline" size={20} color={colors.error} />
            <Text style={realtimeStyles.errorText}>{error}</Text>
          </View>
        ) : null}

        {!active ? (
          <Pressable onPress={startCall} style={realtimeStyles.startButton} accessibilityLabel="Start live call with Alira" testID="alira-call-start">
            <Ionicons name="call" size={23} color="#FFFFFF" />
            <Text style={realtimeStyles.startButtonText}>{phase === "ended" || phase === "error" ? "Start a new call" : "Start live call"}</Text>
          </Pressable>
        ) : (
          <View style={realtimeStyles.callControls}>
            <View style={realtimeStyles.controlWithLabel}>
              <Pressable onPress={toggleMute} disabled={phase === "connecting"} style={[realtimeStyles.roundControl, muted && realtimeStyles.roundControlMuted]} accessibilityLabel={muted ? "Unmute microphone" : "Mute microphone"}>
                {phase === "connecting" ? <ActivityIndicator color={colors.brandPrimary} /> : <Ionicons name={muted ? "mic-off" : "mic"} size={28} color={muted ? colors.error : colors.brandPrimary} />}
              </Pressable>
              <Text style={realtimeStyles.controlLabel}>{muted ? "Unmute" : "Mute"}</Text>
            </View>
            <View style={realtimeStyles.controlWithLabel}>
              <Pressable onPress={() => endCall()} style={[realtimeStyles.roundControl, realtimeStyles.endControl]} accessibilityLabel="End call" testID="alira-call-end">
                <Ionicons name="call" size={28} color="#FFFFFF" />
              </Pressable>
              <Text style={realtimeStyles.controlLabel}>End</Text>
            </View>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const realtimeStyles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F6F9F6" },
  header: { minHeight: 72, flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider, backgroundColor: colors.surface },
  headerButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headerCopy: { flex: 1, alignItems: "center" },
  title: { fontSize: 19, fontWeight: "800", color: colors.onSurface },
  subtitle: { marginTop: 2, fontSize: 11, color: colors.onSurfaceTertiary },
  livePill: { minWidth: 60, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6 },
  liveDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: colors.border },
  liveDotActive: { backgroundColor: colors.success },
  liveText: { fontSize: 12, fontWeight: "800", color: colors.brandPrimary },
  content: { flexGrow: 1, alignItems: "center", padding: spacing.lg, paddingBottom: spacing.xxl },
  avatar: { width: 92, height: 92, borderRadius: 46, alignItems: "center", justifyContent: "center", backgroundColor: "#4C8A5A", marginTop: spacing.md, borderWidth: 6, borderColor: "#E4F0E6" },
  avatarSpeaking: { borderColor: "#BFD9C4" },
  aliraName: { marginTop: spacing.sm, fontSize: 26, fontWeight: "900", color: colors.onSurface },
  status: { marginTop: 4, minHeight: 22, fontSize: 15, lineHeight: 21, fontWeight: "700", textAlign: "center", color: colors.brandPrimary },
  safety: { maxWidth: 590, marginTop: spacing.sm, fontSize: 12, lineHeight: 18, textAlign: "center", color: colors.onSurfaceTertiary },
  liveHint: { width: "100%", maxWidth: 650, flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.lg, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, backgroundColor: "#E8F2EA" },
  liveHintText: { flex: 1, fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary },
  conversationCard: { width: "100%", maxWidth: 650, minHeight: 210, marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, gap: spacing.sm },
  emptyConversation: { flex: 1, minHeight: 175, alignItems: "center", justifyContent: "center", padding: spacing.lg },
  emptyTitle: { marginTop: spacing.sm, fontSize: 17, lineHeight: 23, fontWeight: "800", color: colors.onSurface, textAlign: "center" },
  emptyText: { marginTop: 4, fontSize: 13, color: colors.onSurfaceTertiary, textAlign: "center" },
  turn: { maxWidth: "88%", paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm },
  userTurn: { alignSelf: "flex-end", backgroundColor: "#E7F1E9" },
  aliraTurn: { alignSelf: "flex-start", backgroundColor: "#F1F3F1" },
  turnLabel: { fontSize: 10, fontWeight: "900", textTransform: "uppercase", color: colors.brandPrimary },
  turnText: { marginTop: 3, fontSize: 16, lineHeight: 23, color: colors.onSurface },
  errorCard: { width: "100%", maxWidth: 650, flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: "#FFF1EF" },
  errorText: { flex: 1, fontSize: 13, lineHeight: 19, color: colors.error },
  startButton: { width: "100%", maxWidth: 420, minHeight: 60, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, marginTop: spacing.xl, paddingHorizontal: spacing.lg, borderRadius: radius.md, backgroundColor: colors.brandPrimary },
  startButtonText: { fontSize: 18, fontWeight: "900", color: "#FFFFFF" },
  callControls: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 50, marginTop: spacing.xl },
  controlWithLabel: { alignItems: "center" },
  roundControl: { width: 66, height: 66, borderRadius: 33, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  roundControlMuted: { backgroundColor: "#FFF1EF", borderColor: "#F2C8C2" },
  endControl: { borderColor: colors.error, backgroundColor: colors.error, transform: [{ rotate: "135deg" }] },
  controlLabel: { marginTop: 7, fontSize: 13, fontWeight: "700", color: colors.onSurfaceSecondary },
});

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
