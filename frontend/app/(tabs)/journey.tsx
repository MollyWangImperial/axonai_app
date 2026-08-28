import { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Image, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, useWindowDimensions, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Assessment, fetchHistory } from "@/src/api";
import { addJournalEntry, JournalEntry, loadJournalEntries } from "@/src/journal";
import { colors, radius, spacing } from "@/src/theme";

const brainImage = require("@/assets/images/journey-stroke-brain.png");
const familyImage = require("@/assets/images/journey-family-support.png");

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
  const { width } = useWindowDimensions();
  const wide = width >= 760;
  const [history, setHistory] = useState<Assessment[]>([]);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [showComposer, setShowComposer] = useState(false);
  const [draft, setDraft] = useState("");
  const initialAssessmentId = [...history].reverse().find((item) => item.assessment_package === "initial")?.id ?? history[history.length - 1]?.id;
  const progressWidth = useMemo(() => `${Math.min(100, (history.length + entries.length) * 20)}%` as `${number}%`, [entries.length, history.length]);

  const load = useCallback(async () => {
    setLoading(true);
    const [assessments, journal] = await Promise.all([fetchHistory().catch(() => []), loadJournalEntries()]);
    setHistory(assessments);
    setEntries(journal);
    setLoading(false);
  }, []);

  useFocusEffect(useCallback(() => { void load(); }, [load]));

  const saveEntry = async () => {
    if (!draft.trim()) return;
    setEntries(await addJournalEntry(draft));
    setDraft("");
    setShowComposer(false);
  };

  const askAlira = (prompt: string) => router.push({ pathname: "/chat", params: { prompt } });

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={[styles.content, { paddingTop: insets.top + spacing.md }]} showsVerticalScrollIndicator={false}>
        <View style={styles.page}>
          <View style={styles.headerRow}>
            <Text style={styles.title}>Journey</Text>
            <Pressable testID="journey-add-entry" onPress={() => setShowComposer(true)} style={styles.addButton}>
              <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
              <Text style={styles.addButtonText}>Add entry</Text>
            </Pressable>
          </View>

          <Pressable onPress={() => router.push("/progress")} style={styles.summaryCard}>
            <View style={styles.summaryIcon}><Ionicons name="trending-up" size={27} color={colors.brandPrimary} /></View>
            <View style={styles.summaryCopy}>
              <Text style={styles.summaryTitle}>Your progress at a glance</Text>
              <View style={styles.progressTrack}><View style={[styles.progressFill, { width: progressWidth }]} /></View>
              <Text style={styles.summaryBody}>{history.length} assessment{history.length === 1 ? "" : "s"} completed · {entries.length} journal entr{entries.length === 1 ? "y" : "ies"}</Text>
            </View>
            <Ionicons name="chevron-forward" size={22} color={colors.brandPrimary} />
          </Pressable>

          <Text style={styles.sectionTitle}>Learn about stroke recovery</Text>
          <View style={[styles.articleGrid, wide && styles.articleGridWide]}>
            <Pressable onPress={() => askAlira("Can you explain what happens after a stroke in simple language?")} style={[styles.articleCard, wide && styles.articleCardWide]}>
              <Image source={brainImage} resizeMode="cover" style={styles.articleImage} />
              <View style={styles.articleFooter}>
                <View style={styles.articleIcon}><Ionicons name="book-outline" size={23} color={colors.brandPrimary} /></View>
                <Text style={styles.articleTitle}>What happens after a stroke?</Text>
                <Ionicons name="chevron-forward" size={19} color={colors.onSurfaceTertiary} />
              </View>
            </Pressable>
            <Pressable onPress={() => askAlira("How can family members support stroke recovery day to day?")} style={[styles.articleCard, wide && styles.articleCardWide]}>
              <Image source={familyImage} resizeMode="cover" style={styles.articleImage} />
              <View style={styles.articleFooter}>
                <View style={styles.articleIcon}><Ionicons name="heart" size={22} color={colors.brandPrimary} /></View>
                <Text style={styles.articleTitle}>How family support helps</Text>
                <Ionicons name="chevron-forward" size={19} color={colors.onSurfaceTertiary} />
              </View>
            </Pressable>
          </View>

          <Text style={styles.sectionTitle}>Journal & milestones</Text>
          {entries.length === 0 ? (
            <Pressable onPress={() => setShowComposer(true)} style={styles.journalPrompt}>
              <View style={styles.sectionIcon}><Ionicons name="book-outline" size={24} color={colors.brandPrimary} /></View>
              <Text style={styles.journalPromptText}>Capture a small win</Text>
              <View style={styles.smallAddButton}><Ionicons name="add" size={19} color={colors.onBrandPrimary} /><Text style={styles.smallAddText}>Add entry</Text></View>
            </Pressable>
          ) : entries.map((entry) => (
            <View key={entry.id} style={styles.entryCard}>
              <View style={styles.entryTop}>
                <Text style={styles.entryTag}>{entry.tag}</Text>
                <Text style={styles.entryDate}>{new Date(entry.createdAt).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</Text>
              </View>
              <Text style={styles.entryBody}>{entry.body}</Text>
            </View>
          ))}

          <Text style={styles.sectionTitle} testID="assessment-history">Assessment history</Text>
          {loading ? <ActivityIndicator color={colors.brandPrimary} /> : history.length === 0 ? (
            <View style={styles.historyEmpty}>
              <View style={styles.sectionIcon}><Ionicons name="clipboard-outline" size={24} color={colors.brandPrimary} /></View>
              <Text style={styles.historyEmptyText}>Your assessments will appear here</Text>
              <Ionicons name="sparkles" size={18} color="#78A87E" />
            </View>
          ) : history.slice(0, 6).map((item) => (
            <Pressable key={item.id} testID={`assessment-history-${item.id}`} onPress={() => router.push({ pathname: "/results", params: { id: item.id } })} style={styles.historyRow}>
              <View style={styles.historyIcon}><Ionicons name="analytics-outline" size={21} color={colors.brandPrimary} /></View>
              <View style={styles.historyCopy}>
                <Text style={styles.historyTitle}>{item.id === initialAssessmentId ? "Initial Assessment" : "Movement check-in"}</Text>
                <Text style={styles.historyMeta}>{new Date(item.created_at).toLocaleDateString()} · {assessmentPlanLabel(item)}</Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.borderStrong} />
            </Pressable>
          ))}
        </View>
      </ScrollView>

      <Modal visible={showComposer} transparent animationType="slide" onRequestClose={() => setShowComposer(false)}>
        <View style={styles.modalScrim}>
          <View style={[styles.composer, { paddingBottom: Math.max(insets.bottom, spacing.lg) }]}>
            <View style={styles.composerHeader}>
              <Text style={styles.composerTitle}>New journal entry</Text>
              <Pressable onPress={() => setShowComposer(false)}><Ionicons name="close" size={26} color={colors.onSurface} /></Pressable>
            </View>
            <TextInput testID="journey-entry-input" value={draft} onChangeText={setDraft} multiline autoFocus placeholder="What felt different today?" placeholderTextColor={colors.onSurfaceTertiary} style={styles.input} />
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
  title: { fontSize: 34, lineHeight: 40, fontWeight: "900", color: "#113126" },
  addButton: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: spacing.md, minHeight: 44, borderRadius: radius.pill, backgroundColor: "#26783A" },
  addButtonText: { color: colors.onBrandPrimary, fontWeight: "800" },
  summaryCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: "#FBFCF9", borderWidth: 1, borderColor: "#DCE3DA" },
  summaryIcon: { width: 58, height: 58, borderRadius: 29, backgroundColor: "#EFF6EC", alignItems: "center", justifyContent: "center" },
  summaryCopy: { flex: 1 },
  summaryTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  progressTrack: { height: 9, borderRadius: 5, backgroundColor: "#E6ECE4", overflow: "hidden", marginTop: spacing.sm },
  progressFill: { height: "100%", borderRadius: 5, backgroundColor: colors.brandPrimary },
  summaryBody: { fontSize: 12, lineHeight: 17, color: colors.onSurfaceTertiary, marginTop: 7 },
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
  modalScrim: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(28,32,29,0.36)" },
  composer: { padding: spacing.lg, backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, gap: spacing.md },
  composerHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  composerTitle: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  input: { minHeight: 140, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, color: colors.onSurface, fontSize: 16, lineHeight: 23, textAlignVertical: "top" },
  saveButton: { minHeight: 52, alignItems: "center", justifyContent: "center", borderRadius: radius.md, backgroundColor: colors.brandPrimary },
  saveButtonText: { color: colors.onBrandPrimary, fontSize: 16, fontWeight: "800" },
});
