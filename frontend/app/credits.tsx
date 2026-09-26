import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, radius } from "@/src/theme";
import { fetchBalance, signOut, getCachedUser } from "@/src/auth";

export default function CreditsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [credits, setCredits] = useState<number | null>(null);
  const [costs, setCosts] = useState<Record<string, number>>({});
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    (async () => {
      const b = await fetchBalance();
      setCredits(b.credits);
      setCosts(b.costs);
      setUser(await getCachedUser());
    })();
  }, []);

  const doSignOut = async () => {
    await signOut();
    router.replace("/sign-in");
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.sm }]}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} testID="credits-back"><Ionicons name="chevron-back" size={24} color={colors.onSurface} /></Pressable>
        <Text style={styles.headerTitle}>Your Credits</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 32 }}>
        <View style={styles.hero}>
          <Ionicons name="diamond" size={40} color={colors.brandSecondary} />
          <Text style={styles.heroNum}>{credits ?? "—"}</Text>
          <Text style={styles.heroLabel}>credits available</Text>
          <Text style={styles.heroSub}>Welcome, {user?.name || "—"}</Text>
        </View>

        <Text style={styles.section}>What credits unlock</Text>
        {Object.entries({
          assessment: "Movement assessment",
          rehab_plan: "Generate rehab plan",
          guided_exercise: "Guided exercise (per session)",
          premium_chat_message: "Premium therapist chat (per message)",
          video_call: "Video call with real therapist",
          in_person_session: "In-person rehab session",
        }).map(([key, label]) => (
          <View key={key} style={styles.row}>
            <Text style={styles.rowLabel}>{label}</Text>
            <Text style={styles.rowCost}>{costs[key] ?? "—"} cr</Text>
          </View>
        ))}

        <Text style={styles.disclaim}>
          You started with 100 credits. Top-ups (£4.99 / 100 credits) will be available in the next update.
        </Text>

        <Pressable onPress={doSignOut} style={styles.signOut} testID="credits-signout">
          <Ionicons name="log-out" size={18} color={colors.error} />
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { minHeight: 72, flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  headerTitle: { fontSize: 22, lineHeight: 28, fontWeight: "800", color: colors.onSurface },
  hero: { backgroundColor: colors.brandTertiary, borderWidth: 1, borderColor: colors.border, padding: spacing.xl, borderRadius: radius.lg, alignItems: "center", marginBottom: spacing.lg, gap: 5 },
  heroNum: { fontSize: 64, fontWeight: "900", color: colors.onBrandTertiary, marginTop: 4 },
  heroLabel: { fontSize: 16, lineHeight: 22, color: colors.onBrandTertiary, fontWeight: "700" },
  heroSub: { fontSize: 16, lineHeight: 22, color: colors.onBrandTertiary, opacity: 0.82, marginTop: spacing.sm },
  section: { fontSize: 22, lineHeight: 28, fontWeight: "800", color: colors.onSurface, marginBottom: spacing.sm },
  row: { minHeight: 64, flexDirection: "row", justifyContent: "space-between", alignItems: "center", padding: spacing.md, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, marginBottom: spacing.sm },
  rowLabel: { color: colors.onSurface, fontSize: 16, lineHeight: 22, fontWeight: "700" },
  rowCost: { color: colors.brandPrimary, fontSize: 16, fontWeight: "800" },
  disclaim: { fontSize: 14, color: colors.onSurfaceTertiary, fontStyle: "italic", marginTop: spacing.md, lineHeight: 21 },
  signOut: { minHeight: 52, flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "center", padding: spacing.md, borderRadius: radius.md, marginTop: spacing.lg, borderWidth: 1, borderColor: colors.error },
  signOutText: { color: colors.error, fontWeight: "700" },
});
