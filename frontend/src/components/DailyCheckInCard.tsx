import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { getCachedUser } from "@/src/auth";
import { storage } from "@/src/utils/storage";

const STREAK_KEY = (uid: string) => `daily_checkin_streak_v1:${uid}`;

function dayStamp(d: Date) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

const MESSAGES = [
  "Every session is a step forward. I'm proud of you for showing up.",
  "Small, steady practice is what rebuilds movement. You've got this.",
  "Recovery is a marathon, not a sprint — and you're moving.",
  "Your brain is learning with every rep. Let's do a little today.",
];

export function DailyCheckInCard() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [streak, setStreak] = useState(0);
  const [justGrew, setJustGrew] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      const user = await getCachedUser();
      if (!user?.id) return;
      setName((user.name || "").split(" ")[0] || "");
      const today = dayStamp(new Date());
      const yesterday = dayStamp(new Date(Date.now() - 86400000));
      const raw = await storage.getItem(STREAK_KEY(user.id), "");
      let last = "";
      let count = 0;
      if (raw) {
        try { const p = JSON.parse(raw); last = p.last || ""; count = p.count || 0; } catch { /* */ }
      }
      if (last === today) {
        setStreak(count || 1);
      } else {
        const next = last === yesterday ? count + 1 : 1;
        await storage.setItem(STREAK_KEY(user.id), JSON.stringify({ last: today, count: next }));
        setStreak(next);
        setJustGrew(next > 1);
      }
      setReady(true);
    })();
  }, []);

  if (!ready) return null;

  const message = MESSAGES[new Date().getDate() % MESSAGES.length];
  const celebrate = justGrew || streak === 1;

  return (
    <View style={styles.card} testID="daily-checkin-card">
      <View style={styles.avatar}><Ionicons name="sparkles" size={20} color={colors.onBrandPrimary} /></View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={styles.topRow}>
          <Text style={styles.from}>Alira</Text>
          {streak > 0 && (
            <View style={styles.streakPill} testID="daily-checkin-streak">
              <Ionicons name="flame" size={13} color="#C1571E" />
              <Text style={styles.streakText}>{streak} day{streak === 1 ? "" : "s"}</Text>
            </View>
          )}
        </View>
        <Text style={styles.greeting}>{name ? `Hi ${name}, ` : "Hi there, "}{celebrate ? "great to see you today!" : "welcome back."}</Text>
        <Text style={styles.body}>{message}</Text>
        <Pressable
          testID="daily-checkin-chat"
          onPress={() => { Haptics.selectionAsync(); router.push({ pathname: "/(tabs)/chat" as never, params: { prompt: "I'm here for my daily check-in" } }); }}
          style={styles.cta}
        >
          <Ionicons name="chatbubble-ellipses-outline" size={16} color={colors.brandPrimary} />
          <Text style={styles.ctaText}>Talk to Alira</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { flexDirection: "row", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginBottom: spacing.md },
  avatar: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  topRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  from: { fontSize: 13, fontWeight: "900", color: colors.brandPrimary, letterSpacing: 0.3 },
  streakPill: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill, backgroundColor: "#FCE9DA" },
  streakText: { fontSize: 12, fontWeight: "800", color: "#C1571E" },
  greeting: { fontSize: 15, fontWeight: "800", color: colors.onSurface, marginTop: 3 },
  body: { fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary, marginTop: 3 },
  cta: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", gap: 6, marginTop: spacing.sm, paddingVertical: 8, paddingHorizontal: 12, borderRadius: radius.pill, backgroundColor: colors.brandTertiary },
  ctaText: { fontSize: 13, fontWeight: "800", color: colors.brandPrimary },
});
