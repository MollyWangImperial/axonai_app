import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Image, ActivityIndicator, Modal, TextInput, KeyboardAvoidingView, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { API_BASE as BASE } from "@/src/config";

type Story = { id: string; author: string; title: string; body: string; likes: number; months_since_stroke?: number; photo?: string };
type AIPatient = { id: string; name: string; age: number; months_since_stroke: number; bio: string; photo: string; stage: string; ai: boolean };

const FALLBACK_PATIENTS: AIPatient[] = [
  {
    id: "pt_001",
    name: "Marisol R.",
    age: 58,
    months_since_stroke: 14,
    stage: "moderate",
    ai: true,
    photo: "https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=400",
    bio: "Grandmother of three. Recently held her grandson with both arms after months of steady work.",
  },
  {
    id: "pt_002",
    name: "Daniel K.",
    age: 64,
    months_since_stroke: 8,
    stage: "moderate",
    ai: true,
    photo: "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=400",
    bio: "Retired engineer. Buttoning his own shirt was last month's victory.",
  },
  {
    id: "pt_003",
    name: "Asha N.",
    age: 46,
    months_since_stroke: 22,
    stage: "advanced",
    ai: true,
    photo: "https://images.unsplash.com/photo-1573497019940-1c28c88b4f3e?w=400",
    bio: "Former yoga teacher, now an advocate for slow recovery.",
  },
];

const FALLBACK_STORIES: Story[] = [
  {
    id: "st_001",
    author: "Marisol Reyes",
    months_since_stroke: 14,
    title: "I held my grandson again today",
    body: "My right hand could not grip a spoon at first. This morning I held my grandson with both arms. Recovery is slow, but it is real. Keep going.",
    likes: 312,
    photo: "https://images.unsplash.com/photo-1566616213894-2d4e1baee5d8?w=400&q=80",
  },
  {
    id: "st_002",
    author: "Daniel Okafor",
    months_since_stroke: 11,
    title: "Young stroke, still rebuilding",
    body: "The first six months were hard. Now I am typing this slowly with my affected hand, and that feels like a small revolution.",
    likes: 487,
    photo: "https://images.unsplash.com/photo-1533101585792-27f81a845550?w=400&q=80",
  },
  {
    id: "st_003",
    author: "Asha Narayan",
    months_since_stroke: 22,
    title: "The day my shoulder stopped hiking",
    body: "Last Tuesday, I reached for my chai and my shoulder stayed down. A tiny win. Enormous joy.",
    likes: 218,
    photo: "https://images.unsplash.com/photo-1592621385612-4d7129426394?w=400&q=80",
  },
];

