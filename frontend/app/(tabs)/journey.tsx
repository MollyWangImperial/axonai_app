import { useCallback, useState } from "react";
import { ActivityIndicator, Image, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from "react-native";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Assessment, fetchHistory } from "@/src/api";
import { authedFetch } from "@/src/auth";
import { addJournalEntry, JournalEntry, loadJournalEntries } from "@/src/journal";
import { colors, radius, spacing } from "@/src/theme";
import { DEMO_ASSESSMENT_ID } from "@/src/demoAssessment";
import { loadUserPreferences } from "@/src/userPreferences";
import { getScreenCache, setScreenCache } from "@/src/screenCache";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { JourneyProgressPanel } from "@/src/components/JourneyProgressPanel";

const brainImage = require("@/assets/images/journey-stroke-brain.png");
const familyImage = require("@/assets/images/journey-family-support.png");

type JourneyScreenCache = {
  history: Assessment[];
  entries: JournalEntry[];
  demoMode: boolean;
  exercisesCompleted: number;
  sessionDays: number;
};

function assessmentPlanLabel(item: Assessment) {
  if (item.rehab_plan.length) return `${item.rehab_plan.length} recommended exercise${item.rehab_plan.length === 1 ? "" : "s"}`;
  if (item.clinical_review_gate?.status === "no_rehab_needed") return "No rehab plan recommended";
  if (["research_ready", "validated"].includes(item.patient_insights?.status || "")) return "Movement snapshot ready";
  if (item.clinical_review_gate?.status === "awaiting_model_analysis") return "Movement analysis in progress";
  return "Assessment summary ready";
}

