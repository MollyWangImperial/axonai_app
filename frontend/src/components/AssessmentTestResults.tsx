import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { TestingAssessmentReport } from "@/src/api";
import { useDisplayPreferences } from "@/src/displayPreferences";

type Props = {
  report: TestingAssessmentReport | null;
  loading: boolean;
  error: string | null;
  affectedSide: string;
  onRetryScore: () => void;
  onBack: () => void;
  onTryAgain: () => void;
};

function measure(value: number | null | undefined, unit: string) {
  if (value == null || !Number.isFinite(value)) return "Not measured";
  const scaled = unit === "ratio" ? value * 100 : value;
  return `${Number(scaled.toFixed(1))}${unit === "ratio" ? "%" : unit === "deg" ? "°" : ""}`;
}

export function AssessmentTestResults({ report, loading, error, affectedSide, onRetryScore, onBack, onTryAgain }: Props) {
  const { palette } = useDisplayPreferences();
  const [expanded, setExpanded] = useState<string | null>(null);
  const task = report?.task;
  const text = { color: palette.text };
  const muted = { color: palette.muted };
  const card = { backgroundColor: palette.surface, borderColor: palette.border };
  const peak = (metric: string) => {
    const values = task?.steps.flatMap(step => {
      const value = step.measurements.find(row => row.metric === metric)?.max;
      return value == null ? [] : [value];
    }) || [];
    return values.length ? Math.max(...values) : null;
  };
  return (
    <ScrollView style={[styles.screen, { backgroundColor: palette.page }]} contentContainerStyle={styles.scroll} testID="assessment-library-test-complete">
      <View style={styles.content}>
        <Text style={[styles.eyebrow, { color: palette.brand }]}>TASK TEST COMPLETE</Text>
        <Text accessibilityRole="header" style={[styles.title, text]}>{task?.label || "Movement results"}</Text>
        <Text style={[styles.body, muted]}>{affectedSide} side · Testing only. This run is not saved to your patient record, points or care plan.</Text>
        {loading && <View style={styles.loading}><ActivityIndicator color={palette.brand} /><Text style={[styles.body, text]}>Calculating your movement results…</Text></View>}
        {error && <View accessibilityRole="alert" style={[styles.card, card]}>
          <Text style={[styles.body, text]}>{error}</Text>
          <Pressable onPress={onRetryScore} accessibilityRole="button" style={styles.link}><Text style={[styles.linkText, { color: palette.brand }]}>Retry calculation</Text></Pressable>
        </View>}
        {report && task && <>
          <View style={[styles.card, styles.scoreCard, card]}>
            <View style={styles.scoreCopy}>
              <Text style={[styles.heading, text]}>Movement score</Text>
              <Text style={[styles.score, { color: palette.brand }]} testID="assessment-test-score">{task.score === null ? "Not available" : `${task.score} / 100`}</Text>
              <Text style={[styles.body, muted]}>{task.measured_steps} of {task.total_steps} steps have enough evidence to score.</Text>
              {task.score === null && <Text style={[styles.body, muted]}>A complete score needs every step to be measured. {task.earned_score != null ? `${task.earned_score} points are accounted for so far; this is a partial result.` : "Try again with the affected arm and trunk clearly visible."}</Text>}
              {task.steps.some(step => step.status === "limited_view") && <Text style={[styles.body, muted]}>Limited view: some posture checks were not measurable. The score uses only observed checks.</Text>}
              {task.assisted && <Text style={[styles.body, muted]}>Physical assistance was recorded: the task score is multiplied by 0.5.</Text>}
            </View>
            <View style={styles.completion}>
              <Text style={[styles.heading, text]}>{report.completed_steps} / {task.total_steps} targets</Text>
              <Text style={[styles.body, muted]}>{(report.duration_ms / 1000).toFixed(1)} seconds</Text>
              <Text style={[styles.small, muted]}>Step time includes instructions and waiting.</Text>
            </View>
          </View>
          {task.task_id.startsWith("T") && <>
            <Text style={[styles.heading, text]}>Movement measurements</Text>
            <View style={styles.metricGrid}>
              {[["arm_elevation", "Peak shoulder elevation"], ["elbow_extension", "Peak elbow extension"], ["trunk_lean", "Peak trunk lean"], ["shoulder_hike", "Peak excess shoulder lift"]].map(([id, label]) => <View key={id} style={[styles.metricCard, card]}>
                <Text style={[styles.small, muted]}>{label}</Text>
                <Text style={[styles.metricValue, text]}>{measure(peak(id), "deg")}</Text>
              </View>)}
            </View>
            <Text style={[styles.small, muted]}>Shoulder elevation is the upper-arm angle relative to the torso (0° beside the body). It estimates forward lifting in this task, but does not isolate shoulder flexion from sideways lifting. Peak values describe the run; the score uses the step measurements below.</Text>
          </>}
          <View style={[styles.card, card]} testID="assessment-test-formula">
            <Text style={[styles.heading, text]}>How the score is calculated</Text>
            <Text style={[styles.body, text]}>Step score = (target points + movement points) × form factor.</Text>
            <Text style={[styles.body, muted]}>Target points: 20 when the target is reached, otherwise 0. Movement points: up to 80, using the average of measured angle or control ÷ its reference, capped at 100% for each measure.</Text>
            <Text style={[styles.body, muted]}>The form factor starts at 1. Each detected compensation reduces it by 0.2, down to a minimum of 0.4. A compensation must exceed its threshold for at least 0.5 seconds.</Text>
            <Text style={[styles.body, muted]}>Each of the {task.total_steps} steps has equal weight. {task.score !== null ? `(${task.steps.map(step => step.score).join(" + ")}) ÷ ${task.total_steps}${task.assisted ? " × 0.5 for assistance" : ""} = ${task.score} / 100.` : "Missing measurements leave the overall score unavailable, rather than being assumed perfect."}</Text>
            <Text style={[styles.small, muted]}>Camera-derived testing score, not a validated clinical scale. Reference values are scoring settings, not instructions to force a movement. Timing and supplemental metrics do not add score points.</Text>
          </View>
          <Text style={[styles.heading, text]}>Step-by-step breakdown</Text>
          {task.steps.map((step, index) => {
            const open = expanded === step.step_id;
            const c = step.calculation;
            return <View key={step.step_id} style={[styles.card, card]} testID={`testing-step-${step.step_id}`}>
              <Text style={[styles.stepTitle, text]}>{index + 1}. {step.label}</Text>
              <Text style={[styles.body, muted]}>{step.completed ? "Target reached" : "Target not reached"} · {(step.duration_ms / 1000).toFixed(1)} s · {step.score === null ? "Not scored" : `${step.score} / 100`}</Text>
              {step.criteria.map(rule => <View key={rule.metric} style={[styles.row, { borderColor: palette.border }]}>
                <Text style={[styles.rowLabel, text]}>{rule.label}</Text>
                <Text style={[styles.rowValue, text]}>{measure(rule.observed, rule.unit)} / {measure(rule.target, rule.unit)} reference{rule.attainment == null ? "" : ` · ${measure(rule.attainment, "ratio")} attained`}</Text>
              </View>)}
              <Text style={[styles.small, muted]}>Median at the target with at least 5 samples; otherwise the median of available movement samples. Fewer than 5 samples cannot be scored.</Text>
              {step.compensations.map(check => <View key={check.id} style={styles.check}>
                <Text style={[styles.body, text]}>{check.label}: {check.status === "detected" ? "Detected" : check.status === "not_measured" ? "Not measured" : "Not detected"}</Text>
                <Text style={[styles.small, muted]}>Threshold: above {check.threshold}° for 0.5 s.{check.status === "detected" ? ` ${check.cue}` : ""}</Text>
              </View>)}
              <Text style={[styles.equation, { color: palette.brand }]}>{step.score === null ? "Insufficient movement or posture evidence for this step." : `(${c.completion_points} + ${c.range_points}) × ${Number(c.form_factor.toFixed(1))} = ${step.score} points`}</Text>
              <Pressable onPress={() => setExpanded(open ? null : step.step_id)} accessibilityRole="button" accessibilityState={{ expanded: open }} style={styles.detailsButton} testID={`testing-measurements-${step.step_id}`}>
                <Text style={[styles.linkText, { color: palette.brand }]}>{open ? "Hide" : "Show"} all movement metrics</Text>
                <Ionicons name={open ? "chevron-up" : "chevron-down"} size={20} color={palette.brand} />
              </Pressable>
              {open && <View testID={`testing-measurement-details-${step.step_id}`}>
                {step.measurements.map(row => <View key={row.metric} style={[styles.row, { borderColor: palette.border }]}>
                  <Text style={[styles.rowLabel, text]}>{row.label}</Text>
                  <View style={styles.rowValue}>
                    <Text style={[styles.small, text]}>{row.metric === "target_control" ? "Proportion" : "Median"}: {measure(row.median, row.unit)}</Text>
                    {row.metric !== "target_control" && <Text style={[styles.small, muted]}>At target: {measure(row.endpoint, row.unit)} · Range: {measure(row.min, row.unit)} – {measure(row.max, row.unit)}</Text>}
                    <Text style={[styles.small, muted]}>{row.samples} valid samples</Text>
                  </View>
                </View>)}
                <Text style={[styles.small, muted]}>Reach distance is shoulder-to-wrist distance divided by arm length. Trunk lean is change from the calibrated starting posture. Wrist alignment uses coarse camera landmarks. No value is inferred for an occluded joint.</Text>
              </View>}
            </View>;
          })}
        </>}
        <View style={styles.actions}>
          <Pressable onPress={onTryAgain} accessibilityRole="button" style={[styles.primary, { backgroundColor: palette.brand }]} testID="assessment-library-try-again"><Text style={styles.primaryText}>Test task again</Text></Pressable>
          <Pressable onPress={onBack} accessibilityRole="button" style={[styles.secondary, { borderColor: palette.border }]} testID="assessment-library-back"><Text style={[styles.linkText, { color: palette.brand }]}>Back to Testing</Text></Pressable>
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { ...StyleSheet.absoluteFillObject, zIndex: 10 },
  scroll: { flexGrow: 1, padding: 20, paddingBottom: 80 },
  content: { width: "100%", maxWidth: 1040, alignSelf: "center", gap: 18 },
  eyebrow: { fontSize: 13, fontWeight: "800", letterSpacing: 1, marginTop: 14 },
  title: { fontSize: 30, lineHeight: 38, fontWeight: "800" },
  heading: { fontSize: 21, lineHeight: 28, fontWeight: "700" },
  body: { fontSize: 16, lineHeight: 24 },
  small: { fontSize: 14, lineHeight: 21 },
  loading: { padding: 28, flexDirection: "row", gap: 12, alignItems: "center" },
  card: { padding: 20, borderRadius: 18, borderWidth: 1, gap: 12 },
  scoreCard: { flexDirection: "row", flexWrap: "wrap", gap: 24 },
  scoreCopy: { flexGrow: 1, flexShrink: 1, flexBasis: 360, minWidth: 0, maxWidth: "100%", gap: 8 },
  score: { fontSize: 38, lineHeight: 46, fontWeight: "800" },
  completion: { flexBasis: 180, flexGrow: 1, maxWidth: "100%", gap: 6 },
  metricGrid: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  metricCard: { flexBasis: 180, flexGrow: 1, borderWidth: 1, borderRadius: 14, padding: 16, gap: 8 },
  metricValue: { fontSize: 25, fontWeight: "700" },
  stepTitle: { fontSize: 19, fontWeight: "700", lineHeight: 27 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 10, borderTopWidth: 1, paddingTop: 12, marginTop: 4 },
  rowLabel: { flexBasis: 210, flexGrow: 1, maxWidth: "100%", fontSize: 15, lineHeight: 23, fontWeight: "600" },
  rowValue: { flexBasis: 290, flexGrow: 1, maxWidth: "100%", flexShrink: 1, fontSize: 15, lineHeight: 23 },
  check: { gap: 2 },
  equation: { fontSize: 16, lineHeight: 24, fontWeight: "700" },
  detailsButton: { minHeight: 48, flexDirection: "row", gap: 8, alignItems: "center", justifyContent: "space-between" },
  link: { minHeight: 48, justifyContent: "center" },
  linkText: { fontSize: 16, fontWeight: "700", flexShrink: 1 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  primary: { minHeight: 54, paddingHorizontal: 24, paddingVertical: 16, borderRadius: 14, alignItems: "center", flexGrow: 1 },
  primaryText: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  secondary: { minHeight: 54, borderWidth: 1, borderRadius: 14, paddingHorizontal: 24, paddingVertical: 16, alignItems: "center", flexGrow: 1 },
});
