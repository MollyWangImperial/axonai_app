import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, Share } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import Svg, { Polyline, Circle, Line } from "react-native-svg";
import { authedFetch } from "@/src/auth";
import { colors, spacing, radius } from "@/src/theme";

type Point = { date: string; score: number };

// Derives a 0-100 "movement score" per assessment from whichever metrics exist,
// falling back to a findings-based estimate so the story is never empty.
function scoreFor(a: any): number | null {
  const m = [a.reach_completion, a.bilateral_symmetry, a.hand_opening, a.pinch_grip].find(
    (v) => typeof v === "number",
  );
  if (typeof m === "number") return Math.round(Math.max(0, Math.min(1, m)) * 100);
  if (typeof a.issues_count === "number") return Math.max(20, 100 - a.issues_count * 12);
  return null;
}

export function ProgressStoryCard() {
  const [points, setPoints] = useState<Point[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    (async () => {
      try {
        const r = await authedFetch("/api/progress/summary");
        const j = await r.json();
        const pts: Point[] = (j.assessments || [])
          .map((a: any) => ({ date: a.date, score: scoreFor(a) }))
          .filter((p: any) => typeof p.score === "number");
        if (active) setPoints(pts);
      } catch {
        /* keep empty */
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);

  if (loading || points.length < 2) return null;

  const first = points[0].score;
  const latest = points[points.length - 1].score;
  const delta = latest - first;
  const improving = delta > 2;
  const steady = Math.abs(delta) <= 2;

  const W = 300;
  const H = 90;
  const scores = points.map((p) => p.score);
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const range = Math.max(1, max - min);
  const coords = points.map((p, i) => {
    const x = points.length === 1 ? W / 2 : (i / (points.length - 1)) * (W - 12) + 6;
    const y = H - 10 - ((p.score - min) / range) * (H - 24);
    return { x, y };
  });
  const polyline = coords.map((c) => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" ");

  const headline = improving
    ? `You're up ${delta} points since you started 🎉`
    : steady
      ? "You're holding steady — consistency is progress"
      : "Recovery isn't a straight line — keep going";

  const share = () => {
    void Share.share({
      message: improving
        ? `My Rehyn movement score has improved ${delta} points over ${points.length} sessions. Small steps, real progress!`
        : `I've completed ${points.length} Rehyn movement sessions and I'm keeping at my recovery.`,
    });
  };

  return (
    <View style={styles.card} testID="progress-story-card">
      <View style={styles.head}>
        <View>
          <Text style={styles.eyebrow}>YOUR PROGRESS STORY</Text>
          <Text style={styles.headline}>{headline}</Text>
        </View>
        <Pressable onPress={share} style={styles.shareBtn} testID="progress-story-share" accessibilityLabel="Share progress">
          <Ionicons name="share-outline" size={20} color={colors.brandPrimary} />
        </Pressable>
      </View>

      <View style={styles.chartWrap}>
        <Svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`}>
          <Line x1={6} y1={H - 10} x2={W - 6} y2={H - 10} stroke={colors.border} strokeWidth={1} />
          <Polyline points={polyline} fill="none" stroke={colors.brandPrimary} strokeWidth={3} strokeLinejoin="round" strokeLinecap="round" />
          {coords.map((c, i) => (
            <Circle key={i} cx={c.x} cy={c.y} r={i === coords.length - 1 ? 5 : 3} fill={i === coords.length - 1 ? colors.brandSecondary : colors.brandPrimary} />
          ))}
        </Svg>
      </View>

      <View style={styles.footRow}>
        <View style={styles.stat}><Text style={styles.statValue}>{first}</Text><Text style={styles.statLabel}>Baseline</Text></View>
        <Ionicons name={improving ? "arrow-up" : steady ? "remove" : "trending-up"} size={18} color={improving ? colors.success : colors.onSurfaceTertiary} />
        <View style={styles.stat}><Text style={[styles.statValue, { color: colors.brandPrimary }]}>{latest}</Text><Text style={styles.statLabel}>Latest</Text></View>
        <View style={styles.stat}><Text style={styles.statValue}>{points.length}</Text><Text style={styles.statLabel}>Sessions</Text></View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: { borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: spacing.md, marginBottom: spacing.md },
  head: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.sm },
  eyebrow: { fontSize: 11, fontWeight: "900", color: colors.brandPrimary, letterSpacing: 0.5 },
  headline: { fontSize: 17, lineHeight: 23, fontWeight: "800", color: colors.onSurface, marginTop: 4 },
  shareBtn: { width: 40, height: 40, borderRadius: 20, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary },
  chartWrap: { marginTop: spacing.md },
  footRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-around", marginTop: spacing.sm },
  stat: { alignItems: "center" },
  statValue: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  statLabel: { fontSize: 11, color: colors.onSurfaceTertiary, marginTop: 2 },
});
