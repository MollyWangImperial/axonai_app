import { useEffect, useState } from "react";
import { Linking, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { authedFetch } from "@/src/auth";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { LEGAL_VERSION } from "@/src/legalContent";
import { colors, radius, spacing } from "@/src/theme";
import { DEFAULT_SETTINGS, ensurePermission, loadSettings, rescheduleReminders, saveSettings } from "@/src/utils/notifications";

export default function DataPermissionsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { palette } = useDisplayPreferences();
  const [healthConsent, setHealthConsent] = useState(false);
  const [improvement, setImprovement] = useState(false);
  const [reminders, setReminders] = useState(DEFAULT_SETTINGS.enabled);
  const [cameraStatus, setCameraStatus] = useState("Tap to review");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    void Promise.all([
      authedFetch("/api/users/data-permissions").then((response) => response.ok ? response.json() : null).catch(() => null),
      authedFetch("/api/users/consent").then((response) => response.ok ? response.json() : null).catch(() => null),
      loadSettings(),
    ]).then(([permissions, consent, settings]) => {
      setImprovement(Boolean(permissions?.model_improvement));
      setHealthConsent(Boolean(consent?.accepted));
      setReminders(settings.enabled);
    });
  }, []);

  const toggleImprovement = async (enabled: boolean) => {
    setImprovement(enabled);
    const response = await authedFetch("/api/users/data-permissions", {
      method: "POST",
      body: JSON.stringify({ key: "model_improvement", enabled, version: LEGAL_VERSION }),
    }).catch(() => null);
    if (!response?.ok) {
      setImprovement(!enabled);
      setNotice("We could not save that choice. Please try again.");
      return;
    }
    setNotice(enabled ? "Help improve Rehyn is on." : "Help improve Rehyn is off. Future improvement use has stopped.");
  };

  const toggleNotifications = async (enabled: boolean) => {
    if (enabled && Platform.OS !== "web" && !(await ensurePermission())) {
      setNotice("Notifications are blocked. Allow them in device settings, then try again.");
      return;
    }
    if (enabled && Platform.OS === "web" && "Notification" in window) {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setNotice("Notifications are blocked in this browser.");
        return;
      }
    }
    const next = { ...(await loadSettings()), enabled };
    setReminders(enabled);
    await saveSettings(next);
    await rescheduleReminders(next);
    setNotice(enabled ? "Reminders and encouragement are on." : "Reminders and encouragement are off.");
  };

  const reviewCamera = async () => {
    if (Platform.OS !== "web") {
      await Linking.openSettings();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      stream.getTracks().forEach((track) => track.stop());
      setCameraStatus("Camera permission granted");
    } catch {
      setCameraStatus("Camera blocked - open browser site settings");
    }
  };

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm, backgroundColor: palette.surface, borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} style={styles.headerButton} accessibilityLabel="Go back"><Ionicons name="chevron-back" size={25} color={palette.text} /></Pressable>
        <Text style={[styles.headerTitle, { color: palette.text }]}>Data and permissions</Text>
        <View style={styles.headerButton} />
      </View>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingBottom: Math.max(insets.bottom, spacing.lg) + spacing.xl }]} showsVerticalScrollIndicator={false}>
        <View style={styles.page}>
          <Text style={[styles.title, { color: palette.text }]}>Your information, your choices</Text>
          <Text style={[styles.intro, { color: palette.muted }]}>Control how Rehyn uses your information. You can change these choices at any time.</Text>
          {notice ? <View style={[styles.notice, { backgroundColor: palette.soft }]}><Ionicons name="checkmark-circle" size={20} color={colors.success} /><Text style={[styles.noticeText, { color: palette.text }]}>{notice}</Text></View> : null}

          <SectionLabel text="YOUR HEALTH INFORMATION" color={palette.muted} />
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={styles.rowTop}><View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="medical-outline" size={23} color={palette.brand} /></View><View style={styles.copy}><Text style={[styles.cardTitle, { color: palette.text }]}>Using my health information to build my plan</Text><Text style={healthConsent ? styles.active : styles.pending}>{healthConsent ? `ON · Given with Terms version ${LEGAL_VERSION}` : "NOT YET GIVEN · Return to Terms to continue"}</Text></View></View>
            <Text style={[styles.body, { color: palette.muted }]}>Rehyn uses your movement videos, measurements, assessment answers and goals to build and adapt your rehabilitation plan and show your progress. This is sensitive information, so we use it only with your explicit permission.</Text>
            <Text style={[styles.body, { color: palette.muted }]}>Withdrawing this permission means Rehyn can no longer provide your rehabilitation plan. Your account can remain open. Contact info@rehyn.com to withdraw or ask a question.</Text>
          </View>

          <SectionLabel text="IMPROVING REHYN" color={palette.muted} />
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={styles.toggleRow}><View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="sparkles-outline" size={23} color={palette.brand} /></View><View style={styles.copy}><Text style={[styles.cardTitle, { color: palette.text }]}>Help improve Rehyn</Text><Text style={[styles.optional, { color: palette.muted }]}>Optional · Off by default</Text></View><Switch testID="data-improvement-toggle" value={improvement} onValueChange={toggleImprovement} trackColor={{ false: "#8AA198", true: palette.brand }} thumbColor="#FFFFFF" /></View>
            <Text style={[styles.body, { color: palette.muted }]}>When this is on, we may use movement measurements, assessment results, activity completion and feedback to train, test and improve Rehyn's technology and accuracy. We remove your name, email and account details and replace them with a code.</Text>
            <Text style={[styles.body, { color: palette.muted }]}>Raw movement videos are not used for model training. This choice does not affect your features. Turning it off stops future use for improvement, although it may not be possible to remove the influence of information already used to train a model.</Text>
          </View>

          <SectionLabel text="KEEPING YOUR VIDEOS" color={palette.muted} />
          <InfoCard icon="videocam-off-outline" title="Raw movement videos are not kept for playback" body="Rehyn processes a raw video to create movement measurements, then deletes it within the retention period stated in the Privacy Notice. A keep-videos option is not enabled." palette={palette} />

          <SectionLabel text="NOTIFICATIONS" color={palette.muted} />
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={styles.toggleRow}><View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="notifications-outline" size={23} color={palette.brand} /></View><View style={styles.copy}><Text style={[styles.cardTitle, { color: palette.text }]}>Reminders and encouragement</Text><Text style={[styles.optional, { color: palette.muted }]}>Session reminders and Alira prompts</Text></View><Switch testID="data-notifications-toggle" value={reminders} onValueChange={toggleNotifications} trackColor={{ false: "#8AA198", true: palette.brand }} thumbColor="#FFFFFF" /></View>
            <Text style={[styles.body, { color: palette.muted }]}>Notifications do not include sensitive health details on the lock screen.</Text>
          </View>

          <SectionLabel text="DEVICE PERMISSIONS" color={palette.muted} />
          <Pressable testID="data-camera-permission" onPress={reviewCamera} style={[styles.actionCard, { backgroundColor: palette.surface, borderColor: palette.border }]}><View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="camera-outline" size={23} color={palette.brand} /></View><View style={styles.copy}><Text style={[styles.cardTitle, { color: palette.text }]}>Camera</Text><Text style={[styles.optional, { color: palette.muted }]}>{cameraStatus}</Text></View><Ionicons name="chevron-forward" size={21} color={palette.muted} /></Pressable>

          <SectionLabel text="YOUR DATA" color={palette.muted} />
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border, paddingVertical: 0 }]}>
            <ActionRow icon="download-outline" title="Request a copy of my data" onPress={() => Linking.openURL("mailto:info@rehyn.com?subject=Rehyn%20data%20access%20request")} palette={palette} />
            <Divider color={palette.border} />
            <ActionRow icon="create-outline" title="Correct my information" onPress={() => router.push({ pathname: "/account-center" as never, params: { section: "personal" } })} palette={palette} />
            <Divider color={palette.border} />
            <ActionRow icon="trash-outline" title="Delete my account and data" onPress={() => router.push({ pathname: "/account-center" as never, params: { section: "account" } })} palette={palette} danger />
          </View>

          <SectionLabel text="DOCUMENTS AND CONTACT" color={palette.muted} />
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border, paddingVertical: 0 }]}>
            <ActionRow icon="shield-checkmark-outline" title="Privacy Notice" onPress={() => router.push("/privacy-policy" as never)} palette={palette} />
            <Divider color={palette.border} />
            <ActionRow icon="document-text-outline" title="Terms of Use" onPress={() => router.push("/terms-of-use" as never)} palette={palette} />
            <Divider color={palette.border} />
            <ActionRow icon="mail-outline" title="Questions: info@rehyn.com" onPress={() => Linking.openURL("mailto:info@rehyn.com")} palette={palette} />
          </View>
          <Text style={[styles.ico, { color: palette.muted }]}>You can complain to the Information Commissioner's Office at ico.org.uk or 0303 123 1113.</Text>
        </View>
      </ScrollView>
    </View>
  );
}

