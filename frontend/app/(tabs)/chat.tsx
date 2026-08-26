import { useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { createAudioPlayer } from "expo-audio";
import { LinearGradient } from "expo-linear-gradient";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import Svg, { Path } from "react-native-svg";
import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";
import TypingIndicator from "@/src/components/TypingIndicator";
import { API_BASE as BASE } from "@/src/config";

type Turn = { role: "user" | "assistant"; text: string; ts: string };

const SESSION_KEY = "alira_session_id";
const LOCAL_GREETING =
  "Hi there! I'm Alira, your AI recovery companion. I'm here to support you - body, mind, and progress. How are you feeling today?";

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
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  const playAliraVoice = async (text: string) => {
    try {
      const r = await fetch(`${BASE}/api/tts/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      if (!r.ok) return;
      const d = await r.json();
      const player = createAudioPlayer({ uri: `data:audio/mpeg;base64,${d.audio_b64}` });
      player.play();
    } catch {
      /* voice is optional */
    }
  };

  useEffect(() => {
    (async () => {
      const storedId = await storage.getItem<string>(SESSION_KEY, "");
      const id = storedId || genId();
      if (!storedId) {
        await storage.setItem(SESSION_KEY, id);
      }
      setSessionId(id);
      try {
        const r = await fetch(`${BASE}/api/chat/history?session_id=${encodeURIComponent(id)}`);
        const d = await r.json();
        const existing: Turn[] = d.turns || [];
        if (existing.length > 0) {
          setTurns(existing);
        } else {
          const pr = await fetch(`${BASE}/api/chat/proactive`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: id, text: "" }),
          });
          const pd = await pr.json();
          const greeting = pd.text || LOCAL_GREETING;
          setTurns([{ role: "assistant", text: greeting, ts: new Date().toISOString() }]);
          if (Platform.OS !== "web") playAliraVoice(greeting);
        }
      } catch {
        setTurns([{ role: "assistant", text: LOCAL_GREETING, ts: new Date().toISOString() }]);
        if (Platform.OS !== "web") playAliraVoice(LOCAL_GREETING);
      }
    })();
  }, []);

  const send = async () => {
    const txt = input.trim();
    if (!txt || !sessionId || sending) return;
    Haptics.selectionAsync();
    const now = new Date().toISOString();
    setTurns((t) => [...t, { role: "user", text: txt, ts: now }]);
    setInput("");
    setSending(true);
    try {
      const r = await fetch(`${BASE}/api/chat/message`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, text: txt }),
      });
      if (!r.ok) throw new Error("chat fail");
      const d = await r.json();
      setTurns((t) => [...t, { role: "assistant", text: d.text, ts: new Date().toISOString() }]);
    } catch {
      setTurns((t) => [
        ...t,
        {
          role: "assistant",
          text: "I'm having trouble reaching the server. Let's try again in a moment.",
          ts: new Date().toISOString(),
        },
      ]);
    } finally {
      setSending(false);
      setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 80);
    }
  };

  const actions = [
    { icon: "analytics-outline" as const, text: "Check My Progress" },
    { icon: "walk-outline" as const, text: "Start Guided Exercise" },
    { icon: "heart" as const, text: "Pain Check-in" },
    { icon: "people" as const, text: "Message Therapist" },
  ];

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <LinearGradient colors={["#5B966B", colors.brandPrimary]} style={styles.headerAvatar}>
          <Ionicons name="heart" size={30} color="#fff" />
        </LinearGradient>
        <View style={styles.headerCopy}>
          <Text style={styles.headerTitle}>Alira</Text>
          <Text style={styles.headerSub}>Your recovery companion - always here</Text>
        </View>
        <Pressable style={styles.sparkleButton} accessibilityLabel="Alira insights">
          <Ionicons name="sparkles" size={24} color={colors.brandPrimary} />
        </Pressable>
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 88 : 0}
        style={styles.keyboard}
      >
        <ScrollView
          ref={scrollRef}
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.hero}>
            <Svg height="92" width="100%" viewBox="0 0 360 92" style={styles.wave}>
              <Path
                d="M0 46 C42 20 78 68 120 40 C156 16 190 76 230 44 C272 10 308 72 360 40"
                stroke="#C9DEC9"
                strokeWidth="18"
                strokeLinecap="round"
                fill="none"
                opacity="0.45"
              />
              <Path
                d="M0 46 C42 20 78 68 120 40 C156 16 190 76 230 44 C272 10 308 72 360 40"
                stroke="#7EAF82"
                strokeWidth="2"
                strokeLinecap="round"
                fill="none"
                opacity="0.75"
              />
            </Svg>
            <View style={styles.orbOuter}>
              <LinearGradient colors={["#F6FBF2", "#B8D8B3", "#EAF5DE"]} style={styles.orb}>
                <Svg height="52" width="86" viewBox="0 0 86 52">
                  <Path
                    d="M3 29 C18 8 32 47 47 24 C59 6 69 38 83 20"
                    stroke="#4A7856"
                    strokeWidth="4"
                    strokeLinecap="round"
                    fill="none"
                  />
                  <Path
                    d="M5 32 C22 15 32 49 50 28 C62 13 70 41 84 25"
                    stroke="#FFFFFF"
                    strokeWidth="2"
                    strokeLinecap="round"
                    fill="none"
                    opacity="0.75"
                  />
                </Svg>
              </LinearGradient>
            </View>
            <View style={styles.listeningPill}>
              <View style={styles.listeningDot} />
              <Text style={styles.listeningText}>Alira is listening</Text>
            </View>
          </View>

          {turns.length === 0 ? (
            <ActivityIndicator color={colors.brandPrimary} style={styles.loading} />
          ) : (
            turns.map((item, index) => (
              <View key={`${item.ts}-${index}`} style={[styles.messageRow, item.role === "user" && styles.userRow]}>
                {item.role === "assistant" && (
                  <LinearGradient colors={["#5B966B", colors.brandPrimary]} style={styles.messageAvatar}>
                    <Ionicons name="heart" size={18} color="#fff" />
                  </LinearGradient>
                )}
                <View style={[styles.bubble, item.role === "user" ? styles.userBubble : styles.assistantBubble]}>
                  <Text style={styles.bubbleText}>{item.text}</Text>
                  <Text style={[styles.timeText, item.role === "user" && styles.userTime]}>
                    {formatTime(item.ts)}
                    {item.role === "user" ? "  ✓✓" : ""}
                  </Text>
                </View>
              </View>
            ))
          )}

          {sending && (
            <View style={styles.typingWrap}>
              <TypingIndicator />
            </View>
          )}

          <View style={styles.actionRow}>
            {actions.map((action) => (
              <Pressable key={action.text} style={styles.actionChip} accessibilityLabel={action.text}>
                <View style={styles.actionIconWrap}>
                  <Ionicons name={action.icon} size={21} color={colors.brandPrimary} />
                </View>
                <Text
                  style={styles.actionText}
                  numberOfLines={2}
                  adjustsFontSizeToFit
                  minimumFontScale={0.82}
                >
                  {action.text}
                </Text>
              </Pressable>
            ))}
          </View>
        </ScrollView>

        <View style={[styles.inputWrap, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
          <Pressable style={styles.micButton}>
            <Ionicons name="mic" size={26} color={colors.brandPrimary} />
          </Pressable>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="Message Alira..."
            placeholderTextColor="#A5AAA6"
            style={styles.input}
            multiline
            maxLength={500}
            testID="chat-input"
          />
          <Pressable
            onPress={send}
            disabled={sending || !input.trim()}
            style={[styles.sendBtn, (sending || !input.trim()) && styles.sendBtnDisabled]}
            testID="chat-send"
          >
            <Ionicons name="send" size={22} color="#fff" />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FBFCFA" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
    backgroundColor: "#FBFCFA",
  },
  headerAvatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    alignItems: "center",
    justifyContent: "center",
  },
  headerCopy: { flex: 1 },
  headerTitle: { fontSize: 34, lineHeight: 38, fontWeight: "900", color: colors.onSurface },
  headerSub: { marginTop: 2, fontSize: 17, lineHeight: 22, color: colors.brandPrimary, fontWeight: "600" },
  sparkleButton: {
    width: 56,
    height: 56,
    borderRadius: radius.md,
    backgroundColor: "#F2F6F1",
    alignItems: "center",
    justifyContent: "center",
  },
  keyboard: { flex: 1 },
  scroll: { flex: 1, backgroundColor: "#FBFCFA" },
  scrollContent: { paddingBottom: spacing.md },
  hero: {
    minHeight: 260,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
    backgroundColor: "#FBFCFA",
  },
  wave: { position: "absolute", top: 78 },
  orbOuter: {
    width: 176,
    height: 176,
    borderRadius: 88,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "rgba(255,255,255,0.78)",
    borderWidth: 1,
    borderColor: "rgba(74,120,86,0.12)",
    shadowColor: colors.brandPrimary,
    shadowOpacity: 0.16,
    shadowRadius: 28,
    shadowOffset: { width: 0, height: 8 },
    elevation: 3,
  },
  orb: {
    width: 130,
    height: 130,
    borderRadius: 65,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 4,
    borderColor: "rgba(255,255,255,0.72)",
  },
  listeningPill: {
    marginTop: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.xs,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    borderRadius: radius.pill,
    backgroundColor: "#EEF4EC",
  },
  listeningDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: "#55A466" },
  listeningText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 14 },
  loading: { marginVertical: spacing.xl },
  messageRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    marginBottom: spacing.sm,
  },
  userRow: { justifyContent: "flex-end" },
  messageAvatar: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: "center",
    justifyContent: "center",
    marginTop: 2,
  },
  bubble: {
    maxWidth: "76%",
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xs,
    shadowColor: "#1C201D",
    shadowOpacity: 0.08,
    shadowRadius: 10,
    shadowOffset: { width: 0, height: 4 },
    elevation: 2,
  },
  assistantBubble: {
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#E2E7E0",
    borderTopLeftRadius: radius.sm,
  },
  userBubble: {
    alignSelf: "flex-end",
    backgroundColor: "#E5EEE4",
    borderTopRightRadius: radius.sm,
  },
  bubbleText: { fontSize: 17, lineHeight: 24, color: colors.onSurface },
  timeText: { marginTop: 5, fontSize: 12, color: "#838A84" },
  userTime: { alignSelf: "flex-end", color: colors.brandPrimary },
  typingWrap: { paddingLeft: spacing.lg, marginBottom: spacing.sm },
  actionRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    justifyContent: "space-between",
    rowGap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xl,
  },
  actionChip: {
    width: "48%",
    minHeight: 64,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: "#DCE3DA",
    backgroundColor: "#FFFFFF",
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.sm,
    shadowColor: "#1C201D",
    shadowOpacity: 0.05,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 3 },
    elevation: 1,
  },
  actionIconWrap: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: "#EEF4EC",
    alignItems: "center",
    justifyContent: "center",
  },
  actionText: {
    flex: 1,
    fontSize: 14,
    lineHeight: 17,
    color: colors.onSurface,
    fontWeight: "700",
  },
  inputWrap: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    backgroundColor: "#FBFCFA",
    borderTopWidth: 1,
    borderTopColor: "rgba(227,230,225,0.8)",
  },
  micButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: "#FFFFFF",
    borderWidth: 1,
    borderColor: "#DCE3DA",
    alignItems: "center",
    justifyContent: "center",
  },
  input: {
    flex: 1,
    minHeight: 48,
    maxHeight: 96,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: "#DCE3DA",
    backgroundColor: "#FFFFFF",
    paddingHorizontal: spacing.md,
    paddingVertical: Platform.OS === "ios" ? 12 : 8,
    fontSize: 17,
    color: colors.onSurface,
  },
  sendBtn: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  sendBtnDisabled: { opacity: 0.55 },
});
