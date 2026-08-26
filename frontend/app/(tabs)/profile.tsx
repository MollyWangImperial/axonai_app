import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { authedFetch, getCachedUser, signOut } from "@/src/auth";
import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";

const PHOTO_KEY = "rehyn_profile_photo_v1";
const FACILITY_KEY = "rehyn_care_facility_v1";
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
  "medical_conditions",
  "medical_conditions_other",
  "has_caregiver",
  "notes",
] as const;

type EditMode = "name" | "facility" | null;

export default function ProfileScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [photo, setPhoto] = useState("");
  const [facility, setFacility] = useState("");
  const [profile, setProfile] = useState<Record<string, unknown>>({});
  const [editMode, setEditMode] = useState<EditMode>(null);
  const [draft, setDraft] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    const [user, onboarding, savedPhoto, savedFacility] = await Promise.all([
      getCachedUser(),
      authedFetch("/api/users/onboarding").then((response) => response.json()).catch(() => null),
      storage.getItem(PHOTO_KEY, ""),
      storage.getItem(FACILITY_KEY, ""),
    ]);
    const nextProfile = onboarding?.profile || {};
    const preferredName = nextProfile.preferred_name || user?.name || "Your profile";
    setProfile(nextProfile);
    setName(preferredName);
    setEmail(user?.email || "");
    setPhoto(savedPhoto || "");
    setFacility(savedFacility || "");
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const openEditor = (mode: Exclude<EditMode, null>) => {
    setEditMode(mode);
    setDraft(mode === "name" ? name : facility);
  };

  const saveEdit = async () => {
    const value = draft.trim();
    if (!value) return;
    setSaving(true);
    try {
      if (editMode === "facility") {
        await storage.setItem(FACILITY_KEY, value);
        setFacility(value);
      } else {
        const payload: Record<string, unknown> = {};
        PROFILE_FIELDS.forEach((key) => {
          if (profile[key] !== undefined && profile[key] !== null) payload[key] = profile[key];
        });
        payload.preferred_name = value;
        const response = await authedFetch("/api/users/onboarding", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error("PROFILE_SAVE_FAILED");
        const result = await response.json();
        setProfile(result.profile || payload);
        setName(value);
        await storage.setItem("preferred_name_v1", value);
      }
      setEditMode(null);
    } catch {
      Alert.alert("Could not save", "Please check your connection and try again.");
    } finally {
      setSaving(false);
    }
  };

  const choosePhoto = () => {
    if (Platform.OS !== "web") {
      Alert.alert("Add your photo", "Photo selection is available in the Rehyn web app for now.");
      return;
    }
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/png,image/jpeg,image/webp";
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) return;
      if (file.size > 3 * 1024 * 1024) {
        Alert.alert("Photo is too large", "Choose an image smaller than 3 MB.");
        return;
      }
      const reader = new FileReader();
      reader.onload = async () => {
        const value = typeof reader.result === "string" ? reader.result : "";
        if (!value) return;
        setPhoto(value);
        await storage.setItem(PHOTO_KEY, value);
      };
      reader.readAsDataURL(file);
    };
    input.click();
  };

  const logout = () => {
    Alert.alert("Log out of Rehyn?", "You can sign in again with your email.", [
      { text: "Cancel", style: "cancel" },
      {
        text: "Log out",
        style: "destructive",
        onPress: async () => {
          await signOut();
          router.replace("/sign-in");
        },
      },
    ]);
  };

  return (
    <View style={styles.container}>
      <ScrollView
        contentContainerStyle={[styles.page, { paddingTop: insets.top + spacing.sm }]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.inner}>
          <ScreenHeader title="Your profile" onBack={() => router.back()} />

          <View style={styles.heroCard}>
            <View style={styles.avatarLarge}>
              {photo ? <Image source={{ uri: photo }} style={styles.avatarImage} /> : <Ionicons name="person-outline" size={50} color="#24594F" />}
            </View>
            {loading ? <ActivityIndicator color={colors.brandPrimary} /> : (
              <>
                <Text testID="profile-name" style={styles.name}>{name}</Text>
                <Text style={styles.profileGreeting}>This space is yours, {name.split(" ")[0]}.</Text>
              </>
            )}
            <Pressable testID="profile-add-photo" onPress={choosePhoto} style={styles.photoButton}>
              <Ionicons name="camera-outline" size={20} color={colors.onBrandPrimary} />
              <Text style={styles.photoButtonText}>{photo ? "Change your photo" : "Add your photo"}</Text>
            </Pressable>
            <Text style={styles.photoNote}>Optional - simply a friendly face for your Rehyn profile. You can remove it whenever you like.</Text>
          </View>

          <Pressable testID="profile-edit-facility" onPress={() => openEditor("facility")} style={styles.facilityCard}>
            <View style={styles.rowIcon}><Ionicons name="medkit-outline" size={23} color="#24594F" /></View>
            <View style={styles.rowCopy}>
              <Text style={styles.rowEyebrow}>Your care facility</Text>
              <Text style={styles.facilityName}>{facility || "Not connected yet"}</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.onSurfaceTertiary} />
          </Pressable>

          <View style={styles.sectionCard}>
            <Text style={styles.sectionLabel}>PROFILE INFORMATION</Text>
            <ProfileRow
              testID="profile-edit-personal-details"
              icon="person-outline"
              title="Personal details"
              subtitle={email || "Name and preferred form of address"}
              onPress={() => openEditor("name")}
            />
            <View style={styles.divider} />
            <ProfileRow
              icon="people-outline"
              title="Care circle"
              subtitle="People you have chosen to involve"
              onPress={() => Alert.alert("Care circle", "You have not added anyone to your care circle yet.")}
            />
            <View style={styles.divider} />
            <ProfileRow
              icon="key-outline"
              title="Account and password"
              subtitle="Email-only sign-in"
              onPress={() => Alert.alert("Account and password", `Your Rehyn account uses ${email || "your email"}. Password sign-in is not required.`)}
            />
          </View>

          <Pressable testID="profile-logout" onPress={logout} style={styles.logoutButton}>
            <Ionicons name="log-out-outline" size={21} color={colors.error} />
            <Text style={styles.logoutText}>Log out</Text>
          </Pressable>
          <Text style={styles.footerNote}>{"You're in control of your profile and what you share."}</Text>
        </View>
      </ScrollView>

      <Modal visible={editMode !== null} transparent animationType="fade" onRequestClose={() => setEditMode(null)}>
        <View style={styles.modalScrim}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>{editMode === "name" ? "Your preferred name" : "Your care facility"}</Text>
            <Text style={styles.modalBody}>{editMode === "name" ? "How would you like Rehyn to address you?" : "Add the name of your hospital, clinic, or rehabilitation centre."}</Text>
            <TextInput
              testID="profile-edit-input"
              value={draft}
              onChangeText={setDraft}
              autoFocus
              placeholder={editMode === "name" ? "Preferred name" : "Care facility"}
              placeholderTextColor={colors.onSurfaceTertiary}
              style={styles.input}
            />
            <View style={styles.modalActions}>
              <Pressable onPress={() => setEditMode(null)} style={styles.cancelButton}><Text style={styles.cancelText}>Cancel</Text></Pressable>
              <Pressable testID="profile-save-edit" disabled={saving || !draft.trim()} onPress={saveEdit} style={[styles.saveButton, (!draft.trim() || saving) && styles.disabledButton]}>
                {saving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.saveText}>Save</Text>}
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function ScreenHeader({ title, onBack }: { title: string; onBack: () => void }) {
  return (
    <View style={styles.header}>
      <Pressable accessibilityLabel="Go back" onPress={onBack} style={styles.headerButton}><Ionicons name="arrow-back" size={23} color={colors.onSurfaceSecondary} /></Pressable>
      <Text style={styles.headerTitle}>{title}</Text>
      <Pressable accessibilityLabel="Help" onPress={() => Alert.alert("Need help?", "Contact support from Settings and we'll help you.")} style={styles.headerButton}><Ionicons name="help-circle-outline" size={23} color={colors.onSurfaceSecondary} /></Pressable>
    </View>
  );
}