function SectionLabel({ text, color }: { text: string; color: string }) { return <Text style={[styles.sectionLabel, { color }]}>{text}</Text>; }
function Divider({ color }: { color: string }) { return <View style={[styles.divider, { backgroundColor: color }]} />; }
function InfoCard({ icon, title, body, palette }: { icon: keyof typeof Ionicons.glyphMap; title: string; body: string; palette: ReturnType<typeof useDisplayPreferences>["palette"] }) { return <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}><View style={styles.rowTop}><View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name={icon} size={23} color={palette.brand} /></View><Text style={[styles.cardTitle, styles.copy, { color: palette.text }]}>{title}</Text></View><Text style={[styles.body, { color: palette.muted }]}>{body}</Text></View>; }
function ActionRow({ icon, title, onPress, palette, danger = false }: { icon: keyof typeof Ionicons.glyphMap; title: string; onPress: () => void; palette: ReturnType<typeof useDisplayPreferences>["palette"]; danger?: boolean }) { return <Pressable onPress={onPress} style={styles.actionRow}><Ionicons name={icon} size={22} color={danger ? colors.error : palette.brand} /><Text style={[styles.actionText, { color: danger ? colors.error : palette.text }]}>{title}</Text><Ionicons name="chevron-forward" size={20} color={palette.muted} /></Pressable>; }

