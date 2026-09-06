import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { AssessmentTaskQuality } from "@/src/api";
import { useDisplayPreferences } from "@/src/displayPreferences";

function measurement(value: number | null, unit: string) {
  if (value === null) return "Not measured";
  return `${Math.round(value * (unit === "ratio" ? 100 : 1))}${unit === "ratio" ? "%" : unit === "deg" ? " degrees" : ""}`;
}

export function AssessmentTaskStatistics({ quality }: { quality?: AssessmentTaskQuality }) {
  const { palette } = useDisplayPreferences();
  const [expanded, setExpanded] = useState<string | null>(null);
  if (!quality?.tasks.length) return null;
  return (
    <View style={styles.section} testID="assessment-task-statistics">
      <Text style={[styles.heading, { color: palette.text }]}>Assessment task statistics</Text>
      {quality.tasks.map(task => {
        const open = expanded === task.task_id;
        return <View key={task.task_id} style={[styles.task, { borderColor: palette.border }]}>
          <Pressable onPress={() => setExpanded(open ? null : task.task_id)} accessibilityRole="button" accessibilityState={{ expanded: open }} style={styles.toggle} testID={`task-statistics-${task.task_id}`}>
            <View style={styles.copy}>
              <Text style={[styles.title, { color: palette.text }]}>{task.label}</Text>
              <Text style={[styles.body, { color: palette.muted }]}>{task.score === null ? "Not fully measured" : `${task.score}/100`} · {task.measured_steps}/{task.total_steps} steps measured</Text>
              <Text style={[styles.body, { color: palette.muted }]}>{task.earned_module_points ?? "-"} / {task.module_weight} module points{task.assisted ? " · Assisted" : ""}</Text>
              {task.steps.some(step => step.status === "limited_view") && <Text style={[styles.body, { color: palette.muted }]}>Limited camera view for some posture checks</Text>}
            </View>
            <Ionicons name={open ? "chevron-up" : "chevron-down"} size={24} color={palette.text} />
          </Pressable>
          {open && task.steps.map(step => <View key={step.step_id} style={[styles.step, { borderColor: palette.border }]}>
            <Text style={[styles.title, { color: palette.text }]}>{step.label}</Text>
            <Text style={[styles.body, { color: palette.muted }]}>{step.score === null ? "Not measured" : `${step.score}/100`} · {(step.duration_ms / 1000).toFixed(1)} s · {step.completed ? "Target reached" : "Target not reached"}</Text>
            {step.criteria.map(rule => <Text key={rule.metric} style={[styles.body, { color: palette.text }]}>{rule.label}: {measurement(rule.observed, rule.unit)} · Reference {measurement(rule.target, rule.unit)}</Text>)}
            {step.compensations.map(check => <View key={check.id} style={check.status === "detected" ? styles.warning : undefined}>
              <Text style={[styles.body, { color: check.status === "detected" ? palette.text : palette.muted }]}>{check.label}: {check.status === "detected" ? "Observed" : check.status === "not_measured" ? "Not measured in this view" : "Not detected"}</Text>
              {check.status === "detected" && <Text style={[styles.body, { color: palette.text }]}>{check.cue}</Text>}
            </View>)}
          </View>)}
        </View>;
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { marginBottom: 24 },
  heading: { fontSize: 24, lineHeight: 31, fontWeight: "800", marginBottom: 12 },
  task: { borderBottomWidth: 1 },
  toggle: { flexDirection: "row", alignItems: "center", paddingVertical: 16, gap: 12, minHeight: 48 },
  copy: { flex: 1, minWidth: 0 },
  title: { fontSize: 18, lineHeight: 25, fontWeight: "700" },
  body: { fontSize: 15, lineHeight: 22, marginTop: 4 },
  step: { borderTopWidth: 1, paddingVertical: 14, paddingHorizontal: 8, gap: 4 },
  warning: { borderLeftWidth: 3, borderStyle: "dotted", borderColor: "#C94242", paddingLeft: 10, marginTop: 8 },
});
