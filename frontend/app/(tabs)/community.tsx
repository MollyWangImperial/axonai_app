import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Image, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

type Story = {
  id: string;
  author: string;
  title: string;
  body: string;
  likes: number;
  months_since_stroke?: number;
  photo?: string;
};

export default function CommunityScreen() {
  const insets = useSafeAreaInsets();
  const [stories, setStories] = useState<Story[]>([]);
  const [loading, setLoading] = useState(true);
  const [likes, setLikes] = useState<Record<string, boolean>>({});

  const load = async () => {
    try {
      const res = await fetch(`${BASE}/api/community/stories`);
      const data = await res.json();
      setStories(data.stories || []);
    } catch {
      setStories([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggleLike = (id: string) => {
    Haptics.selectionAsync();
    setLikes((l) => ({ ...l, [id]: !l[id] }));
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Community</Text>
        <Text style={styles.headerSub}>Stories from people walking the same road</Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 32 }} showsVerticalScrollIndicator={false}>
        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        {stories.map((s) => (
          <View key={s.id} style={styles.card} testID={`story-${s.id}`}>
            <View style={styles.cardHead}>
              {s.photo ? (
                <Image source={{ uri: s.photo }} style={styles.avatar} />
              ) : (
                <View style={[styles.avatar, { backgroundColor: colors.brandTertiary }]}>
                  <Text style={{ color: colors.onBrandTertiary, fontWeight: "800", fontSize: 18 }}>
                    {s.author?.[0] || "·"}
                  </Text>
                </View>
              )}
              <View style={{ flex: 1 }}>
                <Text style={styles.author}>{s.author}</Text>
                {s.months_since_stroke ? (
                  <Text style={styles.meta}>{s.months_since_stroke} months into recovery</Text>
                ) : null}
              </View>
            </View>
            <Text style={styles.title}>{s.title}</Text>
            <Text style={styles.body}>{s.body}</Text>
            <View style={styles.actions}>
              <Pressable onPress={() => toggleLike(s.id)} style={styles.likeBtn} testID={`like-${s.id}`}>
                <Ionicons
                  name={likes[s.id] ? "heart" : "heart-outline"}
                  size={20}
                  color={likes[s.id] ? colors.brandSecondary : colors.onSurfaceTertiary}
                />
                <Text style={[styles.likeText, likes[s.id] && { color: colors.brandSecondary }]}>
                  {s.likes + (likes[s.id] ? 1 : 0)}
                </Text>
              </Pressable>
            </View>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: 26, fontWeight: "800", color: colors.onSurface },
  headerSub: { fontSize: 14, color: colors.onSurfaceSecondary, marginTop: 4 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.md, gap: spacing.sm },
  cardHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  avatar: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center" },
  author: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  meta: { fontSize: 12, color: colors.onSurfaceTertiary },
  title: { fontSize: 17, fontWeight: "800", color: colors.onSurface, marginTop: 4 },
  body: { fontSize: 15, color: colors.onSurfaceSecondary, lineHeight: 22 },
  actions: { flexDirection: "row", marginTop: spacing.sm },
  likeBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 4 },
  likeText: { fontSize: 14, color: colors.onSurfaceTertiary, fontWeight: "600" },
});
