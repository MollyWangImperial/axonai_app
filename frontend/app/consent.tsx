import { useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { getCachedUser, setConsentAccepted } from "@/src/auth";

const POINTS: { icon: keyof typeof Ionicons.glyphMap; title: string; body: string }[] = [
  {
    icon: "heart-outline",
    title: "Coaching, not diagnosis",
    body: "Rehyn helps you practise and track movement. It does not diagnose conditions or replace advice from your doctor or therapist.",
  },
  {
    icon: "shield-checkmark-outline",
    title: "Move safely",
    body: "Only attempt movements that feel safe. Sit down for tasks when advised, use your usual walking aid, and have someone nearby for standing or walking.",
  },
  {
    icon: "alert-circle-outline",
    title: "Stop if something feels wrong",
    body: "Stop right away and seek medical help if you feel pain, dizziness, chest discomfort, or become unwell during a session.",
  },
  {
    icon: "lock-closed-outline",
    title: "Your data",
    body: "Your profile, answers, and movement recordings are used to personalise your coaching. They are never sold or used for advertising.",
  },
];

export default function ConsentScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);

  const onAccept = async () => {
    if (!checked || saving) return;
    setSaving(true);
    Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    const user = await getCachedUser();
    if (user?.id) await setConsentAccepted(user.id);
    router.replace("/onboarding");
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.lg }]}>
      <View style={styles.brand}>
        <Ionicons name="heart" size={26} color={colors.brandPrimary} />
        <Text style={styles.brandText}>Rehyn</Text>
      </View>
      <Text style={styles.title}>Before we begin</Text>
      <Text style={styles.subtitle}>Please read and agree so we can keep your sessions safe and helpful.</Text>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        {POINTS.map((point) => (
          <View key={point.title} style={styles.card} testID={`consent-point-${point.icon}`}>
            <View style={styles.cardIcon}><Ionicons name={point.icon} size={22} color={colors.brandPrimary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>{point.title}</Text>
              <Text style={styles.cardBody}>{point.body}</Text>
            </View>
          </View>
        ))}
        <Text style={styles.emergency}>
          Rehyn is not for emergencies. If you think you are having a stroke or medical emergency, call your local emergency number immediately.
        </Text>
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable testID="consent-checkbox" onPress={() => setChecked((v) => !v)} style={styles.checkRow}>
          <Ionicons name={checked ? "checkbox" : "square-outline"} size={26} color={checked ? colors.brandPrimary : colors.onSurfaceTertiary} />
          <Text style={styles.checkText}>
            I understand Rehyn is a movement coaching tool, not a medical diagnosis, and I will move safely.
          </Text>
        </Pressable>
        <Pressable
          testID="consent-accept"
          disabled={!checked || saving}
          onPress={onAccept}
          style={[styles.acceptBtn, (!checked || saving) && styles.acceptBtnDisabled]}
        >
          <Text style={styles.acceptText}>Agree and continue</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface, paddingHorizontal: spacing.lg },
  brand: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: spacing.md },
  brandText: { color: colors.brandPrimary, fontWeight: "800", fontSize: 20, letterSpacing: 0.5 },
  title: { fontSize: 28, lineHeight: 34, fontWeight: "800", color: colors.onSurface },
  subtitle: { fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary, marginTop: spacing.xs },
  scroll: { paddingTop: spacing.lg, paddingBottom: spacing.lg, gap: spacing.sm },
  card: { flexDirection: "row", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  cardIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary },
  cardTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  cardBody: { fontSize: 14, lineHeight: 20, color: colors.onSurfaceSecondary, marginTop: 3 },
  emergency: { marginTop: spacing.sm, fontSize: 13, lineHeight: 19, fontWeight: "700", color: colors.error },
  footer: { paddingTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.divider, gap: spacing.md },
  checkRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm },
  checkText: { flex: 1, fontSize: 14, lineHeight: 20, fontWeight: "600", color: colors.onSurface },
  acceptBtn: { minHeight: 56, borderRadius: radius.md, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  acceptBtnDisabled: { opacity: 0.4 },
  acceptText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "800" },
});
