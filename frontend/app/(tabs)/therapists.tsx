import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, Image, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { fetchHistory } from "@/src/api";
import { API_BASE as BASE } from "@/src/config";

type Therapist = {
  id: string;
  ai?: boolean;
  trained_on?: string;
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

const FALLBACK_MATCHES: Match[] = [
  {
    score: 98,
    reason: "good match for hand and fine-motor recovery",
    therapist: {
      id: "th_001",
      ai: true,
      trained_on: "12 years of OT case data - fine motor and hand rehab",
      name: "Maya (AI Therapist)",
      title: "AI Occupational Therapist - Hand and Fine Motor",
      specialties: ["HAND_OPENING", "PINCH_IMPAIRED", "GROSS_GRASP"],
      location: "Always available - Worldwide",
      languages: ["English", "Spanish"],
      rating: 4.9,
      years: 12,
      availability: ["24/7 chat"],
      blurb: "I specialize in helping survivors rebuild fine motor control with playful, daily activities. We'll go at your pace.",
      photo: "https://images.unsplash.com/photo-1559839734-2b71ea197ec2?w=400",
    },
  },
  {
    score: 94,
    reason: "good match for reach training and trunk control",
    therapist: {
      id: "th_002",
      ai: true,
      trained_on: "9 years of neuro-PT case data - reach training and trunk control",
      name: "Aiden (AI Therapist)",
      title: "AI Physical Therapist - Reach and Shoulder",
      specialties: ["REACH_INCOMPLETE", "SHOULDER_FLEX_LIMITED", "TRUNK_COMP"],
      location: "Always available - Worldwide",
      languages: ["English", "Korean"],
      rating: 4.8,
      years: 9,
      availability: ["24/7 chat"],
      blurb: "Reach training and trunk control specialist. I love seeing the moment a patient realizes their arm can do more than they thought.",
      photo: "https://images.unsplash.com/photo-1622253692010-333f2da6031d?w=400",
    },
  },
  {
    score: 92,
    reason: "good match for daily living and self-care practice",
    therapist: {
      id: "th_005",
      ai: true,
      trained_on: "11 years of OT in ADL retraining - feeding, dressing, grooming",
      name: "Lena (AI Therapist)",
      title: "AI OT - Daily Living and Self-Care",
      specialties: ["H2M_IMPAIRED", "GROSS_GRASP", "PINCH_IMPAIRED"],
      location: "Always available - Worldwide",
      languages: ["English", "German"],
      rating: 4.85,
      years: 11,
      availability: ["24/7 chat"],
      blurb: "Daily-living focused. We'll work on feeding, dressing, and small joys like coin pinches, buttons, and a familiar mug.",
      photo: "https://images.unsplash.com/photo-1551836022-d5d88e9218df?w=400",
    },
  },
];

export default function TherapistsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [matches, setMatches] = useState<Match[]>(FALLBACK_MATCHES);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      let codes = "";
      try {
        const history = await fetchHistory();
        const latest = history[0];
        codes = latest ? latest.functional_issues.map((i) => i.code).join(",") : "";
      } catch {
        codes = "";
      }
      const res = await fetch(`${BASE}/api/therapists/match?issues=${encodeURIComponent(codes)}`);
      const data = await res.json();
      setMatches(data.matches?.length ? data.matches : FALLBACK_MATCHES);
    } catch {
      setMatches(FALLBACK_MATCHES);
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
          Available 24/7, trained on real therapist expertise and experience.
        </Text>
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 32 }} showsVerticalScrollIndicator={false}>
        <View style={styles.eaBanner} testID="ea-banner">
          <Ionicons name="ribbon" size={20} color="#315440" />
          <View style={{ flex: 1 }}>
            <Text style={styles.eaTitle}>Trained on real clinical practice</Text>
            <Text style={styles.eaBody}>Our therapists are built from the methods, voice, and patience of licensed clinicians - grounded in CIMT, Fugl-Meyer, ARAT, and Bobath.</Text>
          </View>
        </View>
        {loading && <ActivityIndicator color="#315440" />}
        {matches.map((m, idx) => {
          const t = m.therapist;
          return (
            <View key={t.id} style={styles.card} testID={`therapist-${t.id}`}>
              <View style={styles.badgeRow}>
                {idx === 0 && (
                  <View style={styles.topMatch}>
                    <Ionicons name="sparkles" size={14} color="#FFFDF5" />
                    <Text style={styles.topMatchText}>TOP MATCH</Text>
                  </View>
                )}
                <View style={styles.aiBadge}>
                  <Ionicons name="sparkles" size={12} color="#214333" />
                  <Text style={styles.aiBadgeText}>AI</Text>
                </View>
              </View>
              <View style={styles.cardHead}>
                <Image source={{ uri: t.photo }} style={styles.avatar} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.name}>{t.name}</Text>
                  <Text style={styles.title}>{t.title}</Text>
                  <View style={styles.metaRow}>
                    <Ionicons name="star" size={15} color="#70845E" />
                    <Text style={styles.metaText}>{t.rating} - {t.years} yrs</Text>
                  </View>
                </View>
              </View>
              <Text style={styles.reason}>Match: {m.reason}</Text>
              {t.trained_on && (
                <View style={styles.trainedRow}>
                  <Ionicons name="school" size={16} color="#315440" />
                  <Text style={styles.trainedText}>Trained on {t.trained_on}</Text>
                </View>
              )}
              <Text style={styles.blurb}>{t.blurb}</Text>
              <View style={styles.tags}>
                {t.languages.map((l: string) => (
                  <View key={l} style={styles.tag}>
                    <Ionicons name="globe" size={13} color="#526B5A" />
                    <Text style={styles.tagText}>{l}</Text>
                  </View>
                ))}
                <View style={styles.tag}>
                  <Ionicons name="time" size={13} color="#526B5A" />
                  <Text style={styles.tagText}>{t.availability.join(" - ")}</Text>
                </View>
              </View>
              <Pressable
                onPress={() => connect(t.id)}
                style={styles.connectBtn}
                testID={`connect-${t.id}`}
              >
                <Ionicons name="chatbubbles" size={19} color="#FFFDF5" />
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
  container: { flex: 1, backgroundColor: "#F7F4EB" },
  header: { paddingHorizontal: spacing.lg, paddingVertical: spacing.lg, backgroundColor: "#FCFAF3", borderBottomWidth: 1, borderBottomColor: "#D7E1D2" },
  headerTitle: { fontSize: 28, fontWeight: "800", color: "#1F3D30", letterSpacing: -0.4 },
  headerSub: { fontSize: 17, lineHeight: 24, color: "#526558", marginTop: 5 },
  card: { backgroundColor: "#FFFEFA", borderWidth: 1, borderColor: "#DCE5D7", borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, gap: 12, shadowColor: "#234033", shadowOpacity: 0.06, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 1 },
  eaBanner: { flexDirection: "row", gap: 11, backgroundColor: "#DCE8D7", borderWidth: 1, borderColor: "#C5D6BF", padding: spacing.lg, borderRadius: radius.lg, marginBottom: spacing.lg, alignItems: "flex-start" },
  eaTitle: { fontSize: 17, fontWeight: "800", color: "#244436", marginBottom: 5 },
  eaBody: { fontSize: 16, color: "#385342", lineHeight: 23 },
  badgeRow: { flexDirection: "row", gap: 7 },
  aiBadge: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: "#E7EEE3", borderWidth: 1, borderColor: "#C8D8C2", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14 },
  aiBadgeText: { color: "#214333", fontSize: 12, fontWeight: "800", letterSpacing: 0.8 },
  topMatch: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: "#315440", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14 },
  topMatchText: { color: "#FFFDF5", fontSize: 12, fontWeight: "800", letterSpacing: 0.8 },
  trainedRow: { flexDirection: "row", gap: 8, alignItems: "center", backgroundColor: "#EEF4EA", padding: spacing.sm, borderRadius: radius.md },
  trainedText: { color: "#385342", fontSize: 15, lineHeight: 21, fontWeight: "700", flex: 1 },
  cardHead: { flexDirection: "row", gap: spacing.md, alignItems: "center" },
  avatar: { width: 68, height: 68, borderRadius: 34, backgroundColor: "#DCE8D7" },
  name: { fontSize: 20, fontWeight: "800", color: "#214333" },
  title: { fontSize: 16, lineHeight: 22, color: "#526558", marginTop: 3 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 5, marginTop: 5 },
  metaText: { fontSize: 16, color: "#385342", fontWeight: "700" },
  reason: { fontSize: 16, lineHeight: 22, color: "#315440", fontWeight: "800" },
  blurb: { fontSize: 16, color: "#40554A", fontStyle: "italic", lineHeight: 24 },
  tags: { flexDirection: "row", flexWrap: "wrap", gap: 7 },
  tag: { flexDirection: "row", alignItems: "center", gap: 5, backgroundColor: "#E9EDE5", borderWidth: 1, borderColor: "#DCE5D7", paddingHorizontal: 10, paddingVertical: 6, borderRadius: 14 },
  tagText: { fontSize: 14, color: "#40554A", fontWeight: "700" },
  avail: { marginTop: 4 },
  availLabel: { fontSize: 12, color: "#5B6F61", fontWeight: "800", letterSpacing: 0.8 },
  availText: { fontSize: 16, color: "#294738", marginTop: 3 },
  connectBtn: { flexDirection: "row", gap: 9, backgroundColor: "#315440", borderRadius: radius.md, minHeight: 52, paddingHorizontal: 16, paddingVertical: 12, alignItems: "center", justifyContent: "center", marginTop: 6, shadowColor: "#183326", shadowOpacity: 0.14, shadowRadius: 5, shadowOffset: { width: 0, height: 2 }, elevation: 2 },
  connectBtnAlt: { backgroundColor: "#6E875E" },
  connectText: { color: "#FFFDF5", fontWeight: "800", fontSize: 17 },
});
