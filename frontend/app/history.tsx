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

      <ScrollView contentContainerStyle={styles.scrollContent} showsVerticalScrollIndicator={false}>
        {loading ? (
          <ActivityIndicator color={colors.brandPrimary} />
        ) : items.length === 0 ? (
          <View style={styles.empty}>
            <Ionicons name="bar-chart" size={48} color={colors.borderStrong} />
            <Text style={styles.emptyTitle}>No assessments yet</Text>
            <Text style={styles.emptySub}>Complete an assessment to start tracking your recovery journey.</Text>
            <Pressable onPress={() => router.push({ pathname: "/session-check" as any, params: { target: "assessment", mode: "initial" } })} style={styles.emptyBtn} testID="history-start">
              <Text style={styles.emptyBtnText}>Start Initial Assessment</Text>
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
  scrollContent: { padding: spacing.lg, paddingBottom: spacing.xxl, flexGrow: 1 },
  header: { minHeight: 72, flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md, paddingBottom: spacing.sm, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border },
  backBtn: { width: 48, height: 48, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 22, lineHeight: 28, fontWeight: "800", color: colors.onSurface },
  empty: { alignItems: "center", paddingVertical: spacing.xxl, gap: spacing.md },
  emptyTitle: { fontSize: 24, lineHeight: 31, fontWeight: "800", color: colors.onSurface, textAlign: "center" },
  emptySub: { maxWidth: 420, fontSize: 16, lineHeight: 24, color: colors.onSurfaceSecondary, textAlign: "center", paddingHorizontal: spacing.md },
  emptyBtn: { minHeight: 52, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.md, marginTop: spacing.md, justifyContent: "center" },
  emptyBtnText: { color: colors.onBrandPrimary, fontSize: 16, fontWeight: "700" },
  row: { minHeight: 88, flexDirection: "row", alignItems: "center", padding: spacing.md, backgroundColor: "#FFFEFA", borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, marginBottom: spacing.md, gap: spacing.md, shadowColor: "#24362F", shadowOpacity: 0.04, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 1 },
  rowIcon: { width: 52, height: 52, borderRadius: 26, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  rowTitle: { fontSize: 18, lineHeight: 24, fontWeight: "800", color: colors.onSurface },
  rowSub: { fontSize: 16, lineHeight: 22, color: colors.onSurfaceSecondary, marginTop: 3 },
});
