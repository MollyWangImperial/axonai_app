import { useCallback, useEffect, useState } from "react";
import { Linking, Modal, Platform, Pressable, ScrollView, Share, StyleSheet, Switch, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Notifications from "expo-notifications";
import * as ImagePicker from "expo-image-picker";

import { authedFetch } from "@/src/auth";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { colors, radius, spacing } from "@/src/theme";
import { ensurePermission, loadSettings, rescheduleReminders, saveSettings } from "@/src/utils/notifications";

// Screen copy follows the "Data and Permissions Screen" specification v1.0.
// Copy is implemented as written; changes to consent wording require legal review.

function formatGivenDate(value?: string): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}

export default function DataPermissionsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { palette } = useDisplayPreferences();
  const [healthConsent, setHealthConsent] = useState(false);
  const [healthGivenAt, setHealthGivenAt] = useState("");
  const [healthEverGiven, setHealthEverGiven] = useState(false);
  const [showHealthOffConfirm, setShowHealthOffConfirm] = useState(false);
  const [improvement, setImprovement] = useState(false);
  const [showImprovementOffDone, setShowImprovementOffDone] = useState(false);
  const [marketing, setMarketing] = useState(false);
  const [reminders, setReminders] = useState(true);
  const [cameraStatus, setCameraStatus] = useState("Checking...");
  const [notificationStatus, setNotificationStatus] = useState("Checking...");
  const [notice, setNotice] = useState("");

  const refreshDevicePermissions = useCallback(async () => {
    // Build note: mirror the live operating system state; never assert a
    // permission is granted without checking. These calls only read state and
    // never trigger a permission prompt.
    try {
      if (Platform.OS === "web") {
        const query = (navigator as unknown as { permissions?: { query: (d: { name: string }) => Promise<{ state: string }> } }).permissions;
        if (query) {
          const camera = await query.query({ name: "camera" }).catch(() => null);
          setCameraStatus(camera ? (camera.state === "granted" ? "Granted" : "Not granted") : "Not granted");
        } else {
          setCameraStatus("Not granted");
        }
        if ("Notification" in window) {
          setNotificationStatus(Notification.permission === "granted" ? "Granted" : "Not granted");
        } else {
          setNotificationStatus("Not granted");
        }
      } else {
        const camera = await ImagePicker.getCameraPermissionsAsync();
        setCameraStatus(camera.status === "granted" ? "Granted" : "Not granted");
        const notification = await Notifications.getPermissionsAsync();
        setNotificationStatus(notification.status === "granted" ? "Granted" : "Not granted");
      }
    } catch {
      setCameraStatus("Not granted");
      setNotificationStatus("Not granted");
    }
  }, []);

  useEffect(() => {
    void Promise.all([
      authedFetch("/api/users/data-permissions").then((response) => (response.ok ? response.json() : null)).catch(() => null),
      authedFetch("/api/users/consent").then((response) => (response.ok ? response.json() : null)).catch(() => null),
      loadSettings(),
    ]).then(async ([permissions, consentPayload, localReminderSettings]) => {
      setImprovement(Boolean(permissions?.model_improvement));
      setMarketing(Boolean(permissions?.marketing_updates));
      const consent = consentPayload?.consent || {};
      setHealthConsent(consent.health_data_consent === true);
      setHealthEverGiven(Boolean(consent.accepted_at || consent.health_consent_given_at));
      setHealthGivenAt(formatGivenDate(consent.health_consent_given_at || consent.accepted_at));
      // Consent is held against the account, not the device: the server value
      // wins, and the local scheduler is brought in line with it.
      const serverReminders = permissions ? Boolean(permissions.reminders) : localReminderSettings.enabled;
      setReminders(serverReminders);
      if (permissions && localReminderSettings.enabled !== serverReminders) {
        const next = { ...localReminderSettings, enabled: serverReminders };
        await saveSettings(next);
        await rescheduleReminders(next);
      }
    });
    void refreshDevicePermissions();
  }, [refreshDevicePermissions]);

  const savePermission = async (key: string, enabled: boolean): Promise<boolean> => {
    const response = await authedFetch("/api/users/data-permissions", {
      method: "POST",
      body: JSON.stringify({ key, enabled }),
    }).catch(() => null);
    return Boolean(response?.ok);
  };

  const toggleHealth = (enabled: boolean) => {
    if (!enabled) {
      // Build note (spec section 1): switching this off must trigger the
      // confirmation screen in section 2.2. Do not allow a silent toggle.
      setShowHealthOffConfirm(true);
      return;
    }
    void (async () => {
      const response = await authedFetch("/api/users/consent/health", {
        method: "POST",
        body: JSON.stringify({ enabled: true }),
      }).catch(() => null);
      if (!response?.ok) {
        setNotice(
          response?.status === 409
            ? "Please review and accept the current Terms of Use first."
            : "We could not save that choice. Please try again."
        );
        return;
      }
      const payload = await response.json().catch(() => null);
      setHealthConsent(true);
      setHealthEverGiven(true);
      setHealthGivenAt(formatGivenDate(payload?.consent?.health_consent_given_at || payload?.changed_at));
      setNotice("Your permission to use your health information is back on.");
    })();
  };

  const confirmHealthOff = async () => {
    const response = await authedFetch("/api/users/consent/health", {
      method: "POST",
      body: JSON.stringify({ enabled: false }),
    }).catch(() => null);
    setShowHealthOffConfirm(false);
    if (!response?.ok) {
      setNotice("We could not save that choice. Please try again.");
      return;
    }
    setHealthConsent(false);
    setNotice("Your permission is off. Plan generation and progress tracking are paused. You can turn this back on at any time.");
  };

  const toggleImprovement = async (enabled: boolean) => {
    setImprovement(enabled);
    if (!(await savePermission("model_improvement", enabled))) {
      setImprovement(!enabled);
      setNotice("We could not save that choice. Please try again.");
      return;
    }
    if (enabled) setNotice("Help improve Rehyn is on.");
    else setShowImprovementOffDone(true); // Confirmation screen 2.1 — one tap, confirmed, finished.
  };

  const toggleMarketing = async (enabled: boolean) => {
    setMarketing(enabled);
    if (!(await savePermission("marketing_updates", enabled))) {
      setMarketing(!enabled);
      setNotice("We could not save that choice. Please try again.");
      return;
    }
    setNotice(enabled ? "Updates about Rehyn are on." : "Updates about Rehyn are off.");
  };

  const toggleReminders = async (enabled: boolean) => {
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
    setReminders(enabled);
    if (!(await savePermission("reminders", enabled))) {
      setReminders(!enabled);
      setNotice("We could not save that choice. Please try again.");
      return;
    }
    const next = { ...(await loadSettings()), enabled };
    await saveSettings(next);
    await rescheduleReminders(next);
    await refreshDevicePermissions();
    setNotice(enabled ? "Reminders and encouragement are on." : "Reminders and encouragement are off.");
  };

  const manageDevicePermission = async () => {
    if (Platform.OS !== "web") {
      await Linking.openSettings();
      await refreshDevicePermissions();
      return;
    }
    setNotice("Manage camera and notification access in your browser's site settings, then return here.");
  };

  const downloadMyData = async () => {
    setNotice("Preparing your copy...");
    const response = await authedFetch("/api/users/data-export").catch(() => null);
    if (!response?.ok) {
      setNotice("We could not prepare your copy right now. Please try again, or email info@rehyn.com.");
      return;
    }
    const data = await response.json().catch(() => null);
    if (!data) {
      setNotice("We could not prepare your copy right now. Please try again, or email info@rehyn.com.");
      return;
    }
    const serialized = JSON.stringify(data, null, 2);
    if (Platform.OS === "web") {
      const blob = new Blob([serialized], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "rehyn-my-data.json";
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setNotice("Your copy has been downloaded as rehyn-my-data.json.");
      return;
    }
    try {
      await Share.share({ title: "My Rehyn data", message: serialized });
      setNotice("Your copy is ready to save from the share sheet.");
    } catch {
      setNotice("We could not open the share sheet. Please try again, or email info@rehyn.com.");
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
          <Text style={[styles.intro, { color: palette.muted }]}>Control how Rehyn uses your information. You can change these at any time.</Text>
          {notice ? <View style={[styles.notice, { backgroundColor: palette.soft }]}><Ionicons name="checkmark-circle" size={20} color={colors.success} /><Text style={[styles.noticeText, { color: palette.text }]}>{notice}</Text></View> : null}

          <SectionLabel text="YOUR HEALTH INFORMATION" color={palette.muted} />
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={styles.toggleRow}>
              <View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="medical-outline" size={23} color={palette.brand} /></View>
              <View style={styles.copy}>
                <Text style={[styles.cardTitle, { color: palette.text }]}>Using my health information to build my plan</Text>
                <Text style={healthConsent ? styles.active : styles.pending}>
                  {healthConsent
                    ? `ON${healthGivenAt ? ` · Given on ${healthGivenAt}` : ""}`
                    : healthEverGiven
                      ? "OFF · You can turn this back on at any time"
                      : "NOT YET GIVEN · Return to Terms to continue"}
                </Text>
              </View>
              <Switch testID="data-health-toggle" value={healthConsent} onValueChange={toggleHealth} trackColor={{ false: "#8AA198", true: palette.brand }} thumbColor="#FFFFFF" />
            </View>
            <Text style={[styles.body, { color: palette.muted }]}>Rehyn uses your movement videos, the measurements taken from them, your assessment answers and your goals to build and adapt your rehabilitation plan and show your progress. This is sensitive information, so we need your permission to use it.</Text>
            <Text style={[styles.body, { color: palette.muted }]}>Turning this off means we can no longer provide your rehabilitation plan. Your account will stay open and you can turn it back on whenever you want.</Text>
          </View>

          <SectionLabel text="IMPROVING REHYN" color={palette.muted} />
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={styles.toggleRow}>
              <View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="sparkles-outline" size={23} color={palette.brand} /></View>
              <View style={styles.copy}>
                <Text style={[styles.cardTitle, { color: palette.text }]}>Help improve Rehyn</Text>
                <Text style={[styles.optional, { color: palette.muted }]}>Optional</Text>
              </View>
              <Switch testID="data-improvement-toggle" value={improvement} onValueChange={toggleImprovement} trackColor={{ false: "#8AA198", true: palette.brand }} thumbColor="#FFFFFF" />
            </View>
            <Text style={[styles.body, { color: palette.muted }]}>When this is on, we may use your movement measurements, assessment results, activity completion and feedback to train, test and improve Rehyn&apos;s technology and accuracy. Before we do, we remove your name, email address and account details and replace them with a code.</Text>
            <Text style={[styles.body, { color: palette.muted }]}>Your raw videos are used only to take the measurements and are then deleted. They are not used for training.</Text>
            <Text style={[styles.body, { color: palette.muted }]}>This is optional. Every feature and your full rehabilitation plan work exactly the same either way. Turning it off stops any further use from the moment you switch it.</Text>
            <Pressable testID="data-improvement-learn-more" accessibilityRole="link" onPress={() => router.push("/privacy-policy" as never)}>
              <Text style={[styles.learnMore, { color: palette.brand }]}>Learn more about how we improve Rehyn</Text>
            </Pressable>
          </View>

          <SectionLabel text="NOTIFICATIONS" color={palette.muted} />
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={styles.toggleRow}>
              <View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="notifications-outline" size={23} color={palette.brand} /></View>
              <View style={styles.copy}><Text style={[styles.cardTitle, { color: palette.text }]}>Reminders and encouragement</Text></View>
              <Switch testID="data-notifications-toggle" value={reminders} onValueChange={toggleReminders} trackColor={{ false: "#8AA198", true: palette.brand }} thumbColor="#FFFFFF" />
            </View>
            <Text style={[styles.body, { color: palette.muted }]}>Prompts from Alira to help you keep going with your plan.</Text>
          </View>
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border, marginTop: spacing.sm }]}>
            <View style={styles.toggleRow}>
              <View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="mail-unread-outline" size={23} color={palette.brand} /></View>
              <View style={styles.copy}>
                <Text style={[styles.cardTitle, { color: palette.text }]}>Updates about Rehyn</Text>
                <Text style={[styles.optional, { color: palette.muted }]}>Optional · Off by default</Text>
              </View>
              <Switch testID="data-marketing-toggle" value={marketing} onValueChange={toggleMarketing} trackColor={{ false: "#8AA198", true: palette.brand }} thumbColor="#FFFFFF" />
            </View>
            <Text style={[styles.body, { color: palette.muted }]}>Occasional emails about new features and how Rehyn is developing. Nothing about your health is included.</Text>
          </View>

          <SectionLabel text="DEVICE PERMISSIONS" color={palette.muted} />
          <Pressable testID="data-camera-permission" onPress={manageDevicePermission} style={[styles.actionCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="camera-outline" size={23} color={palette.brand} /></View>
            <View style={styles.copy}>
              <Text style={[styles.cardTitle, { color: palette.text }]}>Camera</Text>
              <Text style={[styles.optional, { color: palette.muted }]}>{cameraStatus} · Manage in device settings</Text>
              <Text style={[styles.permissionBody, { color: palette.muted }]}>Needed to record your movement assessments.</Text>
            </View>
            <Ionicons name="chevron-forward" size={21} color={palette.muted} />
          </Pressable>
          <Pressable testID="data-device-notifications-permission" onPress={manageDevicePermission} style={[styles.actionCard, { backgroundColor: palette.surface, borderColor: palette.border, marginTop: spacing.sm }]}>
            <View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="notifications-circle-outline" size={23} color={palette.brand} /></View>
            <View style={styles.copy}>
              <Text style={[styles.cardTitle, { color: palette.text }]}>Notifications</Text>
              <Text style={[styles.optional, { color: palette.muted }]}>{notificationStatus} · Manage in device settings</Text>
              <Text style={[styles.permissionBody, { color: palette.muted }]}>Needed to send you reminders.</Text>
            </View>
            <Ionicons name="chevron-forward" size={21} color={palette.muted} />
          </Pressable>

          <SectionLabel text="YOUR DATA" color={palette.muted} />
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border, paddingVertical: 0 }]}>
            <ActionRow testID="data-download" icon="download-outline" title="Download my data" subtitle="Get a copy of the information Rehyn holds about you, in a format you can open and keep." onPress={downloadMyData} palette={palette} />
            <Divider color={palette.border} />
            <ActionRow testID="data-correct" icon="create-outline" title="Correct my information" subtitle="Tell us about anything that is wrong or out of date, and we will fix it." onPress={() => router.push({ pathname: "/account-center" as never, params: { section: "personal" } })} palette={palette} />
            <Divider color={palette.border} />
            <ActionRow testID="data-delete" icon="trash-outline" title="Delete my account and data" subtitle="Permanently close your account and delete your information. This cannot be undone." onPress={() => router.push({ pathname: "/account-center" as never, params: { section: "account" } })} palette={palette} danger />
          </View>

          <SectionLabel text="DOCUMENTS AND CONTACT" color={palette.muted} />
          <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border, paddingVertical: 0 }]}>
            <ActionRow icon="shield-checkmark-outline" title="Privacy Notice" onPress={() => router.push("/privacy-policy" as never)} palette={palette} />
            <Divider color={palette.border} />
            <ActionRow icon="document-text-outline" title="Terms of Use" onPress={() => router.push("/terms-of-use" as never)} palette={palette} />
            <Divider color={palette.border} />
            <ActionRow testID="data-movement-videos" icon="videocam-outline" title="How we handle your movement videos" onPress={() => router.push("/movement-videos" as never)} palette={palette} />
            <Divider color={palette.border} />
            <ActionRow icon="mail-outline" title="Questions about your information: info@rehyn.com" onPress={() => Linking.openURL("mailto:info@rehyn.com")} palette={palette} />
          </View>
          <Text style={[styles.ico, { color: palette.muted }]}>If you are unhappy with how we have handled your information, please tell us first so we can put it right. You can also complain to the Information Commissioner&apos;s Office at ico.org.uk.</Text>
        </View>
      </ScrollView>

      {/* Confirmation screen 2.2 — turning off health information consent.
          Factual consequence, not persuasion. Both buttons equal weight. */}
      <Modal visible={showHealthOffConfirm} transparent animationType="fade" onRequestClose={() => setShowHealthOffConfirm(false)}>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { backgroundColor: palette.surface }]} testID="data-health-off-confirm">
            <Text style={[styles.modalTitle, { color: palette.text }]}>This will stop your rehabilitation plan</Text>
            <Text style={[styles.modalBody, { color: palette.muted }]}>Rehyn builds your plan from information about your health. Without your permission to use it, we cannot generate or update your plan, and your progress tracking will pause.</Text>
            <Text style={[styles.modalBody, { color: palette.muted }]}>Your account stays open and your existing records are kept unless you also delete your account. You can turn this back on at any time.</Text>
            <View style={styles.modalActions}>
              <Pressable testID="data-health-off-anyway" onPress={confirmHealthOff} style={[styles.equalButton, { borderColor: palette.border }]}><Text style={[styles.equalButtonText, { color: palette.text }]}>Turn off anyway</Text></Pressable>
              <Pressable testID="data-health-off-cancel" onPress={() => setShowHealthOffConfirm(false)} style={[styles.equalButton, { borderColor: palette.border }]}><Text style={[styles.equalButtonText, { color: palette.text }]}>Cancel</Text></Pressable>
            </View>
          </View>
        </View>
      </Modal>

      {/* Confirmation screen 2.1 — Help improve Rehyn turned off.
          No retention prompt, no "are you sure", no offer to reconsider. */}
      <Modal visible={showImprovementOffDone} transparent animationType="fade" onRequestClose={() => setShowImprovementOffDone(false)}>
        <View style={styles.modalBackdrop}>
          <View style={[styles.modalCard, { backgroundColor: palette.surface }]} testID="data-improvement-off-done">
            <Text style={[styles.modalTitle, { color: palette.text }]}>Turned off</Text>
            <Text style={[styles.modalBody, { color: palette.muted }]}>We will not use your information to improve Rehyn from now on, and we have removed it from our future training. Information already used in a model we have released cannot always be separated out, but nothing new will be added.</Text>
            <Text style={[styles.modalBody, { color: palette.muted }]}>Your plan and everything else in Rehyn continue exactly as before.</Text>
            <View style={styles.modalActions}>
              <Pressable testID="data-improvement-off-done-button" onPress={() => setShowImprovementOffDone(false)} style={[styles.equalButton, { borderColor: palette.border }]}><Text style={[styles.equalButtonText, { color: palette.text }]}>Done</Text></Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function SectionLabel({ text, color }: { text: string; color: string }) { return <Text style={[styles.sectionLabel, { color }]}>{text}</Text>; }