export default function JourneyScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { action } = useLocalSearchParams<{ action?: string }>();
  const { palette } = useDisplayPreferences();
  const { width } = useWindowDimensions();
  const wide = width >= 760;
  const cached = getScreenCache<JourneyScreenCache>("journey");
  const [history, setHistory] = useState<Assessment[]>(cached?.history ?? []);
  const [entries, setEntries] = useState<JournalEntry[]>(cached?.entries ?? []);
  const [loading, setLoading] = useState(!cached);
  const [showComposer, setShowComposer] = useState(false);
  const [draft, setDraft] = useState("");
  const [demoMode, setDemoMode] = useState(cached?.demoMode ?? false);
  const [exercisesCompleted, setExercisesCompleted] = useState(cached?.exercisesCompleted ?? 0);
  const [sessionDays, setSessionDays] = useState(cached?.sessionDays ?? 0);
  const initialAssessmentId = [...history].reverse().find((item) => item.assessment_package === "initial")?.id ?? history[history.length - 1]?.id;

  const load = useCallback(async () => {
    // Stale-while-revalidate: refresh silently when cached data is on screen.
    if (!getScreenCache<JourneyScreenCache>("journey")) setLoading(true);
    const [assessments, journal, preferences, rewards] = await Promise.all([
      fetchHistory().catch(() => []),
      loadJournalEntries(),
      loadUserPreferences(),
      authedFetch("/api/users/rewards")
        .then(async (response) => response.ok ? response.json() : null)
        .catch(() => null),
    ]);
    const nextExercisesCompleted = Number(rewards?.breakdown?.exercises_completed ?? 0);
    const nextSessionDays = Number(rewards?.breakdown?.session_days ?? 0);
    setHistory(assessments);
    setEntries(journal);
    setDemoMode(preferences.demoMode);
    setExercisesCompleted(nextExercisesCompleted);
    setSessionDays(nextSessionDays);
    setScreenCache<JourneyScreenCache>("journey", { history: assessments, entries: journal, demoMode: preferences.demoMode, exercisesCompleted: nextExercisesCompleted, sessionDays: nextSessionDays });
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));
  useFocusEffect(useCallback(() => {
    if (action === "new-journal") setShowComposer(true);
  }, [action]));

  const saveEntry = async () => {
    if (!draft.trim()) return;
    const nextEntries = await addJournalEntry(draft);
    setEntries(nextEntries);
    setScreenCache<JourneyScreenCache>("journey", { history, entries: nextEntries, demoMode, exercisesCompleted, sessionDays });
    setDraft("");
    setShowComposer(false);
  };

  const askAlira = (prompt: string) => router.push({ pathname: "/chat", params: { prompt } });

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <ScrollView contentContainerStyle={[styles.content, { paddingTop: insets.top + spacing.md }]} showsVerticalScrollIndicator={false}>
        <View style={styles.page}>
          <View style={styles.headerRow}>
            <Text style={[styles.title, { color: palette.text }]}>Journey</Text>
            <Pressable testID="journey-add-entry" onPress={() => setShowComposer(true)} style={styles.addButton}>
              <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
              <Text style={styles.addButtonText}>Add entry</Text>
            </Pressable>
          </View>

          {/* Completed work always leads the page: what the patient has DONE,
              followed by the progress metrics below. */}
          <View style={[styles.completionStrip, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="journey-completion-summary">
            <View style={styles.completionStat}>
              <Text style={[styles.completionNumber, { color: palette.text }]}>{history.length}</Text>
              <Text style={[styles.completionLabel, { color: palette.muted }]}>{history.length === 1 ? "assessment completed" : "assessments completed"}</Text>
            </View>
            <View style={[styles.completionDivider, { backgroundColor: palette.border }]} />
            <View style={styles.completionStat}>
              <Text style={[styles.completionNumber, { color: palette.text }]}>{exercisesCompleted}</Text>
              <Text style={[styles.completionLabel, { color: palette.muted }]}>{exercisesCompleted === 1 ? "exercise completed" : "exercises completed"}</Text>
            </View>
            <View style={[styles.completionDivider, { backgroundColor: palette.border }]} />
            <View style={styles.completionStat}>
              <Text style={[styles.completionNumber, { color: palette.text }]}>{sessionDays}</Text>
              <Text style={[styles.completionLabel, { color: palette.muted }]}>{sessionDays === 1 ? "session day" : "session days"}</Text>
            </View>
          </View>

          <JourneyProgressPanel demoMode={demoMode} />

          <Text style={[styles.sectionTitle, { color: palette.text }]}>Journal & milestones</Text>
          {entries.length === 0 ? (
            <Pressable onPress={() => setShowComposer(true)} style={[styles.journalPrompt, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <View style={[styles.sectionIcon, { backgroundColor: palette.soft }]}><Ionicons name="book-outline" size={24} color={palette.brand} /></View>
              <Text style={[styles.journalPromptText, { color: palette.text }]}>Capture a small win</Text>
              <View style={styles.smallAddButton}><Ionicons name="add" size={19} color={colors.onBrandPrimary} /><Text style={styles.smallAddText}>Add entry</Text></View>
            </Pressable>
          ) : entries.map((entry) => (
            <View key={entry.id} style={[styles.entryCard, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <View style={styles.entryTop}>
                <Text style={styles.entryTag}>{entry.tag}</Text>
                <Text style={[styles.entryDate, { color: palette.muted }]}>{new Date(entry.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</Text>
              </View>
              <Text style={[styles.entryBody, { color: palette.muted }]}>{entry.body}</Text>
            </View>
          ))}

          <Text style={[styles.sectionTitle, { color: palette.text }]} testID="assessment-history">Assessment history</Text>
          {loading ? <ActivityIndicator color={colors.brandPrimary} /> : history.length === 0 && !demoMode ? (
            <View style={[styles.historyEmpty, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <View style={[styles.sectionIcon, { backgroundColor: palette.soft }]}><Ionicons name="clipboard-outline" size={24} color={palette.brand} /></View>
              <Text style={[styles.historyEmptyText, { color: palette.muted }]}>Your assessments will appear here</Text>
              <Ionicons name="sparkles" size={18} color="#78A87E" />
            </View>
          ) : <>
            {demoMode && (
              <Pressable testID="assessment-history-demo" onPress={() => router.push({ pathname: "/function-summary" as never, params: { id: DEMO_ASSESSMENT_ID } })} style={[styles.historyRow, styles.demoHistoryRow, { backgroundColor: palette.surface }]}>
                <View style={[styles.historyIcon, styles.demoHistoryIcon]}><Ionicons name="sparkles" size={21} color="#7B5EA7" /></View>
                <View style={styles.historyCopy}>
                  <View style={styles.demoTitleRow}><Text style={[styles.historyTitle, { color: palette.text }]}>Demo assessment summary</Text><Text style={styles.demoBadge}>SAMPLE</Text></View>
                  <Text style={[styles.historyMeta, { color: palette.muted }]}>Explore a sample function summary, movement story and map</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={colors.borderStrong} />
              </Pressable>
            )}
            {history.slice(0, 6).map((item) => (
              <Pressable key={item.id} testID={`assessment-history-${item.id}`} onPress={() => router.push({ pathname: "/function-summary" as never, params: { id: item.id } })} style={[styles.historyRow, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <View style={[styles.historyIcon, { backgroundColor: palette.soft }]}><Ionicons name="analytics-outline" size={21} color={palette.brand} /></View>
              <View style={styles.historyCopy}>
                <Text style={[styles.historyTitle, { color: palette.text }]}>{item.id === initialAssessmentId ? "Initial Assessment" : "Movement check-in"}</Text>
                <Text style={[styles.historyMeta, { color: palette.muted }]}>{new Date(item.created_at).toLocaleDateString()} · {assessmentPlanLabel(item)}</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.borderStrong} />
              </Pressable>
            ))}
          </>}

          <Text style={[styles.sectionTitle, { color: palette.text }]}>Learn about stroke recovery</Text>
          <View style={[styles.articleGrid, wide && styles.articleGridWide]}>
            <Pressable onPress={() => askAlira("Can you explain what happens after a stroke in simple language?")} style={[styles.articleCard, wide && styles.articleCardWide, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <Image source={brainImage} resizeMode="cover" style={styles.articleImage} />
              <View style={[styles.articleFooter, { backgroundColor: palette.surface }]}>
                <View style={[styles.articleIcon, { backgroundColor: palette.soft }]}><Ionicons name="book-outline" size={23} color={palette.brand} /></View>
                <Text style={[styles.articleTitle, { color: palette.text }]}>What happens after a stroke?</Text>
                <Ionicons name="chevron-forward" size={19} color={palette.muted} />
              </View>
            </Pressable>
            <Pressable onPress={() => askAlira("How can family members support stroke recovery day to day?")} style={[styles.articleCard, wide && styles.articleCardWide, { backgroundColor: palette.surface, borderColor: palette.border }]}>
              <Image source={familyImage} resizeMode="cover" style={styles.articleImage} />
              <View style={[styles.articleFooter, { backgroundColor: palette.surface }]}>
                <View style={[styles.articleIcon, { backgroundColor: palette.soft }]}><Ionicons name="heart" size={22} color={palette.brand} /></View>
                <Text style={[styles.articleTitle, { color: palette.text }]}>How family support helps</Text>
                <Ionicons name="chevron-forward" size={19} color={palette.muted} />
              </View>
            </Pressable>
          </View>
        </View>
      </ScrollView>

      <Modal visible={showComposer} transparent animationType="slide" onRequestClose={() => setShowComposer(false)}>
        <View style={styles.modalScrim}>
          <View style={[styles.composer, { paddingBottom: Math.max(insets.bottom, spacing.lg), backgroundColor: palette.surface }]}>
            <View style={styles.composerHeader}>
              <Text style={[styles.composerTitle, { color: palette.text }]}>New journal entry</Text>
              <Pressable onPress={() => setShowComposer(false)}><Ionicons name="close" size={26} color={palette.text} /></Pressable>
            </View>
            <TextInput testID="journey-entry-input" value={draft} onChangeText={setDraft} multiline autoFocus placeholder="What felt different today?" placeholderTextColor={palette.muted} style={[styles.input, { backgroundColor: palette.soft, color: palette.text }]} />
            <Pressable testID="journey-save-entry" disabled={!draft.trim()} onPress={saveEntry} style={[styles.saveButton, !draft.trim() && { opacity: 0.4 }]}>
              <Text style={styles.saveButtonText}>Save entry</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#FCFDFB" },
  content: { paddingHorizontal: spacing.md, paddingBottom: 120 },
  page: { width: "100%", maxWidth: 1080, alignSelf: "center", gap: spacing.md },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.xs },
  completionStrip: { flexDirection: "row", alignItems: "center", borderWidth: 1, borderRadius: radius.md, paddingVertical: spacing.md, paddingHorizontal: spacing.sm, marginBottom: spacing.sm },
  completionStat: { flex: 1, alignItems: "center", gap: 2 },
  completionNumber: { fontSize: 26, lineHeight: 32, fontWeight: "900" },
  completionLabel: { fontSize: 11, lineHeight: 15, fontWeight: "700", textAlign: "center" },
  completionDivider: { width: 1, alignSelf: "stretch", marginVertical: 4 },
  title: { fontSize: 34, lineHeight: 40, fontWeight: "900", color: "#113126" },
  addButton: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: spacing.md, minHeight: 44, borderRadius: radius.pill, backgroundColor: "#26783A" },
  addButtonText: { color: colors.onBrandPrimary, fontWeight: "800" },
  sectionTitle: { fontSize: 17, lineHeight: 22, fontWeight: "800", color: colors.onSurface, marginTop: spacing.sm },
  articleGrid: { gap: spacing.sm },
  articleGridWide: { flexDirection: "row" },
  articleCard: { overflow: "hidden", borderRadius: radius.md, borderWidth: 1, borderColor: "#DDE3DA", backgroundColor: colors.surface },
  articleCardWide: { flex: 1 },
  articleImage: { width: "100%", height: 146 },
  articleFooter: { minHeight: 64, flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, backgroundColor: "rgba(255,255,255,0.96)" },
  articleIcon: { width: 38, height: 38, borderRadius: 19, backgroundColor: "#EEF5EB", alignItems: "center", justifyContent: "center" },
  articleTitle: { flex: 1, fontSize: 16, lineHeight: 21, fontWeight: "800", color: colors.onSurface },
  journalPrompt: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: "#DDE3DA", backgroundColor: "#FBFCF9" },
  sectionIcon: { width: 46, height: 46, borderRadius: 23, backgroundColor: "#EEF5EB", alignItems: "center", justifyContent: "center" },
  journalPromptText: { flex: 1, fontSize: 16, fontWeight: "800", color: colors.onSurface },
  smallAddButton: { minHeight: 40, borderRadius: radius.pill, paddingHorizontal: spacing.md, flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: "#26783A" },
  smallAddText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 13 },
  entryCard: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  entryTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.xs },
  entryTag: { fontSize: 11, fontWeight: "800", color: colors.brandPrimary, backgroundColor: colors.brandTertiary, paddingHorizontal: spacing.sm, paddingVertical: 5, borderRadius: radius.pill },
  entryDate: { fontSize: 12, color: colors.onSurfaceTertiary },
  entryBody: { fontSize: 14, lineHeight: 21, color: colors.onSurfaceSecondary },
  historyEmpty: { flexDirection: "row", alignItems: "center", gap: spacing.sm, minHeight: 76, paddingHorizontal: spacing.md, borderWidth: 1, borderColor: "#DDE3DA", borderRadius: radius.md, backgroundColor: "#FBFCF9" },
  historyEmptyText: { flex: 1, fontSize: 15, fontWeight: "700", color: colors.onSurfaceSecondary },
  historyRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, backgroundColor: colors.surface },
  historyIcon: { width: 42, height: 42, borderRadius: 21, alignItems: "center", justifyContent: "center", backgroundColor: "#EEF5EB" },
  historyCopy: { flex: 1 },
  historyTitle: { fontSize: 15, fontWeight: "800", color: colors.onSurface },
  historyMeta: { fontSize: 12, lineHeight: 17, color: colors.onSurfaceTertiary, marginTop: 2 },
  demoHistoryRow: { borderColor: "#DCCFEA", backgroundColor: "#FBF8FE" },
  demoHistoryIcon: { backgroundColor: "#F0E9F7" },
  demoTitleRow: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.xs },
  demoBadge: { paddingHorizontal: 7, paddingVertical: 3, borderRadius: radius.pill, backgroundColor: "#EADFF4", color: "#675080", fontSize: 9, fontWeight: "900" },
  modalScrim: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(28,32,29,0.36)" },
  composer: { padding: spacing.lg, backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, gap: spacing.md },
  composerHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  composerTitle: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  input: { minHeight: 140, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, color: colors.onSurface, fontSize: 16, lineHeight: 23, textAlignVertical: "top" },
  saveButton: { minHeight: 52, alignItems: "center", justifyContent: "center", borderRadius: radius.md, backgroundColor: colors.brandPrimary },
  saveButtonText: { color: colors.onBrandPrimary, fontSize: 16, fontWeight: "800" },
});
