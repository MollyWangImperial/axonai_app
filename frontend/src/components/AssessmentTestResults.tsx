import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import Svg, { Circle, Line, Polyline, Text as SvgText } from "react-native-svg";
import { TestingAssessmentReport } from "@/src/api";
import { useDisplayPreferences } from "@/src/displayPreferences";

type Props = {
  report: TestingAssessmentReport | null;
  loading: boolean;
  error: string | null;
  onRetryScore: () => void;
  onBack: () => void;
  onTryAgain: () => void;
};

type ScoredStep = NonNullable<TestingAssessmentReport["task"]>["steps"][number];
type Criterion = ScoredStep["criteria"][number];

function measure(value: number | null | undefined, unit: string) {
  if (value == null || !Number.isFinite(value)) return "not measured";
  const scaled = unit === "ratio" ? value * 100 : value;
  return `${Number(scaled.toFixed(1))}${unit === "ratio" ? "%" : unit === "deg" ? "°" : ""}`;
}

function list(items: string[]) {
  if (!items.length) return "none";
  if (items.length === 1) return items[0];
  return `${items.slice(0, -1).join(", ")} and ${items.at(-1)}`;
}

function alternatives(items: string[]) {
  if (items.length <= 1) return items[0] || "the configured threshold is exceeded";
  return `${items.slice(0, -1).join(", ")} or ${items.at(-1)}`;
}

function metricMeaning(rule: Criterion, stepIndex: number) {
  if (rule.metric === "arm_elevation") {
    const phase = stepIndex === 0 ? "the early phase of a meaningful forward arm lift" : "a meaningful forward reach without requiring the arm to be lifted overhead";
    return `Arm elevation is the angle of the upper arm relative to the torso, where 0° is beside the body. The ${measure(rule.target, rule.unit)} reference represents ${phase}.`;
  }
  if (rule.metric === "elbow_extension") {
    return `Elbow extension is the 2D image-plane angle formed by the shoulder, elbow and wrist, where 180° is a straight elbow in the camera view. The ${measure(rule.target, rule.unit)} reference represents a near-straight functional reach while allowing a comfortable amount of elbow bend.`;
  }
  if (rule.metric === "target_control") {
    return `Target control is the proportion of valid camera samples in which the hand remains inside the target. The ${measure(rule.target, rule.unit)} reference allows brief tracking fluctuations while requiring the hand to remain at the target for most of the step.`;
  }
  return `${rule.label} is compared with a ${measure(rule.target, rule.unit)} reference for this phase of the movement.`;
}

function statisticExplanation(rule: Criterion) {
  if (rule.statistic_source === "sample_proportion") return "We use the proportion of all valid samples recorded inside the target.";
  if (rule.statistic_source === "movement_median") return "Fewer than five valid samples were recorded at the target, so we use the median of all valid movement samples.";
  return "We use the median of the valid samples recorded while the hand is at the target, which reduces the effect of an individual noisy camera frame.";
}

