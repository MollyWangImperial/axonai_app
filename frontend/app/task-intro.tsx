import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { fetchTasks, Task } from "@/src/api";

export default function TaskIntro() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      const r = await fetchTasks();
      setTasks(r.tasks);
      setError(null);
    } catch (e: any) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const onBegin = () => {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    router.push("/assessment");
  };

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="task-intro-back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Movement Assessment</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }}>
        <Text style={styles.title}>7 guided movement tasks</Text>
        <Text style={styles.sub}>
          A warm voice will guide you through each task. Reach the on-screen target with your affected hand. Move into the camera view, sitting upright with good lighting.
        </Text>

        <View style={styles.tipsCard} testID="task-intro-tips">
          <Text style={styles.tipsHeader}>Before we begin</Text>
          {[
            "Wear short or fitted sleeves so your arms are visible",
            "Have someone nearby for safety if needed",
            "Stable seat, clear background, good lighting",
            "Keep your phone propped up at chest height, ~6 feet away",
          ].map((t, i) => (
            <View key={i} style={styles.tipRow}>
              <Ionicons name="checkmark-circle" size={18} color={colors.brandPrimary} />
              <Text style={styles.tipText}>{t}</Text>
            </View>
          ))}
        </View>

        {loading && <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.lg }} />}
        {error && <Text style={{ color: colors.error, marginTop: spacing.md }}>Could not load tasks. {error}</Text>}

        {tasks.map((t, i) => (
          <View key={t.id} style={styles.taskRow} testID={`task-row-${t.id}`}>
            <View style={styles.taskNum}><Text style={styles.taskNumText}>{i + 1}</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={styles.taskTitle}>{t.id} · {t.title}</Text>
              <Text style={styles.taskFocus}>{t.focus}</Text>
              <Text style={styles.taskView}>{t.view}</Text>
            </View>
          </View>
        ))}
      </ScrollView>

      <View style={[styles.cta, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable onPress={onBegin} style={styles.ctaBtn} testID="task-intro-begin">
          <Ionicons name="videocam" size={22} color={colors.onBrandPrimary} />
          <Text style={styles.ctaText}>Open Camera & Begin</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  title: { fontSize: 26, fontWeight: "800", color: colors.onSurface, marginBottom: spacing.sm },
  sub: { fontSize: 15, color: colors.onSurfaceSecondary, lineHeight: 22, marginBottom: spacing.lg },
  tipsCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.lg },
  tipsHeader: { fontSize: 16, fontWeight: "700", color: colors.onBrandTertiary, marginBottom: spacing.sm },
  tipRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 4 },
  tipText: { color: colors.onBrandTertiary, fontSize: 14, flex: 1 },
  taskRow: { flexDirection: "row", gap: spacing.md, padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, marginBottom: spacing.sm, alignItems: "center" },
  taskNum: { width: 44, height: 44, borderRadius: 12, backgroundColor: colors.brandSecondary, alignItems: "center", justifyContent: "center" },
  taskNumText: { color: "#fff", fontWeight: "800", fontSize: 18 },
  taskTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: 2 },
  taskFocus: { fontSize: 13, color: colors.onSurfaceTertiary, lineHeight: 18 },
  taskView: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", marginTop: 4 },
  cta: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  ctaBtn: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.md, alignItems: "center", justifyContent: "center", minHeight: 56 },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "700" },
});
