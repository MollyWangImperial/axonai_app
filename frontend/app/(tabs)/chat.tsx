import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, KeyboardAvoidingView, Platform, TextInput } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { storage } from "@/src/utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

type Turn = { role: "user" | "assistant"; text: string; ts: string };

const SESSION_KEY = "hope_session_id";

function genId() {
  return "s_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
}

export default function ChatScreen() {
  const insets = useSafeAreaInsets();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList<Turn>>(null);

  // Initialize session + proactive greeting
  useEffect(() => {
    (async () => {
      let id = await storage.getItem(SESSION_KEY);
      if (!id) {
        id = genId();
        await storage.setItem(SESSION_KEY, id);
      }
      setSessionId(id);
      // Load past turns
      try {
        const r = await fetch(`${BASE}/api/chat/history?session_id=${encodeURIComponent(id)}`);
        const d = await r.json();
        const existing: Turn[] = d.turns || [];
        if (existing.length > 0) {
          setTurns(existing);
        } else {
          // Spontaneous opener
          const pr = await fetch(`${BASE}/api/chat/proactive`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: id, text: "" }),
          });
          const pd = await pr.json();
          setTurns([{ role: "assistant", text: pd.text, ts: new Date().toISOString() }]);
        }
      } catch {/* */}
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
      setTurns((t) => [...t, { role: "assistant", text: "I'm having trouble reaching the server. Let's try again in a moment.", ts: new Date().toISOString() }]);
    } finally {
      setSending(false);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 80);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <View style={styles.avatar}><Ionicons name="heart" size={20} color="#fff" /></View>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Hope</Text>
          <Text style={styles.headerSub}>Your recovery companion · always here</Text>
        </View>
      </View>

      <FlatList
        ref={listRef}
        data={turns}
        keyExtractor={(_, i) => String(i)}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: 32, gap: spacing.sm }}
        renderItem={({ item }) => (
          <View style={[styles.bubble, item.role === "user" ? styles.user : styles.assistant]}>
            <Text style={[styles.bubbleText, item.role === "user" ? { color: "#fff" } : { color: colors.onSurface }]}>
              {item.text}
            </Text>
          </View>
        )}
        ListEmptyComponent={<ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />}
      />

      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        keyboardVerticalOffset={Platform.OS === "ios" ? 80 : 0}
      >
        <View style={[styles.inputBar, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder="Tell Hope how you're feeling…"
            placeholderTextColor={colors.onSurfaceTertiary}
            style={styles.input}
            multiline
            maxLength={500}
            testID="chat-input"
          />
          <Pressable onPress={send} disabled={sending || !input.trim()} style={styles.sendBtn} testID="chat-send">
            {sending ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Ionicons name="arrow-up" size={20} color="#fff" />
            )}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  avatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  headerSub: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
  bubble: { maxWidth: "82%", padding: spacing.sm + 2, borderRadius: radius.lg },
  user: { alignSelf: "flex-end", backgroundColor: colors.brandPrimary, borderBottomRightRadius: 4 },
  assistant: { alignSelf: "flex-start", backgroundColor: colors.surfaceSecondary, borderBottomLeftRadius: 4 },
  bubbleText: { fontSize: 15, lineHeight: 22 },
  inputBar: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, padding: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider, backgroundColor: colors.surface },
  input: { flex: 1, fontSize: 15, color: colors.onSurface, maxHeight: 100, paddingHorizontal: spacing.sm, paddingVertical: 10, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, minHeight: 44 },
  sendBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
});