function TimeSeriesChart({ rule, brand, text, muted, border, surface }: {
  rule: Criterion; brand: string; text: string; muted: string; border: string; surface: string;
}) {
  const { width: viewportWidth } = useWindowDimensions();
  const series = (rule.series || []).filter(point => Number.isFinite(point.elapsed_ms) && Number.isFinite(point.value));
  if (!series.length) return <Text style={[styles.small, { color: muted }]}>No valid time-series samples were available for this metric.</Text>;
  const width = Math.min(720, Math.max(210, viewportWidth - 104));
  const height = viewportWidth <= 480 ? 175 : 190;
  const labelSize = viewportWidth <= 480 ? 9 : 12;
  const left = viewportWidth <= 480 ? 37 : 48, right = 8, top = 18, bottom = 34;
  const values = [...series.map(point => point.value), rule.target, ...(rule.observed == null ? [] : [rule.observed])];
  const rawMin = rule.unit === "ratio" ? 0 : Math.min(...values);
  const rawMax = rule.unit === "ratio" ? 1 : Math.max(...values);
  const padding = Math.max((rawMax - rawMin) * .12, rule.unit === "deg" ? 4 : .05);
  const yMin = rule.unit === "ratio" ? 0 : Math.max(0, rawMin - padding);
  const yMax = rule.unit === "ratio" ? 1 : rawMax + padding;
  const maxTime = Math.max(1, ...series.map(point => point.elapsed_ms));
  const x = (elapsed: number) => left + elapsed / maxTime * (width - left - right);
  const y = (value: number) => top + (yMax - value) / Math.max(.001, yMax - yMin) * (height - top - bottom);
  const points = series.map(point => `${x(point.elapsed_ms)},${y(point.value)}`).join(" ");
  const targetY = y(rule.target);
  return <View style={[styles.chart, { borderColor: border, backgroundColor: surface }]} testID={`testing-time-series-${rule.metric}`}>
    <Text style={[styles.chartTitle, { color: text }]}>{rule.label} over time</Text>
    <Svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} accessibilityLabel={`${rule.label} time series`}>
      <Line x1={left} x2={width - right} y1={height - bottom} y2={height - bottom} stroke={border} strokeWidth={1} />
      <Line x1={left} x2={left} y1={top} y2={height - bottom} stroke={border} strokeWidth={1} />
      <Line x1={left} x2={width - right} y1={targetY} y2={targetY} stroke="#B06737" strokeWidth={2} strokeDasharray="7 6" />
      {rule.observed != null && <Line x1={left} x2={width - right} y1={y(rule.observed)} y2={y(rule.observed)} stroke={muted} strokeWidth={1.5} strokeDasharray="3 5" />}
      <Polyline points={points} fill="none" stroke={brand} strokeWidth={3} strokeLinecap="round" strokeLinejoin="round" />
      {series.map((point, index) => point.in_target && (index % Math.max(1, Math.ceil(series.length / 70)) === 0)
        ? <Circle key={`${point.elapsed_ms}-${index}`} cx={x(point.elapsed_ms)} cy={y(point.value)} r={3.4} fill="#B06737" /> : null)}
      <SvgText x={left - 5} y={top + 4} fill={muted} fontSize={labelSize} textAnchor="end">{measure(yMax, rule.unit)}</SvgText>
      <SvgText x={left - 5} y={height - bottom + 4} fill={muted} fontSize={labelSize} textAnchor="end">{measure(yMin, rule.unit)}</SvgText>
      <SvgText x={left} y={height - 9} fill={muted} fontSize={labelSize}>0 s</SvgText>
      <SvgText x={width - right} y={height - 9} fill={muted} fontSize={labelSize} textAnchor="end">{(maxTime / 1000).toFixed(1)} s</SvgText>
      <SvgText x={width - right - 3} y={Math.max(13, targetY - 7)} fill="#8A4C28" fontSize={labelSize} textAnchor="end">Reference {measure(rule.target, rule.unit)}</SvgText>
      {rule.observed != null && <SvgText x={left + 4} y={Math.max(13, y(rule.observed) - 6)} fill={muted} fontSize={labelSize}>Scoring value {measure(rule.observed, rule.unit)}</SvgText>}
    </Svg>
    <Text style={[styles.chartNote, { color: muted }]}>Green line: valid measurements · Brown dots: samples recorded at the target · Brown dashed line: reference · Grey dotted line: scoring statistic</Text>
  </View>;
}

