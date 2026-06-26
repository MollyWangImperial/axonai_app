import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, Dimensions } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter, useFocusEffect } from "expo-router";
import Svg, { Line, Circle, Polyline, Text as SvgText } from "react-native-svg";
import React from "react";
import { colors, spacing, radius } from "@/src/theme";
import { authedFetch } from "@/src/auth";

type AssessmentPoint = {
  id: string;
  date: string;
  shoulder_flexion_deg: number | null;
  trunk_lean_deg: number | null;
  reach_completion: number | null;
  bilateral_symmetry: number | null;
  pinch_grip: number | null;
  hand_opening: number | null;
  issues_count: number;
  exercises_count: number;
};

type Summary = {
  assessments: AssessmentPoint[];
  issues_history: { issue: string; count: number }[];
  first_seen: string | null;
  count?: number;
};

const METRICS: { key: keyof AssessmentPoint; label: string; unit: string; higherIsBetter: boolean }[] = [
  { key: "shoulder_flexion_deg", label: "Shoulder flexion", unit: "°", higherIsBetter: true },
  { key: "reach_completion", label: "Reach completion", unit: "%", higherIsBetter: true },
  { key: "bilateral_symmetry", label: "Bilateral symmetry", unit: "", higherIsBetter: true },
  { key: "trunk_lean_deg", label: "Trunk lean (compensation)", unit: "°", higherIsBetter: false },
];

function dateLabel(iso: string) {
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch { return ""; }
}

function MetricChart({ data, mKey, label, unit, higherIsBetter }: { data: AssessmentPoint[]; mKey: keyof AssessmentPoint; label: string; unit: string; higherIsBetter: boolean }) {
  const W = Dimensions.get("window").width - spacing.lg * 2;
  const H = 110;
  const PAD = { l: 36, r: 12, t: 14, b: 22 };
  const pts = data.map((d) => ({ x: d.date, y: typeof d[mKey] === "number" ? (d[mKey] as number) : null }));
  const validPts = pts.filter((p) => p.y != null) as { x: string; y: number }[];
  if (validPts.length === 0) {
    return (
      <View style={styles.chartCard}>
        <Text style={styles.chartLabel}>{label}</Text>
        <Text style={styles.chartEmpty}>No data yet</Text>
      </View>
    );
  }
  const ys = validPts.map((p) => p.y);
  const yMin = Math.min(...ys, 0);
  const yMax = Math.max(...ys, yMin + 1);
  const yRange = yMax - yMin || 1;
  const sx = (i: number) => PAD.l + ((W - PAD.l - PAD.r) * i) / Math.max(1, validPts.length - 1);
  const sy = (y: number) => PAD.t + (H - PAD.t - PAD.b) * (1 - (y - yMin) / yRange);
  const polyPoints = validPts.map((p, i) => `${sx(i)},${sy(p.y)}`).join(" ");
  const last = validPts[validPts.length - 1].y;
  const first = validPts[0].y;
  const delta = last - first;
  const improving = higherIsBetter ? delta > 0.5 : delta < -0.5;
  const declining = higherIsBetter ? delta < -0.5 : delta > 0.5;
  return (
    <View style={styles.chartCard}>
      <View style={styles.chartHead}>
        <Text style={styles.chartLabel}>{label}</Text>
        <View style={styles.chartLatest}>
          <Text style={styles.chartLatestNum}>{Number(last).toFixed(unit === "%" ? 0 : 1)}{unit}</Text>
          {validPts.length > 1 && (
            <View style={[styles.deltaPill, improving ? styles.deltaUp : declining ? styles.deltaDown : styles.deltaFlat]}>
              <Ionicons name={improving ? "arrow-up" : declining ? "arrow-down" : "remove"} size={11} color="#fff" />
              <Text style={styles.deltaText}>{Math.abs(delta).toFixed(1)}{unit}</Text>
            </View>
          )}
        </View>
      </View>
      <Svg width={W} height={H}>
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <Line key={t} x1={PAD.l} y1={PAD.t + (H - PAD.t - PAD.b) * t} x2={W - PAD.r} y2={PAD.t + (H - PAD.t - PAD.b) * t} stroke={colors.divider} strokeWidth={1} />
        ))}
        <Polyline points={polyPoints} fill="none" stroke={colors.brandPrimary} strokeWidth={2.5} />
        {validPts.map((p, i) => (
          <Circle key={i} cx={sx(i)} cy={sy(p.y)} r={3.5} fill={colors.brandPrimary} />
        ))}
        <SvgText x={PAD.l - 4} y={PAD.t + 4} fontSize={9} fill={colors.onSurfaceTertiary} textAnchor="end">{yMax.toFixed(unit === "%" ? 0 : 0)}</SvgText>
        <SvgText x={PAD.l - 4} y={H - PAD.b + 2} fontSize={9} fill={colors.onSurfaceTertiary} textAnchor="end">{yMin.toFixed(unit === "%" ? 0 : 0)}</SvgText>
        {validPts.length > 0 && (
          <SvgText x={sx(0)} y={H - 6} fontSize={9} fill={colors.onSurfaceTertiary} textAnchor="start">{dateLabel(validPts[0].x)}</SvgText>
        )}
        {validPts.length > 1 && (
          <SvgText x={sx(validPts.length - 1)} y={H - 6} fontSize={9} fill={colors.onSurfaceTertiary} textAnchor="end">{dateLabel(validPts[validPts.length - 1].x)}</SvgText>
        )}
      </Svg>
    </View>
  );
}

