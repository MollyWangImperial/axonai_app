import { useEffect, useRef, useState } from "react";
import { View, Text, StyleSheet, Pressable, Modal, ActivityIndicator, Platform, Linking } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as WebBrowser from "expo-web-browser";
import { colors, spacing, radius } from "@/src/theme";
import { authedFetch } from "@/src/auth";
import { API_BASE as BASE } from "@/src/config";

type Props = {
  visible: boolean;
  onClose: () => void;
  onSubscribed?: () => void;     // called after successful subscription (refresh credit balance, etc.)
  reason?: string;                // "You ran out of credits to start another exercise."
};

export default function PaywallModal({ visible, onClose, onSubscribed, reason }: Props) {
  const [busy, setBusy] = useState<null | "sub" | "credits">(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingSession, setPendingSession] = useState<string | null>(null);
  const pollRef = useRef<any>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const startCheckout = async (kind: "sub" | "credits") => {
    setBusy(kind); setError(null);
    try {
      const path = kind === "sub" ? "/api/billing/subscribe" : "/api/billing/buy-credits";
      const r = await authedFetch(path, { method: "POST" });
      if (!r.ok) {
        const t = await r.text();
        setError(t.includes("Invalid API Key") ? "Stripe payments are activated after deployment. (Test sentinel detected.)" : "Could not start checkout. Try again.");
        setBusy(null);
        return;
      }
      const d = await r.json();
      setPendingSession(d.session_id);
      // Open the Checkout URL in the in-app browser on mobile, a new tab on web.
      if (Platform.OS === "web") {
        window.open(d.url, "_blank");
      } else {
        await WebBrowser.openBrowserAsync(d.url);
      }
      // Poll verify-session every 2s up to 90s.
      let elapsed = 0;
      pollRef.current = setInterval(async () => {
        elapsed += 2;
        try {
          const vr = await authedFetch(`/api/billing/verify-session?session_id=${encodeURIComponent(d.session_id)}`);
          if (vr.ok) {
            const j = await vr.json();
            if (j.status === "applied") {
              clearInterval(pollRef.current);
              setBusy(null);
              setPendingSession(null);
              onSubscribed?.();
              onClose();
              return;
            }
          }
        } catch {/* */}
        if (elapsed >= 90) { clearInterval(pollRef.current); setBusy(null); }
      }, 2000);
    } catch (e) {
      setError("Network error — try again.");
      setBusy(null);
    }
  };

  return (
    <Modal visible={visible} animationType="slide" transparent={false} onRequestClose={onClose}>
      <View style={styles.container} testID="paywall-modal">
        <Pressable onPress={onClose} style={styles.closeBtn} hitSlop={16} testID="paywall-close">
          <Ionicons name="close" size={26} color={colors.onSurface} />
        </Pressable>

        <View style={styles.hero}>
          <View style={styles.crown}><Ionicons name="sparkles" size={36} color={colors.onBrandPrimary} /></View>
          <Text style={styles.title}>Keep recovering, every day.</Text>
          <Text style={styles.subtitle}>{reason || "You've used your starter credits. Unlock unlimited movement work for less than a single therapy session."}</Text>
        </View>

        <View style={styles.planCard} testID="paywall-sub-card">
          <View style={styles.planHead}>
            <Text style={styles.planName}>Unlimited Monthly</Text>
            <Text style={styles.planPrice}>$9.99<Text style={styles.planPriceSlash}>/month</Text></Text>
          </View>
          <View style={styles.bullets}>
            {[
              "Unlimited assessments",
              "Unlimited personalized plans",
              "Unlimited guided exercises with form scoring",
              "Alira companion chat included",
              "Cancel anytime",
            ].map((b) => (
              <View key={b} style={styles.bulletRow}>
                <Ionicons name="checkmark-circle" size={18} color={colors.brandPrimary} />
                <Text style={styles.bulletText}>{b}</Text>
              </View>
            ))}
          </View>
          <Pressable
            disabled={!!busy}
            onPress={() => startCheckout("sub")}
            style={[styles.cta, busy && { opacity: 0.6 }]}
            testID="paywall-subscribe"
          >
            {busy === "sub" ? <ActivityIndicator color={colors.onBrandPrimary} /> : (
              <>
                <Ionicons name="lock-open" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.ctaText}>Subscribe — $9.99/mo</Text>
              </>
            )}
          </Pressable>
        </View>

        <View style={styles.divider}><Text style={styles.dividerText}>OR</Text></View>

        <View style={styles.creditsCard} testID="paywall-credits-card">
          <Text style={styles.cardLabel}>Need credits for AI therapist chat?</Text>
          <Text style={styles.cardSub}>200 credits for $4.99 — works alongside or without subscription.</Text>
          <Pressable
            disabled={!!busy}
            onPress={() => startCheckout("credits")}
            style={[styles.ctaOutline, busy && { opacity: 0.6 }]}
            testID="paywall-buy-credits"
          >
            {busy === "credits" ? <ActivityIndicator color={colors.brandPrimary} /> :
              <Text style={styles.ctaOutlineText}>Buy 200 credits — $4.99</Text>}
          </Pressable>
        </View>

        {error && <Text style={styles.error}>{error}</Text>}
        {pendingSession && !error && (
          <Text style={styles.waiting}>Waiting for payment to complete… you can close this and we'll auto-unlock.</Text>
        )}
        <Text style={styles.legal}>Recurring monthly subscription. Cancel anytime from your account.</Text>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface, padding: spacing.lg, paddingTop: 64 },
  closeBtn: { position: "absolute", top: 48, right: 16, width: 40, height: 40, alignItems: "center", justifyContent: "center", zIndex: 10 },
  hero: { alignItems: "center", marginBottom: spacing.lg },
  crown: { width: 72, height: 72, borderRadius: 36, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  title: { fontSize: 24, fontWeight: "800", color: colors.onSurface, textAlign: "center" },
  subtitle: { fontSize: 15, color: colors.onSurfaceSecondary, textAlign: "center", marginTop: spacing.sm, lineHeight: 22 },
  planCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md },
  planHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline" },
  planName: { fontSize: 17, fontWeight: "800", color: colors.onBrandTertiary },
  planPrice: { fontSize: 26, fontWeight: "800", color: colors.onBrandTertiary },
  planPriceSlash: { fontSize: 14, fontWeight: "600", color: colors.onBrandTertiary },
  bullets: { gap: 6 },
  bulletRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  bulletText: { fontSize: 14, color: colors.onBrandTertiary, fontWeight: "500" },
  cta: { backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: 14, flexDirection: "row", gap: 8, justifyContent: "center", alignItems: "center", minHeight: 52 },
  ctaText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 16 },
  divider: { alignItems: "center", marginVertical: spacing.lg },
  dividerText: { color: colors.onSurfaceTertiary, fontWeight: "700", letterSpacing: 1 },
  creditsCard: { borderWidth: 1, borderColor: colors.divider, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  cardLabel: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  cardSub: { fontSize: 13, color: colors.onSurfaceSecondary },
  ctaOutline: { borderWidth: 2, borderColor: colors.brandPrimary, borderRadius: radius.lg, padding: 12, alignItems: "center", marginTop: spacing.sm, minHeight: 48 },
  ctaOutlineText: { color: colors.brandPrimary, fontWeight: "800", fontSize: 15 },
  error: { color: colors.brandSecondary, fontSize: 13, marginTop: spacing.md, textAlign: "center" },
  waiting: { color: colors.brandPrimary, fontSize: 13, marginTop: spacing.md, textAlign: "center" },
  legal: { color: colors.onSurfaceTertiary, fontSize: 11, marginTop: spacing.lg, textAlign: "center" },
});
