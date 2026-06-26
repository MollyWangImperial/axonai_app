import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { fetchAssessment, Assessment } from "@/src/api";

export default function RehabPlanScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(true);
  const [done, setDone] = useState<Record<string, boolean>>({});

  useEffect(() => {
    (async () => {
      try {
        if (id) setData(await fetchAssessment(id));
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const toggle = (exId: string) => {
    Haptics.selectionAsync();
    setDone((d) => ({ ...d, [exId]: !d[exId] }));
  };

  const completedCount = Object.values(done).filter(Boolean).length;

  if (loading) {
    return (
      <View style={[styles.container, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }
  if (!data) {
    return (
      <View style={[styles.container, styles.center]}>
        <Text>No plan available.</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="plan-back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Rehab Plan</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 140 }}>
        <View style={styles.hero}>
          <Text style={styles.heroTitle}>Today's Plan</Text>
          <Text style={styles.heroSub}>
            {data.rehab_plan.length} exercises tailored to your focus areas. Evidence-based protocols.
          </Text>
          <View style={styles.progress}>
            <View style={[styles.progressFill, { width: `${(completedCount / Math.max(1, data.rehab_plan.length)) * 100}%` }]} />
          </View>
          <Text style={styles.progressText}>{completedCount} of {data.rehab_plan.length} complete</Text>
        </View>

        {data.rehab_plan.map((ex, i) => {
          const isDone = !!done[ex.id];
          return (
            <View
              key={ex.id}
              style={[styles.exCard, isDone && styles.exCardDone]}
              testID={`exercise-${ex.id}`}
            >
              <View style={styles.exHead}>
                <View style={[styles.exNum, isDone && { backgroundColor: colors.success }]}>
                  {isDone ? (
                    <Ionicons name="checkmark" size={20} color="#fff" />
                  ) : (
                    <Text style={styles.exNumText}>{i + 1}</Text>
                  )}
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.exTitle}>{ex.name}</Text>
                  <Text style={styles.exMeta}>{ex.sets} sets × {ex.reps} reps · {ex.frequency}</Text>
                </View>
              </View>
              <Text style={styles.exDesc}>{ex.description}</Text>
              <Text style={styles.exSource}>📖 {ex.source}</Text>
              <View style={styles.exActions}>
                <Pressable
                  onPress={() => {
                    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
                    router.push({ pathname: "/exercise", params: { exercise_id: ex.id, name: ex.name } });
                  }}
                  style={styles.guidedBtn}
                  testID={`exercise-guided-${ex.id}`}
                >
                  <Ionicons name="videocam" size={18} color="#fff" />
                  <Text style={styles.guidedBtnText}>Guided practice</Text>
                </Pressable>
                <Pressable
                  onPress={() => toggle(ex.id)}
                  style={styles.markBtn}
                  testID={`exercise-mark-${ex.id}`}
                >
                  <Ionicons name={isDone ? "checkmark-circle" : "ellipse-outline"} size={18} color={isDone ? colors.success : colors.onSurfaceSecondary} />
                  <Text style={[styles.markBtnText, isDone && { color: colors.success }]}>{isDone ? "Done" : "Mark done"}</Text>
                </Pressable>
              </View>
            </View>
          );
        })}

        <Text style={styles.disclaimer}>
          This plan is an educational guide derived from established rehabilitation sources. Always consult your therapist or clinician before starting a new exercise program.
        </Text>
      </ScrollView>

      <View style={[styles.ctaBar, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <Pressable
          onPress={() => router.replace("/")}
          style={styles.cta}
          testID="plan-done"
        >
          <Ionicons name="checkmark-circle" size={22} color={colors.onBrandPrimary} />
          <Text style={styles.ctaText}>Finish Session</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  hero: { backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, marginBottom: spacing.lg, gap: spacing.sm },
  heroTitle: { fontSize: 22, fontWeight: "800", color: colors.onBrandTertiary },
  heroSub: { color: colors.onBrandTertiary, fontSize: 14, lineHeight: 20 },
  progress: { height: 8, backgroundColor: "rgba(28,32,29,0.15)", borderRadius: 4, marginTop: spacing.sm, overflow: "hidden" },
  progressFill: { height: "100%", backgroundColor: colors.brandPrimary },
  progressText: { color: colors.onBrandTertiary, fontSize: 13, fontWeight: "600" },
  exCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, marginBottom: spacing.sm, gap: spacing.sm, borderWidth: 2, borderColor: "transparent" },
  exCardDone: { borderColor: colors.success, backgroundColor: "#EAF3EE" },
  exHead: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  exNum: { width: 36, height: 36, borderRadius: 10, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  exNumText: { color: "#fff", fontSize: 16, fontWeight: "800" },
  exTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface, marginBottom: 2 },
  exMeta: { fontSize: 13, color: colors.brandPrimary, fontWeight: "600" },
  exDesc: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20 },
  exSource: { fontSize: 12, color: colors.onSurfaceTertiary, fontStyle: "italic" },
  exActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  guidedBtn: { flex: 1, flexDirection: "row", gap: 6, backgroundColor: colors.brandPrimary, paddingVertical: 12, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  guidedBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  markBtn: { flexDirection: "row", gap: 6, backgroundColor: colors.surfaceTertiary, paddingVertical: 12, paddingHorizontal: spacing.md, borderRadius: radius.md, alignItems: "center", justifyContent: "center" },
  markBtnText: { color: colors.onSurfaceSecondary, fontWeight: "700", fontSize: 14 },
  disclaimer: { fontSize: 12, color: colors.onSurfaceTertiary, fontStyle: "italic", marginTop: spacing.lg, lineHeight: 18 },
  ctaBar: { position: "absolute", left: 0, right: 0, bottom: 0, padding: spacing.md, backgroundColor: colors.surface, borderTopWidth: 1, borderTopColor: colors.divider },
  cta: { flexDirection: "row", gap: spacing.sm, backgroundColor: colors.brandPrimary, borderRadius: radius.lg, padding: spacing.md, alignItems: "center", justifyContent: "center", minHeight: 56 },
  ctaText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "700" },
});