const styles = StyleSheet.create({
  container: { flex: 1 }, header: { minHeight: 58, paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, headerButton: { width: 42, height: 42, alignItems: "center", justifyContent: "center" }, headerTitle: { fontSize: 18, fontWeight: "800" },
  scroll: { padding: spacing.md }, page: { width: "100%", maxWidth: 720, alignSelf: "center" }, title: { fontSize: 28, lineHeight: 35, fontWeight: "900", marginTop: spacing.md }, intro: { fontSize: 15, lineHeight: 22, marginTop: spacing.xs, marginBottom: spacing.md },
  notice: { minHeight: 48, borderRadius: radius.sm, padding: spacing.sm, flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.sm }, noticeText: { flex: 1, fontSize: 13, lineHeight: 19, fontWeight: "600" },
  sectionLabel: { fontSize: 11, fontWeight: "900", marginTop: spacing.lg, marginBottom: spacing.xs }, card: { borderWidth: 1, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm }, rowTop: { flexDirection: "row", alignItems: "center", gap: spacing.sm }, toggleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  icon: { width: 46, height: 46, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" }, copy: { flex: 1 }, cardTitle: { fontSize: 16, lineHeight: 22, fontWeight: "800" }, active: { color: colors.success, fontSize: 12, fontWeight: "800", marginTop: 2 }, pending: { color: colors.warning, fontSize: 12, fontWeight: "800", marginTop: 2 }, optional: { fontSize: 12, lineHeight: 17, marginTop: 2 }, body: { fontSize: 14, lineHeight: 21 },
  actionCard: { minHeight: 76, borderWidth: 1, borderRadius: radius.md, padding: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.sm }, actionRow: { minHeight: 62, flexDirection: "row", alignItems: "center", gap: spacing.sm }, actionText: { flex: 1, fontSize: 15, fontWeight: "700" }, divider: { height: 1, marginLeft: 34 }, ico: { fontSize: 13, lineHeight: 19, marginTop: spacing.md },
});
