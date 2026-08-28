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
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { Assessment, fetchHistory } from "@/src/api";
import { getCachedUser, preferredNameKey } from "@/src/auth";
import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";

const assessmentBenefits = [
  {
    icon: "locate-outline" as const,
    title: "What to focus on",
    detail: "Your clearest priority for the week",
    backgroundColor: "#F2EEF8",
    iconColor: "#6750A4",
  },
  {
    icon: "heart-outline" as const,
    title: "How you can help",
    detail: "Simple ways to support recovery",
    backgroundColor: "#FFF3E5",
    iconColor: "#A85F12",
  },
  {
    icon: "trending-up-outline" as const,
    title: "Track progress over time",
    detail: "A clear record after every assessment",
    backgroundColor: "#EAF3F8",
    iconColor: "#356C91",
  },
];

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
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
    <View style={styles.container}>
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
              <Text style={styles.brand}>Rehyn</Text>
            </View>
            <View style={styles.headerActions}>
              <Pressable
                testID="home-open-settings"
                accessibilityLabel="Settings"
                onPress={() => router.push("/settings" as any)}
                style={({ pressed }) => [styles.iconButton, pressed && styles.pressed]}
              >
                <Ionicons name="settings-outline" size={21} color={colors.onSurfaceSecondary} />
              </Pressable>
              <Pressable
                testID="home-open-profile"
                accessibilityLabel="Profile"
                onPress={() => router.push("/profile" as any)}
                style={({ pressed }) => [styles.avatar, pressed && styles.pressed]}
              >
                <Text style={styles.avatarText}>{greetName.slice(0, 1).toUpperCase()}</Text>
              </Pressable>
            </View>
          </View>

          {loading ? (
            <View style={styles.loadingState}>
              <ActivityIndicator color={colors.brandPrimary} />
            </View>
          ) : (
            <>
              <View style={[styles.hero, isWide && styles.heroWide]}>
                <View style={[styles.heroCopy, isWide && styles.heroCopyWide]}>
                  {!isInitialAssessment && (
                    <Text style={styles.eyebrow}>{`WELCOME BACK, ${greetName.toUpperCase()}`}</Text>
                  )}
                  <Text style={[styles.heroTitle, isWide && styles.heroTitleWide]}>
                    {isInitialAssessment
                      ? "See where your recovery stands today"
                      : "See how your recovery looks today"}
                  </Text>
                  <Text style={styles.heroBody}>
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
                      <Text style={styles.durationText}>About 3 minutes</Text>
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
                <Text style={styles.discoveryHeading}>What every assessment gives you</Text>
                <View style={[styles.discoveryRow, !isWide && styles.discoveryRowCompact]}>
                  {assessmentBenefits.map((benefit) => (
                    <View
                      key={benefit.title}
                      style={[
                        styles.discoveryItem,
                        !isWide && styles.discoveryItemCompact,
                        { backgroundColor: benefit.backgroundColor },
                      ]}
                    >
                      <View style={[styles.discoveryIcon, !isWide && styles.discoveryIconCompact]}>
                        <Ionicons name={benefit.icon} size={22} color={benefit.iconColor} />
                      </View>
                      <View style={styles.discoveryCopy}>
                        <Text style={[styles.discoveryTitle, !isWide && styles.discoveryTitleCompact]}>
                          {benefit.title}
                        </Text>
                        <Text style={[styles.discoveryDetail, !isWide && styles.discoveryDetailCompact]}>
                          {benefit.detail}
                        </Text>
                      </View>
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
  page: { paddingHorizontal: spacing.md, paddingBottom: 108 },
  inner: { width: "100%", maxWidth: 1080, alignSelf: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    minHeight: 64,
    marginBottom: spacing.md,
  },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  brandIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.sm,
    backgroundColor: "#1F6255",
    alignItems: "center",
    justifyContent: "center",
  },
  brand: { fontSize: 24, fontWeight: "800", color: "#17483F" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  iconButton: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  avatar: {
    width: 42,
    height: 42,
    borderRadius: 21,
    backgroundColor: "#DDEBE1",
    alignItems: "center",
    justifyContent: "center",
  },
  avatarText: { color: colors.onSurface, fontSize: 16, fontWeight: "800" },
  pressed: { opacity: 0.68 },
  loadingState: { minHeight: 420, alignItems: "center", justifyContent: "center" },
  hero: {
    backgroundColor: "#F5F8F6",
    borderRadius: radius.sm,
    overflow: "hidden",
    paddingTop: spacing.lg,
  },
  heroWide: {
    minHeight: 530,
    paddingTop: 0,
    paddingHorizontal: spacing.xl,
    flexDirection: "row",
    alignItems: "center",
  },
  heroCopy: { paddingHorizontal: spacing.md, zIndex: 2 },
  heroCopyWide: { width: "48%", paddingHorizontal: spacing.md, paddingVertical: spacing.xxl },
  eyebrow: { fontSize: 12, lineHeight: 18, fontWeight: "800", color: colors.brandPrimary },
  heroTitle: {
    maxWidth: 500,
    marginTop: spacing.sm,
    fontSize: 34,
    lineHeight: 40,
    fontWeight: "800",
    color: "#183A32",
  },
  heroTitleWide: { fontSize: 48, lineHeight: 57 },
  heroBody: {
    maxWidth: 440,
    marginTop: spacing.md,
    fontSize: 16,
    lineHeight: 24,
    color: colors.onSurfaceSecondary,
  },
  primaryActions: { marginTop: 20, alignItems: "flex-start", gap: spacing.sm },
  startButton: {
    minHeight: 54,
    minWidth: 244,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.sm,
    backgroundColor: "#1F6A59",
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.xs,
    shadowColor: "#16483D",
    shadowOpacity: 0.18,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 7 },
    elevation: 3,
  },
  startButtonPressed: { backgroundColor: "#174F43", transform: [{ scale: 0.99 }] },
  startButtonText: { color: colors.onBrandPrimary, fontSize: 16, fontWeight: "800" },
  durationRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  durationText: { color: colors.onSurfaceTertiary, fontSize: 13, fontWeight: "700" },
  resultsLink: {
    minHeight: 44,
    marginTop: spacing.sm,
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: 6,
  },
  resultsLinkText: { color: colors.brandPrimary, fontSize: 14, fontWeight: "800" },
  artwork: { height: 220, marginTop: spacing.sm, position: "relative" },
  artworkWide: { width: "52%", height: 500, marginTop: 0 },
  heroImage: { width: "100%", height: "100%" },
  discoverySection: { paddingVertical: spacing.lg },
  discoveryHeading: {
    marginBottom: spacing.lg,
    textAlign: "center",
    fontSize: 18,
    lineHeight: 24,
    fontWeight: "800",
    color: colors.onSurface,
  },
  discoveryRow: { flexDirection: "row", gap: spacing.md },
  discoveryRowCompact: { flexDirection: "column", gap: spacing.sm },
  discoveryItem: {
    flex: 1,
    minHeight: 154,
    alignItems: "flex-start",
    justifyContent: "center",
    padding: spacing.lg,
    borderRadius: radius.sm,
  },
  discoveryItemCompact: {
    minHeight: 94,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "flex-start",
  },
  discoveryIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: "#E9F2EB",
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  discoveryIconCompact: { marginRight: spacing.md, marginBottom: 0 },
  discoveryCopy: { flex: 1, minWidth: 0 },
  discoveryTitle: { fontSize: 16, lineHeight: 21, fontWeight: "800", color: colors.onSurface },
  discoveryTitleCompact: { fontSize: 15, lineHeight: 20 },
  discoveryDetail: { marginTop: 5, fontSize: 12, lineHeight: 17, color: colors.onSurfaceTertiary },
  discoveryDetailCompact: { marginTop: 2 },
});
