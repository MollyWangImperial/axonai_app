import { useCallback, useState } from "react";
import { Alert, Linking, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { colors, radius, spacing } from "@/src/theme";
import { DEFAULT_SETTINGS, ensurePermission, loadSettings, rescheduleReminders, saveSettings } from "@/src/utils/notifications";
import { storage } from "@/src/utils/storage";

const DARK_MODE_KEY = "rehyn_dark_mode_v1";
const TEXT_SIZE_KEY = "rehyn_text_size_v1";
const VOICE_GUIDANCE_KEY = "rehyn_voice_guidance_v1";
const TEXT_SIZES = ["Comfortable", "Large", "Extra large"] as const;

export default function SettingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [reminders, setReminders] = useState(DEFAULT_SETTINGS.enabled);
  const [darkMode, setDarkMode] = useState(false);
  const [voiceGuidance, setVoiceGuidance] = useState(true);
  const [textSize, setTextSize] = useState<(typeof TEXT_SIZES)[number]>("Comfortable");

  useFocusEffect(useCallback(() => {
    void (async () => {
      const [savedReminders, savedDarkMode, savedVoice, savedTextSize] = await Promise.all([
        loadSettings(),
        storage.getItem(DARK_MODE_KEY, false),
        storage.getItem(VOICE_GUIDANCE_KEY, true),
        storage.getItem(TEXT_SIZE_KEY, "Comfortable"),
      ]);
      setReminders(savedReminders.enabled);
      setDarkMode(Boolean(savedDarkMode));
      setVoiceGuidance(Boolean(savedVoice));
      if (TEXT_SIZES.includes(savedTextSize as (typeof TEXT_SIZES)[number])) setTextSize(savedTextSize as (typeof TEXT_SIZES)[number]);
    })();
  }, []));

  const toggleReminders = async (enabled: boolean) => {
    if (enabled && Platform.OS !== "web") {
      const allowed = await ensurePermission();
      if (!allowed) {
        Alert.alert("Notifications are off", "Allow notifications in your device settings to receive Rehyn reminders.");
        return;
      }
    }
    const current = await loadSettings();
    const next = { ...current, enabled };
    setReminders(enabled);
    await saveSettings(next);
    await rescheduleReminders(next);
  };

  const toggleDarkMode = async (enabled: boolean) => {
    setDarkMode(enabled);
    await storage.setItem(DARK_MODE_KEY, enabled);
    Alert.alert("Appearance saved", enabled ? "Dark mode will be used where it is supported." : "Light mode is now selected.");
  };

  const toggleVoiceGuidance = async (enabled: boolean) => {
    setVoiceGuidance(enabled);
    await storage.setItem(VOICE_GUIDANCE_KEY, enabled);
  };

  const chooseTextSize = () => {
    Alert.alert("Text size", "Choose the size that feels most comfortable.", [
      ...TEXT_SIZES.map((size) => ({
        text: size === textSize ? `${size} (selected)` : size,
        onPress: async () => {
          setTextSize(size);
          await storage.setItem(TEXT_SIZE_KEY, size);
        },
      })),
      { text: "Cancel", style: "cancel" as const },
    ]);
  };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={[styles.page, { paddingTop: insets.top + spacing.sm }]} showsVerticalScrollIndicator={false}>
        <View style={styles.inner}>
          <View style={styles.header}>
            <Pressable accessibilityLabel="Go back" onPress={() => router.back()} style={styles.headerButton}><Ionicons name="arrow-back" size={23} color={colors.onSurfaceSecondary} /></Pressable>
            <Text style={styles.headerTitle}>Settings</Text>
            <Pressable accessibilityLabel="Help" onPress={() => Alert.alert("Need help?", "Choose Help centre or Contact support below.")} style={styles.headerButton}><Ionicons name="help-circle-outline" size={23} color={colors.onSurfaceSecondary} /></Pressable>
          </View>

          <View style={styles.intro}>
            <Text style={styles.title}>Make Rehyn work for you</Text>
            <Text style={styles.subtitle}>Choose what feels comfortable. You can change these preferences at any time.</Text>
          </View>

          <SettingsGroup label="GENERAL">
            <SettingsToggle testID="settings-reminders" icon="notifications-outline" title="Reminders" subtitle="Sessions and gentle check-ins" value={reminders} onValueChange={toggleReminders} />
            <Divider />
            <SettingsToggle testID="settings-dark-mode" icon="moon-outline" title="Dark mode" subtitle="Reduce brightness in low light" value={darkMode} onValueChange={toggleDarkMode} />
            <Divider />
            <SettingsLink testID="settings-text-size" icon="reorder-three-outline" title="Text size" subtitle={textSize} onPress={chooseTextSize} />
            <Divider />
            <SettingsToggle testID="settings-voice-guidance" icon="volume-high-outline" title="Voice guidance" subtitle="Spoken cues during sessions" value={voiceGuidance} onValueChange={toggleVoiceGuidance} />
          </SettingsGroup>

          <SettingsGroup label="SUPPORT & PRIVACY">
            <SettingsLink icon="shield-checkmark-outline" title="Privacy policy" subtitle="How Rehyn protects your information" onPress={() => Alert.alert("Privacy policy", "Your rehabilitation information is used only to provide and improve your Rehyn experience. A full policy will be published before public release.")} />
            <Divider />
            <SettingsLink icon="lock-closed-outline" title="Data and permissions" subtitle="Review what you choose to share" onPress={() => Alert.alert("Data and permissions", "Camera access is used only during guided assessments. You can change permission access in your browser or device settings.")} />
            <Divider />
            <SettingsLink icon="help-circle-outline" title="Help centre" subtitle="Answers and guidance" onPress={() => Alert.alert("Help centre", "For assessment help, keep your full body visible, use good lighting, and place your phone on a stable surface.")} />
            <Divider />
            <SettingsLink icon="chatbubble-outline" title="Contact support" subtitle="We're here to help" onPress={() => Linking.openURL("mailto:support@rehyn.com?subject=Rehyn%20support")} />
          </SettingsGroup>

          <Text style={styles.version}>Rehyn version 1.0.0</Text>
        </View>
      </ScrollView>
    </View>
  );
}

function SettingsGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={styles.group}>
      <Text style={styles.groupLabel}>{label}</Text>
      {children}
    </View>
  );
}

function SettingsToggle({ icon, title, subtitle, value, onValueChange, testID }: { icon: keyof typeof Ionicons.glyphMap; title: string; subtitle: string; value: boolean; onValueChange: (value: boolean) => void; testID?: string }) {
  return (
    <View style={styles.settingRow}>
      <View style={styles.settingIcon}><Ionicons name={icon} size={22} color="#24594F" /></View>
      <View style={styles.settingCopy}><Text style={styles.settingTitle}>{title}</Text><Text style={styles.settingSubtitle}>{subtitle}</Text></View>
      <Switch testID={testID} value={value} onValueChange={onValueChange} trackColor={{ false: "#DCE8E6", true: "#176257" }} thumbColor="#FFFFFF" ios_backgroundColor="#DCE8E6" />
    </View>
  );
}

function SettingsLink({ icon, title, subtitle, onPress, testID }: { icon: keyof typeof Ionicons.glyphMap; title: string; subtitle: string; onPress: () => void; testID?: string }) {
  return (
    <Pressable testID={testID} onPress={onPress} style={styles.settingRow}>
      <View style={styles.settingIcon}><Ionicons name={icon} size={22} color="#24594F" /></View>
      <View style={styles.settingCopy}><Text style={styles.settingTitle}>{title}</Text><Text style={styles.settingSubtitle}>{subtitle}</Text></View>
      <Ionicons name="chevron-forward" size={20} color={colors.onSurfaceTertiary} />
    </Pressable>
  );
}

function Divider() {
  return <View style={styles.divider} />;
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F8FAF9" },
  page: { paddingHorizontal: spacing.md, paddingBottom: 36 },
  inner: { width: "100%", maxWidth: 620, alignSelf: "center", gap: spacing.md },
  header: { minHeight: 56, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headerButton: { width: 42, height: 42, borderRadius: 21, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 22, fontWeight: "800", color: "#173D35" },
  intro: { gap: spacing.xs, paddingBottom: spacing.xs },
  title: { fontSize: 27, lineHeight: 34, fontWeight: "800", color: "#173D35" },
  subtitle: { maxWidth: 500, fontSize: 15, lineHeight: 22, color: colors.onSurfaceTertiary },
  group: { borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.divider, paddingHorizontal: spacing.md, paddingBottom: spacing.xs },
  groupLabel: { fontSize: 11, fontWeight: "800", color: "#61766F", paddingTop: spacing.sm, paddingBottom: 2 },
  settingRow: { minHeight: 82, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  settingIcon: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: "#ECF5F2", alignItems: "center", justifyContent: "center" },
  settingCopy: { flex: 1, minWidth: 0 },
  settingTitle: { fontSize: 16, fontWeight: "800", color: "#173D35" },
  settingSubtitle: { fontSize: 12, lineHeight: 17, color: colors.onSurfaceTertiary, marginTop: 2 },
  divider: { height: 1, backgroundColor: colors.divider, marginLeft: 56 },
  version: { textAlign: "center", color: colors.onSurfaceTertiary, fontSize: 12, marginVertical: spacing.sm },
});
