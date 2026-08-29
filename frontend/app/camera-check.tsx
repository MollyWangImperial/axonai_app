import { View, Text, StyleSheet, Pressable, ScrollView } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";

const TIPS: { icon: keyof typeof Ionicons.glyphMap; title: string; body: string }[] = [
  { icon: "expand-outline", title: "Fit your whole body in frame", body: "Prop your phone so your head, arms, and hips are all visible. Stand back about 2–3 metres for standing tasks." },
  { icon: "sunny-outline", title: "Light from the front", body: "Face a window or light. Avoid a bright light or window directly behind you — it hides your movement." },
  { icon: "shirt-outline", title: "Wear fitted clothing", body: "Short or close-fitting sleeves let the camera see your arms and joints clearly." },
  { icon: "phone-landscape-outline", title: "Keep the phone steady", body: "Lean it against something stable at chest height. Ask a helper to hold it steady for walking tasks." },
];

export default function CameraCheckScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ package?: string; start_task?: string; completed_tasks?: string; affected_side?: string }>();

  const onReady = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.replace({
      pathname: "/assessment",
      params: {
        package: params.package || "initial",
        start_task: params.start_task || "",
        completed_tasks: params.completed_tasks || "",
        affected_side: params.affected_side || "right",
      },
    });
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="camera-check-back" accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Set up your camera</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} showsVerticalScrollIndicator={false}>
        <View style={styles.frameHint} testID="camera-frame-hint">
          <Ionicons name="body-outline" size={60} color={colors.brandPrimary} />
          <View style={styles.frameCorner} />
          <View style={[styles.frameCorner, styles.frameCornerTR]} />
          <View style={[styles.frameCorner, styles.frameCornerBL]} />
          <View style={[styles.frameCorner, styles.frameCornerBR]} />
        </View>
        <Text style={styles.lead}>A good setup gives you an accurate result. Take a moment to check these before you start.</Text>

        {TIPS.map((tip) => (
          <View key={tip.title} style={styles.tipCard} testID={`camera-tip-${tip.icon}`}>
            <View style={styles.tipIcon}><Ionicons name={tip.icon} size={22} color={colors.brandPrimary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.tipTitle}>{tip.title}</Text>
              <Text style={styles.tipBody}>{tip.body}</Text>
            </View>
          </View>
        ))}
      </ScrollView>

      <View style={[styles.footer, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable testID="camera-check-ready" onPress={onReady} style={styles.readyBtn}>
          <Ionicons name="videocam" size={20} color={colors.onBrandPrimary} />
          <Text style={styles.readyText}>I&apos;m set up — start</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  scroll: { width: "100%", maxWidth: 620, alignSelf: "center", padding: spacing.lg, gap: spacing.sm, paddingBottom: spacing.xl },
  frameHint: { height: 150, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center", marginBottom: spacing.md },
  frameCorner: { position: "absolute", top: 12, left: 12, width: 26, height: 26, borderTopWidth: 3, borderLeftWidth: 3, borderColor: colors.brandPrimary, borderTopLeftRadius: 6 },
  frameCornerTR: { left: undefined, right: 12, borderLeftWidth: 0, borderRightWidth: 3, borderTopLeftRadius: 0, borderTopRightRadius: 6 },
  frameCornerBL: { top: undefined, bottom: 12, borderTopWidth: 0, borderBottomWidth: 3, borderTopLeftRadius: 0, borderBottomLeftRadius: 6 },
  frameCornerBR: { top: undefined, left: undefined, right: 12, bottom: 12, borderTopWidth: 0, borderLeftWidth: 0, borderRightWidth: 3, borderBottomWidth: 3, borderTopLeftRadius: 0, borderBottomRightRadius: 6 },
  lead: { fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary, marginBottom: spacing.sm },
  tipCard: { flexDirection: "row", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  tipIcon: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary },
  tipTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  tipBody: { fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary, marginTop: 2 },
  footer: { padding: spacing.md, borderTopWidth: 1, borderTopColor: colors.divider, backgroundColor: colors.surface },
  readyBtn: { width: "100%", maxWidth: 620, alignSelf: "center", minHeight: 56, borderRadius: radius.md, backgroundColor: colors.brandPrimary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm },
  readyText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "800" },
});