export default function ProgressScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const r = await authedFetch("/api/progress/summary");
      const d = await r.json();
      setData(d);
    } catch {
      setData({ assessments: [], issues_history: [], first_seen: null });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);
  useFocusEffect(React.useCallback(() => { load(); }, []));

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.topBar}>
        <Pressable onPress={() => router.back()} hitSlop={12} testID="progress-back">
          <Ionicons name="chevron-back" size={26} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Your Progress</Text>
        <View style={{ width: 26 }} />
      </View>

      {loading ? (
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      ) : !data || data.assessments.length === 0 ? (
        <View style={styles.emptyWrap} testID="progress-empty">
          <View style={styles.emptyIcon}><Ionicons name="bar-chart-outline" size={42} color={colors.brandPrimary} /></View>
          <Text style={styles.emptyTitle}>No assessment data yet</Text>
          <Text style={styles.emptyBody}>Take your first assessment and your functional metrics will appear here. Every 7 days, you'll see how your shoulder flexion, reach, and symmetry are changing.</Text>
          <Pressable onPress={() => router.replace("/")} style={styles.emptyCta} testID="progress-empty-cta">
            <Text style={styles.emptyCtaText}>Take your first assessment</Text>
          </Pressable>
        </View>
      ) : (
        <ScrollView contentContainerStyle={styles.scroll}>
          <View style={styles.summaryRow}>
            <View style={styles.summaryCard} testID="progress-count">
              <Text style={styles.summaryNum}>{data.assessments.length}</Text>
              <Text style={styles.summaryLab}>Assessments</Text>
            </View>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryNum}>{data.assessments.reduce((acc, a) => acc + (a.exercises_count || 0), 0)}</Text>
              <Text style={styles.summaryLab}>Exercises planned</Text>
            </View>
            <View style={styles.summaryCard}>
              <Text style={styles.summaryNum}>{data.first_seen ? Math.max(1, Math.floor((Date.now() - new Date(data.first_seen).getTime()) / 86400000)) : 0}</Text>
              <Text style={styles.summaryLab}>Days on plan</Text>
            </View>
          </View>

          <Text style={styles.sectionTitle}>Functional metrics over time</Text>
          {METRICS.map((m) => (
            <MetricChart key={String(m.key)} data={data.assessments} mKey={m.key} label={m.label} unit={m.unit} higherIsBetter={m.higherIsBetter} />
          ))}

          {data.issues_history.length > 0 && (
            <>
              <Text style={styles.sectionTitle}>Issues identified across assessments</Text>
              <View style={styles.issuesCard}>
                {data.issues_history.slice(0, 6).map((it) => (
                  <View key={it.issue} style={styles.issueRow}>
                    <Text style={styles.issueText} numberOfLines={2}>{it.issue}</Text>
                    <View style={styles.issueCount}><Text style={styles.issueCountText}>×{it.count}</Text></View>
                  </View>
                ))}
              </View>
            </>
          )}

          <Text style={styles.disclaimer}>Your metrics update every time you complete a new assessment. Aim for at least one assessment per week to track recovery.</Text>
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  topBar: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  title: { fontSize: 18, fontWeight: "800", color: colors.onSurface },
  scroll: { padding: spacing.lg, paddingBottom: 48, gap: spacing.md },
  summaryRow: { flexDirection: "row", gap: spacing.sm },
  summaryCard: { flex: 1, backgroundColor: colors.brandTertiary, borderRadius: radius.lg, padding: spacing.md, alignItems: "center" },
  summaryNum: { fontSize: 28, fontWeight: "800", color: colors.onBrandTertiary },
  summaryLab: { fontSize: 11, color: colors.onBrandTertiary, fontWeight: "600", textAlign: "center", marginTop: 2 },
  sectionTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface, marginTop: spacing.md },
  chartCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, gap: 6 },
  chartHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  chartLabel: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  chartLatest: { flexDirection: "row", alignItems: "center", gap: 6 },
  chartLatestNum: { fontSize: 18, fontWeight: "800", color: colors.brandPrimary },
  chartEmpty: { fontSize: 12, color: colors.onSurfaceTertiary, fontStyle: "italic" },
  deltaPill: { flexDirection: "row", alignItems: "center", gap: 3, paddingHorizontal: 6, paddingVertical: 2, borderRadius: 999 },
  deltaUp: { backgroundColor: colors.success },
  deltaDown: { backgroundColor: colors.brandSecondary },
  deltaFlat: { backgroundColor: colors.onSurfaceTertiary },
  deltaText: { color: "#fff", fontSize: 10, fontWeight: "800" },
  issuesCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.md, gap: spacing.sm },
  issueRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: spacing.sm },
  issueText: { flex: 1, fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  issueCount: { backgroundColor: colors.brandTertiary, borderRadius: 999, paddingHorizontal: 8, paddingVertical: 2 },
  issueCountText: { color: colors.onBrandTertiary, fontWeight: "800", fontSize: 12 },
  disclaimer: { fontSize: 12, color: colors.onSurfaceTertiary, fontStyle: "italic", textAlign: "center", marginTop: spacing.md },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyWrap: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, gap: spacing.md },
  emptyIcon: { width: 88, height: 88, borderRadius: 44, backgroundColor: colors.brandTertiary, alignItems: "center", justifyContent: "center" },
  emptyTitle: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  emptyBody: { fontSize: 14, color: colors.onSurfaceSecondary, textAlign: "center", lineHeight: 22, maxWidth: 320 },
  emptyCta: { backgroundColor: colors.brandPrimary, borderRadius: radius.lg, paddingHorizontal: spacing.lg, paddingVertical: 14, marginTop: spacing.sm },
  emptyCtaText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 15 },
});
