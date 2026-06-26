import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ImageBackground, Dimensions, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { LinearGradient } from "expo-linear-gradient";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { fetchHistory, Assessment } from "@/src/api";
import { ensurePermission, loadSettings, rescheduleReminders } from "@/src/utils/notifications";
import CreditsBadge from "@/src/components/CreditsBadge";
import AriaFloatingChat from "@/src/components/AriaFloatingChat";
import { storage } from "@/src/utils/storage";
import { getCachedUser } from "@/src/auth";

const HERO = "https://images.pexels.com/photos/8460412/pexels-photo-8460412.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940";
const BASE = process.env.EXPO_PUBLIC_BACKEND_URL;

type ReminderStatus = {
  days_since_assessment: number | null;
  exercise_overdue: boolean;
  assessment_overdue: boolean;
  daily_reminder_text: string;
  weekly_reminder_text: string;
};

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [history, setHistory] = useState<Assessment[]>([]);
  const [reminder, setReminder] = useState<ReminderStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [greetName, setGreetName] = useState<string>("");

  const load = async () => {
    try {
      const [h, r] = await Promise.all([
        fetchHistory().catch(() => []),
        fetch(`${BASE}/api/reminders/status`).then((res) => res.json()).catch(() => null),
      ]);
      setHistory(h || []);
      setReminder(r);
      // greeting name preference: preferred_name from onboarding > cached user.name
      const pref = await storage.getItem("preferred_name_v1");
      if (pref) setGreetName(pref);
      else {
        const u = await getCachedUser();
        if (u?.name) setGreetName(u.name.split(" ")[0]);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // Schedule reminders on first launch (silent on web / Expo Go iOS limitations)
    (async () => {
      if (Platform.OS === "web") return;
      const granted = await ensurePermission();
      if (granted) {
        const s = await loadSettings();
        await rescheduleReminders(s);
      }
    })();
  }, []);

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
            <View style={styles.heroTopRow}>
              <Text style={styles.heroBadge} testID="home-app-badge">NEUROMOTION</Text>
              <CreditsBadge />
            </View>
            <Text style={styles.heroTitle}>{greetName ? `Good day, ${greetName}.` : "Good day."}{"\n"}Let's move forward, together.</Text>
            <Text style={styles.heroSub}>
              A guided upper-limb movement assessment with personalized rehabilitation, grounded in clinical sources.
            </Text>
          </View>
        </ImageBackground>

        {/* Reminder cards */}
        {reminder?.assessment_overdue ? (
          <View style={styles.section}>
            <Pressable
              testID="weekly-reminder-card"
              onPress={() => router.push("/task-intro")}
              style={[styles.reminderCard, { backgroundColor: colors.brandSecondary }]}
            >
              <Ionicons name="calendar" size={24} color={colors.onBrandSecondary} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.reminderTitle, { color: colors.onBrandSecondary }]}>Weekly movement check-in</Text>
                <Text style={[styles.reminderBody, { color: colors.onBrandSecondary }]}>
                  {reminder.days_since_assessment == null
                    ? "Let's start your first assessment to see where you are."
                    : `It has been ${reminder.days_since_assessment} days. A quick check-in helps us tune your plan.`}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.onBrandSecondary} />
            </Pressable>
          </View>
        ) : reminder?.exercise_overdue ? (
          <View style={styles.section}>
            <Pressable
              testID="daily-reminder-card"
              onPress={() => latest && router.push({ pathname: "/rehab-plan", params: { id: latest.id } })}
              style={[styles.reminderCard, { backgroundColor: colors.brandPrimary }]}
            >
              <Ionicons name="alarm" size={24} color={colors.onBrandPrimary} />
              <View style={{ flex: 1 }}>
                <Text style={[styles.reminderTitle, { color: colors.onBrandPrimary }]}>Today's exercise reminder</Text>
                <Text style={[styles.reminderBody, { color: colors.onBrandPrimary }]} numberOfLines={2}>
                  {reminder.daily_reminder_text}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.onBrandPrimary} />
            </Pressable>
          </View>
        ) : null}

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

      {/* Aria — floating caring companion */}
      <AriaFloatingChat bottomOffset={(insets.bottom || 0) + 84} />
    </View>
  );
}

const W = Dimensions.get("window").width;
const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  hero: { width: "100%", paddingBottom: spacing.xl, minHeight: 260, justifyContent: "flex-end" },
  heroInner: { paddingHorizontal: spacing.lg, paddingBottom: spacing.lg },
  heroTopRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  heroBadge: { color: colors.brandTertiary, fontWeight: "700", letterSpacing: 2, fontSize: 12 },
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
  reminderCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.lg },
  reminderTitle: { fontSize: 16, fontWeight: "800", marginBottom: 2 },
  reminderBody: { fontSize: 13, lineHeight: 18 },
});
