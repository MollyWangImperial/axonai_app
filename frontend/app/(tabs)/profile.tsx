import { useCallback, useMemo, useState } from "react";
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
import * as ImagePicker from "expo-image-picker";

import { authedFetch, getCachedUser, preferredNameKey, signOut } from "@/src/auth";
import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";
import { careFacilityKey, loadCareCircle, loadUserPreferences, profilePhotoKey, textScaleFor, UserPreferences } from "@/src/userPreferences";

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
  "secondary_goals_other",
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
  const [userId, setUserId] = useState("");
  const [careCircleCount, setCareCircleCount] = useState(0);
  const [preferences, setPreferences] = useState<UserPreferences | null>(null);
  const [editMode, setEditMode] = useState<EditMode>(null);
  const [draft, setDraft] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    const user = await getCachedUser();
    if (!user) {
      router.replace("/sign-in");
      return;
    }
    const [savedPhoto, legacyPhoto, savedFacility, legacyFacility, careCircle, savedPreferences] = await Promise.all([
      storage.getItem(profilePhotoKey(user.id), ""),
      storage.getItem(PHOTO_KEY, ""),
      storage.getItem(careFacilityKey(user.id), ""),
      storage.getItem(FACILITY_KEY, ""),
      loadCareCircle(user.id),
      loadUserPreferences(),
    ]);
    setUserId(user.id);
    setName(user?.name || "Your profile");
    setEmail(user?.email || "");
    setPhoto(savedPhoto || legacyPhoto || "");
    setFacility(savedFacility || legacyFacility || "");
    setCareCircleCount(careCircle.length);
    setPreferences(savedPreferences);
    setLoading(false);

    const onboarding = await authedFetch("/api/users/onboarding")
      .then((response) => response.json())
      .catch(() => null);
    const nextProfile = onboarding?.profile || {};
    setProfile(nextProfile);
    setName(nextProfile.preferred_name || user?.name || "Your profile");
  }, [router]);

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
        await storage.setItem(careFacilityKey(userId), value);
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
        const user = await getCachedUser();
        if (user?.id) await storage.setItem(preferredNameKey(user.id), value);
      }
      setEditMode(null);
    } catch {
      Alert.alert("Could not save", "Please check your connection and try again.");
    } finally {
      setSaving(false);
    }
  };

  const choosePhoto = async () => {
    if (Platform.OS !== "web") {
      const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!permission.granted) {
        Alert.alert("Photo access is off", "Allow photo access in your device settings to choose a profile photo.");
        return;
      }
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.72,
        base64: true,
      });
      if (result.canceled || !result.assets[0]) return;
      const asset = result.assets[0];
      const value = asset.base64 ? `data:${asset.mimeType || "image/jpeg"};base64,${asset.base64}` : asset.uri;
      setPhoto(value);
      await storage.setItem(profilePhotoKey(userId), value);
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
        await storage.setItem(profilePhotoKey(userId), value);
      };
      reader.readAsDataURL(file);
    };
    input.click();
  };

  const removePhoto = async () => {
    setPhoto("");
    await storage.removeItem(profilePhotoKey(userId));
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

  const dark = Boolean(preferences?.darkMode);
  const scale = textScaleFor(preferences?.textSize || "Comfortable");
  const palette = useMemo(() => ({
    page: dark ? "#10201B" : "#F8FAF9",
    surface: dark ? "#193028" : colors.surface,
    soft: dark ? "#213A32" : "#ECF5F2",
    text: dark ? "#F3F8F6" : "#173D35",
    muted: dark ? "#B8C9C3" : colors.onSurfaceTertiary,
    border: dark ? "#355047" : colors.divider,
  }), [dark]);
  const openSection = (section: string) => router.push({ pathname: "/account-center" as never, params: { section } });

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <ScrollView
        contentContainerStyle={[styles.page, { paddingTop: insets.top + spacing.sm }]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.inner}>
          <ScreenHeader title="Your profile" onBack={() => router.back()} onHelp={() => openSection("help")} palette={palette} scale={scale} />

          <View style={[styles.heroCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <View style={[styles.avatarLarge, { backgroundColor: palette.soft }]}>
              {photo ? <Image source={{ uri: photo }} style={styles.avatarImage} /> : <Ionicons name="person-outline" size={50} color="#24594F" />}
            </View>
            {loading ? <ActivityIndicator color={colors.brandPrimary} /> : (
              <>
                <Text testID="profile-name" style={[styles.name, { color: palette.text, fontSize: 24 * scale, lineHeight: 30 * scale }]}>{name}</Text>
                <Text style={[styles.profileGreeting, { color: palette.muted, fontSize: 15 * scale, lineHeight: 21 * scale }]}>This space is yours, {name.split(" ")[0]}.</Text>
              </>
            )}
            <Pressable testID="profile-add-photo" onPress={choosePhoto} style={styles.photoButton}>
              <Ionicons name="camera-outline" size={20} color={colors.onBrandPrimary} />
              <Text style={styles.photoButtonText}>{photo ? "Change your photo" : "Add your photo"}</Text>
            </Pressable>
            {photo ? <Pressable testID="profile-remove-photo" onPress={removePhoto}><Text style={styles.removePhotoText}>Remove photo</Text></Pressable> : null}
            <Text style={[styles.photoNote, { color: palette.muted }]}>Optional - simply a friendly face for your Rehyn profile. You can remove it whenever you like.</Text>
          </View>

          <Pressable testID="profile-edit-facility" onPress={() => openEditor("facility")} style={[styles.facilityCard, { backgroundColor: palette.soft }]}>
            <View style={[styles.rowIcon, { backgroundColor: palette.surface }]}><Ionicons name="medkit-outline" size={23} color="#24594F" /></View>
            <View style={styles.rowCopy}>
              <Text style={[styles.rowEyebrow, { color: palette.muted }]}>Your care facility</Text>
              <Text style={[styles.facilityName, { color: palette.text, fontSize: 16 * scale }]}>{facility || "Not connected yet"}</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={palette.muted} />
          </Pressable>

          <View style={[styles.sectionCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Text style={[styles.sectionLabel, { color: palette.muted }]}>PROFILE INFORMATION</Text>
            <ProfileRow
              testID="profile-edit-personal-details"
              icon="person-outline"
              title="Personal details"
              subtitle={email || "Name and preferred form of address"}
              onPress={() => openSection("personal")}
              palette={palette}
              scale={scale}
            />
            <View style={[styles.divider, { backgroundColor: palette.border }]} />
            <ProfileRow
              testID="profile-care-circle"
              icon="people-outline"
              title="Care circle"
              subtitle={careCircleCount ? `${careCircleCount} ${careCircleCount === 1 ? "person" : "people"} added` : "People you have chosen to involve"}
              onPress={() => openSection("care-circle")}
              palette={palette}
              scale={scale}
            />
            <View style={[styles.divider, { backgroundColor: palette.border }]} />
            <ProfileRow
              testID="profile-account"
              icon="key-outline"
              title="Account and password"
              subtitle="Email-only sign-in"
              onPress={() => openSection("account")}
              palette={palette}
              scale={scale}
            />
          </View>

          <Pressable testID="profile-logout" onPress={logout} style={styles.logoutButton}>
            <Ionicons name="log-out-outline" size={21} color={colors.error} />
            <Text style={styles.logoutText}>Log out</Text>
          </Pressable>
          <Text style={[styles.footerNote, { color: palette.muted }]}>{"You're in control of your profile and what you share."}</Text>
        </View>
      </ScrollView>

      <Modal visible={editMode !== null} transparent animationType="fade" onRequestClose={() => setEditMode(null)}>
        <View style={styles.modalScrim}>
          <View style={[styles.modalCard, { backgroundColor: palette.surface }]}>
            <Text style={[styles.modalTitle, { color: palette.text }]}>{editMode === "name" ? "Your preferred name" : "Your care facility"}</Text>
            <Text style={[styles.modalBody, { color: palette.muted }]}>{editMode === "name" ? "How would you like Rehyn to address you?" : "Add the name of your hospital, clinic, or rehabilitation centre."}</Text>
            <TextInput
              testID="profile-edit-input"
              value={draft}
              onChangeText={setDraft}
              autoFocus
              placeholder={editMode === "name" ? "Preferred name" : "Care facility"}
              placeholderTextColor={colors.onSurfaceTertiary}
              style={[styles.input, { color: palette.text, borderColor: palette.border, backgroundColor: palette.soft }]}
            />
            <View style={styles.modalActions}>
              <Pressable onPress={() => setEditMode(null)} style={[styles.cancelButton, { backgroundColor: palette.soft }]}><Text style={[styles.cancelText, { color: palette.text }]}>Cancel</Text></Pressable>
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

type ProfilePalette = { page: string; surface: string; soft: string; text: string; muted: string; border: string };

function ScreenHeader({ title, onBack, onHelp, palette, scale }: { title: string; onBack: () => void; onHelp: () => void; palette: ProfilePalette; scale: number }) {
  return (
    <View style={styles.header}>
      <Pressable accessibilityLabel="Go back" onPress={onBack} style={[styles.headerButton, { backgroundColor: palette.surface, borderColor: palette.border }]}><Ionicons name="arrow-back" size={23} color={palette.text} /></Pressable>
      <Text style={[styles.headerTitle, { color: palette.text, fontSize: 22 * scale }]}>{title}</Text>
      <Pressable accessibilityLabel="Help" onPress={onHelp} style={[styles.headerButton, { backgroundColor: palette.surface, borderColor: palette.border }]}><Ionicons name="help-circle-outline" size={23} color={palette.text} /></Pressable>
    </View>
  );
}

function ProfileRow({ icon, title, subtitle, onPress, testID, palette, scale }: { icon: keyof typeof Ionicons.glyphMap; title: string; subtitle: string; onPress: () => void; testID?: string; palette: ProfilePalette; scale: number }) {
  return (
    <Pressable testID={testID} onPress={onPress} style={styles.profileRow}>
      <View style={[styles.rowIcon, { backgroundColor: palette.soft }]}><Ionicons name={icon} size={22} color="#4A7856" /></View>
      <View style={styles.rowCopy}>
        <Text style={[styles.rowTitle, { color: palette.text, fontSize: 16 * scale }]}>{title}</Text>
        <Text style={[styles.rowSubtitle, { color: palette.muted, fontSize: 12 * scale, lineHeight: 17 * scale }]} numberOfLines={2}>{subtitle}</Text>
      </View>
      <Ionicons name="chevron-forward" size={20} color={palette.muted} />
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
  removePhotoText: { color: colors.error, fontSize: 13, fontWeight: "800", paddingVertical: 4 },
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
