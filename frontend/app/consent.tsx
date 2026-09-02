import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";

import { LegalDocument } from "@/src/components/LegalDocument";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { getCachedUser, setConsentAccepted } from "@/src/auth";
import { LEGAL_EFFECTIVE_DATE, LEGAL_VERSION, TERMS_INTRO, TERMS_SECTIONS } from "@/src/legalContent";
import { colors, radius, spacing } from "@/src/theme";

export default function ConsentScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { palette } = useDisplayPreferences();
  const [termsChecked, setTermsChecked] = useState(false);
  const [healthChecked, setHealthChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const ready = termsChecked && healthChecked;

  const onAccept = async () => {
    if (!ready || saving) return;
    setSaving(true);
    setError("");
    try {
      const user = await getCachedUser();
      if (!user?.id) {
        router.replace("/sign-in");
        return;
      }
      await setConsentAccepted(user.id);
      await Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      router.replace("/");
    } catch {
      setError("We could not save your choices. Check your connection and try again.");
      setSaving(false);
    }
  };

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm, backgroundColor: palette.surface, borderBottomColor: palette.border }]}>
        <View style={styles.brandMark}><Ionicons name="pulse" size={22} color="#FFFFFF" /></View>
        <View style={styles.headerCopy}>
          <Text style={[styles.headerTitle, { color: palette.text }]}>Terms of Use</Text>
          <Text style={[styles.headerMeta, { color: palette.muted }]}>Version {LEGAL_VERSION} · Effective date: {LEGAL_EFFECTIVE_DATE}</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, { paddingBottom: Math.max(insets.bottom, spacing.lg) + spacing.xl }]} showsVerticalScrollIndicator={false}>
        <View style={styles.page}>
          <Text style={[styles.documentTitle, { color: palette.text }]}>REHYN APP TERMS OF USE</Text>
          <Text style={[styles.company, { color: palette.muted }]}>Rehyn Ltd · Company number 17417716 · info@rehyn.com</Text>
          <LegalDocument intro={TERMS_INTRO} sections={TERMS_SECTIONS} palette={palette} />

          <View style={[styles.dataCard, { backgroundColor: palette.soft, borderColor: palette.border }]}>
            <View style={styles.dataIcon}><Ionicons name="lock-closed-outline" size={24} color={palette.brand} /></View>
            <View style={styles.dataCopy}>
              <Text style={[styles.dataEyebrow, { color: palette.brand }]}>DATA AND USAGE</Text>
              <Text style={[styles.dataTitle, { color: palette.text }]}>See how Rehyn uses your information</Text>
              <Text style={[styles.dataBody, { color: palette.muted }]}>Read the full Data and permissions information, including movement videos, model improvement and your rights.</Text>
            </View>
            <Ionicons name="chevron-forward" size={22} color={palette.muted} />
            <Pressable testID="consent-open-data-usage" accessibilityRole="link" accessibilityLabel="Read Data and Usage" onPress={() => router.push({ pathname: "/data-permissions" as never, params: { from: "consent" } })} style={StyleSheet.absoluteFill} />
          </View>

          <View style={[styles.acknowledgements, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Text style={[styles.ackTitle, { color: palette.text }]}>Your agreement</Text>
            <CheckboxRow testID="consent-terms-checkbox" checked={termsChecked} onPress={() => setTermsChecked((value) => !value)} text="I have read and agree to the Rehyn Terms of Use." palette={palette} />
            <View style={[styles.divider, { backgroundColor: palette.border }]} />
            <CheckboxRow testID="consent-health-checkbox" checked={healthChecked} onPress={() => setHealthChecked((value) => !value)} text="I give explicit permission for Rehyn to use my health information, assessment answers, movement recordings and derived measurements to provide my plan and progress. I can withdraw this permission in Settings." palette={palette} />
            <Text style={[styles.optionalNote, { color: palette.muted }]}>This does not opt you into model improvement. Help improve Rehyn is a separate, optional choice that is off by default.</Text>
          </View>

          {error ? <Text testID="consent-save-error" accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
          <Pressable testID="consent-accept" disabled={!ready || saving} onPress={onAccept} style={[styles.acceptButton, (!ready || saving) && styles.acceptButtonDisabled]}>
            {saving ? <ActivityIndicator color="#FFFFFF" /> : <><Text style={styles.acceptText}>Accept and continue</Text><Ionicons name="arrow-forward" size={20} color="#FFFFFF" /></>}
          </Pressable>
        </View>
      </ScrollView>
    </View>
  );
}

function CheckboxRow({ checked, onPress, text, testID, palette }: { checked: boolean; onPress: () => void; text: string; testID: string; palette: ReturnType<typeof useDisplayPreferences>["palette"] }) {
  return (
    <Pressable testID={testID} accessibilityRole="checkbox" accessibilityState={{ checked }} onPress={onPress} style={styles.checkRow}>
      <Ionicons name={checked ? "checkbox" : "square-outline"} size={28} color={checked ? palette.brand : palette.muted} />
      <Text style={[styles.checkText, { color: palette.text }]}>{text}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { minHeight: 72, paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  brandMark: { width: 42, height: 42, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  headerCopy: { flex: 1 }, headerTitle: { fontSize: 20, fontWeight: "800" }, headerMeta: { fontSize: 12, lineHeight: 17, marginTop: 2 },
  scroll: { padding: spacing.md }, page: { width: "100%", maxWidth: 780, alignSelf: "center" },
  documentTitle: { fontSize: 28, lineHeight: 35, fontWeight: "900", marginTop: spacing.md }, company: { fontSize: 13, lineHeight: 19, marginTop: spacing.xs, marginBottom: spacing.xl },
  dataCard: { position: "relative", minHeight: 132, borderWidth: 1, borderRadius: radius.md, padding: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.md, marginTop: spacing.sm, marginBottom: spacing.xl },
  dataIcon: { width: 48, height: 48, borderRadius: 24, backgroundColor: "rgba(47,128,83,0.10)", alignItems: "center", justifyContent: "center" }, dataCopy: { flex: 1 },
  dataEyebrow: { fontSize: 11, fontWeight: "900" }, dataTitle: { fontSize: 17, lineHeight: 23, fontWeight: "800", marginTop: 3 }, dataBody: { fontSize: 13, lineHeight: 19, marginTop: 4 },
  acknowledgements: { borderWidth: 1, borderRadius: radius.md, padding: spacing.md, gap: spacing.md }, ackTitle: { fontSize: 20, fontWeight: "800" }, checkRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, minHeight: 48 },
  checkText: { flex: 1, fontSize: 15, lineHeight: 22, fontWeight: "600" }, divider: { height: 1 }, optionalNote: { fontSize: 13, lineHeight: 19 },
  error: { color: colors.error, fontSize: 14, lineHeight: 20, fontWeight: "700", marginTop: spacing.md },
  acceptButton: { minHeight: 58, borderRadius: radius.md, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  acceptButtonDisabled: { opacity: 0.4 }, acceptText: { color: "#FFFFFF", fontSize: 17, fontWeight: "800" },
});
