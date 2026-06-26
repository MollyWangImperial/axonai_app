import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Image, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { fetchHistory } from "@/src/api";

const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

type Therapist = {
  id: string;
  ai?: boolean;
  name: string;
  title: string;
  specialties: string[];
  location: string;
  languages: string[];
  rating: number;
  years: number;
  availability: string[];
  blurb: string;
  photo: string;
};

type Match = { therapist: Therapist; score: number; reason: string };

export default function TherapistsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [matches, setMatches] = useState<Match[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const history = await fetchHistory();
      const latest = history[0];
      const codes = latest ? latest.functional_issues.map((i) => i.code).join(",") : "";
      const res = await fetch(`${BASE}/api/therapists/match?issues=${encodeURIComponent(codes)}`);
      const data = await res.json();
      setMatches(data.matches || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const connect = async (id: string) => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({ pathname: "/persona-chat", params: { persona_id: id } });
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Find your therapist</Text>
        <Text style={styles.headerSub}>
          Matched to your focus areas. Available 24/7 in early access.
        </Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 32 }} showsVerticalScrollIndicator={false}>
        <View style={styles.eaBanner} testID="ea-banner">
          <Ionicons name="information-circle" size={18} color={colors.onBrandTertiary} />
          <View style={{ flex: 1 }}>
            <Text style={styles.eaTitle}>Early access — AI therapist companions</Text>
            <Text style={styles.eaBody}>While we onboard licensed clinicians, our AI therapist personas — grounded in CIMT, Fugl-Meyer, ARAT, and Bobath — are here for you anytime.</Text>
          </View>
        </View>
        {loading && <ActivityIndicator color={colors.brandPrimary} />}
        {matches.map((m, idx) => {
          const t = m.therapist;
          return (
            <View key={t.id} style={styles.card} testID={`therapist-${t.id}`}>
              <View style={styles.badgeRow}>
                {idx === 0 && (
                  <View style={styles.topMatch}>
                    <Ionicons name="sparkles" size={14} color={colors.onBrandSecondary} />
                    <Text style={styles.topMatchText}>TOP MATCH</Text>
                  </View>
                )}
                <View style={styles.aiBadge}>
                  <Ionicons name="sparkles" size={12} color={colors.onBrandSecondary} />
                  <Text style={styles.aiBadgeText}>AI</Text>
                </View>
              </View>
              <View style={styles.cardHead}>
                <Image source={{ uri: t.photo }} style={styles.avatar} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.name}>{t.name}</Text>
                  <Text style={styles.title}>{t.title}</Text>
                  <View style={styles.metaRow}>
                    <Ionicons name="star" size={14} color={colors.brandSecondary} />
                    <Text style={styles.metaText}>{t.rating} · {t.years} yrs</Text>
                  </View>
                </View>
              </View>
              <Text style={styles.reason}>✓ {m.reason}</Text>
              <Text style={styles.blurb}>{t.blurb}</Text>
              <View style={styles.tags}>
                {t.languages.map((l: string) => (
                  <View key={l} style={styles.tag}>
                    <Ionicons name="globe" size={11} color={colors.onSurfaceSecondary} />
                    <Text style={styles.tagText}>{l}</Text>
                  </View>
                ))}
                <View style={styles.tag}>
                  <Ionicons name="time" size={11} color={colors.onSurfaceSecondary} />
                  <Text style={styles.tagText}>{t.availability.join(" · ")}</Text>
                </View>
              </View>
              <Pressable
                onPress={() => connect(t.id)}
                style={styles.connectBtn}
                testID={`connect-${t.id}`}
              >
                <Ionicons name="chatbubbles" size={18} color="#fff" />
                <Text style={styles.connectText}>Chat with {t.name.split(" ")[0]}</Text>
              </Pressable>
            </View>
          );
        })}
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
  eaBanner: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandTertiary, padding: spacing.md, borderRadius: radius.lg, marginBottom: spacing.md, alignItems: "flex-start" },
  eaTitle: { fontSize: 14, fontWeight: "800", color: colors.onBrandTertiary, marginBottom: 4 },
  eaBody: { fontSize: 13, color: colors.onBrandTertiary, lineHeight: 18 },
  badgeRow: { flexDirection: "row", gap: 6 },
  aiBadge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandSecondary, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  aiBadgeText: { color: colors.onBrandSecondary, fontSize: 11, fontWeight: "800", letterSpacing: 1 },
  topMatch: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandPrimary, paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  topMatchText: { color: colors.onBrandPrimary, fontSize: 11, fontWeight: "800", letterSpacing: 1 },
  cardHead: { flexDirection: "row", gap: spacing.md, alignItems: "center" },
  avatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.brandTertiary },
  name: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  title: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 2 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  metaText: { fontSize: 13, color: colors.onSurface, fontWeight: "600" },
  reason: { fontSize: 13, color: colors.brandPrimary, fontWeight: "700" },
  blurb: { fontSize: 14, color: colors.onSurfaceSecondary, fontStyle: "italic", lineHeight: 20 },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  tag: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.surfaceTertiary, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12 },
  tagText: { fontSize: 11, color: colors.onSurfaceSecondary, fontWeight: "600" },
  avail: { marginTop: 4 },
  availLabel: { fontSize: 11, color: colors.onSurfaceTertiary, fontWeight: "700", letterSpacing: 1 },
  availText: { fontSize: 13, color: colors.onSurface, marginTop: 2 },
  connectBtn: { flexDirection: "row", gap: 8, backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingVertical: 13, alignItems: "center", justifyContent: "center", marginTop: 6 },
  connectBtnAlt: { backgroundColor: colors.success },
  connectText: { color: "#fff", fontWeight: "700", fontSize: 15 },
});
