import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { authedFetch, getCachedUser, preferredNameKey, signOut } from "@/src/auth";
import { colors, radius, spacing } from "@/src/theme";
import { ensurePermission } from "@/src/utils/notifications";
import { storage } from "@/src/utils/storage";
import {
  CareCircleContact,
  careFacilityKey,
  loadCareCircle,
  loadUserPreferences,
  saveCareCircle,
  saveUserPreference,
  textScaleFor,
  UserPreferences,
} from "@/src/userPreferences";

const PROFILE_FIELDS = [
  "preferred_name",
  "age_band",
  "months_since_stroke",
  "side_affected",
  "affected_areas",
  "affected_areas_other",
  "dominant_hand",
  "mobility_level",
  "primary_goal",
  "secondary_goals",
  "secondary_goals_other",
  "medical_conditions",
  "medical_conditions_other",
  "has_caregiver",
  "notes",
] as const;

type Section = "personal" | "care-circle" | "account" | "privacy" | "permissions" | "help" | "support";

const SECTION_TITLES: Record<Section, string> = {
  personal: "Personal details",
  "care-circle": "Care circle",
  account: "Account and sign-in",
  privacy: "Privacy policy",
  permissions: "Data and permissions",
  help: "Help centre",
  support: "Contact support",
};

const FAQS = [
  ["How should I position the camera?", "Place the device on a stable surface. Keep the body parts named in the setup guide visible and use even lighting."],
  ["Can I stop an assessment?", "Yes. Use Exit at any time. Completed tasks are saved to your account, so you can continue with the remaining tasks later."],
  ["What if a movement feels painful?", "Stop the task and choose Skip. Do not push through pain, dizziness, or a movement that feels unsafe."],
  ["Who can see my results?", "Your results stay private unless you choose to share them with someone in your care circle or your clinical team."],
] as const;

