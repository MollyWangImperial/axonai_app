import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { colors, spacing, radius } from "@/src/theme";
import { authedFetch } from "@/src/auth";

export default function BillingReturnScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ session_id?: string; kind?: string }>();
  const [status, setStatus] = useState<"verifying" | "ok" | "fail">("verifying");
  const [creditsNow, setCreditsNow] = useState<number | null>(null);
  const [sub, setSub] = useState<boolean>(false);

  useEffect(() => {
    let cancelled = false;
    let tries = 0;
    const tick = async () => {
      if (cancelled) return;
      tries += 1;
      if (!params.session_id) {
        setStatus("fail");
        return;
      }
      try {
        const r = await authedFetch(`/api/billing/verify-session?session_id=${encodeURIComponent(params.session_id)}`);
        const d = await r.json();
        if (d.status === "applied") {
          setCreditsNow(d.credits ?? null);
          setSub(!!d.subscription_active);
          setStatus("ok");
          return;
        }
      } catch {/* */}
      if (tries < 45) setTimeout(tick, 2000);
      else setStatus("fail");
    };
    tick();
    return () => { cancelled = true; };
  }, [params.session_id]);

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.lg }]}>
      <View style={styles.card}>
        {status === "verifying" ? (
          <>
            <ActivityIndicator size="large" color={colors.brandPrimary} />
            <Text style={styles.title}>Confirming your payment…</Text>
            <Text style={styles.body}>This usually takes a few seconds.</Text>
          </>
        ) : status === "ok" ? (
          <>
            <View style={styles.icOk}><Ionicons name="checkmark" size={36} color="#fff" /></View>
            <Text style={styles.title}>{sub ? "You're subscribed!" : "Credits added!"}</Text>
            <Text style={styles.body}>
              {sub
                ? "Unlimited assessments, plans, and guided exercises are now unlocked."
                : `Your balance: ${creditsNow ?? "—"} credits.`}
            </Text>
            <Pressable onPress={() => router.replace("/")} style={styles.cta} testID="billing-return-home">
              <Text style={styles.ctaText}>Back to NeuroMotion</Text>
            </Pressable>
          </>
        ) : (
          <>
            <View style={styles.icFail}><Ionicons name="alert" size={36} color="#fff" /></View>
            <Text style={styles.title}>Couldn't verify the payment</Text>
            <Text style={styles.body}>If you completed checkout, your unlock may take a minute to apply. Try refreshing your credits later.</Text>
            <Pressable onPress={() => router.replace("/")} style={styles.cta}>
              <Text style={styles.ctaText}>Back to NeuroMotion</Text>
            </Pressable>
          </>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface, padding: spacing.lg },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.xl, alignItems: "center", gap: spacing.md, marginTop: spacing.xl },
  icOk: { width: 70, height: 70, borderRadius: 35, backgroundColor: colors.success, alignItems: "center", justifyContent: "center" },
  icFail: { width: 70, height: 70, borderRadius: 35, backgroundColor: colors.brandSecondary, alignItems: "center", justifyContent: "center" },
  title: { fontSize: 22, fontWeight: "800", color: colors.onSurface, textAlign: "center" },
  body: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 22 },
  cta: { backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: 14, paddingHorizontal: 28, marginTop: spacing.md },
  ctaText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 15 },
});
