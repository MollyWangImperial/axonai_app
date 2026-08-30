import { useEffect, useRef, useState } from "react";
import { ActivityIndicator, Alert, Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from "react-native";
import { createAudioPlayer } from "expo-audio";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";
import TypingIndicator from "@/src/components/TypingIndicator";
import { API_BASE as BASE } from "@/src/config";
import { authedFetch } from "@/src/auth";
import { fetchHistory } from "@/src/api";
import { useDisplayPreferences } from "@/src/displayPreferences";
import AliraLivingBackground from "@/src/components/AliraLivingBackground";
import { resolveAliraNavigation } from "@/src/aliraNavigation";

type Turn = { role: "user" | "assistant"; text: string; ts: string };

const SESSION_KEY = "alira_session_id";
const LOCAL_GREETING = "Hi there! I'm Alira, your recovery companion. I'm here to support you - body, mind, and progress. How are you feeling today?";
const companionImage = require("@/assets/images/alira-companion.png");

function genId() {
  return "s_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

function formatTime(ts: string) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function ChatScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { palette, preferences } = useDisplayPreferences();
  const { width } = useWindowDimensions();
  const { prompt } = useLocalSearchParams<{ prompt?: string }>();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState(prompt || "");
  const [sending, setSending] = useState(false);
  const [openingAction, setOpeningAction] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const scrollRef = useRef<ScrollView>(null);
  const inputRef = useRef<TextInput>(null);
  const wide = width >= 760;

  const playAliraVoice = async (text: string) => {
    try {
      const response = await fetch(`${BASE}/api/tts/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!response.ok) return;
      const audio = await response.json();
      createAudioPlayer({ uri: `data:audio/mpeg;base64,${audio.audio_b64}` }).play();
    } catch {
      /* Voice is a helpful enhancement, not a blocker for chat. */
    }
  };

  const openAliraDestination = async (destination: string) => {
    setOpeningAction("navigation");
    try {
      const resolution = await resolveAliraNavigation(destination);
      if (!resolution.success) {
        Alert.alert("Page unavailable", resolution.message);
        return;
      }
      if (resolution.action === "back") {
        router.back();
      } else if (resolution.path) {
        router.push(resolution.path as never);
      }
    } finally {
      setOpeningAction(null);
    }
  };

  const downloadChatHistory = async () => {
    if (!turns.length || downloading) return;
    if (Platform.OS !== "web" || typeof document === "undefined") {
      Alert.alert("Open Rehyn in a browser", "Chat-history downloads are currently available from the web version of Rehyn.");
      return;
    }
    setDownloading(true);
    try {
      const generatedAt = new Date();
      const transcript = [
        "Rehyn - Alira chat history",
        `Downloaded: ${generatedAt.toLocaleString()}`,
        "",
        ...turns.flatMap((turn) => [
          `${turn.role === "user" ? "You" : "Alira"} (${new Date(turn.ts).toLocaleString()}):`,
          turn.text,
          "",
        ]),
      ].join("\n");
      const blob = new Blob([transcript], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `rehyn-alira-chat-${generatedAt.toISOString().slice(0, 10)}.txt`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch {
      Alert.alert("Download unavailable", "Your chat history could not be prepared. Please try again.");
    } finally {
      setDownloading(false);
    }
  };

  useEffect(() => {
    (async () => {
      const storedId = await storage.getItem<string>(SESSION_KEY, "");
      const id = storedId || genId();
      if (!storedId) await storage.setItem(SESSION_KEY, id);
      setSessionId(id);
      try {
        const response = await authedFetch(`/api/chat/history?session_id=${encodeURIComponent(id)}`);
        const data = await response.json();
        const existing: Turn[] = data.turns || [];
        if (existing.length > 0) {
          setTurns(existing);
        } else {
          const proactive = await authedFetch("/api/chat/proactive", {
            method: "POST",
            body: JSON.stringify({ session_id: id, text: "" }),
          });
          const proactiveData = await proactive.json();
          const greeting = proactiveData.text || LOCAL_GREETING;
          setTurns([{ role: "assistant", text: greeting, ts: new Date().toISOString() }]);
        }
      } catch {
        setTurns([{ role: "assistant", text: LOCAL_GREETING, ts: new Date().toISOString() }]);
      }
    })();
  }, []);

  useEffect(() => {
    if (prompt) setInput(prompt);
  }, [prompt]);

  const sendMessage = async (message: string, speakReply = false) => {
    const text = message.trim();
    if (!text || !sessionId || sending) return;
    Haptics.selectionAsync();
    setTurns((current) => [...current, { role: "user", text, ts: new Date().toISOString() }]);
    setInput("");
    setSending(true);
    try {
      const response = await authedFetch("/api/chat/message", {
        method: "POST",
        body: JSON.stringify({ session_id: sessionId, text }),
      });
      if (!response.ok) throw new Error("chat fail");
      const data = await response.json();
      setTurns((current) => [...current, { role: "assistant", text: data.text, ts: new Date().toISOString() }]);
      if (speakReply) void playAliraVoice(data.text);
      if (data.navigation_destination) {
        await openAliraDestination(String(data.navigation_destination));
      }
    } catch {
      setTurns((current) => [...current, { role: "assistant", text: "I'm having trouble reaching the server. Let's try again in a moment.", ts: new Date().toISOString() }]);
    } finally {
      setSending(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
    }
  };

  const send = async () => sendMessage(input);

  const startGuidedExercise = async () => {
    setOpeningAction("exercise");
    try {
      const history = await fetchHistory();
      const assessment = history.find((item) => item.rehab_plan.length > 0 && (item.clinical_review_gate?.rehab_access ?? "allowed") === "allowed");
      if (assessment) {
        router.push({ pathname: "/rehab-plan", params: { id: assessment.id } });
        return;
      }
      if (history[0]) {
        router.push({ pathname: "/results", params: { id: history[0].id } });
        return;
      }
      router.push({ pathname: "/session-check" as never, params: { target: "assessment", mode: "initial" } });
    } catch {
      router.push("/journey");
    } finally {
      setOpeningAction(null);
    }
  };

  const startPrompt = (value: string) => {
    setInput(value);
    setTimeout(() => inputRef.current?.focus(), 80);
  };

  const conversationTurns = turns.length === 1 && turns[0]?.role === "assistant" ? [] : turns;
  const actions = [
    { id: "progress", icon: "trending-up-outline" as const, text: "Check My Progress", tone: preferences.darkMode ? palette.soft : "#EFF6F4", onPress: () => router.push("/progress") },
    { id: "exercise", icon: "walk-outline" as const, text: "Start Guided Exercise", tone: preferences.darkMode ? palette.soft : "#F1F4EC", onPress: () => void startGuidedExercise() },
    { id: "pain", icon: "heart" as const, text: "Pain Check-in", tone: preferences.darkMode ? palette.soft : "#F5F0FA", onPress: () => void sendMessage("Please guide me through a gentle pain check-in. Ask me one short question at a time, beginning with where I feel pain and how strong it is from zero to ten.", true) },
    { id: "reflect", icon: "book-outline" as const, text: "Reflect on Today", tone: preferences.darkMode ? palette.soft : "#FAF3EA", onPress: () => void sendMessage("Please guide me through a short reflection on today's recovery. Ask me one encouraging question at a time and help me notice one small win.", true) },
  ];

  return (
    <View style={[styles.container, { paddingTop: insets.top, backgroundColor: palette.page }]}>
      <AliraLivingBackground darkMode={preferences.darkMode} engaged={sending || conversationTurns.length > 0} />
      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} keyboardVerticalOffset={Platform.OS === "ios" ? 84 : 0} style={styles.keyboard}>
        <ScrollView ref={scrollRef} contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
          <View style={styles.page}>
            <View style={[styles.header, { borderBottomColor: palette.border }]}>
              <View style={styles.headerAvatar}><Ionicons name="heart" size={25} color="#FFFFFF" /></View>
              <View style={styles.headerCopy}>
                <Text style={[styles.headerTitle, { color: palette.text }]}>Alira</Text>
                <Text style={styles.headerSub}>Your recovery companion</Text>
              </View>
              <View style={styles.headerActions}>
                <Pressable testID="alira-download-chat" onPress={() => void downloadChatHistory()} disabled={!turns.length || downloading} style={[styles.sparkleButton, { backgroundColor: palette.soft }, (!turns.length || downloading) && styles.headerActionDisabled]} accessibilityLabel="Download chat history">
                  {downloading ? <ActivityIndicator color={palette.brand} /> : <Ionicons name="download-outline" size={22} color={palette.brand} />}
                </Pressable>
                <Pressable onPress={() => startPrompt("What should I focus on today?")} style={[styles.sparkleButton, { backgroundColor: palette.soft }]} accessibilityLabel="Ask Alira for today's focus">
                  <Ionicons name="sparkles" size={22} color={palette.brand} />
                </Pressable>
              </View>
            </View>

            <View style={[styles.hero, wide && styles.heroWide]}>
              <View style={styles.heroCopy}>
                <Text style={[styles.heroTitle, { color: palette.text }]}>Hi, I’m Alira.{"\n"}I’m here for you.</Text>
                <Text style={[styles.heroSub, { color: palette.muted }]}>We’ll take this recovery journey one step at a time, together.</Text>
              </View>
              <Image source={companionImage} resizeMode="contain" style={styles.companionImage} />
            </View>

            <View style={[styles.callCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <View style={[styles.callIcon, { backgroundColor: palette.soft }]}><Ionicons name="call" size={24} color={palette.brand} /></View>
              <View style={styles.callCopy}>
                <Text style={[styles.callTitle, { color: palette.text }]}>Talk to Alira now</Text>
                <Text style={[styles.callSub, { color: palette.muted }]}>Speak naturally and hear Alira reply</Text>
              </View>
              <Pressable testID="alira-call" onPress={() => router.push("/alira-call" as never)} style={styles.callButton}>
                <Ionicons name="call" size={19} color="#FFFFFF" />
                <Text style={styles.callButtonText}>Call Alira</Text>
              </Pressable>
            </View>

            <View style={[styles.actionGrid, wide && styles.actionGridWide]}>
              {actions.map((action) => (
                <Pressable key={action.text} testID={`alira-action-${action.id}`} disabled={sending || (["pain", "reflect"].includes(action.id) && !sessionId)} onPress={action.onPress} style={[styles.actionCard, wide && styles.actionCardWide, { backgroundColor: action.tone }, (sending || (["pain", "reflect"].includes(action.id) && !sessionId)) && { opacity: 0.6 }]} accessibilityLabel={action.text}>
                  <View style={styles.actionIcon}>{openingAction === action.id ? <ActivityIndicator color={colors.brandPrimary} /> : <Ionicons name={action.icon} size={24} color={colors.brandPrimary} />}</View>
                  <Text style={[styles.actionText, { color: palette.text }]}>{openingAction === action.id ? "Opening your plan..." : action.text}</Text>
                </Pressable>
              ))}
            </View>

            {turns.length === 0 && <ActivityIndicator color={colors.brandPrimary} style={styles.loading} />}
            {conversationTurns.length > 0 && <Text style={[styles.conversationTitle, { color: palette.text }]}>Your conversation</Text>}
            {conversationTurns.map((item, index) => (
              <View key={`${item.ts}-${index}`} style={[styles.messageRow, item.role === "user" && styles.userRow]}>
                {item.role === "assistant" && <View style={styles.messageAvatar}><Ionicons name="heart" size={17} color="#FFFFFF" /></View>}
                <View style={[styles.bubble, item.role === "user" ? styles.userBubble : styles.assistantBubble, { backgroundColor: item.role === "user" ? palette.soft : palette.surface, borderColor: palette.border }]}>
                  <Text style={[styles.bubbleText, { color: palette.text }]}>{item.text}</Text>
                  <Text style={[styles.timeText, { color: palette.muted }]}>{formatTime(item.ts)}</Text>
                </View>
              </View>
            ))}
            {sending && <View style={styles.typingWrap}><TypingIndicator /></View>}
          </View>
        </ScrollView>

        <View style={[styles.inputBar, { paddingBottom: Math.max(insets.bottom, spacing.sm), backgroundColor: palette.surface, borderTopColor: palette.border }]}>
          <View style={styles.inputInner}>
            <Pressable onPress={() => playAliraVoice("I'm listening. Tell me how I can help.")} style={[styles.micButton, { backgroundColor: palette.surface, borderColor: palette.border }]} accessibilityLabel="Hear Alira">
              <Ionicons name="mic" size={23} color={colors.brandPrimary} />
            </Pressable>
            <TextInput ref={inputRef} value={input} onChangeText={setInput} placeholder="Message Alira..." placeholderTextColor={palette.muted} style={[styles.input, { backgroundColor: palette.surface, borderColor: palette.border, color: palette.text }]} multiline maxLength={500} testID="chat-input" />
            <Pressable onPress={send} disabled={sending || !input.trim()} style={[styles.sendBtn, (sending || !input.trim()) && styles.sendBtnDisabled]} testID="chat-send">
              <Ionicons name="send" size={21} color="#FFFFFF" />
            </Pressable>
          </View>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FCFDFB", overflow: "hidden" },
  keyboard: { flex: 1, zIndex: 1 },
  scrollContent: { paddingBottom: spacing.xl },
  page: { width: "100%", maxWidth: 1080, alignSelf: "center", paddingHorizontal: spacing.md },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerAvatar: { width: 52, height: 52, borderRadius: 26, backgroundColor: "#4C8A5A", alignItems: "center", justifyContent: "center" },
  headerCopy: { flex: 1 },
  headerTitle: { fontSize: 28, lineHeight: 32, fontWeight: "900", color: "#123326" },
  headerSub: { marginTop: 1, fontSize: 14, color: colors.brandPrimary, fontWeight: "600" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  sparkleButton: { width: 46, height: 46, borderRadius: radius.md, backgroundColor: "#F1F5EF", alignItems: "center", justifyContent: "center" },
  headerActionDisabled: { opacity: 0.45 },
  hero: { paddingTop: spacing.xl, alignItems: "center" },
  heroWide: { minHeight: 280, flexDirection: "row", justifyContent: "space-between" },
  heroCopy: { width: "100%", maxWidth: 420, alignSelf: "flex-start", zIndex: 1 },
  heroTitle: { fontSize: 35, lineHeight: 42, fontWeight: "800", color: "#123326" },
  heroSub: { marginTop: spacing.md, maxWidth: 360, fontSize: 17, lineHeight: 25, color: colors.onSurfaceTertiary },
  companionImage: { width: "100%", maxWidth: 540, height: 210, marginTop: -12 },
  callCard: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderWidth: 1, borderColor: "#DCE3DA", borderRadius: radius.md, backgroundColor: "#FBFCF9" },
  callIcon: { width: 46, height: 46, borderRadius: 23, backgroundColor: "#EAF3E8", alignItems: "center", justifyContent: "center" },
  callCopy: { flex: 1 },
  callTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  callSub: { fontSize: 12, lineHeight: 17, color: colors.onSurfaceTertiary, marginTop: 2 },
  callButton: { minHeight: 46, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 7, borderRadius: radius.pill, backgroundColor: "#2F7540", paddingHorizontal: spacing.md },
  callButtonText: { color: "#FFFFFF", fontSize: 14, fontWeight: "800" },
  actionGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.md },
  actionGridWide: { flexWrap: "nowrap" },
  actionCard: { width: "48%", minHeight: 118, padding: spacing.md, borderWidth: 1, borderColor: "rgba(74,120,86,0.12)", borderRadius: radius.md, justifyContent: "space-between" },
  actionCardWide: { flex: 1, width: "auto" },
  actionIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: "rgba(255,255,255,0.78)", alignItems: "center", justifyContent: "center" },
  actionText: { fontSize: 15, lineHeight: 20, color: colors.onSurface, fontWeight: "800" },
  loading: { marginVertical: spacing.xl },
  conversationTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, marginTop: spacing.xl, marginBottom: spacing.md },
  messageRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, marginBottom: spacing.sm },
  userRow: { justifyContent: "flex-end" },
  messageAvatar: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  bubble: { maxWidth: "78%", borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  assistantBubble: { backgroundColor: "#FFFFFF", borderWidth: 1, borderColor: colors.border },
  userBubble: { backgroundColor: "#E5EEE4" },
  bubbleText: { fontSize: 15, lineHeight: 22, color: colors.onSurface },
  timeText: { marginTop: 4, fontSize: 11, color: colors.onSurfaceTertiary },
  typingWrap: { marginVertical: spacing.sm },
  inputBar: { borderTopWidth: 1, borderTopColor: colors.divider, backgroundColor: "rgba(252,253,251,0.98)", paddingHorizontal: spacing.md, paddingTop: spacing.sm },
  inputInner: { width: "100%", maxWidth: 1080, alignSelf: "center", flexDirection: "row", alignItems: "center", gap: spacing.sm },
  micButton: { width: 46, height: 46, borderRadius: 23, borderWidth: 1, borderColor: "#DCE3DA", backgroundColor: "#FFFFFF", alignItems: "center", justifyContent: "center" },
  input: { flex: 1, minHeight: 46, maxHeight: 92, borderRadius: radius.pill, borderWidth: 1, borderColor: "#DCE3DA", backgroundColor: "#FFFFFF", paddingHorizontal: spacing.md, paddingVertical: Platform.OS === "ios" ? 12 : 8, fontSize: 16, color: colors.onSurface },
  sendBtn: { width: 48, height: 48, borderRadius: 24, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  sendBtnDisabled: { opacity: 0.5 },
});
