import { useCallback, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import Svg, { Circle, Path } from "react-native-svg";

import { authedFetch } from "@/src/auth";
import { DisplayPalette, useDisplayPreferences } from "@/src/displayPreferences";
import { radius, spacing } from "@/src/theme";

type AssessmentPoint = {
  date: string;
  shoulder_flexion_deg: number | null;
  reach_completion: number | null;
  bilateral_symmetry: number | null;
  pinch_grip: number | null;
  hand_opening: number | null;
};

type TrendPoint = { date: string; value: number };
type Trend = {
  id: "reaching" | "hand" | "walking";
  title: string;
  points: TrendPoint[];
  insight: string;
};

const DEMO_TRENDS: Trend[] = [
  {
    id: "reaching",
    title: "Reaching",
    points: [
      { date: "2026-06-12", value: 34 },
      { date: "2026-06-28", value: 51 },
      { date: "2026-07-16", value: 66 },
      { date: "2026-08-03", value: 68 },
      { date: "2026-08-28", value: 82 },
    ],
    insight: "Reaching is becoming easier.",
  },
  {
    id: "hand",
    title: "Hand control",
    points: [
      { date: "2026-06-12", value: 35 },
      { date: "2026-06-28", value: 60 },
      { date: "2026-07-16", value: 74 },
      { date: "2026-08-03", value: 65 },
      { date: "2026-08-28", value: 81 },
    ],
    insight: "Your hand movements look steadier.",
  },
  {
    id: "walking",
    title: "Walking",
    points: [
      { date: "2026-06-12", value: 47 },
      { date: "2026-06-28", value: 55 },
      { date: "2026-07-16", value: 39 },
      { date: "2026-08-03", value: 59 },
      { date: "2026-08-28", value: 79 },
    ],
    insight: "Your walking looks steadier.",
  },
];

const COPY: Record<Trend["id"], { up: string; flat: string; down: string; first: string }> = {
  reaching: {
    up: "Reaching is becoming easier.",
    flat: "Your reaching is holding steady.",
    down: "Reaching is ready for a closer review.",
    first: "Your first reaching baseline is ready.",
  },
  hand: {
    up: "Your hand movements look steadier.",
    flat: "Your hand control is holding steady.",
    down: "Hand control is ready for a closer review.",
    first: "Your first hand-control baseline is ready.",
  },
  walking: {
    up: "Your walking looks steadier.",
    flat: "Your walking pattern is holding steady.",
    down: "Walking is ready for a closer review.",
    first: "Your first walking baseline is ready.",
  },
};

const clamp = (value: number) => Math.min(100, Math.max(0, value));

function normalize(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return clamp(Math.abs(value) <= 1.5 ? value * 100 : value);
}

function metric(point: AssessmentPoint, id: Trend["id"]) {
  if (id === "reaching") {
    return normalize(point.reach_completion) ?? (
      typeof point.shoulder_flexion_deg === "number" ? clamp(point.shoulder_flexion_deg / 1.2) : null
    );
  }
  if (id === "walking") return normalize(point.bilateral_symmetry);
  const hand = [normalize(point.hand_opening), normalize(point.pinch_grip)]
    .filter((value): value is number => value !== null);
  return hand.length ? hand.reduce((sum, value) => sum + value, 0) / hand.length : null;
}

function insight(id: Trend["id"], points: TrendPoint[]) {
  if (!points.length) return "Complete an assessment to start this trend.";
  if (points.length === 1) return COPY[id].first;
  const change = points.at(-1)!.value - points[0].value;
  return change >= 2 ? COPY[id].up : change <= -2 ? COPY[id].down : COPY[id].flat;
}

function makeTrends(assessments: AssessmentPoint[], demoMode: boolean): Trend[] {
  if (demoMode) return DEMO_TRENDS;
  const ordered = [...assessments]
    .filter((point) => Boolean(point.date))
    .sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());

  return ([
    ["reaching", "Reaching"],
    ["hand", "Hand control"],
    ["walking", "Walking"],
  ] as const).map(([id, title]) => {
    const points = ordered
      .map((assessment) => ({ date: assessment.date, value: metric(assessment, id) }))
      .filter((point): point is TrendPoint => point.value !== null)
      .slice(-5);
    return { id, title, points, insight: insight(id, points) };
  });
}

