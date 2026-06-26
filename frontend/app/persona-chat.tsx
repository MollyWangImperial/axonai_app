import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, FlatList, ActivityIndicator, KeyboardAvoidingView, Platform, TextInput, Image } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { storage } from "@/src/utils/storage";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

type Turn = { role: "user" | "assistant"; text: string; ts: string };
type Persona = { id: string; name: string; photo?: string; title?: string; bio?: string; months_since_stroke?: number; ai?: boolean };

export default function PersonaChatScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { persona_id } = useLocalSearchParams<{ persona_id: string }>();
  const [persona, setPersona] = useState<Persona | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList<Turn>>(null);

  useEffect(() => {
    (async () => {
      if (!persona_id) return;
      const sessKey = `persona_session_${persona_id}`;
      let id = await storage.getItem(sessKey);
      if (!id) {
        id = "s_" + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
        await storage.setItem(sessKey, id);
      }
      setSessionId(id);
      try {
        const r = await fetch(`${BASE}/api/personas/chat/history?persona_id=${encodeURIComponent(persona_id)}&session_id=${encodeURIComponent(id)}`);
        const d = await r.json();
        setPersona(d.persona);
        const existing: Turn[] = d.turns || [];
        if (existing.length > 0) {
          setTurns(existing);
        } else {
          const op = await fetch(`${BASE}/api/personas/${encodeURIComponent(persona_id)}/opener`);
          const od = await op.json();
          setTurns([{ role: "assistant", text: od.text, ts: new Date().toISOString() }]);
        }
      } catch {/* */}
    })();
  }, [persona_id]);

  const send = async () => {
    const txt = input.trim();
    if (!txt || !sessionId || !persona_id || sending) return;
    Haptics.selectionAsync();
    const now = new Date().toISOString();
    setTurns((t) => [...t, { role: "user", text: txt, ts: now }]);
    setInput("");
    setSending(true);
    try {
      const r = await fetch(`${BASE}/api/personas/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ persona_id, session_id: sessionId, text: txt }),
      });
      if (!r.ok) throw new Error("chat fail");
      const d = await r.json();
      setTurns((t) => [...t, { role: "assistant", text: d.text, ts: new Date().toISOString() }]);
    } catch {
      setTurns((t) => [...t, { role: "assistant", text: "Sorry, I can't respond right now. Please try again shortly.", ts: new Date().toISOString() }]);
    } finally {
      setSending(false);
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 80);
    }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="persona-back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        {persona?.photo ? (
          <Image source={{ uri: persona.photo }} style={styles.avatar} />
        ) : (
          <View style={[styles.avatar, { backgroundColor: colors.brandTertiary }]} />
        )}
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
            <Text style={styles.headerTitle}>{persona?.name?.replace(" (AI Therapist)", "") || "…"}</Text>
            {persona?.ai && (
              <View style={styles.aiBadge}>
                <Ionicons name="sparkles" size={10} color={colors.onBrandSecondary} />
                <Text style={styles.aiText}>AI</Text>
              </View>
            )}
          </View>
          <Text style={styles.headerSub} numberOfLines={1}>
            {persona?.title || (persona?.months_since_stroke ? `${persona.months_since_stroke} months in recovery` : "Recovery companion")}
          </Text>
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

      <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} keyboardVerticalOffset={Platform.OS === "ios" ? 80 : 0}>
        <View style={[styles.inputBar, { paddingBottom: Math.max(insets.bottom, spacing.sm) }]}>
          <TextInput
            value={input}
            onChangeText={setInput}
            placeholder={`Message ${persona?.name?.split(" ")[0] || "…"}`}
            placeholderTextColor={colors.onSurfaceTertiary}
            style={styles.input}
            multiline
            maxLength={500}
            testID="persona-chat-input"
          />
          <Pressable onPress={send} disabled={sending || !input.trim()} style={styles.sendBtn} testID="persona-chat-send">
            {sending ? <ActivityIndicator color="#fff" /> : <Ionicons name="arrow-up" size={20} color="#fff" />}
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 36, height: 36, alignItems: "center", justifyContent: "center" },
  avatar: { width: 40, height: 40, borderRadius: 20 },
  headerTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  headerSub: { fontSize: 12, color: colors.onSurfaceTertiary },
  aiBadge: { flexDirection: "row", alignItems: "center", gap: 2, backgroundColor: colors.brandSecondary, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 },
  aiText: { color: colors.onBrandSecondary, fontSize: 9, fontWeight: "800", letterSpacing: 0.5 },
  bubble: { maxWidth: "82%", padding: spacing.sm + 2, borderRadius: radius.lg },
  user: { alignSelf: "flex-end", backgroundColor: colors.brandPrimary, borderBottomRightRadius: 4 },
  assistant: { alignSelf: "flex-start", backgroundColor: colors.surfaceSecondary, borderBottomLeftRadius: 4 },
  bubbleText: { fontSize: 15, lineHeight: 22 },
  inputBar: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, padding: spacing.sm, borderTopWidth: 1, borderTopColor: colors.divider, backgroundColor: colors.surface },
  input: { flex: 1, fontSize: 15, color: colors.onSurface, maxHeight: 100, paddingHorizontal: spacing.sm, paddingVertical: 10, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, minHeight: 44 },
  sendBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
});