function ReachStepExplanation({ step, index, palette }: {
  step: ScoredStep; index: number; palette: ReturnType<typeof useDisplayPreferences>["palette"];
}) {
  const c = step.calculation;
  const detected = step.compensations.filter(check => check.status === "detected");
  const notMeasured = step.compensations.filter(check => check.status === "not_measured");
  const criterionResults = step.criteria.map(rule => rule.observed == null
    ? `${rule.label.toLowerCase()} could not be measured`
    : `${rule.label.toLowerCase()} was ${measure(rule.observed, rule.unit)} against the ${measure(rule.target, rule.unit)} reference (${measure(rule.attainment, "ratio")} achieved)`).join("; ");
  const compensationNames = list(step.compensations.map(check => check.label.toLowerCase()));
  const thresholds = step.compensations.map(check => `${check.label.toLowerCase()} above ${measure(check.threshold, "deg")} for at least 0.5 seconds`);
  const statisticText = [...new Set(step.criteria.map(statisticExplanation))].join(" ");
  const pointSummary = step.score == null ? "This step could not be scored because there was not enough valid movement or posture evidence."
    : `${step.completed ? "The target was reached, adding 20 target points" : "The target was not reached, so no target points were added"}. The measured movement contributed ${Number((c.range_points ?? 0).toFixed(1))} of 80 movement points. ${detected.length ? `${list(detected.map(check => check.label))} ${detected.length === 1 ? "was" : "were"} detected, so the form factor was reduced to ${Number(c.form_factor.toFixed(1))}.` : notMeasured.length ? `${list(notMeasured.map(check => check.label))} could not be measured, so the available posture evidence was used.` : "No compensatory movement was detected, so no form penalty was applied."}`;
  return <View style={[styles.card, { backgroundColor: palette.surface, borderColor: palette.border }]} testID={`testing-step-${step.step_id}`}>
    <Text style={[styles.stepTitle, { color: palette.text }]}>{index + 1}. {step.label}</Text>
    {step.criteria.map(rule => <Text key={`${rule.metric}-meaning`} style={[styles.body, { color: palette.text }]}>
      <Text style={styles.bold}>Movement metric: {rule.label}{"\n"}</Text>
      {metricMeaning(rule, index)} Reaching or exceeding the reference gives 100% attainment for this metric; a lower measurement gives proportional attainment. When a step uses more than one metric, their attainment percentages are averaged to award the 80 movement points.
    </Text>)}
    <Text style={[styles.body, { color: palette.text }]}>{statisticText} We also check for <Text style={styles.bold}>{compensationNames}</Text>. A compensation is identified when {alternatives(thresholds)}.</Text>
    <Text style={[styles.body, { color: palette.text }]}>In this attempt, {criterionResults || "the required movement statistic was not available"}. {pointSummary}</Text>
    <Text style={[styles.equation, { color: palette.brand }]}>{step.score === null ? "Score unavailable" : `${c.completion_points} target points + ${Number((c.range_points ?? 0).toFixed(1))} movement points${c.form_factor < 1 ? `, multiplied by ${Number(c.form_factor.toFixed(1))}` : ""} = ${step.score} points`}</Text>
    <Text style={[styles.subheading, { color: palette.text }]}>Movement evidence over time</Text>
    {step.criteria.map(rule => <TimeSeriesChart key={rule.metric} rule={rule} brand={palette.brand} text={palette.text} muted={palette.muted} border={palette.border} surface={palette.page} />)}
  </View>;
}