export default function AccountCenterScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ section?: string; focus?: string }>();
  const section = (Object.prototype.hasOwnProperty.call(SECTION_TITLES, params.section || "") ? params.section : "personal") as Section;
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [userId, setUserId] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [facility, setFacility] = useState("");
  const [profile, setProfile] = useState<Record<string, unknown>>({});
  const [contacts, setContacts] = useState<CareCircleContact[]>([]);
  const [contactName, setContactName] = useState("");
  const [relationship, setRelationship] = useState("");
  const [contactMethod, setContactMethod] = useState("");
  const [showContactForm, setShowContactForm] = useState(false);
  const [preferences, setPreferences] = useState<UserPreferences | null>(null);
  const [expandedFaq, setExpandedFaq] = useState<number | null>(null);
  const [supportSubject, setSupportSubject] = useState("Help with Rehyn");
  const [supportMessage, setSupportMessage] = useState("");
  const [cameraStatus, setCameraStatus] = useState("Not checked");
  const [notificationStatus, setNotificationStatus] = useState("Not checked");

  useEffect(() => {
    void (async () => {
      const user = await getCachedUser();
      if (!user) {
        router.replace("/sign-in");
        return;
      }
      const [savedFacility, savedContacts, savedPreferences] = await Promise.all([
        storage.getItem(careFacilityKey(user.id), ""),
        loadCareCircle(user.id),
        loadUserPreferences(),
      ]);
      setUserId(user.id);
      setEmail(user.email || "");
      setName(String(user.name || ""));
      setFacility(savedFacility || "");
      setContacts(savedContacts);
      setPreferences(savedPreferences);
      setLoading(false);

      const onboarding = await authedFetch("/api/users/onboarding")
        .then((response) => response.json())
        .catch(() => null);
      const nextProfile = onboarding?.profile || {};
      setProfile(nextProfile);
      setName(String(nextProfile.preferred_name || user.name || ""));
    })();
  }, [router]);

  const scale = textScaleFor(preferences?.textSize || "Comfortable");
  const dark = Boolean(preferences?.darkMode);
  const palette = useMemo(() => ({
    page: dark ? "#10201B" : "#F8FAF9",
    surface: dark ? "#193028" : "#FFFFFF",
    surfaceSoft: dark ? "#213A32" : "#ECF5F2",
    text: dark ? "#F3F8F6" : "#173D35",
    muted: dark ? "#B8C9C3" : colors.onSurfaceTertiary,
    border: dark ? "#355047" : colors.divider,
  }), [dark]);

  const savePersonal = async () => {
    if (!name.trim()) return;
    setSaving(true);
    setNotice("");
    try {
      const payload: Record<string, unknown> = {};
      PROFILE_FIELDS.forEach((key) => {
        if (profile[key] !== undefined && profile[key] !== null) payload[key] = profile[key];
      });
      payload.preferred_name = name.trim();
      const response = await authedFetch("/api/users/onboarding", { method: "POST", body: JSON.stringify(payload) });
      if (!response.ok) throw new Error("save failed");
      const result = await response.json();
      await Promise.all([
        storage.setItem(careFacilityKey(userId), facility.trim()),
        storage.setItem(preferredNameKey(userId), name.trim()),
      ]);
      setProfile(result.profile || payload);
      setNotice("Your personal details were saved.");
    } catch {
      setNotice("We could not save these details. Check your connection and try again.");
    } finally {
      setSaving(false);
    }
  };

  const addContact = async () => {
    if (!contactName.trim() || !relationship.trim()) return;
    const next: CareCircleContact = {
      id: `care_${Date.now()}`,
      name: contactName.trim(),
      relationship: relationship.trim(),
      contact: contactMethod.trim(),
    };
    const updated = [...contacts, next];
    setContacts(updated);
    setContactName("");
    setRelationship("");
    setContactMethod("");
    setShowContactForm(false);
    await saveCareCircle(userId, updated);
    setNotice(`${next.name} was added to your care circle.`);
  };

  const removeContact = async (id: string) => {
    const removed = contacts.find((item) => item.id === id);
    const updated = contacts.filter((item) => item.id !== id);
    setContacts(updated);
    await saveCareCircle(userId, updated);
    setNotice(removed ? `${removed.name} was removed.` : "Care circle updated.");
  };

  const updatePreference = async <K extends keyof UserPreferences>(key: K, value: UserPreferences[K]) => {
    if (!preferences) return;
    setPreferences({ ...preferences, [key]: value });
    await saveUserPreference(key, value);
    setNotice("Your sharing preference was saved.");
  };

  const checkCamera = async () => {
    if (Platform.OS !== "web") {
      await Linking.openSettings();
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      stream.getTracks().forEach((track) => track.stop());
      setCameraStatus("Camera and microphone allowed");
    } catch {
      setCameraStatus("Permission blocked - use browser site settings");
    }
  };

  const checkNotifications = async () => {
    if (Platform.OS === "web") {
      if (!("Notification" in window)) {
        setNotificationStatus("Not supported by this browser");
        return;
      }
      const result = await Notification.requestPermission();
      setNotificationStatus(result === "granted" ? "Notifications allowed" : "Notifications blocked");
      return;
    }
    setNotificationStatus(await ensurePermission() ? "Notifications allowed" : "Notifications blocked");
  };

  const sendSupportRequest = async () => {
    const subject = encodeURIComponent(supportSubject.trim() || "Help with Rehyn");
    const body = encodeURIComponent(`${supportMessage.trim()}\n\nAccount: ${email}`);
    await Linking.openURL(`mailto:support@rehyn.com?subject=${subject}&body=${body}`);
  };

  if (loading || !preferences) {
    return <View style={[styles.center, { backgroundColor: palette.page }]}><ActivityIndicator color={colors.brandPrimary} /></View>;
  }

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <ScrollView contentContainerStyle={[styles.page, { paddingTop: insets.top + spacing.sm }]} showsVerticalScrollIndicator={false}>
        <View style={styles.inner}>
          <View style={styles.header}>
            <Pressable accessibilityLabel="Go back" onPress={() => router.back()} style={[styles.headerButton, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <Ionicons name="arrow-back" size={23} color={palette.text} />
            </Pressable>
            <Text style={[styles.headerTitle, { color: palette.text, fontSize: 22 * scale }]}>{SECTION_TITLES[section]}</Text>
            <View style={styles.headerSpacer} />
          </View>

          {notice ? <View style={[styles.notice, { backgroundColor: palette.surfaceSoft }]}><Ionicons name="checkmark-circle" size={20} color={colors.success} /><Text style={[styles.noticeText, { color: palette.text }]}>{notice}</Text></View> : null}

          {section === "personal" ? (
            <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <Field label="Preferred name" value={name} onChangeText={setName} palette={palette} scale={scale} />
              <Field label="Care facility" value={facility} onChangeText={setFacility} placeholder="Hospital, clinic, or rehabilitation centre" palette={palette} scale={scale} />
              <ReadOnlyRow label="Account email" value={email} palette={palette} scale={scale} />
              <ReadOnlyRow label="Affected side" value={String(profile.side_affected || "Not recorded")} palette={palette} scale={scale} />
              <Pressable testID="personal-save" disabled={saving || !name.trim()} onPress={savePersonal} style={[styles.primaryButton, (!name.trim() || saving) && styles.disabled]}>
                {saving ? <ActivityIndicator color="#FFFFFF" /> : <Text style={styles.primaryButtonText}>Save details</Text>}
              </Pressable>
            </View>
          ) : null}

          {section === "care-circle" ? (
            <>
              <Text style={[styles.lead, { color: palette.muted, fontSize: 15 * scale }]}>Add family members, carers, or clinicians you want to involve. Nothing is shared automatically.</Text>
              {contacts.map((contact) => (
                <View key={contact.id} style={[styles.contactCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                  <View style={[styles.iconBox, { backgroundColor: palette.surfaceSoft }]}><Ionicons name="people-outline" size={22} color={colors.brandPrimary} /></View>
                  <View style={styles.flex}><Text style={[styles.cardTitle, { color: palette.text, fontSize: 17 * scale }]}>{contact.name}</Text><Text style={[styles.cardBody, { color: palette.muted }]}>{contact.relationship}{contact.contact ? ` · ${contact.contact}` : ""}</Text></View>
                  <Pressable accessibilityLabel={`Remove ${contact.name}`} onPress={() => removeContact(contact.id)} style={styles.iconButton}><Ionicons name="trash-outline" size={21} color={colors.error} /></Pressable>
                </View>
              ))}
              {!contacts.length && !showContactForm ? <EmptyState icon="people-outline" title="Your care circle is empty" body="Add someone when you are ready. You stay in control of what they can see." palette={palette} scale={scale} /> : null}
              {showContactForm ? (
                <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                  <Field label="Name" value={contactName} onChangeText={setContactName} palette={palette} scale={scale} />
                  <Field label="Relationship" value={relationship} onChangeText={setRelationship} placeholder="Family member, carer, therapist..." palette={palette} scale={scale} />
                  <Field label="Email or phone (optional)" value={contactMethod} onChangeText={setContactMethod} palette={palette} scale={scale} />
                  <View style={styles.actionRow}><Pressable onPress={() => setShowContactForm(false)} style={[styles.secondaryButton, { borderColor: palette.border }]}><Text style={[styles.secondaryText, { color: palette.text }]}>Cancel</Text></Pressable><Pressable testID="care-circle-save" onPress={addContact} disabled={!contactName.trim() || !relationship.trim()} style={[styles.primarySmall, (!contactName.trim() || !relationship.trim()) && styles.disabled]}><Text style={styles.primaryButtonText}>Add person</Text></Pressable></View>
                </View>
              ) : <Pressable testID="care-circle-add" onPress={() => setShowContactForm(true)} style={styles.primaryButton}><Ionicons name="person-add-outline" size={20} color="#FFFFFF" /><Text style={styles.primaryButtonText}>Add someone</Text></Pressable>}
            </>
          ) : null}

          {section === "account" ? (
            <>
              <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                <ReadOnlyRow label="Email" value={email} palette={palette} scale={scale} />
                <ReadOnlyRow label="Sign-in method" value="Secure email-only sign-in" palette={palette} scale={scale} />
                <Text style={[styles.lead, { color: palette.muted }]}>Rehyn does not store a password for this account. Use the same email to return to your saved survey and assessments.</Text>
              </View>
              <Pressable testID="account-sign-out" onPress={async () => { await signOut(); router.replace("/sign-in"); }} style={styles.dangerButton}><Ionicons name="log-out-outline" size={20} color={colors.error} /><Text style={styles.dangerText}>Log out</Text></Pressable>
            </>
          ) : null}

          {section === "privacy" ? (
            <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <PolicySection title="Your information" body="Rehyn uses your profile, survey answers, task videos, and movement results to provide assessments, progress records, and rehabilitation guidance." palette={palette} scale={scale} />
              <PolicySection title="Video and movement data" body="Task recordings and derived movement data are linked to your signed-in account. They are not sold or used for advertising." palette={palette} scale={scale} />
              <PolicySection title="Clinical limits" body="Rehyn supports rehabilitation but does not replace a diagnosis or your clinical team. Findings that need review are held for a therapist." palette={palette} scale={scale} />
              <PolicySection title="Your choices" body="You can control sharing, permissions, and your care circle at any time from Data and permissions." palette={palette} scale={scale} />
              <Pressable onPress={() => router.push({ pathname: "/account-center" as never, params: { section: "permissions" } })} style={styles.primaryButton}><Text style={styles.primaryButtonText}>Review data choices</Text></Pressable>
            </View>
          ) : null}

          {section === "permissions" ? (
            <>
              <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                <ActionRow icon="camera-outline" title="Camera and microphone" subtitle={cameraStatus} action="Check" onPress={checkCamera} palette={palette} scale={scale} />
                <Divider color={palette.border} />
                <ActionRow icon="notifications-outline" title="Notifications" subtitle={notificationStatus} action="Check" onPress={checkNotifications} palette={palette} scale={scale} />
              </View>
              <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                <ToggleRow title="Save assessment results" subtitle="Keep results in Assessment history" value={preferences.shareAssessments} onValueChange={(value) => updatePreference("shareAssessments", value)} palette={palette} scale={scale} />
                <Divider color={palette.border} />
                <ToggleRow title="Share with care circle" subtitle="Allow people you add to see shared summaries" value={preferences.shareCareCircle} onValueChange={(value) => updatePreference("shareCareCircle", value)} palette={palette} scale={scale} />
                <Divider color={palette.border} />
                <ToggleRow title="Anonymous usage analytics" subtitle="Help improve navigation and reliability" value={preferences.usageAnalytics} onValueChange={(value) => updatePreference("usageAnalytics", value)} palette={palette} scale={scale} />
              </View>
            </>
          ) : null}

          {section === "help" ? (
            <>
              {FAQS.map(([question, answer], index) => (
                <Pressable key={question} onPress={() => setExpandedFaq(expandedFaq === index ? null : index)} style={[styles.faq, { backgroundColor: palette.surface, borderColor: palette.border }]}>
                  <View style={styles.flex}><Text style={[styles.cardTitle, { color: palette.text, fontSize: 16 * scale }]}>{question}</Text>{expandedFaq === index ? <Text style={[styles.cardBody, { color: palette.muted, fontSize: 14 * scale }]}>{answer}</Text> : null}</View>
                  <Ionicons name={expandedFaq === index ? "chevron-up" : "chevron-down"} size={20} color={palette.muted} />
                </Pressable>
              ))}
              <Pressable onPress={() => router.push({ pathname: "/(tabs)/chat", params: { prompt: "I need help using Rehyn" } })} style={styles.primaryButton}><Ionicons name="chatbubbles-outline" size={20} color="#FFFFFF" /><Text style={styles.primaryButtonText}>Ask Alira</Text></Pressable>
              <Pressable onPress={() => router.push({ pathname: "/account-center" as never, params: { section: "support" } })} style={[styles.secondaryButton, { borderColor: palette.border }]}><Text style={[styles.secondaryText, { color: palette.text }]}>Contact support</Text></Pressable>
            </>
          ) : null}

          {section === "support" ? (
            <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <Text style={[styles.lead, { color: palette.muted, fontSize: 15 * scale }]}>Tell us what happened. Your email app will open with the details ready to send.</Text>
              <Field label="Subject" value={supportSubject} onChangeText={setSupportSubject} palette={palette} scale={scale} />
              <Text style={[styles.fieldLabel, { color: palette.text, fontSize: 13 * scale }]}>Message</Text>
              <TextInput testID="support-message" value={supportMessage} onChangeText={setSupportMessage} multiline textAlignVertical="top" placeholder="What can we help with?" placeholderTextColor={palette.muted} style={[styles.input, styles.messageInput, { backgroundColor: palette.surfaceSoft, borderColor: palette.border, color: palette.text, fontSize: 16 * scale }]} />
              <Pressable testID="support-send" disabled={!supportMessage.trim()} onPress={sendSupportRequest} style={[styles.primaryButton, !supportMessage.trim() && styles.disabled]}><Ionicons name="mail-outline" size={20} color="#FFFFFF" /><Text style={styles.primaryButtonText}>Open email to send</Text></Pressable>
            </View>
          ) : null}
        </View>
      </ScrollView>
    </View>
  );
}

type Palette = { page: string; surface: string; surfaceSoft: string; text: string; muted: string; border: string };

function Field({ label, value, onChangeText, placeholder, palette, scale }: { label: string; value: string; onChangeText: (value: string) => void; placeholder?: string; palette: Palette; scale: number }) {
  return <View><Text style={[styles.fieldLabel, { color: palette.text, fontSize: 13 * scale }]}>{label}</Text><TextInput value={value} onChangeText={onChangeText} placeholder={placeholder} placeholderTextColor={palette.muted} style={[styles.input, { backgroundColor: palette.surfaceSoft, borderColor: palette.border, color: palette.text, fontSize: 16 * scale }]} /></View>;
}

function ReadOnlyRow({ label, value, palette, scale }: { label: string; value: string; palette: Palette; scale: number }) {
  return <View style={[styles.readOnlyRow, { borderBottomColor: palette.border }]}><Text style={[styles.readOnlyLabel, { color: palette.muted, fontSize: 12 * scale }]}>{label}</Text><Text style={[styles.readOnlyValue, { color: palette.text, fontSize: 16 * scale }]}>{value}</Text></View>;
}

function PolicySection({ title, body, palette, scale }: { title: string; body: string; palette: Palette; scale: number }) {
  return <View style={styles.policySection}><Text style={[styles.cardTitle, { color: palette.text, fontSize: 17 * scale }]}>{title}</Text><Text style={[styles.cardBody, { color: palette.muted, fontSize: 14 * scale }]}>{body}</Text></View>;
}

function EmptyState({ icon, title, body, palette, scale }: { icon: keyof typeof Ionicons.glyphMap; title: string; body: string; palette: Palette; scale: number }) {
  return <View style={[styles.emptyState, { backgroundColor: palette.surface, borderColor: palette.border }]}><View style={[styles.iconBox, { backgroundColor: palette.surfaceSoft }]}><Ionicons name={icon} size={24} color={colors.brandPrimary} /></View><Text style={[styles.cardTitle, { color: palette.text, fontSize: 17 * scale }]}>{title}</Text><Text style={[styles.cardBody, { color: palette.muted, fontSize: 14 * scale, textAlign: "center" }]}>{body}</Text></View>;
}

function ActionRow({ icon, title, subtitle, action, onPress, palette, scale }: { icon: keyof typeof Ionicons.glyphMap; title: string; subtitle: string; action: string; onPress: () => void; palette: Palette; scale: number }) {
  return <View style={styles.actionItem}><View style={[styles.iconBox, { backgroundColor: palette.surfaceSoft }]}><Ionicons name={icon} size={22} color={colors.brandPrimary} /></View><View style={styles.flex}><Text style={[styles.cardTitle, { color: palette.text, fontSize: 16 * scale }]}>{title}</Text><Text style={[styles.cardBody, { color: palette.muted }]}>{subtitle}</Text></View><Pressable onPress={onPress} style={styles.checkButton}><Text style={styles.checkButtonText}>{action}</Text></Pressable></View>;
}

function ToggleRow({ title, subtitle, value, onValueChange, palette, scale }: { title: string; subtitle: string; value: boolean; onValueChange: (value: boolean) => void; palette: Palette; scale: number }) {
  return <View style={styles.actionItem}><View style={styles.flex}><Text style={[styles.cardTitle, { color: palette.text, fontSize: 16 * scale }]}>{title}</Text><Text style={[styles.cardBody, { color: palette.muted }]}>{subtitle}</Text></View><Switch value={value} onValueChange={onValueChange} trackColor={{ false: "#8AA198", true: colors.brandPrimary }} thumbColor="#FFFFFF" /></View>;
}

function Divider({ color }: { color: string }) { return <View style={[styles.divider, { backgroundColor: color }]} />; }

const styles = StyleSheet.create({
  container: { flex: 1 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  page: { paddingHorizontal: spacing.md, paddingBottom: 48 },
  inner: { width: "100%", maxWidth: 620, alignSelf: "center", gap: spacing.md },
  header: { minHeight: 56, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headerButton: { width: 42, height: 42, borderRadius: 21, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  headerSpacer: { width: 42, height: 42 },
  headerTitle: { fontWeight: "800", textAlign: "center" },
  notice: { minHeight: 48, borderRadius: radius.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.xs },
  noticeText: { flex: 1, fontSize: 13, lineHeight: 19, fontWeight: "600" },
  lead: { fontSize: 15, lineHeight: 22 },
  card: { borderRadius: radius.md, borderWidth: 1, padding: spacing.md, gap: spacing.md },
  fieldLabel: { fontWeight: "800", marginBottom: 6 },
  input: { minHeight: 50, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: spacing.md },
  messageInput: { minHeight: 150, paddingTop: spacing.md },
  readOnlyRow: { paddingBottom: spacing.sm, borderBottomWidth: 1 },
  readOnlyLabel: { fontWeight: "700", marginBottom: 4 },
  readOnlyValue: { fontWeight: "600", textTransform: "none" },
  primaryButton: { minHeight: 52, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, paddingHorizontal: spacing.lg },
  primarySmall: { minHeight: 46, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md },
  primaryButtonText: { color: "#FFFFFF", fontSize: 15, fontWeight: "800" },
  secondaryButton: { minHeight: 50, borderRadius: radius.pill, borderWidth: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md },
  secondaryText: { fontSize: 15, fontWeight: "800" },
  disabled: { opacity: 0.45 },
  actionRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm },
  contactCard: { minHeight: 82, borderRadius: radius.md, borderWidth: 1, padding: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  iconBox: { width: 44, height: 44, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  iconButton: { width: 42, height: 42, alignItems: "center", justifyContent: "center" },
  flex: { flex: 1, minWidth: 0 },
  cardTitle: { fontWeight: "800" },
  cardBody: { marginTop: 4, fontSize: 13, lineHeight: 19 },
  emptyState: { minHeight: 190, borderRadius: radius.md, borderWidth: 1, padding: spacing.lg, alignItems: "center", justifyContent: "center", gap: spacing.sm },
  dangerButton: { minHeight: 52, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs },
  dangerText: { color: colors.error, fontSize: 15, fontWeight: "800" },
  policySection: { gap: 4, paddingBottom: spacing.sm },
  actionItem: { minHeight: 76, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  checkButton: { minHeight: 40, minWidth: 70, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.sm },
  checkButtonText: { color: "#FFFFFF", fontSize: 13, fontWeight: "800" },
  divider: { height: 1 },
  faq: { minHeight: 74, borderRadius: radius.md, borderWidth: 1, padding: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.sm },
});
