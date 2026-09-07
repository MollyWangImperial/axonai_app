import { StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { Ionicons, MaterialCommunityIcons } from "@expo/vector-icons";

import { BodyFunctionDomainSummary, FunctionalMetrics } from "@/src/api";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { radius, spacing } from "@/src/theme";

type DomainId = BodyFunctionDomainSummary["domain"];

type ScorePresentation = {
  domain: DomainId;
  label: string;
  score: number | null;
  status: string;
  color: string;
  soft: string;
  coverage?: string;
};

const DOMAIN_LABELS: Record<DomainId, string> = {
  upper_limb: "Upper limb",
  hand: "Hand control",
  lower_limb: "Lower limb",
};

function scoreTone(score: number | null) {
  if (score === null) return { status: "Not fully measured", color: "#6D7771", soft: "#E5E8E6" };
  if (score >= 80) return { status: "Moving well", color: "#17603F", soft: "#DDE9DD" };
  if (score >= 65) return { status: "Steady", color: "#27714D", soft: "#DDE9DD" };
  return { status: "Building control", color: "#C47A00", soft: "#F5E6C3" };
}

function domainIcon(domain: DomainId, color: string, compact: boolean) {
  const size = compact ? 43 : 58;
  if (domain === "upper_limb") return <MaterialCommunityIcons name="human-handsup" size={size} color={color} />;
  if (domain === "hand") return <MaterialCommunityIcons name="hand-back-left-outline" size={size} color={color} />;
  return <MaterialCommunityIcons name="walk" size={size} color={color} />;
}

export function MovementScoresPanel({ domains, metrics, isSample = false }: { domains: BodyFunctionDomainSummary[]; metrics?: FunctionalMetrics; isSample?: boolean }) {
  const { width } = useWindowDimensions();
  const { palette } = useDisplayPreferences();
  const compact = width < 760;
  const orderedDomains = (["upper_limb", "hand", "lower_limb"] as const).map((domainId) => (
    domains.find((domain) => domain.domain === domainId) ?? {
      domain: domainId,
      label: DOMAIN_LABELS[domainId],
      status: "not_observed" as const,
      tasks_completed: 0,
      tasks_observed: 0,
      step_completion_percent: 0,
      average_task_duration_ms: 0,
      findings_count: 0,
      summary: "This area was not observed in this assessment.",
    }
  ));
  const presentations: ScorePresentation[] = orderedDomains.map((domain) => {
    const module = metrics?.task_quality?.modules?.[domain.domain];
    const score = module?.score ?? module?.earned_score ?? null;
    const partial = module?.score == null && score !== null;
    const tone = scoreTone(score);
    return {
      domain: domain.domain, label: DOMAIN_LABELS[domain.domain], score, ...tone,
      ...(partial ? {
        status: "Partial score",
        color: palette.muted,
        soft: palette.border,
        coverage: `${module?.measured_steps}/${module?.total_steps} steps measured. Points recorded so far; unmeasured steps are not scored.`,
      } : {}),
    };
  });

  return (
    <View style={[styles.panel, compact && styles.panelCompact, { backgroundColor: palette.surface, borderColor: palette.border }]} testID="movement-scores-panel">
      <View style={[styles.header, compact && styles.headerCompact]}>
        <View style={styles.headerCopy}>
          <Text style={[styles.title, compact && styles.titleCompact, { color: palette.text }]}>Your movement scores</Text>
          <Text style={[styles.subtitle, compact && styles.subtitleCompact, { color: palette.muted }]}>
            {isSample
              ? "Generated for testing only. Higher sample values represent steadier movement."
              : "Based on today's guided movement tasks. Higher means steadier movement."}
          </Text>
        </View>
        <View style={styles.measureNote}>
          <Ionicons name="information-circle-outline" size={20} color="#38614B" />
          <Text style={styles.measureNoteText}>Guided-task scores - not a clinical measure.</Text>
        </View>
      </View>

      <View style={[styles.scoreRow, compact && styles.scoreRowCompact]}>
        {presentations.map((item, index) => (
          <View
            key={item.domain}
            style={[
              styles.scoreItem,
              compact && styles.scoreItemCompact,
              !compact && index > 0 && { borderLeftWidth: 1, borderLeftColor: palette.border },
            ]}
            testID={`movement-score-${item.domain}`}
          >
            <View style={styles.iconWrap}>{domainIcon(item.domain, item.color, compact)}</View>
            <View style={styles.scoreCopy}>
              <Text style={[styles.domainLabel, compact && styles.domainLabelCompact, { color: palette.text }]}>{item.label}</Text>
              <View style={styles.valueRow}>
                <Text style={[styles.scoreValue, compact && styles.scoreValueCompact, { color: item.color }]}>{item.score ?? "-"}</Text>
                <Text style={[styles.scoreScale, { color: item.score === null ? palette.muted : item.color }]}> / 100</Text>
              </View>
              <Text style={[styles.scoreStatus, { color: item.color }]}>{item.status}</Text>
              {item.coverage && <Text style={[styles.coverage, { color: palette.muted }]}>{item.coverage}</Text>}
              <View style={[styles.track, { backgroundColor: item.soft }]}>
                <View style={[styles.fill, { width: `${Math.max(0, item.score ?? 0)}%` as `${number}%`, backgroundColor: item.color }]} />
              </View>
            </View>
          </View>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: { borderWidth: 1, borderRadius: radius.sm, padding: spacing.lg, marginBottom: spacing.lg },
  panelCompact: { padding: spacing.md },
  header: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.lg },
  headerCompact: { flexDirection: "column", gap: spacing.sm },
  headerCopy: { flex: 1, minWidth: 0 },
  title: { fontSize: 27, lineHeight: 34, fontWeight: "900" },
  titleCompact: { fontSize: 23, lineHeight: 29 },
  subtitle: { marginTop: 4, fontSize: 16, lineHeight: 23 },
  subtitleCompact: { fontSize: 14, lineHeight: 20 },
  measureNote: { flexDirection: "row", alignItems: "center", gap: spacing.xs, paddingTop: 4 },
  measureNoteText: { fontSize: 13, lineHeight: 18, color: "#52655B" },
  scoreRow: { marginTop: spacing.lg, flexDirection: "row", alignItems: "stretch" },
  scoreRowCompact: { flexDirection: "column", marginTop: spacing.md },
  scoreItem: { flex: 1, minWidth: 0, minHeight: 184, paddingHorizontal: spacing.lg, flexDirection: "row", alignItems: "flex-start", gap: spacing.md },
  scoreItemCompact: { flex: 0, flexBasis: "auto", minHeight: 0, paddingHorizontal: 0, paddingVertical: spacing.md, borderTopWidth: 1, borderTopColor: "#DDE2DE" },
  iconWrap: { width: 76, paddingTop: 3, alignItems: "center" },
  scoreCopy: { flex: 1, minWidth: 0 },
  domainLabel: { fontSize: 18, lineHeight: 24, fontWeight: "900" },
  domainLabelCompact: { fontSize: 17, lineHeight: 23 },
  valueRow: { marginTop: 7, flexDirection: "row", alignItems: "baseline" },
  scoreValue: { fontSize: 48, lineHeight: 54, fontWeight: "900" },
  scoreValueCompact: { fontSize: 40, lineHeight: 46 },
  scoreScale: { fontSize: 27, lineHeight: 34, fontWeight: "900" },
  scoreStatus: { marginTop: 2, fontSize: 16, lineHeight: 22, fontWeight: "700" },
  coverage: { marginTop: 6, fontSize: 14, lineHeight: 20 },
  track: { height: 12, marginTop: spacing.md, borderRadius: 6, overflow: "hidden" },
  fill: { height: 12, borderRadius: 6 },
});
