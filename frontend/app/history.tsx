import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { colors, spacing, radius } from "@/src/theme";
import { fetchHistory, Assessment } from "@/src/api";

export default function HistoryScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [items, setItems] = useState<Assessment[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try { setItems(await fetchHistory()); } catch { setItems([]); }
      finally { setLoading(false); }
    })();
  }, []);

  return (
    <View style={styles.container}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} testID="history-back">
          <Ionicons name="chevron-back" size={24} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Progress History</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}>
        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : items.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="bar-chart" size={48} color={colors.borderStrong} />
            <Text style={styles.emptyTitle}>No assessments yet</Text>
            <Text style={styles.emptySub}>Complete an assessment to start tracking your recovery journey.</Text>
            <Pressable onPress={() => router.push("/task-intro")} style={styles.emptyBtn} testID="history-start">
              <Text style={styles.emptyBtnText}>Start an assessment</Text>
            </Pressable>
          </View>
        ) : (
          items.map((a) => {
            const date = new Date(a.created_at);
            return (
              <Pressable
                key={a.id}
                onPress={() => router.push({ pathname: "/results", params: { id: a.id } })}
                style={styles.row}
                testID={`history-${a.id}`}
              >
                <View style={styles.rowIcon}>
                  <Ionicons name="document-text" size={22} color={colors.brandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>{date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" })}</Text>
                  <Text style={styles.rowSub}>
                    {a.functional_issues.length} issues · {a.rehab_plan.length} exercises · {date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={colors.borderStrong} />
              </Pressable>
            );
          })
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 17, fontWeight: "700", color: colors.onSurface },
  empty: { alignItems: "center", paddingVertical: spacing.xxl, gap: spacing.sm },
  emptyTitle: { fontSize: 18, fontWeight: "700", color: colors.onSurface },
  emptySub: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center", paddingHorizontal: spacing.md },
  emptyBtn: { backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.lg, marginTop: spacing.md },
  emptyBtnText: { color: colors.onBrandPrimary, fontWeight: "700" },
  row: { flexDirection: "row", alignItems: "center", padding: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, marginBottom: spacing.sm, gap: spacing.md },
  rowIcon: { width: 44, height: 44, borderRadius: 12, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  rowSub: { fontSize: 13, color: colors.onSurfaceSecondary, marginTop: 2 },
});
