import { useCallback, useMemo, useState } from "react";
import { Appearance, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { colors, radius, spacing } from "@/src/theme";
import { DEFAULT_SETTINGS, ensurePermission, loadSettings, rescheduleReminders, saveSettings } from "@/src/utils/notifications";
import { loadUserPreferences, saveUserPreference, TEXT_SIZES, textScaleFor, TextSizePreference, UserPreferences } from "@/src/userPreferences";

type Palette = { page: string; surface: string; soft: string; text: string; muted: string; border: string };

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [reminders, setReminders] = useState(DEFAULT_SETTINGS.enabled);
  const [preferences, setPreferences] = useState<UserPreferences | null>(null);
  const [showTextSizes, setShowTextSizes] = useState(false);
  const [notice, setNotice] = useState("");

  useFocusEffect(useCallback(() => {
    void (async () => {
      const [savedReminders, savedPreferences] = await Promise.all([loadSettings(), loadUserPreferences()]);
      setReminders(savedReminders.enabled);
      setPreferences(savedPreferences);
    })();
  }, []));

  const dark = Boolean(preferences?.darkMode);
  const scale = textScaleFor(preferences?.textSize || "Comfortable");
  const palette = useMemo<Palette>(() => ({
    page: dark ? "#10201B" : "#F8FAF9",
    surface: dark ? "#193028" : "#FFFFFF",
    soft: dark ? "#213A32" : "#ECF5F2",
    text: dark ? "#F3F8F6" : "#173D35",
    muted: dark ? "#B8C9C3" : colors.onSurfaceTertiary,
    border: dark ? "#355047" : colors.divider,
  }), [dark]);
  const openSection = (section: string) => router.push({ pathname: "/account-center" as never, params: { section } });

  const toggleReminders = async (enabled: boolean) => {
    setNotice("");
    if (enabled && Platform.OS === "web" && "Notification" in window) {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setNotice("Browser notifications are blocked. Allow them in site settings, then try again.");
        return;
      }
    } else if (enabled && Platform.OS !== "web") {
      const allowed = await ensurePermission();
      if (!allowed) {
        setNotice("Notifications are blocked. Allow them in device settings, then try again.");
        return;
      }
    }
    const current = await loadSettings();
    const next = { ...current, enabled };
    setReminders(enabled);
    await saveSettings(next);
    await rescheduleReminders(next);
    setNotice(enabled ? "Session reminders are on." : "Session reminders are off.");
  };

  const updatePreference = async <K extends keyof UserPreferences>(key: K, value: UserPreferences[K], message: string) => {
    if (!preferences) return;
    setPreferences({ ...preferences, [key]: value });
    await saveUserPreference(key, value);
    setNotice(message);
  };

  const toggleDarkMode = async (enabled: boolean) => {
    if (Platform.OS === "web") {
      document.documentElement.style.colorScheme = enabled ? "dark" : "light";
    } else {
      Appearance.setColorScheme(enabled ? "dark" : "light");
    }
    await updatePreference("darkMode", enabled, enabled ? "Dark mode is on." : "Light mode is on.");
  };

  const selectTextSize = async (size: TextSizePreference) => {
    await updatePreference("textSize", size, `${size} text is now selected.`);
    setShowTextSizes(false);
  };

  if (!preferences) return <View style={[styles.center, { backgroundColor: palette.page }]}><Text style={{ color: palette.muted }}>Loading settings...</Text></View>;

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <ScrollView contentContainerStyle={[styles.page, { paddingTop: insets.top + spacing.sm }]} showsVerticalScrollIndicator={false}>
        <View style={styles.inner}>
          <View style={styles.header}>
            <Pressable accessibilityLabel="Go back" onPress={() => router.back()} style={[styles.headerButton, { borderColor: palette.border, backgroundColor: palette.surface }]}><Ionicons name="arrow-back" size={23} color={palette.text} /></Pressable>
            <Text style={[styles.headerTitle, { color: palette.text, fontSize: 22 * scale }]}>Settings</Text>
            <Pressable accessibilityLabel="Help" onPress={() => openSection("help")} style={[styles.headerButton, { borderColor: palette.border, backgroundColor: palette.surface }]}><Ionicons name="help-circle-outline" size={23} color={palette.text} /></Pressable>
          </View>

          <View style={styles.intro}>
            <Text style={[styles.title, { color: palette.text, fontSize: 27 * scale, lineHeight: 34 * scale }]}>Make Rehyn work for you</Text>
            <Text style={[styles.subtitle, { color: palette.muted, fontSize: 15 * scale, lineHeight: 22 * scale }]}>Choose what feels comfortable. You can change these preferences at any time.</Text>
          </View>

          {notice ? <View style={[styles.notice, { backgroundColor: palette.soft }]}><Ionicons name="checkmark-circle" size={20} color={colors.success} /><Text style={[styles.noticeText, { color: palette.text }]}>{notice}</Text></View> : null}

          <SettingsGroup label="GENERAL" palette={palette}>
            <SettingsToggle testID="settings-reminders" icon="notifications-outline" title="Reminders" subtitle="Sessions and gentle check-ins" value={reminders} onValueChange={toggleReminders} palette={palette} scale={scale} />
            <Divider palette={palette} />
            <SettingsToggle testID="settings-dark-mode" icon="moon-outline" title="Dark mode" subtitle="Reduce brightness in low light" value={preferences.darkMode} onValueChange={toggleDarkMode} palette={palette} scale={scale} />
            <Divider palette={palette} />
            <SettingsLink testID="settings-text-size" icon="reorder-three-outline" title="Text size" subtitle={preferences.textSize} onPress={() => setShowTextSizes(true)} palette={palette} scale={scale} />
            <Divider palette={palette} />
            <SettingsToggle testID="settings-voice-guidance" icon="volume-high-outline" title="Voice guidance" subtitle="Spoken cues during sessions" value={preferences.voiceGuidance} onValueChange={(value) => updatePreference("voiceGuidance", value, value ? "Voice guidance is on." : "Voice guidance is off.")} palette={palette} scale={scale} />
          </SettingsGroup>

          <SettingsGroup label="SUPPORT & PRIVACY" palette={palette}>
            <SettingsLink testID="settings-privacy" icon="shield-checkmark-outline" title="Privacy policy" subtitle="How Rehyn protects your information" onPress={() => openSection("privacy")} palette={palette} scale={scale} />
            <Divider palette={palette} />
            <SettingsLink testID="settings-permissions" icon="lock-closed-outline" title="Data and permissions" subtitle="Review what you choose to share" onPress={() => openSection("permissions")} palette={palette} scale={scale} />
            <Divider palette={palette} />
            <SettingsLink testID="settings-help" icon="help-circle-outline" title="Help centre" subtitle="Answers and guidance" onPress={() => openSection("help")} palette={palette} scale={scale} />
            <Divider palette={palette} />
            <SettingsLink testID="settings-support" icon="chatbubble-outline" title="Contact support" subtitle="We're here to help" onPress={() => openSection("support")} palette={palette} scale={scale} />
          </SettingsGroup>

          <Text style={[styles.version, { color: palette.muted, fontSize: 12 * scale }]}>Rehyn version 1.0.0</Text>
        </View>
      </ScrollView>

      <Modal visible={showTextSizes} transparent animationType="fade" onRequestClose={() => setShowTextSizes(false)}>
        <View style={styles.modalScrim}>
          <View style={[styles.modalCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
            <Text style={[styles.modalTitle, { color: palette.text, fontSize: 20 * scale }]}>Text size</Text>
            <Text style={[styles.modalBody, { color: palette.muted, fontSize: 14 * scale }]}>Choose the size that feels easiest to read.</Text>
            {TEXT_SIZES.map((size) => (
              <Pressable key={size} testID={`text-size-${size.toLowerCase().replace(" ", "-")}`} onPress={() => selectTextSize(size)} style={[styles.sizeOption, { borderColor: palette.border }, preferences.textSize === size && styles.sizeOptionSelected]}>
                <Text style={[styles.sizeLabel, { color: palette.text, fontSize: size === "Comfortable" ? 15 : size === "Large" ? 17 : 19 }]}>{size}</Text>
                {preferences.textSize === size ? <Ionicons name="checkmark-circle" size={22} color={colors.brandPrimary} /> : null}
              </Pressable>
            ))}
            <Pressable onPress={() => setShowTextSizes(false)} style={[styles.cancelButton, { borderColor: palette.border }]}><Text style={[styles.cancelText, { color: palette.text }]}>Cancel</Text></Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function SettingsGroup({ label, children, palette }: { label: string; children: React.ReactNode; palette: Palette }) {
  return <View style={[styles.group, { backgroundColor: palette.surface, borderColor: palette.border }]}><Text style={[styles.groupLabel, { color: palette.muted }]}>{label}</Text>{children}</View>;
}

function SettingsToggle({ icon, title, subtitle, value, onValueChange, testID, palette, scale }: { icon: keyof typeof Ionicons.glyphMap; title: string; subtitle: string; value: boolean; onValueChange: (value: boolean) => void; testID?: string; palette: Palette; scale: number }) {
  return <View style={styles.settingRow}><View style={[styles.settingIcon, { backgroundColor: palette.soft }]}><Ionicons name={icon} size={22} color={colors.brandPrimary} /></View><View style={styles.settingCopy}><Text style={[styles.settingTitle, { color: palette.text, fontSize: 16 * scale }]}>{title}</Text><Text style={[styles.settingSubtitle, { color: palette.muted, fontSize: 12 * scale, lineHeight: 17 * scale }]}>{subtitle}</Text></View><Switch testID={testID} value={value} onValueChange={onValueChange} trackColor={{ false: "#8AA198", true: colors.brandPrimary }} thumbColor="#FFFFFF" /></View>;
}

function SettingsLink({ icon, title, subtitle, onPress, testID, palette, scale }: { icon: keyof typeof Ionicons.glyphMap; title: string; subtitle: string; onPress: () => void; testID?: string; palette: Palette; scale: number }) {
  return <Pressable testID={testID} onPress={onPress} style={styles.settingRow}><View style={[styles.settingIcon, { backgroundColor: palette.soft }]}><Ionicons name={icon} size={22} color={colors.brandPrimary} /></View><View style={styles.settingCopy}><Text style={[styles.settingTitle, { color: palette.text, fontSize: 16 * scale }]}>{title}</Text><Text style={[styles.settingSubtitle, { color: palette.muted, fontSize: 12 * scale, lineHeight: 17 * scale }]}>{subtitle}</Text></View><Ionicons name="chevron-forward" size={20} color={palette.muted} /></Pressable>;
}

function Divider({ palette }: { palette: Palette }) { return <View style={[styles.divider, { backgroundColor: palette.border }]} />; }

const styles = StyleSheet.create({
  container: { flex: 1 }, center: { flex: 1, alignItems: "center", justifyContent: "center" },
  page: { paddingHorizontal: spacing.md, paddingBottom: 36 }, inner: { width: "100%", maxWidth: 620, alignSelf: "center", gap: spacing.md },
  header: { minHeight: 56, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headerButton: { width: 42, height: 42, borderRadius: 21, borderWidth: 1, alignItems: "center", justifyContent: "center" }, headerTitle: { fontWeight: "800" },
  intro: { gap: spacing.xs, paddingBottom: spacing.xs }, title: { fontWeight: "800" }, subtitle: { maxWidth: 500 },
  notice: { minHeight: 48, borderRadius: radius.sm, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", gap: spacing.xs }, noticeText: { flex: 1, fontSize: 13, lineHeight: 19, fontWeight: "600" },
  group: { borderRadius: radius.md, borderWidth: 1, paddingHorizontal: spacing.md, paddingBottom: spacing.xs }, groupLabel: { fontSize: 11, fontWeight: "800", paddingTop: spacing.sm, paddingBottom: 2 },
  settingRow: { minHeight: 82, flexDirection: "row", alignItems: "center", gap: spacing.sm }, settingIcon: { width: 44, height: 44, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  settingCopy: { flex: 1, minWidth: 0 }, settingTitle: { fontWeight: "800" }, settingSubtitle: { marginTop: 2 }, divider: { height: 1, marginLeft: 56 }, version: { textAlign: "center", marginVertical: spacing.sm },
  modalScrim: { flex: 1, backgroundColor: "rgba(8,18,14,0.58)", alignItems: "center", justifyContent: "center", padding: spacing.lg },
  modalCard: { width: "100%", maxWidth: 430, borderRadius: radius.md, borderWidth: 1, padding: spacing.lg, gap: spacing.sm }, modalTitle: { fontWeight: "800" }, modalBody: { lineHeight: 20, marginBottom: spacing.xs },
  sizeOption: { minHeight: 58, borderWidth: 1, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md }, sizeOptionSelected: { borderColor: colors.brandPrimary, borderWidth: 2 }, sizeLabel: { fontWeight: "700" },
  cancelButton: { minHeight: 48, borderWidth: 1, borderRadius: radius.sm, alignItems: "center", justifyContent: "center", marginTop: spacing.xs }, cancelText: { fontSize: 15, fontWeight: "800" },
});
