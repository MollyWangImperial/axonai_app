import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, useWindowDimensions, View } from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import {
  AssessmentPackageId,
  fetchTestingLibrary,
  TestingAssessmentPackage,
  TestingAssessmentTask,
  TestingExercise,
  TestingLibrary,
} from "@/src/api";
import { getCachedPatientProfile, getUserId } from "@/src/auth";
import { useDisplayPreferences } from "@/src/displayPreferences";
import { colors, radius, spacing } from "@/src/theme";
import { loadUserPreferences, textScaleFor } from "@/src/userPreferences";

type LibraryMode = "assessments" | "exercises";
type AffectedSide = "left" | "right";

const packageIcons: Record<string, keyof typeof Ionicons.glyphMap> = {
  upper_limb: "body-outline",
  hand: "hand-left-outline",
  lower_limb: "walk-outline",
  balance: "accessibility-outline",
};

export default function TestingLibraryScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { width } = useWindowDimensions();
  const { palette } = useDisplayPreferences();
  const [library, setLibrary] = useState<TestingLibrary | null>(null);
  const [mode, setMode] = useState<LibraryMode>("assessments");
  const [affectedSide, setAffectedSide] = useState<AffectedSide>("right");
  const [scale, setScale] = useState(1);
  const [error, setError] = useState("");
  const isWide = width >= 760;

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const [payload, preferences, userId] = await Promise.all([
          fetchTestingLibrary(),
          loadUserPreferences(),
          getUserId(),
        ]);
        const profile = userId ? await getCachedPatientProfile(userId) : null;
        if (!active) return;
        setLibrary(payload);
        setScale(textScaleFor(preferences.textSize));
        if (profile?.side_affected === "left" || profile?.side_affected === "right") {
          setAffectedSide(profile.side_affected);
        }
      } catch (reason) {
        if (active) setError(reason instanceof Error ? reason.message : "Could not load the testing library");
      }
    })();
    return () => { active = false; };
  }, []);

  const startAssessmentTask = (packageId: AssessmentPackageId, task: TestingAssessmentTask) => {
    router.push({
      pathname: "/assessment",
      params: {
        package: packageId,
        start_task: task.id,
        task_ids: task.id,
        affected_side: affectedSide,
        library_test: "1",
      },
    });
  };

  const startExercise = (exercise: TestingExercise) => {
    router.push({
      pathname: "/exercise",
      params: {
        exercise_id: exercise.id,
        name: exercise.name,
        plan_id: "library-test",
        sets: "1",
        reps: String(exercise.guided_reps),
        library_test: "1",
      },
    });
  };

  return (
    <View style={[styles.container, { backgroundColor: palette.page }]}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.xs, borderBottomColor: palette.border }]}>
        <Pressable accessibilityLabel="Back to Settings" onPress={() => router.back()} style={styles.headerButton}>
          <Ionicons name="arrow-back" size={24} color={palette.text} />
        </Pressable>
        <Text style={[styles.headerTitle, { color: palette.text, fontSize: 19 * scale }]}>Testing library</Text>
        <View style={styles.headerButton} />
      </View>

      {!library && !error ? (
        <View style={styles.center}>
          <ActivityIndicator color={palette.brand} />
          <Text style={[styles.loadingText, { color: palette.muted }]}>Loading guided items...</Text>
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Ionicons name="alert-circle-outline" size={42} color={colors.error} />
          <Text style={[styles.errorText, { color: palette.text }]}>{error}</Text>
          <Pressable onPress={() => router.back()} style={[styles.returnButton, { backgroundColor: palette.brand }]}>
            <Text style={styles.returnButtonText}>Back to Settings</Text>
          </Pressable>
        </View>
      ) : library ? (
        <ScrollView contentContainerStyle={[styles.content, isWide && styles.contentWide]} showsVerticalScrollIndicator={false}>
          <View style={styles.intro}>
            <Text style={[styles.title, { color: palette.text, fontSize: 28 * scale, lineHeight: 34 * scale }]}>Test guided activities</Text>
            <Text style={[styles.subtitle, { color: palette.muted, fontSize: 14 * scale, lineHeight: 21 * scale }]}>Open one item at a time. Test runs are kept separate from the patient record.</Text>
          </View>

          <View style={[styles.notice, { backgroundColor: palette.soft, borderColor: palette.border }]}>
            <Ionicons name="shield-checkmark-outline" size={23} color={palette.brand} />
            <Text style={[styles.noticeText, { color: palette.text }]}>Nothing tested here is added to Assessment history, Progress, or the daily exercise plan.</Text>
          </View>

          <View style={[styles.modeControl, { backgroundColor: palette.soft, borderColor: palette.border }]}>
            <ModeButton
              active={mode === "assessments"}
              icon="videocam-outline"
              label={isWide ? "Assessment tasks" : "Tasks"}
              count={library.assessment_task_count}
              onPress={() => setMode("assessments")}
              palette={palette}
            />
            <ModeButton
              active={mode === "exercises"}
              icon="fitness-outline"
              label="Exercises"
              count={library.exercise_count}
              onPress={() => setMode("exercises")}
              palette={palette}
            />
          </View>

          {mode === "assessments" ? (
            <>
              <View style={styles.sideRow}>
                <View>
                  <Text style={[styles.sideLabel, { color: palette.text }]}>Affected side</Text>
                  <Text style={[styles.sideHint, { color: palette.muted }]}>Used by the camera targets</Text>
                </View>
                <View style={[styles.sideControl, { borderColor: palette.border, backgroundColor: palette.surface }]}>
                  {(["left", "right"] as AffectedSide[]).map((side) => (
                    <Pressable
                      key={side}
                      accessibilityRole="button"
                      accessibilityState={{ selected: affectedSide === side }}
                      onPress={() => setAffectedSide(side)}
                      style={[styles.sideButton, affectedSide === side && { backgroundColor: palette.brand }]}
                      testID={`testing-side-${side}`}
                    >
                      <Text style={[styles.sideButtonText, { color: affectedSide === side ? "#FFFFFF" : palette.text }]}>{side === "left" ? "Left" : "Right"}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>
              {library.assessment_packages.map((item) => (
                <AssessmentPackageSection
                  key={item.id}
                  item={item}
                  isWide={isWide}
                  scale={scale}
                  palette={palette}
                  onStart={(task) => startAssessmentTask(item.id, task)}
                />
              ))}
            </>
          ) : (
            <View style={[styles.itemGrid, isWide && styles.itemGridWide]}>
              {library.exercises.map((exercise) => (
                <ExerciseRow
                  key={exercise.id}
                  exercise={exercise}
                  isWide={isWide}
                  scale={scale}
                  palette={palette}
                  onStart={() => startExercise(exercise)}
                />
              ))}
            </View>
          )}
        </ScrollView>
      ) : null}
    </View>
  );
}

function ModeButton({ active, icon, label, count, onPress, palette }: {
  active: boolean;
  icon: keyof typeof Ionicons.glyphMap;
  label: string;
  count: number;
  onPress: () => void;
  palette: ReturnType<typeof useDisplayPreferences>["palette"];
}) {
  return (
    <Pressable accessibilityRole="tab" accessibilityState={{ selected: active }} onPress={onPress} style={[styles.modeButton, active && { backgroundColor: palette.brand }]}>
      <Ionicons name={icon} size={20} color={active ? "#FFFFFF" : palette.text} />
      <Text numberOfLines={1} style={[styles.modeLabel, { color: active ? "#FFFFFF" : palette.text }]}>{label}</Text>
      <View style={[styles.countBadge, { backgroundColor: active ? "rgba(255,255,255,0.2)" : palette.surface }]}>
        <Text style={[styles.countText, { color: active ? "#FFFFFF" : palette.text }]}>{count}</Text>
      </View>
    </Pressable>
  );
}

function AssessmentPackageSection({ item, isWide, scale, palette, onStart }: {
  item: TestingAssessmentPackage;
  isWide: boolean;
  scale: number;
  palette: ReturnType<typeof useDisplayPreferences>["palette"];
  onStart: (task: TestingAssessmentTask) => void;
}) {
  return (
    <View style={styles.section}>
      <View style={styles.sectionHeading}>
        <View style={[styles.sectionIcon, { backgroundColor: palette.soft }]}><Ionicons name={packageIcons[item.id] || "body-outline"} size={22} color={palette.brand} /></View>
        <View style={styles.sectionCopy}>
          <Text style={[styles.sectionTitle, { color: palette.text, fontSize: 18 * scale }]}>{item.title}</Text>
          <Text style={[styles.sectionCount, { color: palette.muted }]}>{item.tasks.length} tasks</Text>
        </View>
      </View>
      <View style={[styles.itemGrid, isWide && styles.itemGridWide]}>
        {item.tasks.map((task) => (
          <TaskRow key={task.id} task={task} isWide={isWide} scale={scale} palette={palette} onStart={() => onStart(task)} />
        ))}
      </View>
    </View>
  );
}

function TaskRow({ task, isWide, scale, palette, onStart }: {
  task: TestingAssessmentTask;
  isWide: boolean;
  scale: number;
  palette: ReturnType<typeof useDisplayPreferences>["palette"];
  onStart: () => void;
}) {
  const needsSupport = task.safety_tier === "spotter_required";
  return (
    <View style={[styles.itemCard, isWide && styles.itemCardWide, { backgroundColor: palette.surface, borderColor: palette.border }]} testID={`testing-task-${task.id}`}>
      <View style={styles.itemTopRow}>
        <View style={[styles.idBadge, { backgroundColor: palette.soft }]}><Text style={[styles.idText, { color: palette.brand }]}>{task.id}</Text></View>
        {needsSupport ? <StatusPill icon="people-outline" label="Support needed" tone="warning" /> : <StatusPill icon="checkmark-circle-outline" label="Seated" tone="safe" />}
      </View>
      <Text style={[styles.itemTitle, { color: palette.text, fontSize: 17 * scale, lineHeight: 22 * scale }]}>{task.title}</Text>
      <Text numberOfLines={2} style={[styles.itemDescription, { color: palette.muted }]}>{task.focus}</Text>
      <View style={styles.metaRow}>
        <Ionicons name="list-outline" size={16} color={palette.muted} />
        <Text style={[styles.metaText, { color: palette.muted }]}>{task.step_count} guided steps</Text>
      </View>
      {task.safety_note ? <Text numberOfLines={2} style={styles.safetyText}>{task.safety_note}</Text> : null}
      <Pressable accessibilityRole="button" onPress={onStart} style={[styles.startButton, { backgroundColor: palette.brand }]} testID={`testing-start-task-${task.id}`}>
        <Ionicons name="play" size={18} color="#FFFFFF" />
        <Text style={styles.startButtonText}>Test task</Text>
      </Pressable>
    </View>
  );
}

function ExerciseRow({ exercise, isWide, scale, palette, onStart }: {
  exercise: TestingExercise;
  isWide: boolean;
  scale: number;
  palette: ReturnType<typeof useDisplayPreferences>["palette"];
  onStart: () => void;
}) {
  return (
    <View style={[styles.itemCard, isWide && styles.itemCardWide, { backgroundColor: palette.surface, borderColor: palette.border }]} testID={`testing-exercise-${exercise.id}`}>
      <View style={styles.itemTopRow}>
        <View style={[styles.exerciseIcon, { backgroundColor: palette.soft }]}><Ionicons name={exercise.pose_mode === "tap" ? "hand-left-outline" : "fitness-outline"} size={20} color={palette.brand} /></View>
        <StatusPill icon={exercise.support_required ? "people-outline" : "sparkles-outline"} label={exercise.support_required ? "Support needed" : "Guided"} tone={exercise.support_required ? "warning" : "safe"} />
      </View>
      <Text style={[styles.itemTitle, { color: palette.text, fontSize: 17 * scale, lineHeight: 22 * scale }]}>{exercise.name}</Text>
      <Text numberOfLines={3} style={[styles.itemDescription, { color: palette.muted }]}>{exercise.description}</Text>
      <View style={styles.metaRow}>
        <Ionicons name="repeat-outline" size={16} color={palette.muted} />
        <Text style={[styles.metaText, { color: palette.muted }]}>{exercise.guided_reps} guided reps | {exercise.frequency}</Text>
      </View>
      <Pressable accessibilityRole="button" onPress={onStart} style={[styles.startButton, { backgroundColor: palette.brand }]} testID={`testing-start-exercise-${exercise.id}`}>
        <Ionicons name="play" size={18} color="#FFFFFF" />
        <Text style={styles.startButtonText}>Test exercise</Text>
      </Pressable>
    </View>
  );
}

function StatusPill({ icon, label, tone }: { icon: keyof typeof Ionicons.glyphMap; label: string; tone: "safe" | "warning" }) {
  const strong = tone === "warning" ? "#A86212" : "#34794B";
  const soft = tone === "warning" ? "#FFF4E2" : "#EAF5EC";
  return <View style={[styles.statusPill, { backgroundColor: soft }]}><Ionicons name={icon} size={14} color={strong} /><Text style={[styles.statusText, { color: strong }]}>{label}</Text></View>;
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { minHeight: 64, paddingHorizontal: spacing.sm, paddingBottom: spacing.xs, borderBottomWidth: 1, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  headerButton: { width: 46, height: 44, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontWeight: "800", textAlign: "center" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.xl },
  loadingText: { fontSize: 14 },
  errorText: { maxWidth: 440, fontSize: 16, lineHeight: 23, textAlign: "center" },
  returnButton: { minHeight: 50, minWidth: 180, paddingHorizontal: spacing.lg, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  returnButtonText: { color: "#FFFFFF", fontSize: 15, fontWeight: "800" },
  content: { width: "100%", maxWidth: 760, alignSelf: "center", padding: spacing.md, paddingBottom: 56, gap: spacing.md },
  contentWide: { maxWidth: 1080, paddingHorizontal: spacing.xl },
  intro: { gap: 4, paddingTop: spacing.xs },
  title: { fontWeight: "900" },
  subtitle: { maxWidth: 680 },
  notice: { minHeight: 62, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderWidth: 1, borderRadius: radius.sm, flexDirection: "row", alignItems: "center", gap: spacing.sm },
  noticeText: { flex: 1, fontSize: 13, lineHeight: 19, fontWeight: "600" },
  modeControl: { height: 58, padding: 4, borderWidth: 1, borderRadius: radius.sm, flexDirection: "row", gap: 4 },
  modeButton: { flex: 1, minWidth: 0, paddingHorizontal: spacing.sm, borderRadius: 6, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs },
  modeLabel: { minWidth: 0, fontSize: 14, fontWeight: "800" },
  countBadge: { minWidth: 28, height: 24, paddingHorizontal: 6, borderRadius: 12, alignItems: "center", justifyContent: "center" },
  countText: { fontSize: 12, fontWeight: "900" },
  sideRow: { minHeight: 64, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  sideLabel: { fontSize: 15, fontWeight: "800" },
  sideHint: { marginTop: 2, fontSize: 12 },
  sideControl: { width: 176, height: 44, padding: 3, borderWidth: 1, borderRadius: radius.sm, flexDirection: "row" },
  sideButton: { flex: 1, borderRadius: 5, alignItems: "center", justifyContent: "center" },
  sideButtonText: { fontSize: 14, fontWeight: "800" },
  section: { gap: spacing.sm, paddingTop: spacing.sm },
  sectionHeading: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  sectionIcon: { width: 42, height: 42, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  sectionCopy: { flex: 1, minWidth: 0 },
  sectionTitle: { fontWeight: "800" },
  sectionCount: { marginTop: 1, fontSize: 12, fontWeight: "600" },
  itemGrid: { gap: spacing.sm },
  itemGridWide: { flexDirection: "row", flexWrap: "wrap" },
  itemCard: { minHeight: 262, padding: spacing.md, borderWidth: 1, borderRadius: radius.sm, gap: spacing.xs },
  itemCardWide: { width: "48.8%" },
  itemTopRow: { minHeight: 34, flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  idBadge: { minWidth: 42, height: 30, paddingHorizontal: spacing.xs, borderRadius: 6, alignItems: "center", justifyContent: "center" },
  idText: { fontSize: 13, fontWeight: "900" },
  exerciseIcon: { width: 34, height: 34, borderRadius: 17, alignItems: "center", justifyContent: "center" },
  statusPill: { minHeight: 28, paddingHorizontal: spacing.xs, borderRadius: 14, flexDirection: "row", alignItems: "center", gap: 4 },
  statusText: { fontSize: 11, fontWeight: "800" },
  itemTitle: { marginTop: 4, fontWeight: "800" },
  itemDescription: { minHeight: 40, fontSize: 13, lineHeight: 19 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 5 },
  metaText: { flex: 1, fontSize: 12, lineHeight: 17, fontWeight: "600" },
  safetyText: { color: "#95560B", fontSize: 12, lineHeight: 17 },
  startButton: { minHeight: 48, marginTop: "auto", borderRadius: radius.sm, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs },
  startButtonText: { color: "#FFFFFF", fontSize: 15, fontWeight: "800" },
});