function Divider({ color }: { color: string }) { return <View style={[styles.divider, { backgroundColor: color }]} />; }
function ActionRow({ icon, title, subtitle, onPress, palette, danger = false, testID }: { icon: keyof typeof Ionicons.glyphMap; title: string; subtitle?: string; onPress: () => void; palette: ReturnType<typeof useDisplayPreferences>["palette"]; danger?: boolean; testID?: string }) {
  return (
    <Pressable testID={testID} onPress={onPress} style={styles.actionRow}>
      <Ionicons name={icon} size={22} color={danger ? colors.error : palette.brand} />
      <View style={styles.copy}>
        <Text style={[styles.actionText, { color: danger ? colors.error : palette.text }]}>{title}</Text>
        {subtitle ? <Text style={[styles.actionSubtitle, { color: palette.muted }]}>{subtitle}</Text> : null}
      </View>
      <Ionicons name="chevron-forward" size={20} color={palette.muted} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 }, header: { minHeight: 58, paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, headerButton: { width: 42, height: 42, alignItems: "center", justifyContent: "center" }, headerTitle: { fontSize: 18, fontWeight: "800" },
  scroll: { padding: spacing.md }, page: { width: "100%", maxWidth: 720, alignSelf: "center" }, intro: { fontSize: 15, lineHeight: 22, marginTop: spacing.md, marginBottom: spacing.md },
  notice: { minHeight: 48, borderRadius: radius.sm, padding: spacing.sm, flexDirection: "row", alignItems: "center", gap: spacing.xs, marginBottom: spacing.sm }, noticeText: { flex: 1, fontSize: 13, lineHeight: 19, fontWeight: "600" },
  sectionLabel: { fontSize: 11, fontWeight: "900", marginTop: spacing.lg, marginBottom: spacing.xs }, card: { borderWidth: 1, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm }, toggleRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  icon: { width: 46, height: 46, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" }, copy: { flex: 1 }, cardTitle: { fontSize: 16, lineHeight: 22, fontWeight: "800" }, active: { color: colors.success, fontSize: 12, fontWeight: "800", marginTop: 2 }, pending: { color: colors.warning, fontSize: 12, fontWeight: "800", marginTop: 2 }, optional: { fontSize: 12, lineHeight: 17, marginTop: 2 }, body: { fontSize: 14, lineHeight: 21 },
  learnMore: { fontSize: 14, lineHeight: 21, fontWeight: "800", textDecorationLine: "underline" }, permissionBody: { fontSize: 13, lineHeight: 19, marginTop: 3 },
  actionCard: { minHeight: 76, borderWidth: 1, borderRadius: radius.md, padding: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.sm }, actionRow: { minHeight: 62, flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm }, actionText: { fontSize: 15, fontWeight: "700" }, actionSubtitle: { fontSize: 12, lineHeight: 17, marginTop: 2 }, divider: { height: 1, marginLeft: 34 }, ico: { fontSize: 13, lineHeight: 19, marginTop: spacing.md },
  modalBackdrop: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, backgroundColor: "rgba(10,22,16,0.6)" },
  modalCard: { width: "100%", maxWidth: 460, borderRadius: radius.md, padding: spacing.lg, gap: spacing.sm },
  modalTitle: { fontSize: 20, lineHeight: 26, fontWeight: "800" }, modalBody: { fontSize: 14, lineHeight: 21 },
  modalActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  equalButton: { flex: 1, minHeight: 50, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1 },
  equalButtonText: { fontSize: 15, fontWeight: "700" },
});
