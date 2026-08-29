import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, radius } from "@/src/theme";

const UPDATED = "August 2026";

const SECTIONS: { title: string; body: string }[] = [
  {
    title: "What Rehyn is",
    body: "Rehyn is a movement coaching and wellness-tracking app for people recovering after a stroke. It helps you practise guided movements, track how they change over time, and stay motivated. Rehyn is not a medical device and does not provide a medical diagnosis or replace your doctor or therapist.",
  },
  {
    title: "Information we collect",
    body: "Account details (your name and email), the profile and survey answers you provide during onboarding, the movement sessions and guided exercises you complete, and — when you choose to run an assessment — camera-based movement data used to give you feedback.",
  },
  {
    title: "How your camera is used",
    body: "During an assessment or exercise, the camera analyses your movement to guide you and estimate joint motion. We process what is needed to give you feedback and to save your results to your account so you can see your progress. We do not use your camera for advertising and we never sell your recordings.",
  },
  {
    title: "How we use your information",
    body: "To personalise your coaching and plan, show your progress over time, keep sessions safe, and improve the reliability of the app. If you add a therapist or care circle, we share only the summaries you choose to share.",
  },
  {
    title: "What we never do",
    body: "We do not sell your personal or health information. We do not use your health data or recordings for advertising or profiling.",
  },
  {
    title: "Your choices and rights",
    body: "You can review your data choices and permissions in Settings. You can delete your account at any time from Account and sign-in, which removes your profile, survey answers, and assessments from Rehyn.",
  },
  {
    title: "Data retention",
    body: "We keep your information for as long as your account is active. When you delete your account, your data is removed from active use in the app.",
  },
  {
    title: "Not for emergencies",
    body: "Rehyn is not for medical emergencies. If you think you are having a stroke or other emergency, call your local emergency number immediately.",
  },
  {
    title: "Contact us",
    body: "Questions about your privacy? Reach us any time through Help centre → Contact support in the app.",
  },
];

export default function PrivacyPolicyScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="privacy-back" accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Privacy policy</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingBottom: Math.max(insets.bottom, spacing.lg) + spacing.lg }]} showsVerticalScrollIndicator={false}>
        <View style={styles.page}>
          <Text style={styles.updated}>Last updated {UPDATED}</Text>
          <Text style={styles.intro}>Your recovery is personal, and so is your data. This page explains, in plain language, what Rehyn collects and how it is used.</Text>
          {SECTIONS.map((s, i) => (
            <View key={s.title} style={styles.section} testID={`privacy-section-${i}`}>
              <Text style={styles.sectionTitle}>{s.title}</Text>
              <Text style={styles.sectionBody}>{s.body}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  scroll: { padding: spacing.lg },
  page: { width: "100%", maxWidth: 720, alignSelf: "center" },
  updated: { fontSize: 12, fontWeight: "700", color: colors.onSurfaceTertiary, textTransform: "uppercase", letterSpacing: 0.5 },
  intro: { fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary, marginTop: spacing.sm, marginBottom: spacing.lg },
  section: { marginBottom: spacing.lg },
  sectionTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface, marginBottom: spacing.xs },
  sectionBody: { fontSize: 14, lineHeight: 21, color: colors.onSurfaceSecondary },
});
