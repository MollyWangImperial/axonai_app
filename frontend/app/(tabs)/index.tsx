import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ImageBackground, Dimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius, font } from "@/src/theme";
import { fetchHistory, Assessment } from "@/src/api";

const HERO = "https://images.pexels.com/photos/8460412/pexels-photo-8460412.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940";

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [history, setHistory] = useState<Assessment[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const h = await fetchHistory();
      setHistory(h || []);
    } catch (e) {
      setHistory([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const latest = history[0];

  const onStart = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push("/task-intro");
  };

  return (
    <View style={[styles.container]}>
      <ScrollView contentContainerStyle={{ paddingBottom: 140 }} showsVerticalScrollIndicator={false}>
        {/* Hero */}
        <ImageBackground source={{ uri: HERO }} style={[styles.hero, { paddingTop: insets.top + spacing.lg }]}>
          <LinearGradient
            colors={["rgba(28,32,29,0.15)", "rgba(28,32,29,0.85)"]}
            style={StyleSheet.absoluteFill}
          />
          <View style={styles.heroInner}>
            <Text style={styles.heroBadge} testID="home-app-badge">NEUROMOTION</Text>
            <Text style={styles.heroTitle}>Good day.{"\n"}Let's move forward, together.</Text>
            <Text style={styles.heroSub}>
              A guided upper-limb movement assessment with personalized rehabilitation, grounded in clinical sources.
            </Text>
          </View>
        </ImageBackground>

        {/* Today's plan */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Today's plan</Text>
          {loading ? (
            <View style={styles.card}><Text style={styles.muted}>Loading…</Text></View>
          ) : latest ? (
            <Pressable
              testID="latest-plan-card"
              onPress={() => router.push({ pathname: "/rehab-plan", params: { id: latest.id } })}
              style={styles.card}
            >
              <View style={styles.cardHeader}>
                <Ionicons name="fitness" size={22} color={colors.brandPrimary} />
                <Text style={styles.cardTitle}>Personalized rehab plan</Text>
              </View>
              <Text style={styles.cardBody}>
                {latest.rehab_plan.length} exercises · {latest.functional_issues.length} focus areas
              </Text>
              <View style={styles.chips}>
                {latest.functional_issues.slice(0, 3).map(i => (
                  <View key={i.code} style={styles.chip}>
                    <Text style={styles.chipText} numberOfLines={1}>{i.label}</Text>
                  </View>
                ))}
              </View>
              <Text style={styles.cardLink}>Open plan →</Text>
            </Pressable>
          ) : (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>No assessment yet</Text>
              <Text style={styles.cardBody}>Start your first assessment to receive a personalized plan.</Text>
            </View>
          )}
        </View>

        {/* How it works */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>How it works</Text>
          {[
            { icon: "videocam", title: "Live camera assessment", body: "7 short upper-limb movement tasks, guided by a warm voice and on-screen targets." },
            { icon: "analytics", title: "Identify functional issues", body: "Pose tracking flags reduced reach, trunk compensation, hand opening, pinch, and more." },
            { icon: "medical", title: "Evidence-based plan", body: "Exercises drawn from Fugl-Meyer, ARAT, CIMT, BATRAC, and Task-Specific Training." },
          ].map((s, i) => (
            <View key={i} style={styles.step}>
              <View style={styles.stepIcon}>
                <Ionicons name={s.icon as any} size={22} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.stepTitle}>{s.title}</Text>
                <Text style={styles.stepBody}>{s.body}</Text>
              </View>
            </View>
          ))}
        </View>

        {/* Quick actions */}
        <View style={styles.section}>
          <View style={styles.row}>
            <Pressable
              testID="home-history-btn"
              onPress={() => router.push("/history")}
              style={[styles.quickCard, { backgroundColor: colors.surfaceSecondary }]}
            >
              <Ionicons name="time" size={26} color={colors.brandPrimary} />
              <Text style={styles.quickTitle}>Progress</Text>
              <Text style={styles.quickSub}>{history.length} past sessions</Text>
            </Pressable>
            <Pressable
              testID="home-plan-btn"
              onPress={() => latest && router.push({ pathname: "/rehab-plan", params: { id: latest.id } })}
              style={[styles.quickCard, { backgroundColor: colors.brandTertiary }]}
            >
              <Ionicons name="clipboard" size={26} color={colors.onBrandTertiary} />
              <Text style={[styles.quickTitle, { color: colors.onBrandTertiary }]}>My Plan</Text>
              <Text style={[styles.quickSub, { color: colors.onBrandTertiary }]}>{latest ? "View today" : "—"}</Text>
            </Pressable>
          </View>
        </View>
      </ScrollView>

      {/* Sticky CTA */}
      <View style={[styles.cta, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable
          testID="home-start-assessment"
          onPress={onStart}
          style={({ pressed }) => [styles.ctaBtn, pressed && { opacity: 0.85 }]}
        >
          <Ionicons name="play-circle" size={22} color={colors.onBrandPrimary} />
          <Text style={styles.ctaText}>Start Assessment</Text>
        </Pressable>
      </View>
    </View>
  );
}

const W = Dimensions.get("window").width;
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  hero: { width: "100%", paddingBottom: spacing.xl, minHeight: 260, justifyContent: "flex-end" },
  heroInner: { paddingHorizontal: spacing.lg, paddingBottom: spacing.lg },
  heroBadge: { color: colors.brandTertiary, fontWeight: "700", letterSpacing: 2, fontSize: 12, marginBottom: spacing.sm },
  heroTitle: { color: colors.onSurfaceInverse, fontSize: 26, fontWeight: "800", lineHeight: 32, marginBottom: spacing.sm },
  heroSub: { color: "#E8EBE6", fontSize: 15, lineHeight: 22 },
  section: { paddingHorizontal: spacing.lg, paddingTop: spacing.lg },
  sectionTitle: { fontSize: 20, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.md },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  cardHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  cardTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface },
  cardBody: { fontSize: 15, color: colors.onSurfaceSecondary, lineHeight: 22 },
  cardLink: { color: colors.brandPrimary, fontWeight: "700", marginTop: spacing.xs },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.xs },
  chip: { backgroundColor: colors.brandTertiary, borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 6 },
  chipText: { color: colors.onBrandTertiary, fontSize: 12, fontWeight: "600", maxWidth: W * 0.55 },
  muted: { color: colors.onSurfaceTertiary },
  step: { flexDirection: "row", gap: spacing.md, paddingVertical: spacing.sm, alignItems: "flex-start" },
  stepIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  stepTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: 2 },
  stepBody: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
  row: { flexDirection: "row", gap: spacing.md },
  quickCard: { flex: 1, padding: spacing.md, borderRadius: radius.lg, gap: 4, minHeight: 100, justifyContent: "center" },
  quickTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginTop: spacing.xs },
  quickSub: { fontSize: 13, color: colors.onSurfaceSecondary },
  cta: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  ctaBtn: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.md, alignItems: "center", justifyContent: "center", minHeight: 56 },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "700" },
});