export function AssessmentTestResults({ report, loading, error, onRetryScore, onBack, onTryAgain }: Props) {
  const { palette } = useDisplayPreferences();
  const task = report?.task;
  const card = { backgroundColor: palette.surface, borderColor: palette.border };
  const isForwardReach = task?.task_id === "T1";
  return (
    <ScrollView style={[styles.screen, { backgroundColor: palette.page }]} contentContainerStyle={styles.scroll} testID="assessment-library-test-complete">
      <View style={styles.content}>
        <Text style={[styles.eyebrow, { color: palette.brand }]}>TASK TEST COMPLETE</Text>
        <Text accessibilityRole="header" style={[styles.title, { color: palette.text }]}>{task?.label || "Movement results"}</Text>
        {loading && <View style={styles.loading}><ActivityIndicator color={palette.brand} /><Text style={[styles.body, { color: palette.text }]}>Calculating your movement results…</Text></View>}
        {error && <View accessibilityRole="alert" style={[styles.card, card]}>
          <Text style={[styles.body, { color: palette.text }]}>{error}</Text>
          <Pressable onPress={onRetryScore} accessibilityRole="button" style={styles.link}><Text style={[styles.linkText, { color: palette.brand }]}>Retry calculation</Text></Pressable>
        </View>}
        {report && task && <>
          <View style={[styles.card, styles.scoreCard, card]}>
            <Text style={[styles.heading, { color: palette.text }]}>Movement score</Text>
            <Text style={[styles.score, { color: palette.brand }]} testID="assessment-test-score">{task.score === null ? "Not available" : `${task.score} / 100`}</Text>
          </View>
          <View style={[styles.card, card]} testID="assessment-test-formula">
            <Text style={[styles.heading, { color: palette.text }]}>How the score is calculated</Text>
            {isForwardReach ? <>
              <Text style={[styles.body, { color: palette.text }]}>The <Text style={styles.bold}>Seated Forward Reach</Text> exercise is divided into four steps: <Text style={styles.bold}>{task.steps.map((step, index) => `(${index + 1}) ${step.label.toLowerCase()}`).join(", ")}</Text>. Each step is scored out of <Text style={styles.bold}>100 points</Text>, and all four steps have equal weight in the final score.</Text>
              <Text style={[styles.body, { color: palette.text }]}>For each step, the score is calculated as <Text style={styles.bold}>(Target points + Movement points) × Form factor</Text>. You receive <Text style={styles.bold}>20 target points</Text> when the target is reached. The remaining <Text style={styles.bold}>80 movement points</Text> compare the measured movement with the reference for that step. Meeting or exceeding a reference receives full credit; a lower result receives a proportional score. When a step uses two metrics, their attainment percentages are averaged. We also check for trunk lean and excess shoulder lift. Each detected compensation reduces the pre-penalty step score by 20%.</Text>
              <Text style={[styles.body, { color: palette.text }]}>The final movement score is the <Text style={styles.bold}>average of the four step scores</Text>. In this assessment, the score is</Text>
              <Text style={[styles.equation, { color: palette.brand }]}>{task.score === null ? "A final score needs valid evidence for all four steps." : `(${task.steps.map(step => step.score).join(" + ")}) ÷ 4${task.assisted ? " × 0.5 for recorded assistance" : ""} = ${task.score} / 100`}</Text>
            </> : <>
              <Text style={[styles.body, { color: palette.text }]}>Each step is scored as <Text style={styles.bold}>(Target points + Movement points) × Form factor</Text>. Reaching the target contributes 20 points, and movement compared with the step reference contributes up to 80 points.</Text>
              <Text style={[styles.body, { color: palette.text }]}>The final movement score is the average of the equally weighted step scores.</Text>
            </>}
          </View>
          <Text style={[styles.heading, { color: palette.text }]}>Step-by-step breakdown</Text>
          {isForwardReach ? task.steps.map((step, index) => <ReachStepExplanation key={step.step_id} step={step} index={index} palette={palette} />)
            : task.steps.map((step, index) => <View key={step.step_id} style={[styles.card, card]} testID={`testing-step-${step.step_id}`}>
              <Text style={[styles.stepTitle, { color: palette.text }]}>{index + 1}. {step.label}</Text>
              <Text style={[styles.body, { color: palette.text }]}>{step.score === null ? "Not enough evidence to score this step." : `Movement score: ${step.score} / 100.`}</Text>
              {step.criteria.map(rule => <TimeSeriesChart key={rule.metric} rule={rule} brand={palette.brand} text={palette.text} muted={palette.muted} border={palette.border} surface={palette.page} />)}
            </View>)}
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
  subheading: { fontSize: 17, lineHeight: 24, fontWeight: "700", marginTop: 4 },
  body: { fontSize: 16, lineHeight: 25 },
  small: { fontSize: 14, lineHeight: 21 },
  bold: { fontWeight: "700" },
  loading: { padding: 28, flexDirection: "row", gap: 12, alignItems: "center" },
  card: { padding: 20, borderRadius: 18, borderWidth: 1, gap: 14 },
  scoreCard: { gap: 8 },
  score: { fontSize: 38, lineHeight: 46, fontWeight: "800" },
  stepTitle: { fontSize: 19, fontWeight: "700", lineHeight: 27 },
  equation: { fontSize: 16, lineHeight: 25, fontWeight: "700" },
  chart: { borderWidth: 1, borderRadius: 14, padding: 12, overflow: "hidden" },
  chartTitle: { fontSize: 15, lineHeight: 22, fontWeight: "700", marginBottom: 4 },
  chartNote: { fontSize: 12, lineHeight: 18, marginTop: 2 },
  link: { minHeight: 48, justifyContent: "center" },
  linkText: { fontSize: 16, fontWeight: "700", flexShrink: 1 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  primary: { minHeight: 54, paddingHorizontal: 24, paddingVertical: 16, borderRadius: 14, alignItems: "center", flexGrow: 1 },
  primaryText: { color: "#FFFFFF", fontWeight: "700", fontSize: 16 },
  secondary: { minHeight: 54, borderWidth: 1, borderRadius: 14, paddingHorizontal: 24, paddingVertical: 16, alignItems: "center", flexGrow: 1 },
});
