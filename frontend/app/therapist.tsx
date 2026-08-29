import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, TextInput, ActivityIndicator, KeyboardAvoidingView, Platform, Modal } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import * as Haptics from "expo-haptics";
import { colors, spacing, radius } from "@/src/theme";
import { authedFetch, getUserId, signOut } from "@/src/auth";
import { API_BASE } from "@/src/config";

const ISSUE_OPTIONS = [
  { code: "REACH_INCOMPLETE", label: "Reduced reach" },
  { code: "SHOULDER_FLEX_LIMITED", label: "Shoulder flexion" },
  { code: "SHOULDER_HIKE", label: "Shoulder hike" },
  { code: "HAND_OPENING", label: "Hand opening" },
  { code: "PINCH_IMPAIRED", label: "Pinch / fine motor" },
  { code: "H2M_IMPAIRED", label: "Hand-to-mouth" },
  { code: "GROSS_GRASP", label: "Gross grasp" },
  { code: "BILATERAL_NONUSE", label: "Bilateral coord." },
  { code: "TRUNK_COMP", label: "Trunk compensation" },
];

export default function TherapistPortal() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [step, setStep] = useState<"loading" | "onboard" | "dashboard">("loading");
  const [questions, setQuestions] = useState<any[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [specialties, setSpecialties] = useState<string[]>([]);
  const [me, setMe] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const [patients, setPatients] = useState<any[]>([]);
  const [reviewPatient, setReviewPatient] = useState<any | null>(null);
  const [signingOff, setSigningOff] = useState(false);

  const load = async () => {
    const uid = await getUserId();
    if (!uid) { router.replace("/sign-in"); return; }
    try {
      const r = await authedFetch("/api/therapist/me");
      if (r.ok) {
        const d = await r.json();
        setMe(d);
        if (d.profile) { setStep("dashboard"); void loadPatients(); } else setStep("onboard");
      } else if (r.status === 400) {
        router.replace("/sign-in"); // not a therapist account
      }
    } catch {/* */}
    if (step === "loading" || step === "onboard") {
      const q = await fetch(`${API_BASE}/api/therapist/onboarding/questions`).then((x) => x.json());
      setQuestions(q.questions || []);
      setStep((s) => (s === "loading" ? "onboard" : s));
    }
  };

  useEffect(() => { load(); }, []);

  const toggleSpec = (c: string) => {
    setSpecialties((s) => s.includes(c) ? s.filter((x) => x !== c) : [...s, c]);
  };

  const submitOnboard = async () => {
    const uid = await getUserId();
    if (!uid) return;
    if (Object.keys(answers).length < 6 || specialties.length === 0) return;
    setSubmitting(true);
    try {
      const r = await authedFetch("/api/therapist/onboarding/submit", {
        method: "POST",
        body: JSON.stringify({ therapist_user_id: uid, answers, specialties }),
      });
      if (r.ok) {
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
        await load();
        setStep("dashboard");
      }
    } finally { setSubmitting(false); }
  };

  const doSignOut = async () => {
    await signOut();
    router.replace("/sign-in");
  };

  const loadPatients = async () => {
    try {
      const r = await authedFetch("/api/therapist/patients");
      if (r.ok) { const d = await r.json(); setPatients(d.patients || []); }
    } catch {/* */}
  };

  const signOffPlan = async () => {
    if (!reviewPatient?.latest_assessment_id) { setReviewPatient(null); return; }
    setSigningOff(true);
    try {
      const r = await authedFetch(`/api/therapist/patient/${reviewPatient.patient_user_id}/signoff`, {
        method: "POST",
        body: JSON.stringify({ assessment_id: reviewPatient.latest_assessment_id }),
      });
      if (r.ok) { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success); await loadPatients(); setReviewPatient(null); }
    } finally { setSigningOff(false); }
  };

  if (step === "loading") {
    return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brandPrimary} /></View>;
  }

  if (step === "onboard") {
    return (
      <View style={[styles.container, { paddingTop: insets.top + spacing.sm }]}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Therapist onboarding</Text>
          <Pressable onPress={doSignOut} testID="therapist-signout">
            <Ionicons name="log-out" size={22} color={colors.onSurfaceSecondary} />
          </Pressable>
        </View>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: 120 }}>
            <Text style={styles.intro}>
              Your answers train your <Text style={{ color: colors.brandPrimary, fontWeight: "800" }}>AI persona</Text> — a chat experience that reflects your clinical voice for patients in early access. You earn <Text style={{ color: colors.brandPrimary, fontWeight: "800" }}>70% commission</Text> on paid chats, video calls, and in-person sessions.
            </Text>

            <Text style={styles.label}>Your upper-limb specialties</Text>
            <View style={styles.chips}>
              {ISSUE_OPTIONS.map((o) => {
                const active = specialties.includes(o.code);
                return (
                  <Pressable key={o.code} onPress={() => toggleSpec(o.code)} style={[styles.chip, active && styles.chipActive]} testID={`spec-${o.code}`}>
                    <Text style={[styles.chipText, active && { color: "#fff" }]}>{o.label}</Text>
                  </Pressable>
                );
              })}
            </View>

            {questions.map((q) => (
              <View key={q.id} style={styles.qBlock}>
                <Text style={styles.label}>{q.question}</Text>
                <TextInput
                  value={answers[q.id] || ""}
                  onChangeText={(t) => setAnswers((a) => ({ ...a, [q.id]: t }))}
                  placeholder="Your answer…"
                  placeholderTextColor={colors.onSurfaceTertiary}
                  multiline={q.type === "text"}
                  style={[styles.input, q.type === "text" && { minHeight: 70, textAlignVertical: "top" }]}
                  testID={`ans-${q.id}`}
                />
              </View>
            ))}

            <Pressable onPress={submitOnboard} disabled={submitting || specialties.length === 0} style={[styles.submit, (submitting || specialties.length === 0) && { opacity: 0.5 }]} testID="onboard-submit">
              {submitting ? <ActivityIndicator color="#fff" /> : <Text style={styles.submitText}>Create my AI persona</Text>}
            </Pressable>
          </ScrollView>
        </KeyboardAvoidingView>
      </View>
    );
  }

  // Dashboard
  const profile = me?.profile;
  const bookings = me?.bookings || [];
  const totalGBP = ((me?.commission_total_pence || 0) / 100).toFixed(2);
  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.sm }]}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Therapist Portal</Text>
        <Pressable onPress={doSignOut} testID="therapist-signout-2">
          <Ionicons name="log-out" size={22} color={colors.onSurfaceSecondary} />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 32 }}>
        <View style={styles.heroCard}>
          <Text style={styles.heroTitle}>Welcome back, {me?.user?.name}</Text>
          <Text style={styles.heroSub}>Your AI persona is live. Patients can chat with it 24/7.</Text>
        </View>

        <View style={styles.statsRow}>
          <View style={styles.statCard}>
            <Ionicons name="cash" size={20} color={colors.brandPrimary} />
            <Text style={styles.statValue}>£{totalGBP}</Text>
            <Text style={styles.statLabel}>Commissions earned</Text>
          </View>
          <View style={styles.statCard}>
            <Ionicons name="calendar" size={20} color={colors.brandPrimary} />
            <Text style={styles.statValue}>{bookings.length}</Text>
            <Text style={styles.statLabel}>Booked sessions</Text>
          </View>
        </View>

        <Text style={styles.sectionTitle}>Upcoming bookings</Text>
        {bookings.length === 0 && <Text style={styles.muted}>No bookings yet. Patients will book chats, video calls, or in-person sessions with you.</Text>}
        {bookings.map((b: any) => (
          <View key={b.id} style={styles.bookCard} testID={`booking-${b.id}`}>
            <View style={{ flex: 1 }}>
              <Text style={styles.bookKind}>{b.kind.replace("_", " ").toUpperCase()}</Text>
              <Text style={styles.bookName}>{b.patient_name}</Text>
              <Text style={styles.bookSlot}>{new Date(b.slot_iso).toLocaleString()}</Text>
            </View>
            <Text style={styles.bookAmount}>£{(b.amount_pence / 100).toFixed(0)}</Text>
          </View>
        ))}

        <Text style={styles.sectionTitle}>My patients</Text>
        {patients.length === 0 && <Text style={styles.muted}>Patients who connect or book with you appear here with their latest movement summary and plan status.</Text>}
        {patients.map((p) => (
          <View key={p.patient_user_id} style={styles.patientCard} testID={`patient-${p.patient_user_id}`}>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={styles.patientName}>{p.name}</Text>
              <Text style={styles.patientMeta}>{p.last_assessment_date ? `Last assessment ${new Date(p.last_assessment_date).toLocaleDateString()}` : "No assessment yet"} · {p.issues_count} finding{p.issues_count === 1 ? "" : "s"} · {p.exercises_count} exercises</Text>
              {p.plan_signed
                ? <View style={styles.signedRow}><Ionicons name="checkmark-circle" size={15} color={colors.success} /><Text style={styles.signedText}>Plan signed off</Text></View>
                : <Text style={styles.pendingText}>Awaiting your review</Text>}
            </View>
            <Pressable onPress={() => setReviewPatient(p)} disabled={!p.latest_assessment_id} style={[styles.reviewBtn, !p.latest_assessment_id && { opacity: 0.4 }]} testID={`patient-review-${p.patient_user_id}`}>
              <Text style={styles.reviewBtnText}>{p.plan_signed ? "View" : "Review"}</Text>
            </Pressable>
          </View>
        ))}

        <Text style={styles.sectionTitle}>Your AI persona</Text>
        <View style={styles.personaCard}>
          <Ionicons name="sparkles" size={20} color={colors.brandSecondary} />
          <Text style={styles.personaText}>
            Trained on your responses · {profile?.specialties?.length || 0} specialties · {profile?.commission_pct}% commission per booking
          </Text>
        </View>
      </ScrollView>

      <Modal visible={!!reviewPatient} transparent animationType="fade" onRequestClose={() => setReviewPatient(null)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard} testID="patient-review-modal">
            <Text style={styles.modalTitle}>{reviewPatient?.name}</Text>
            <Text style={styles.modalMeta}>{reviewPatient?.last_assessment_date ? new Date(reviewPatient.last_assessment_date).toLocaleDateString() : ""}</Text>
            <View style={styles.modalStats}>
              <View style={styles.modalStat}><Text style={styles.modalStatValue}>{reviewPatient?.issues_count ?? 0}</Text><Text style={styles.modalStatLabel}>Findings</Text></View>
              <View style={styles.modalStat}><Text style={styles.modalStatValue}>{reviewPatient?.exercises_count ?? 0}</Text><Text style={styles.modalStatLabel}>Exercises</Text></View>
            </View>
            <Text style={styles.modalNote}>Confirm you have reviewed this patient&apos;s latest movement summary and approve their guided exercise plan.</Text>
            <View style={styles.modalActions}>
              <Pressable onPress={() => setReviewPatient(null)} style={styles.modalCancel} testID="patient-review-close"><Text style={styles.modalCancelText}>Close</Text></Pressable>
              {!reviewPatient?.plan_signed && (
                <Pressable onPress={signOffPlan} disabled={signingOff} style={styles.modalSign} testID="patient-signoff-confirm">
                  {signingOff ? <ActivityIndicator color="#fff" /> : <Text style={styles.modalSignText}>Sign off plan</Text>}
                </Pressable>
              )}
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.divider },
  headerTitle: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  intro: { fontSize: 14, color: colors.onSurfaceSecondary, lineHeight: 20, marginBottom: spacing.sm },
  label: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: 6 },
  qBlock: { gap: 6 },
  input: { backgroundColor: colors.surfaceSecondary, padding: spacing.md, borderRadius: radius.md, fontSize: 15, color: colors.onSurface },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: { backgroundColor: colors.surfaceTertiary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: radius.pill },
  chipActive: { backgroundColor: colors.brandPrimary },
  chipText: { color: colors.onSurfaceSecondary, fontSize: 12, fontWeight: "700" },
  submit: { backgroundColor: colors.brandPrimary, padding: 16, borderRadius: radius.lg, alignItems: "center", marginTop: spacing.md },
  submitText: { color: "#fff", fontWeight: "800", fontSize: 16 },
  heroCard: { backgroundColor: colors.brandTertiary, padding: spacing.md, borderRadius: radius.lg, marginBottom: spacing.md, gap: 4 },
  heroTitle: { fontSize: 18, fontWeight: "800", color: colors.onBrandTertiary },
  heroSub: { fontSize: 13, color: colors.onBrandTertiary },
  statsRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  statCard: { flex: 1, backgroundColor: colors.surfaceSecondary, padding: spacing.md, borderRadius: radius.lg, gap: 4 },
  statValue: { fontSize: 22, fontWeight: "800", color: colors.onSurface },
  statLabel: { fontSize: 12, color: colors.onSurfaceTertiary },
  sectionTitle: { fontSize: 18, fontWeight: "800", color: colors.onSurface, marginTop: spacing.md, marginBottom: spacing.sm },
  muted: { color: colors.onSurfaceTertiary, fontStyle: "italic" },
  bookCard: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surfaceSecondary, padding: spacing.md, borderRadius: radius.lg, marginBottom: spacing.sm },
  bookKind: { fontSize: 10, fontWeight: "800", letterSpacing: 1, color: colors.brandPrimary },
  bookName: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginTop: 2 },
  bookSlot: { fontSize: 12, color: colors.onSurfaceTertiary },
  bookAmount: { fontSize: 18, fontWeight: "800", color: colors.brandPrimary },
  personaCard: { flexDirection: "row", gap: 10, alignItems: "center", backgroundColor: colors.surfaceSecondary, padding: spacing.md, borderRadius: radius.lg },
  personaText: { flex: 1, color: colors.onSurfaceSecondary, fontSize: 13 },
  patientCard: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, padding: spacing.md, borderRadius: radius.lg, marginBottom: spacing.sm },
  patientName: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  patientMeta: { fontSize: 12, lineHeight: 17, color: colors.onSurfaceTertiary, marginTop: 3 },
  signedRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 5 },
  signedText: { fontSize: 12, fontWeight: "800", color: colors.success },
  pendingText: { fontSize: 12, fontWeight: "800", color: colors.warning, marginTop: 5 },
  reviewBtn: { minHeight: 40, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  reviewBtnText: { color: "#fff", fontSize: 13, fontWeight: "800" },
  modalBackdrop: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.lg, backgroundColor: "rgba(10,22,16,0.6)" },
  modalCard: { width: "100%", maxWidth: 440, borderRadius: radius.lg, backgroundColor: colors.surface, padding: spacing.lg },
  modalTitle: { fontSize: 20, fontWeight: "800", color: colors.onSurface },
  modalMeta: { fontSize: 13, color: colors.onSurfaceTertiary, marginTop: 2 },
  modalStats: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  modalStat: { flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, alignItems: "center" },
  modalStatValue: { fontSize: 24, fontWeight: "800", color: colors.onSurface },
  modalStatLabel: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 2 },
  modalNote: { fontSize: 13, lineHeight: 19, color: colors.onSurfaceSecondary, marginTop: spacing.md },
  modalActions: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.lg },
  modalCancel: { minHeight: 46, minWidth: 90, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border },
  modalCancelText: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  modalSign: { minHeight: 46, minWidth: 130, alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.md, borderRadius: radius.md, backgroundColor: colors.brandPrimary },
  modalSignText: { color: "#fff", fontSize: 15, fontWeight: "800" },
});