function shortDate(value?: string) {
  if (!value) return "First check";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? value
    : parsed.toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

type Coordinate = { x: number; y: number };

function chartCoordinates(points: TrendPoint[]): Coordinate[] {
  return points.map((point, index) => ({
    x: points.length === 1 ? 234 : 14 + (index / (points.length - 1)) * 220,
    y: 88 - (clamp(point.value) / 100) * 72,
  }));
}

function chartPath(points: Coordinate[]) {
  if (points.length < 2) return "";
  return points.slice(0, -1).reduce((path, point, index) => {
    const next = points[index + 1];
    const controlX = (point.x + next.x) / 2;
    return `${path} C ${controlX} ${point.y}, ${controlX} ${next.y}, ${next.x} ${next.y}`;
  }, `M ${points[0].x} ${points[0].y}`);
}

function TrendChart({ points, palette }: { points: TrendPoint[]; palette: DisplayPalette }) {
  const coordinates = chartCoordinates(points);
  const endpoint = coordinates.at(-1);

  return (
    <View style={styles.chartFrame} accessibilityLabel={points.length ? `${points.length} assessment trend points` : "No trend data yet"}>
      <Svg width="100%" height={108} viewBox="0 0 248 108">
        {!coordinates.length ? (
          <Path d="M 14 74 C 72 70, 176 70, 234 74" fill="none" stroke={palette.border} strokeWidth={2} strokeDasharray="5 7" strokeLinecap="round" />
        ) : null}
        {coordinates.length > 1 ? (
          <Path d={chartPath(coordinates)} fill="none" stroke={palette.brand} strokeOpacity={0.4} strokeWidth={3.5} strokeLinecap="round" strokeLinejoin="round" />
        ) : null}
        {coordinates.slice(0, -1).map((point, index) => (
          <Circle key={index} cx={point.x} cy={point.y} r={5.5} fill={palette.brand} fillOpacity={0.35} stroke={palette.surface} strokeWidth={2} />
        ))}
        {endpoint ? (
          <>
            <Circle cx={endpoint.x} cy={endpoint.y} r={17} fill={palette.brand} opacity={0.07} />
            <Circle cx={endpoint.x} cy={endpoint.y} r={12} fill={palette.brand} opacity={0.14} />
            <Circle cx={endpoint.x} cy={endpoint.y} r={7.5} fill={palette.brand} stroke={palette.surface} strokeWidth={2} />
            <Circle cx={endpoint.x - 2} cy={endpoint.y - 2} r={2} fill={palette.onBrand} opacity={0.72} />
          </>
        ) : null}
      </Svg>
    </View>
  );
}

function TrendPanel({
  trend,
  palette,
  wide,
  width,
  divider,
}: {
  trend: Trend;
  palette: DisplayPalette;
  wide: boolean;
  width: number;
  divider: boolean;
}) {
  return (
    <View style={[
      styles.trendPanel,
      wide ? styles.trendPanelWide : { width },
      divider && { borderLeftWidth: 1, borderLeftColor: palette.border },
    ]}>
      <Text style={[styles.trendTitle, { color: palette.text }]}>{trend.title}</Text>
      <TrendChart points={trend.points} palette={palette} />
      <View style={styles.dateRow}>
        <Text style={[styles.dateText, { color: palette.muted }]}>{shortDate(trend.points[0]?.date)}</Text>
        <Text style={[styles.dateText, { color: palette.muted }]}>
          {trend.points.length > 1 ? shortDate(trend.points.at(-1)?.date) : "Latest"}
        </Text>
      </View>
      <Text style={[styles.insight, { color: palette.text }]}>{trend.insight}</Text>
    </View>
  );
}

export function JourneyProgressPanel({ demoMode }: { demoMode: boolean }) {
  const router = useRouter();
  const { palette } = useDisplayPreferences();
  const { width: viewportWidth } = useWindowDimensions();
  const wide = viewportWidth >= 760;
  const panelWidth = Math.max(220, viewportWidth - 96);
  const [assessments, setAssessments] = useState<AssessmentPoint[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const response = await authedFetch("/api/progress/summary");
      if (!response.ok) throw new Error("Unable to load progress");
      const payload = await response.json();
      setAssessments(Array.isArray(payload.assessments) ? payload.assessments : []);
    } catch {
      setAssessments([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(useCallback(() => {
    void load();
  }, [load]));

  const trends = useMemo(() => makeTrends(assessments, demoMode), [assessments, demoMode]);
  const badge = demoMode
    ? "Sample progress"
    : assessments.length > 1
      ? `${assessments.length} assessments`
      : assessments.length === 1
        ? "First baseline"
        : "Start your trend";

  return (
    <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]}>
      <View style={styles.header}>
        <Text style={[styles.heading, { color: palette.text }]}>Your progress</Text>
        <View style={[styles.badge, { backgroundColor: palette.soft }]}>
          <Text style={[styles.badgeText, { color: palette.text }]}>{badge}</Text>
        </View>
      </View>

      {loading && !demoMode ? (
        <View style={styles.loading}>
          <ActivityIndicator color={palette.brand} />
          <Text style={[styles.loadingText, { color: palette.muted }]}>Loading your progress...</Text>
        </View>
      ) : wide ? (
        <View style={styles.trendGrid}>
          {trends.map((trend, index) => (
            <TrendPanel key={trend.id} trend={trend} palette={palette} wide width={panelWidth} divider={index > 0} />
          ))}
        </View>
      ) : (
        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          contentContainerStyle={styles.trendRail}
          snapToInterval={panelWidth + spacing.md}
          decelerationRate="fast"
        >
          {trends.map((trend) => (
            <TrendPanel key={trend.id} trend={trend} palette={palette} wide={false} width={panelWidth} divider={false} />
          ))}
        </ScrollView>
      )}

      <Pressable
        accessibilityRole="button"
        testID="journey-see-full-progress"
        onPress={() => router.push("/progress")}
        style={({ pressed }) => [styles.fullProgressButton, pressed && { opacity: 0.68 }]}
      >
        <Text style={[styles.fullProgressText, { color: palette.brand }]}>See full progress</Text>
        <Ionicons name="chevron-forward" size={20} color={palette.brand} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderWidth: 1, borderRadius: radius.md, padding: spacing.lg, overflow: "hidden" },
  header: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: spacing.sm },
  heading: { fontSize: 20, lineHeight: 26, fontWeight: "900" },
  badge: { borderRadius: radius.pill, paddingHorizontal: 11, paddingVertical: 5 },
  badgeText: { fontSize: 12, lineHeight: 15, fontWeight: "700" },
  loading: { minHeight: 206, alignItems: "center", justifyContent: "center", gap: spacing.sm },
  loadingText: { fontSize: 13 },
  trendGrid: { flexDirection: "row", marginTop: spacing.lg },
  trendScroller: { width: "100%", overflow: "hidden" },
  trendRail: { gap: spacing.md, paddingTop: spacing.lg },
  trendPanel: { minHeight: 268 },
  trendPanelWide: { flex: 1, paddingHorizontal: spacing.lg },
  trendTitle: { fontSize: 17, lineHeight: 22, fontWeight: "900" },
  chartFrame: { width: "100%", height: 108, marginTop: spacing.sm },
  dateRow: { flexDirection: "row", justifyContent: "space-between", marginTop: 1 },
  dateText: { fontSize: 12, lineHeight: 16 },
  insight: { fontSize: 14, lineHeight: 20, marginTop: spacing.md },
  fullProgressButton: {
    alignSelf: "flex-end",
    minHeight: 44,
    flexDirection: "row",
    alignItems: "center",
    gap: 5,
    paddingHorizontal: spacing.sm,
    marginTop: spacing.xs,
  },
  fullProgressText: { fontSize: 14, fontWeight: "900" },
});