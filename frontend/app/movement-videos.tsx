import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { LegalDocument } from "@/src/components/LegalDocument";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { LEGAL_EFFECTIVE_DATE, LEGAL_VERSION, PRIVACY_SECTIONS } from "@/src/legalContent";
import { spacing } from "@/src/theme";

// Verbatim reproduction of the movement-video handling sections of the
// Rehyn Privacy Notice, presented as the standalone document listed on the
// Data and permissions screen ("How we handle your movement videos").
const MOVEMENT_VIDEOS_INTRO =
  "Movement videos. We use raw video to take the measurements the assessment needs, then delete the raw video. We keep the measurements.";
const MOVEMENT_VIDEO_SECTIONS = PRIVACY_SECTIONS.filter(
  (section) => section.title.startsWith("6.") || section.title.startsWith("5.")
);

export default function MovementVideosScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { palette } = useDisplayPreferences();
  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm, backgroundColor: palette.surface, borderBottomColor: palette.border }]}>
        <Pressable onPress={() => router.back()} style={styles.headerButton} accessibilityLabel="Go back"><Ionicons name="chevron-back" size={25} color={palette.text} /></Pressable>
        <Text style={[styles.headerTitle, { color: palette.text }]}>Your movement videos</Text>
        <View style={styles.headerButton} />
      </View>
      <ScrollView contentContainerStyle={[styles.scroll, { paddingBottom: Math.max(insets.bottom, spacing.lg) + spacing.xl }]} showsVerticalScrollIndicator={false}>
        <View style={styles.page}>
          <Text style={[styles.documentTitle, { color: palette.text }]}>HOW WE HANDLE YOUR MOVEMENT VIDEOS</Text>
          <Text style={[styles.meta, { color: palette.muted }]}>Effective date: {LEGAL_EFFECTIVE_DATE} · Version {LEGAL_VERSION}</Text>
          <Text style={[styles.company, { color: palette.muted }]}>From the Rehyn Privacy Notice · Rehyn Ltd · Company number 17417716 · info@rehyn.com</Text>
          <LegalDocument intro={MOVEMENT_VIDEOS_INTRO} sections={MOVEMENT_VIDEO_SECTIONS} palette={palette} />
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 }, header: { minHeight: 58, paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headerButton: { width: 42, height: 42, alignItems: "center", justifyContent: "center" }, headerTitle: { fontSize: 18, fontWeight: "800" }, scroll: { padding: spacing.md },
  page: { width: "100%", maxWidth: 780, alignSelf: "center" }, documentTitle: { fontSize: 26, lineHeight: 33, fontWeight: "900", marginTop: spacing.md },
  meta: { fontSize: 13, lineHeight: 19, marginTop: spacing.xs }, company: { fontSize: 13, lineHeight: 19, marginTop: 2, marginBottom: spacing.xl },
});
