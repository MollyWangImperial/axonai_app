import { useCallback, useState } from "react";
import { ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { Assessment, fetchHistory } from "@/src/api";
import { addJournalEntry, JournalEntry, loadJournalEntries } from "@/src/journal";
import { colors, radius, spacing } from "@/src/theme";

export default function JourneyScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [history, setHistory] = useState<Assessment[]>([]);
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [showComposer, setShowComposer] = useState(false);
  const [draft, setDraft] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    const [assessments, journal] = await Promise.all([
      fetchHistory().catch(() => []),
      loadJournalEntries(),
    ]);
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

  return (
    <View style={styles.container}>
      <ScrollView contentContainerStyle={[styles.content, { paddingTop: insets.top + spacing.lg }]} showsVerticalScrollIndicator={false}>
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.eyebrow}>YOUR RECOVERY</Text>
            <Text style={styles.title}>Journey</Text>
          </View>
          <Pressable testID="journey-add-entry" onPress={() => setShowComposer(true)} style={styles.addButton}>
            <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
            <Text style={styles.addButtonText}>Add entry</Text>
          </Pressable>
        </View>

        <View style={styles.summaryCard}>
          <View style={styles.summaryIcon}><Ionicons name="trending-up" size={24} color={colors.brandPrimary} /></View>
          <View style={{ flex: 1 }}>
            <Text style={styles.summaryTitle}>Your progress in one place</Text>
            <Text style={styles.summaryBody}>{history.length} completed assessment{history.length === 1 ? "" : "s"} and {entries.length} journal entr{entries.length === 1 ? "y" : "ies"}.</Text>
          </View>
          <Pressable onPress={() => router.push("/progress")} hitSlop={10}>
            <Ionicons name="chevron-forward" size={22} color={colors.brandPrimary} />
          </Pressable>
        </View>

        <Text style={styles.sectionTitle}>Journal & milestones</Text>
        {entries.length === 0 ? (
          <Pressable onPress={() => setShowComposer(true)} style={styles.emptyCard}>
            <Ionicons name="book-outline" size={30} color={colors.brandPrimary} />
            <Text style={styles.emptyTitle}>Capture a small win</Text>
            <Text style={styles.emptyBody}>Write down what felt easier, harder, or meaningful today. Alira can use these notes to support future check-ins.</Text>
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

        <Text style={styles.sectionTitle}>Assessment history</Text>
        {loading ? <ActivityIndicator color={colors.brandPrimary} /> : history.length === 0 ? (
          <Text style={styles.muted}>Your Initial Assessment will appear here when it is complete.</Text>
        ) : history.slice(0, 6).map((item, index) => (
          <Pressable key={item.id} onPress={() => router.push({ pathname: "/results", params: { id: item.id } })} style={styles.historyRow}>
            <View style={styles.historyIcon}><Ionicons name="checkmark" size={19} color={colors.onBrandPrimary} /></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.historyTitle}>{index === history.length - 1 ? "Initial Assessment" : "Movement check-in"}</Text>
              <Text style={styles.historyMeta}>{new Date(item.created_at).toLocaleDateString()} · {item.rehab_plan.length} recommended exercises</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.borderStrong} />
          </Pressable>
        ))}
      </ScrollView>

      <Modal visible={showComposer} transparent animationType="slide" onRequestClose={() => setShowComposer(false)}>
        <View style={styles.modalScrim}>
          <View style={[styles.composer, { paddingBottom: Math.max(insets.bottom, spacing.lg) }]}>
            <View style={styles.composerHeader}>
              <Text style={styles.composerTitle}>New journal entry</Text>
              <Pressable onPress={() => setShowComposer(false)}><Ionicons name="close" size={26} color={colors.onSurface} /></Pressable>
            </View>
            <TextInput
              testID="journey-entry-input"
              value={draft}
              onChangeText={setDraft}
              multiline
              autoFocus
              placeholder="What felt different today?"
              placeholderTextColor={colors.onSurfaceTertiary}
              style={styles.input}
            />
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
  container: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: spacing.lg, paddingBottom: 120, gap: spacing.md },
  headerRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  eyebrow: { fontSize: 11, fontWeight: "800", color: colors.brandPrimary },
  title: { fontSize: 30, lineHeight: 36, fontWeight: "800", color: colors.onSurface },
  addButton: { flexDirection: "row", alignItems: "center", gap: 5, paddingHorizontal: spacing.md, minHeight: 44, borderRadius: radius.md, backgroundColor: colors.brandPrimary },
  addButtonText: { color: colors.onBrandPrimary, fontWeight: "800" },
  summaryCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.brandTertiary },
  summaryIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surface, alignItems: "center", justifyContent: "center" },
  summaryTitle: { fontSize: 16, fontWeight: "800", color: colors.onBrandTertiary },
  summaryBody: { fontSize: 13, lineHeight: 18, color: colors.onBrandTertiary, marginTop: 2 },
  sectionTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface, marginTop: spacing.md },
  emptyCard: { alignItems: "center", gap: spacing.xs, padding: spacing.lg, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary },
  emptyTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  emptyBody: { fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary, textAlign: "center" },
  entryCard: { padding: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  entryTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.xs },
  entryTag: { fontSize: 11, fontWeight: "800", color: colors.brandPrimary, backgroundColor: colors.brandTertiary, paddingHorizontal: spacing.sm, paddingVertical: 5, borderRadius: radius.pill },
  entryDate: { fontSize: 12, color: colors.onSurfaceTertiary },
  entryBody: { fontSize: 14, lineHeight: 21, color: colors.onSurfaceSecondary },
  muted: { fontSize: 14, lineHeight: 20, color: colors.onSurfaceTertiary },
  historyRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  historyIcon: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  historyTitle: { fontSize: 15, fontWeight: "800", color: colors.onSurface },
  historyMeta: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 2 },
  modalScrim: { flex: 1, justifyContent: "flex-end", backgroundColor: "rgba(28,32,29,0.36)" },
  composer: { padding: spacing.lg, backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, gap: spacing.md },
  composerHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  composerTitle: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  input: { minHeight: 140, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, color: colors.onSurface, fontSize: 16, lineHeight: 23, textAlignVertical: "top" },
  saveButton: { minHeight: 52, alignItems: "center", justifyContent: "center", borderRadius: radius.md, backgroundColor: colors.brandPrimary },
  saveButtonText: { color: colors.onBrandPrimary, fontSize: 16, fontWeight: "800" },
});