function ProfileRow({ icon, title, subtitle, onPress, testID }: { icon: keyof typeof Ionicons.glyphMap; title: string; subtitle: string; onPress: () => void; testID?: string }) {
  return (
    <Pressable testID={testID} onPress={onPress} style={styles.profileRow}>
      <View style={styles.rowIcon}><Ionicons name={icon} size={22} color="#24594F" /></View>
      <View style={styles.rowCopy}>
        <Text style={styles.rowTitle}>{title}</Text>
        <Text style={styles.rowSubtitle} numberOfLines={2}>{subtitle}</Text>
      </View>
      <Ionicons name="chevron-forward" size={20} color={colors.onSurfaceTertiary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F8FAF9" },
  page: { paddingHorizontal: spacing.md, paddingBottom: 32 },
  inner: { width: "100%", maxWidth: 620, alignSelf: "center", gap: spacing.md },
  header: { minHeight: 56, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headerButton: { width: 42, height: 42, borderRadius: 21, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 22, fontWeight: "800", color: "#173D35" },
  heroCard: { alignItems: "center", borderRadius: radius.md, backgroundColor: colors.surface, paddingHorizontal: spacing.lg, paddingVertical: spacing.lg, borderWidth: 1, borderColor: colors.divider, gap: spacing.xs },
  avatarLarge: { width: 116, height: 116, borderRadius: 58, overflow: "hidden", backgroundColor: "#E7F1EE", alignItems: "center", justifyContent: "center", marginBottom: spacing.sm },
  avatarImage: { width: "100%", height: "100%" },
  name: { fontSize: 24, lineHeight: 30, fontWeight: "800", color: "#173D35", textAlign: "center" },
  profileGreeting: { fontSize: 15, lineHeight: 21, color: colors.onSurfaceTertiary, textAlign: "center" },
  photoButton: { minHeight: 48, marginTop: spacing.sm, borderRadius: radius.pill, backgroundColor: "#176257", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, paddingHorizontal: spacing.lg },
  photoButtonText: { color: colors.onBrandPrimary, fontSize: 15, fontWeight: "800" },
  photoNote: { maxWidth: 390, marginTop: spacing.sm, fontSize: 12, lineHeight: 18, color: colors.onSurfaceTertiary, textAlign: "center" },
  facilityCard: { minHeight: 94, borderRadius: radius.md, padding: spacing.md, backgroundColor: "#E8F3F1", flexDirection: "row", alignItems: "center", gap: spacing.sm },
  sectionCard: { borderRadius: radius.md, paddingHorizontal: spacing.md, paddingBottom: spacing.xs, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.divider },
  sectionLabel: { fontSize: 11, fontWeight: "800", color: "#61766F", paddingTop: spacing.sm, paddingBottom: 2 },
  profileRow: { minHeight: 82, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  rowIcon: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: "#ECF5F2", alignItems: "center", justifyContent: "center" },
  rowCopy: { flex: 1, minWidth: 0 },
  rowEyebrow: { fontSize: 11, fontWeight: "800", color: "#61766F", marginBottom: 3 },
  facilityName: { fontSize: 16, lineHeight: 21, color: colors.onSurface, fontWeight: "600" },
  rowTitle: { fontSize: 16, fontWeight: "800", color: "#173D35" },
  rowSubtitle: { fontSize: 12, lineHeight: 17, color: colors.onSurfaceTertiary, marginTop: 2 },
  divider: { height: 1, backgroundColor: colors.divider, marginLeft: 56 },
  logoutButton: { minHeight: 52, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.error, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs, backgroundColor: colors.surface },
  logoutText: { color: colors.error, fontSize: 16, fontWeight: "800" },
  footerNote: { fontSize: 12, lineHeight: 18, color: colors.onSurfaceTertiary, textAlign: "center", marginBottom: spacing.md },
  modalScrim: { flex: 1, backgroundColor: "rgba(19,34,29,0.4)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  modalCard: { width: "100%", maxWidth: 440, borderRadius: radius.md, backgroundColor: colors.surface, padding: spacing.lg },
  modalTitle: { fontSize: 20, fontWeight: "800", color: "#173D35" },
  modalBody: { fontSize: 14, lineHeight: 20, color: colors.onSurfaceTertiary, marginTop: spacing.xs },
  input: { minHeight: 50, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.sm, paddingHorizontal: spacing.md, fontSize: 16, color: colors.onSurface, marginTop: spacing.md },
  modalActions: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md },
  cancelButton: { minHeight: 44, minWidth: 90, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  cancelText: { color: colors.onSurfaceSecondary, fontWeight: "700" },
  saveButton: { minHeight: 44, minWidth: 100, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, backgroundColor: "#176257" },
  disabledButton: { opacity: 0.45 },
  saveText: { color: colors.onBrandPrimary, fontWeight: "800" },
});