export default function CommunityScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [stories, setStories] = useState<Story[]>(FALLBACK_STORIES);
  const [aiPatients, setAiPatients] = useState<AIPatient[]>(FALLBACK_PATIENTS);
  const [loading, setLoading] = useState(true);
  const [likes, setLikes] = useState<Record<string, boolean>>({});
  const [postOpen, setPostOpen] = useState(false);
  const [pAuthor, setPAuthor] = useState("");
  const [pTitle, setPTitle] = useState("");
  const [pBody, setPBody] = useState("");
  const [posting, setPosting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const [r1, r2] = await Promise.all([
        fetch(`${BASE}/api/community/stories`).then((r) => r.json()),
        fetch(`${BASE}/api/community/ai_patients`).then((r) => r.json()),
      ]);
      setStories((r1.stories?.length ? r1.stories : FALLBACK_STORIES));
      setAiPatients((r2.patients?.length ? r2.patients : FALLBACK_PATIENTS));
    } catch {
      setStories(FALLBACK_STORIES);
      setAiPatients(FALLBACK_PATIENTS);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggleLike = (id: string) => {
    Haptics.selectionAsync();
    setLikes((l) => ({ ...l, [id]: !l[id] }));
  };

  const submitPost = async () => {
    if (!pAuthor.trim() || !pTitle.trim() || !pBody.trim()) return;
    setPosting(true);
    try {
      const r = await fetch(`${BASE}/api/community/stories`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ author: pAuthor.trim(), title: pTitle.trim(), body: pBody.trim() }),
      });
      if (r.ok) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        setPAuthor(""); setPTitle(""); setPBody("");
        setPostOpen(false);
        await load();
      }
    } finally { setPosting(false); }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Community</Text>
          <Text style={styles.headerSub}>Survivors walking the same road</Text>
        </View>
        <Pressable onPress={() => { Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium); setPostOpen(true); }} style={styles.postBtn} testID="community-post-btn">
          <Ionicons name="add" size={18} color={colors.onBrandPrimary} />
          <Text style={styles.postBtnText}>Post</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 32 }} showsVerticalScrollIndicator={false}>
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Chat with survivors</Text>
          <Text style={styles.sectionSub}>AI personas of stroke survivors at different stages. Real wisdom, available 24/7.</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: spacing.lg, gap: spacing.sm, paddingVertical: spacing.sm }}>
            {aiPatients.map((p) => (
              <Pressable
                key={p.id}
                onPress={() => router.push({ pathname: "/persona-chat", params: { persona_id: p.id } })}
                style={styles.patientCard}
                testID={`ai-patient-${p.id}`}
              >
                <Image source={{ uri: p.photo }} style={styles.patientAvatar} />
                <View style={styles.aiPill}>
                  <Ionicons name="sparkles" size={9} color={colors.onBrandSecondary} />
                  <Text style={styles.aiPillText}>AI</Text>
                </View>
                <Text style={styles.patientName} numberOfLines={1}>{p.name.split(" ")[0]}</Text>
                <Text style={styles.patientMeta}>{p.months_since_stroke} mo - {p.stage}</Text>
                <View style={styles.chatChip}>
                  <Ionicons name="chatbubble" size={11} color="#fff" />
                  <Text style={styles.chatChipText}>Chat</Text>
                </View>
              </Pressable>
            ))}
          </ScrollView>
        </View>

        <View style={{ paddingHorizontal: spacing.lg }}>
          <Text style={styles.sectionTitle}>Stories</Text>
        </View>

        <View style={{ paddingHorizontal: spacing.lg, gap: spacing.md, paddingBottom: spacing.lg }}>
          {loading && <ActivityIndicator color={colors.brandPrimary} />}
          {stories.map((s) => (
            <View key={s.id} style={styles.card} testID={`story-${s.id}`}>
              <View style={styles.cardHead}>
                {s.photo ? (
                  <Image source={{ uri: s.photo }} style={styles.avatar} />
                ) : (
                  <View style={[styles.avatar, { backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" }]}>
                    <Text style={{ color: colors.onBrandTertiary, fontWeight: "800", fontSize: 18 }}>{s.author?.[0] || "A"}</Text>
                  </View>
                )}
                <View style={{ flex: 1 }}>
                  <Text style={styles.author}>{s.author}</Text>
                  {s.months_since_stroke ? <Text style={styles.meta}>{s.months_since_stroke} months into recovery</Text> : null}
                </View>
              </View>
              <Text style={styles.title}>{s.title}</Text>
              <Text style={styles.body}>{s.body}</Text>
              <View style={styles.actions}>
                <Pressable onPress={() => toggleLike(s.id)} style={styles.likeBtn} testID={`like-${s.id}`}>
                  <Ionicons name={likes[s.id] ? "heart" : "heart-outline"} size={20} color={likes[s.id] ? colors.brandSecondary : colors.onSurfaceTertiary} />
                  <Text style={[styles.likeText, likes[s.id] && { color: colors.brandSecondary }]}>{s.likes + (likes[s.id] ? 1 : 0)}</Text>
                </Pressable>
              </View>
            </View>
          ))}
        </View>
      </ScrollView>

      <Modal visible={postOpen} animationType="slide" transparent onRequestClose={() => setPostOpen(false)}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.modalBg}>
          <Pressable style={StyleSheet.absoluteFill} onPress={() => setPostOpen(false)} />
          <View style={[styles.modalSheet, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
            <View style={styles.modalHandle} />
            <Text style={styles.modalTitle}>Share your story</Text>
            <Text style={styles.modalSub}>Your words can help someone today.</Text>
            <TextInput value={pAuthor} onChangeText={setPAuthor} placeholder="Your name" placeholderTextColor={colors.onSurfaceTertiary} style={styles.modalInput} testID="post-author-input" />
            <TextInput value={pTitle} onChangeText={setPTitle} placeholder="Title" placeholderTextColor={colors.onSurfaceTertiary} style={styles.modalInput} testID="post-title-input" />
            <TextInput value={pBody} onChangeText={setPBody} placeholder="Your story..." placeholderTextColor={colors.onSurfaceTertiary} multiline style={[styles.modalInput, { minHeight: 120, textAlignVertical: "top" }]} testID="post-body-input" />
            <Pressable onPress={submitPost} style={[styles.modalSubmit, (!pAuthor.trim() || !pTitle.trim() || !pBody.trim() || posting) && { opacity: 0.5 }]} disabled={!pAuthor.trim() || !pTitle.trim() || !pBody.trim() || posting} testID="post-submit">
              {posting ? <ActivityIndicator color="#fff" /> : <Text style={styles.modalSubmitText}>Share</Text>}
            </Pressable>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider, gap: spacing.sm },
  headerTitle: { fontSize: 26, fontWeight: "800", color: colors.onSurface },
  headerSub: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: 4 },
  postBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill },
  postBtnText: { color: colors.onBrandPrimary, fontWeight: "700" },
  section: { paddingTop: spacing.md },
  sectionTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface, paddingHorizontal: spacing.lg, marginBottom: 4 },
  sectionSub: { fontSize: 13, color: colors.onSurfaceSecondary, paddingHorizontal: spacing.lg, marginBottom: spacing.xs },
  patientCard: { width: 130, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.sm, alignItems: "center", gap: 4 },
  patientAvatar: { width: 64, height: 64, borderRadius: 32, marginBottom: 4 },
  aiPill: { position: "absolute", top: 8, right: 8, flexDirection: "row", alignItems: "center", gap: 2, backgroundColor: colors.brandSecondary, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 },
  aiPillText: { color: colors.onBrandSecondary, fontSize: 9, fontWeight: "800", letterSpacing: 0.5 },
  patientName: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  patientMeta: { fontSize: 11, color: colors.onSurfaceTertiary, textAlign: "center" },
  chatChip: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandPrimary, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12, marginTop: 4 },
  chatChipText: { color: "#fff", fontSize: 11, fontWeight: "700" },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, gap: spacing.sm },
  cardHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  avatar: { width: 44, height: 44, borderRadius: 22 },
  author: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  meta: { fontSize: 12, color: colors.onSurfaceTertiary },
  title: { fontSize: 17, fontWeight: "800", color: colors.onSurface, marginTop: 4 },
  body: { fontSize: 15, color: colors.onSurfaceSecondary, lineHeight: 22 },
  actions: { flexDirection: "row", marginTop: spacing.sm },
  likeBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 4 },
  likeText: { fontSize: 14, color: colors.onSurfaceTertiary, fontWeight: "600" },
  modalBg: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(28,32,29,0.55)" },
  modalSheet: { backgroundColor: colors.surface, borderTopLeftRadius: 28, borderTopRightRadius: 28, padding: spacing.lg, gap: spacing.sm },
  modalHandle: { width: 40, height: 4, borderRadius: 2, backgroundColor: colors.borderStrong, alignSelf: "center", marginBottom: spacing.sm },
  modalTitle: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  modalSub: { fontSize: 14, color: colors.onSurfaceSecondary, marginBottom: spacing.sm },
  modalInput: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, fontSize: 15, color: colors.onSurface },
  modalSubmit: { backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.md, alignItems: "center", marginTop: spacing.sm },
  modalSubmitText: { color: "#fff", fontWeight: "800", fontSize: 16 },
});
