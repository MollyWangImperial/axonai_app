import { useCallback, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { Assessment, fetchHistory } from "@/src/api";
import { getCachedUser, preferredNameKey } from "@/src/auth";
import { JournalEntry, loadJournalEntries } from "@/src/journal";
import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [history, setHistory] = useState<Assessment[]>([]);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [greetName, setGreetName] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const user = await getCachedUser();
    const [assessments, journal, preferredName] = await Promise.all([
      fetchHistory().catch(() => []),
      loadJournalEntries(),
      user?.id ? storage.getItem(preferredNameKey(user.id), "") : Promise.resolve(""),
    ]);
    setHistory(assessments);
    setEntries(journal);
    setGreetName(preferredName || user?.name?.split(" ")[0] || "there");
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const latest = history[0];
  const hasInitialAssessment = history.some((item) => item.assessment_package === "initial");
  const isInitialAssessment = !hasInitialAssessment;
  const completedThisWeek = Math.min(7, history.length + Math.min(4, entries.length));
  const weeklyPercent = Math.round((completedThisWeek / 7) * 100);

  const startNextSession = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push({ pathname: "/session-check" as any, params: { target: "assessment", mode: isInitialAssessment ? "initial" : "followup" } });
  };

  const viewLatestResults = () => {
    if (latest) router.push({ pathname: "/results", params: { id: latest.id } });
  };

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={[styles.page, { paddingTop: insets.top + spacing.md }]} showsVerticalScrollIndicator={false}>
        <View style={styles.inner}>
          <View style={styles.header}>
            <View style={styles.brandRow}>
              <View style={styles.brandIcon}><Ionicons name="pulse" size={19} color={colors.onBrandPrimary} /></View>
              <Text style={styles.brand}>Rehyn</Text>
            </View>
            <View style={styles.headerActions}>
              <Pressable accessibilityLabel="Notifications" style={styles.iconButton}><Ionicons name="notifications-outline" size={20} color={colors.onSurfaceSecondary} /></Pressable>
              <Pressable testID="home-open-settings" accessibilityLabel="Settings" onPress={() => router.push("/settings" as any)} style={styles.iconButton}><Ionicons name="settings-outline" size={20} color={colors.onSurfaceSecondary} /></Pressable>
              <Pressable testID="home-open-profile" accessibilityLabel="Profile" onPress={() => router.push("/profile" as any)} style={styles.avatar}><Text style={styles.avatarText}>{greetName.slice(0, 1).toUpperCase()}</Text></Pressable>
            </View>
          </View>

          <View style={styles.welcomeCard}>
            <View style={styles.welcomeBar} />
            <View style={{ flex: 1 }}>
              <Text style={styles.welcomeLabel}>Welcome back, {greetName}</Text>
              <Text style={styles.welcomeText}>{isInitialAssessment ? "Let's learn where to begin, together." : "Every step forward counts. You are building consistency."}</Text>
            </View>
          </View>

          <View style={styles.goalCard}>
            <View style={styles.goalRing}>
              <Text style={styles.goalPercent}>{weeklyPercent}%</Text>
              <Text style={styles.goalWord}>GOAL</Text>
            </View>
            <View style={styles.goalCopy}>
              <Text style={styles.goalTitle}>Weekly active goal</Text>
              <Text style={styles.goalSubtitle}>
                {isInitialAssessment
                  ? "Begin with your Initial Assessment"
                  : "Your next movement check-in is ready"}
              </Text>
              <View style={styles.goalMetaRow}>
                <View style={styles.metaPill}><Ionicons name="checkmark" size={13} color={colors.brandPrimary} /><Text style={styles.metaText}>{completedThisWeek}/7 sessions</Text></View>
                <View style={styles.streakPill}><Ionicons name="flame-outline" size={13} color={colors.warning} /><Text style={styles.streakText}>{Math.max(1, entries.length)} day streak</Text></View>
              </View>
            </View>
          </View>

          <View style={styles.sessionCard}>
            <View style={styles.sessionTopRow}>
              <Text style={styles.sessionBadge}>{isInitialAssessment ? "GET STARTED" : "NEXT ASSESSMENT"}</Text>
              <View style={styles.duration}><Ionicons name="time-outline" size={15} color="#E8F0EA" /><Text style={styles.durationText}>15 mins</Text></View>
            </View>
            <Text style={styles.sessionTitle}>{isInitialAssessment ? "Initial Assessment" : "Next Assessment"}</Text>
            <Text style={styles.sessionDescription}>
              {isInitialAssessment
                ? "The same seven guided arm, hand, and walking observations for every new patient, so we can understand your movement broadly."
                : "Complete the same guided movement collection again so changes in your upper limb, hand function, and walking can be compared over time."}
            </Text>
            <Pressable testID="home-start-next-session" onPress={startNextSession} style={styles.startButton}>
              <Ionicons name="play" size={18} color={colors.brandPrimary} />
              <Text style={styles.startButtonText}>{isInitialAssessment ? "Start Initial Assessment" : "Start Next Assessment"}</Text>
            </Pressable>
            {!isInitialAssessment && latest && (
              <Pressable testID="home-view-latest-results" onPress={viewLatestResults} style={styles.resultsButton}>
                <Ionicons name="analytics-outline" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.resultsButtonText}>View latest results</Text>
              </Pressable>
            )}
          </View>

          <View style={styles.sectionHeader}>
            <Text style={styles.sectionTitle}>Journal & milestones</Text>
            <Pressable testID="home-add-journal" onPress={() => router.push("/journey" as any)} style={styles.addEntry}>
              <Ionicons name="add" size={17} color={colors.brandPrimary} />
              <Text style={styles.addEntryText}>Add entry</Text>
            </Pressable>
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} /> : entries.length === 0 ? (
            <Pressable onPress={() => router.push("/journey" as any)} style={styles.emptyJournal}>
              <View style={styles.journalIcon}><Ionicons name="book-outline" size={21} color={colors.brandPrimary} /></View>
              <View style={{ flex: 1 }}>
                <Text style={styles.journalTitle}>Record your first recovery note</Text>
                <Text style={styles.journalBody}>Small observations help make future support more personal.</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.borderStrong} />
            </Pressable>
          ) : entries.slice(0, 2).map((entry) => (
            <View key={entry.id} style={styles.journalCard}>
              <View style={styles.journalTopRow}>
                <Text style={styles.journalTag}>{entry.tag}</Text>
                <Text style={styles.journalDate}>{new Date(entry.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</Text>
              </View>
              <Text style={styles.journalBody} numberOfLines={3}>{entry.body}</Text>
            </View>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  page: { paddingHorizontal: spacing.md, paddingBottom: 110 },
  inner: { width: "100%", maxWidth: 620, alignSelf: "center", gap: spacing.md },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", minHeight: 52 },
  brandRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  brandIcon: { width: 34, height: 34, borderRadius: radius.sm, backgroundColor: "#24594F", alignItems: "center", justifyContent: "center" },
  brand: { fontSize: 22, fontWeight: "800", color: "#24594F" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  iconButton: { width: 38, height: 38, borderRadius: 19, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  avatar: { width: 38, height: 38, borderRadius: 19, backgroundColor: colors.brandSecondary, alignItems: "center", justifyContent: "center" },
  avatarText: { color: colors.onBrandSecondary, fontWeight: "800" },
  welcomeCard: { flexDirection: "row", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, backgroundColor: "#EAF1EF" },
  welcomeBar: { width: 4, borderRadius: 2, backgroundColor: "#3C8273" },
  welcomeLabel: { fontSize: 13, color: colors.onSurfaceSecondary },
  welcomeText: { fontSize: 15, lineHeight: 21, fontWeight: "800", color: colors.onSurface },
  goalCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  goalRing: { width: 78, height: 78, borderRadius: 39, borderWidth: 8, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
  goalPercent: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  goalWord: { fontSize: 9, color: colors.onSurfaceTertiary, fontWeight: "700" },
  goalCopy: { flex: 1, minWidth: 0 },
  goalTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  goalSubtitle: { fontSize: 12, lineHeight: 17, color: colors.onSurfaceTertiary, marginTop: 2 },
  goalMetaRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs, marginTop: spacing.sm },
  metaPill: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.sm, paddingVertical: 5, borderRadius: radius.pill },
  metaText: { fontSize: 11, color: colors.onSurfaceSecondary, fontWeight: "700" },
  streakPill: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: "#FFF3DC", paddingHorizontal: spacing.sm, paddingVertical: 5, borderRadius: radius.pill },
  streakText: { fontSize: 11, color: "#8A5B18", fontWeight: "700" },
  sessionCard: { padding: spacing.md, borderRadius: radius.md, backgroundColor: "#24594F", gap: spacing.xs },
  sessionTopRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  sessionBadge: { color: "#DDEBE6", backgroundColor: "rgba(255,255,255,0.13)", borderRadius: radius.sm, paddingHorizontal: spacing.sm, paddingVertical: 5, fontSize: 10, fontWeight: "800" },
  duration: { flexDirection: "row", alignItems: "center", gap: 4 },
  durationText: { color: "#E8F0EA", fontSize: 12, fontWeight: "700" },
  sessionTitle: { color: "#FFFFFF", fontSize: 21, fontWeight: "800", marginTop: spacing.sm },
  sessionDescription: { color: "#E8F0EA", fontSize: 13, lineHeight: 19 },
  startButton: { minHeight: 48, marginTop: spacing.sm, borderRadius: radius.sm, backgroundColor: colors.surface, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs },
  startButtonText: { color: colors.brandPrimary, fontSize: 15, fontWeight: "800" },
  resultsButton: { minHeight: 42, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs },
  resultsButtonText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "700" },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  sectionTitle: { fontSize: 17, fontWeight: "800", color: colors.onSurface },
  addEntry: { flexDirection: "row", alignItems: "center", gap: 3, minHeight: 40, paddingHorizontal: spacing.xs },
  addEntryText: { fontSize: 13, fontWeight: "800", color: colors.brandPrimary },
  emptyJournal: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  journalIcon: { width: 42, height: 42, borderRadius: 21, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  journalTitle: { fontSize: 14, fontWeight: "800", color: colors.onSurface },
  journalBody: { fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary },
  journalCard: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  journalTopRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.xs },
  journalTag: { fontSize: 11, fontWeight: "800", color: colors.brandPrimary },
  journalDate: { fontSize: 11, color: colors.onSurfaceTertiary },
});
