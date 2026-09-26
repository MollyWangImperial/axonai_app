import { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { Assessment, fetchHistory } from "@/src/api";
import { getCachedUser, preferredNameKey } from "@/src/auth";
import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";
import { useDisplayPreferences } from "@/src/displayPreferences";

const assessmentBenefits = [
  {
    icon: "target" as const,
    number: "01",
    title: "Your next priority",
    detail: "Know what to focus on during the coming week.",
  },
  {
    icon: "hand-heart-outline" as const,
    number: "02",
    title: "Simple ways to help",
    detail: "Get practical actions that support recovery.",
  },
  {
    icon: "chart-line" as const,
    number: "03",
    title: "See your progress",
    detail: "Compare results after every assessment.",
  },
];

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { palette } = useDisplayPreferences();
  const { width } = useWindowDimensions();
  const isWide = width >= 760;
  const [history, setHistory] = useState<Assessment[]>([]);
  const [greetName, setGreetName] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const user = await getCachedUser();
    const [assessments, preferredName] = await Promise.all([
      fetchHistory().catch(() => []),
      user?.id ? storage.getItem(preferredNameKey(user.id), "") : Promise.resolve(""),
    ]);
    setHistory(assessments);
    setGreetName(preferredName || user?.name?.split(" ")[0] || "there");
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const latest = history[0];
  const hasInitialAssessment = history.some((item) => item.assessment_package === "initial");
  const isInitialAssessment = !hasInitialAssessment;
  const assessmentDescription = isInitialAssessment
    ? "The same seven guided arm, hand, and walking observations create your first recovery picture."
    : "A fresh guided check of your arm, hand, and walking.";
  const assessmentButtonLabel = isInitialAssessment ? "Start Initial Assessment" : "Start Next Assessment";

  const startNextSession = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({ pathname: "/session-check" as any, params: { target: "assessment", mode: isInitialAssessment ? "initial" : "followup" } });
  };

  const viewLatestResults = () => {
    if (latest) router.push({ pathname: "/results", params: { id: latest.id } });
  };

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <ScrollView
        contentContainerStyle={[styles.page, { paddingTop: insets.top + spacing.sm }]}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.inner}>
          <View style={styles.header}>
            <View style={styles.brandRow}>
              <View style={styles.brandIcon}>
                <Ionicons name="pulse" size={20} color={colors.onBrandPrimary} />
              </View>
              <Text style={[styles.brand, { color: palette.text }]}>Rehyn</Text>
            </View>
            <View style={styles.headerActions}>
              <Pressable
                testID="home-open-settings"
                accessibilityLabel="Settings"
                onPress={() => router.push("/settings" as any)}
                style={({ pressed }) => [styles.iconButton, { backgroundColor: palette.surface, borderColor: palette.border }, pressed && styles.pressed]}
              >
                <Ionicons name="settings-outline" size={21} color={palette.muted} />
              </Pressable>
              <Pressable
                testID="home-open-profile"
                accessibilityLabel="Profile"
                onPress={() => router.push("/profile" as any)}
                style={({ pressed }) => [styles.avatar, { backgroundColor: palette.soft }, pressed && styles.pressed]}
              >
                <Text style={[styles.avatarText, { color: palette.text }]}>{greetName.slice(0, 1).toUpperCase()}</Text>
              </Pressable>
            </View>
          </View>

          {loading ? (
            <View style={styles.loadingState}>
              <ActivityIndicator color={colors.brandPrimary} />
            </View>
          ) : (
            <>
              <View style={[styles.hero, { backgroundColor: palette.surface }, isWide && styles.heroWide]}>
                <View style={[styles.heroCopy, isWide && styles.heroCopyWide]}>
                  {!isInitialAssessment && (
                    <Text style={[styles.eyebrow, { color: palette.brand }]}>{`WELCOME BACK, ${greetName.toUpperCase()}`}</Text>
                  )}
                  <Text style={[styles.heroTitle, { color: palette.text }, isWide && styles.heroTitleWide]}>
                    {isInitialAssessment
                      ? "See where your recovery stands today"
                      : "See how your recovery looks today"}
                  </Text>
                  <Text style={[styles.heroBody, { color: palette.muted }]}>
                    {assessmentDescription}
                  </Text>

                  <View style={styles.primaryActions}>
                    <Pressable
                      testID="home-start-next-session"
                      onPress={startNextSession}
                      style={({ pressed }) => [styles.startButton, pressed && styles.startButtonPressed]}
                    >
                      <Ionicons name="play" size={18} color={colors.onBrandPrimary} />
                      <Text style={styles.startButtonText}>
                        {assessmentButtonLabel}
                      </Text>
                    </Pressable>
                    <View style={styles.durationRow}>
                      <Ionicons name="time-outline" size={18} color={colors.onSurfaceTertiary} />
                      <Text style={[styles.durationText, { color: palette.muted }]}>About 3 minutes</Text>
                    </View>
                  </View>

                  {!isInitialAssessment && latest && (
                    <Pressable
                      testID="home-view-latest-results"
                      onPress={viewLatestResults}
                      style={({ pressed }) => [styles.resultsLink, pressed && styles.pressed]}
                    >
                      <Ionicons name="analytics-outline" size={18} color={colors.brandPrimary} />
                      <Text style={styles.resultsLinkText}>View latest results</Text>
                      <Ionicons name="arrow-forward" size={17} color={colors.brandPrimary} />
                    </Pressable>
                  )}
                </View>

                <View style={[styles.artwork, isWide && styles.artworkWide]}>
                  <Image
                    source={require("../../assets/images/rehyn-home-reach.png")}
                    resizeMode="contain"
                    style={styles.heroImage}
                    accessibilityLabel="An older adult completing a comfortable guided shoulder reach"
                  />
                </View>
              </View>

              <View style={styles.discoverySection}>
                <Text style={[styles.discoveryHeading, { color: palette.text }]}>{"What you'll get after every assessment"}</Text>
                <View style={[styles.discoveryRow, { backgroundColor: palette.surface, borderColor: palette.border }, !isWide && styles.discoveryRowCompact]}>
                  {assessmentBenefits.map((benefit, index) => (
                    <View
                      key={benefit.title}
                      style={[
                        styles.discoveryItem,
                        !isWide && styles.discoveryItemCompact,
                        index > 0 && styles.discoveryItemDivided,
                        !isWide && index > 0 && styles.discoveryItemDividedCompact,
                      ]}
                    >
                      <View style={styles.discoveryNumber}>
                        <Text style={styles.discoveryNumberText}>{benefit.number}</Text>
                      </View>
                      <View style={styles.discoveryMainRow}>
                        <View style={styles.discoveryIcon}>
                          <MaterialCommunityIcons name={benefit.icon} size={isWide ? 58 : 46} color={colors.brand} />
                        </View>
                        <Text style={[styles.discoveryTitle, { color: palette.text }]}>{benefit.title}</Text>
                      </View>
                      <Text style={[styles.discoveryDetail, { color: palette.muted }, !isWide && styles.discoveryDetailCompact]}>{benefit.detail}</Text>
                    </View>
                  ))}
                </View>
              </View>
            </>
          )}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  page: { paddingHorizontal: 20, paddingBottom: 128 },
  inner: { width: "100%", maxWidth: 1080, alignSelf: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: 72,
    marginBottom: 20,
  },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  brandIcon: {
    width: 44,
    height: 44,
    borderRadius: 14,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  brand: { fontSize: 26, lineHeight: 32, fontWeight: "800", color: colors.onSurface },
  headerActions: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  iconButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  avatar: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { color: colors.onSurface, fontSize: 18, lineHeight: 22, fontWeight: "800" },
  pressed: { opacity: 0.68 },
  loadingState: { minHeight: 420, alignItems: "center", justifyContent: "center" },
  hero: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    overflow: "hidden",
    paddingTop: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  heroWide: {
    minHeight: 530,
    paddingTop: 0,
    paddingHorizontal: spacing.xl,
    flexDirection: "row",
    alignItems: "center",
  },
  heroCopy: { paddingHorizontal: spacing.lg, zIndex: 2 },
  heroCopyWide: { width: "48%", paddingHorizontal: spacing.md, paddingVertical: spacing.xxl },
  eyebrow: { fontSize: 14, lineHeight: 20, fontWeight: "800", letterSpacing: 0.7, color: colors.brandPrimary },
  heroTitle: {
    maxWidth: 500,
    marginTop: spacing.sm,
    fontSize: 36,
    lineHeight: 44,
    fontWeight: "800",
    color: colors.onSurface,
  },
  heroTitleWide: { fontSize: 50, lineHeight: 59 },
  heroBody: {
    maxWidth: 460,
    marginTop: spacing.md,
    fontSize: 18,
    lineHeight: 28,
    color: colors.onSurfaceSecondary,
  },
  primaryActions: { marginTop: spacing.lg, alignItems: "flex-start", gap: spacing.sm },
  startButton: {
    minHeight: 58,
    minWidth: 258,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.brandPrimary,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    shadowColor: colors.onBrandTertiary,
    shadowOpacity: 0.16,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 7 },
    elevation: 3,
  },
  startButtonPressed: { backgroundColor: colors.onBrandTertiary, transform: [{ scale: 0.99 }] },
  startButtonText: { color: colors.onBrandPrimary, fontSize: 17, lineHeight: 22, fontWeight: "800" },
  durationRow: { minHeight: 28, flexDirection: "row", alignItems: "center", gap: 7 },
  durationText: { color: colors.onSurfaceTertiary, fontSize: 16, lineHeight: 22, fontWeight: "700" },
  resultsLink: {
    minHeight: 48,
    marginTop: spacing.sm,
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: spacing.xs,
  },
  resultsLinkText: { color: colors.brandPrimary, fontSize: 16, lineHeight: 22, fontWeight: "800" },
  artwork: { height: 240, marginTop: spacing.sm, position: "relative" },
  artworkWide: { width: "52%", height: 500, marginTop: 0 },
  heroImage: { width: "100%", height: "100%" },
  discoverySection: { paddingTop: spacing.xl, paddingBottom: spacing.lg },
  discoveryHeading: {
    marginBottom: spacing.md,
    fontSize: 22,
    lineHeight: 29,
    fontWeight: "800",
    color: colors.onSurface,
  },
  discoveryRow: {
    flexDirection: "row",
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    overflow: "hidden",
  },
  discoveryRowCompact: { flexDirection: "column" },
  discoveryItem: {
    flex: 1,
    minWidth: 0,
    minHeight: 258,
    justifyContent: "center",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.lg,
  },
  discoveryItemDivided: { borderLeftWidth: 1, borderLeftColor: colors.border },
  discoveryItemCompact: {
    minHeight: 176,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  discoveryItemDividedCompact: { borderLeftWidth: 0, borderTopWidth: 1, borderTopColor: colors.border },
  discoveryNumber: {
    width: 48,
    height: 48,
    marginBottom: spacing.md,
    borderRadius: 24,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  discoveryNumberText: { color: colors.brandPrimary, fontSize: 16, lineHeight: 21, fontWeight: "900" },
  discoveryMainRow: { minHeight: 64, flexDirection: "row", alignItems: "center", gap: spacing.md },
  discoveryIcon: {
    width: 64,
    height: 64,
    alignItems: "center",
    justifyContent: "center",
  },
  discoveryTitle: { flex: 1, minWidth: 0, fontSize: 20, lineHeight: 26, fontWeight: "800", color: colors.onSurface },
  discoveryDetail: { maxWidth: 290, marginTop: spacing.md, fontSize: 17, lineHeight: 26, color: colors.onSurfaceSecondary },
  discoveryDetailCompact: { maxWidth: "100%" },
});
