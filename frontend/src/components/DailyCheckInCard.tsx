import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { authedFetch, getCachedUser } from "@/src/auth";
import { loadSettings, rescheduleReminders } from "@/src/utils/notifications";

export function DailyCheckInCard() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [surveyDue, setSurveyDue] = useState(false);
  const [message, setMessage] = useState("Your recovery plan is up to date today.");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      const user = await getCachedUser();
      if (!user?.id) return;
      setName((user.name || "").split(" ")[0] || "");
      try {
        const response = await authedFetch("/api/alira/care-plan");
        if (response.ok) {
          const plan = await response.json();
          void loadSettings().then((settings) => rescheduleReminders(settings, plan));
          const due = Boolean(plan?.survey?.due);
          setSurveyDue(due);
          if (plan?.safety?.status && plan.safety.status !== "clear") {
            setMessage("A change needs attention before your plan continues. Talk with Alira for the next safe step.");
          } else if (due) {
            setMessage("A short recovery check-in is due. Alira will ask only the few questions needed for your next plan.");
          } else if (plan?.exercise_plan?.action === "maintain") {
            setMessage("No survey is due today. Keep following your current plan and tell Alira if anything feels different.");
          }
        }
      } catch {
        setMessage("I'm here whenever you want to share how recovery is feeling today.");
      }
      setReady(true);
    })();
  }, []);

  if (!ready) return null;

  return (
    <View style={styles.card} testID="daily-checkin-card">
      <View style={styles.avatar}><Ionicons name="sparkles" size={20} color={colors.onBrandPrimary} /></View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={styles.topRow}>
          <Text style={styles.from}>Alira</Text>
          {surveyDue ? <View style={styles.duePill}><Text style={styles.dueText}>Check-in due</Text></View> : null}
        </View>
        <Text style={styles.greeting}>{name ? `Hi ${name}, ` : "Hi there, "}{surveyDue ? "shall we check in?" : "your plan is on track."}</Text>
        <Text style={styles.body}>{message}</Text>
        <Pressable
          testID="daily-checkin-chat"
          onPress={() => {
            Haptics.selectionAsync();
            router.push({
              pathname: "/(tabs)/chat" as never,
              params: { prompt: surveyDue ? "Please begin my scheduled short recovery check-in." : "I would like to talk about how recovery is going today." },
            });
          }}
          style={styles.cta}
        >
          <Ionicons name="chatbubble-ellipses-outline" size={16} color={colors.brandPrimary} />
          <Text style={styles.ctaText}>{surveyDue ? "Start short check-in" : "Talk to Alira"}</Text>
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
  duePill: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill, backgroundColor: "#FCE9DA" },
  dueText: { fontSize: 12, fontWeight: "800", color: "#A94D1B" },
  greeting: { fontSize: 15, fontWeight: "800", color: colors.onSurface, marginTop: 3 },
  body: { fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary, marginTop: 3 },
  cta: { flexDirection: "row", alignItems: "center", alignSelf: "flex-start", gap: 6, marginTop: spacing.sm, paddingVertical: 8, paddingHorizontal: 12, borderRadius: radius.pill, backgroundColor: colors.brandTertiary },
  ctaText: { fontSize: 13, fontWeight: "800", color: colors.brandPrimary },
});
