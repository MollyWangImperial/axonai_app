import { useEffect, useState } from "react";
import { View, Text, StyleSheet, Pressable, ScrollView, TextInput, ActivityIndicator, KeyboardAvoidingView, Platform } from "react-native";
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

  const load = async () => {
    const uid = await getUserId();
    if (!uid) { router.replace("/sign-in"); return; }
    try {
      const r = await authedFetch("/api/therapist/me");
      if (r.ok) {
        const d = await r.json();
        setMe(d);
        if (d.profile) setStep("dashboard"); else setStep("onboard");
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

  if (step === "loading") {
    return <View style={[styles.container, styles.center]}><ActivityIndicator color={colors.brandPrimary} /></View>;
  }

  if (step === "onboard") {
    return (
      <View style={[styles.container, { paddingTop: insets.top + spacing.sm }]}>
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Therapist onboarding</Text>
          <Pressable onPress={doSignOut} style={styles.iconButton} testID="therapist-signout">
            <Ionicons name="log-out" size={22} color="#385342" />
          </Pressable>
        </View>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
          <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: 120 }}>
            <Text style={styles.intro}>
              Your answers train your <Text style={{ color: "#244436", fontWeight: "800" }}>AI persona</Text> — a chat experience that reflects your clinical voice for patients in early access. You earn <Text style={{ color: "#244436", fontWeight: "800" }}>70% commission</Text> on paid chats, video calls, and in-person sessions.
            </Text>

            <Text style={styles.label}>Your upper-limb specialties</Text>
            <View style={styles.chips}>
              {ISSUE_OPTIONS.map((o) => {
                const active = specialties.includes(o.code);
                return (
                  <Pressable key={o.code} onPress={() => toggleSpec(o.code)} style={[styles.chip, active && styles.chipActive]} testID={`spec-${o.code}`}>
                    <Text style={[styles.chipText, active && { color: "#FFFDF5" }]}>{o.label}</Text>
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
                  placeholderTextColor="#738274"
                  multiline={q.type === "text"}
                  style={[styles.input, q.type === "text" && { minHeight: 108, textAlignVertical: "top" }]}
                  testID={`ans-${q.id}`}
                />
              </View>
            ))}

            <Pressable onPress={submitOnboard} disabled={submitting || specialties.length === 0} style={[styles.submit, (submitting || specialties.length === 0) && { opacity: 0.5 }]} testID="onboard-submit">
              {submitting ? <ActivityIndicator color="#FFFDF5" /> : <Text style={styles.submitText}>Create my AI persona</Text>}
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
        <Pressable onPress={doSignOut} style={styles.iconButton} testID="therapist-signout-2">
          <Ionicons name="log-out" size={22} color="#385342" />
        </Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: spacing.lg, paddingBottom: 32 }}>
        <View style={styles.heroCard}>
          <Text style={styles.heroTitle}>Welcome back, {me?.user?.name}</Text>
          <Text style={styles.heroSub}>Your AI persona is live. Patients can chat with it 24/7.</Text>
        </View>

        <View style={styles.statsRow}>
          <View style={styles.statCard}>
            <Ionicons name="cash" size={20} color="#315440" />
            <Text style={styles.statValue}>£{totalGBP}</Text>
            <Text style={styles.statLabel}>Commissions earned</Text>
          </View>
          <View style={styles.statCard}>
            <Ionicons name="calendar" size={20} color="#315440" />
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

        <Text style={styles.sectionTitle}>Your AI persona</Text>
        <View style={styles.personaCard}>
          <Ionicons name="sparkles" size={20} color="#6E875E" />
          <Text style={styles.personaText}>
            Trained on your responses · {profile?.specialties?.length || 0} specialties · {profile?.commission_pct}% commission per booking
          </Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F7F4EB" },
  center: { alignItems: "center", justifyContent: "center" },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", minHeight: 60, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm, backgroundColor: "#FCFAF3", borderBottomWidth: 1, borderBottomColor: "#D7E1D2" },
  headerTitle: { fontSize: 22, fontWeight: "800", color: "#1F3D30", letterSpacing: -0.2 },
  iconButton: { width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: "#E8F0E4" },
  intro: { fontSize: 17, color: "#40554A", lineHeight: 25, marginBottom: spacing.sm },
  label: { fontSize: 16, fontWeight: "800", color: "#294738", lineHeight: 22, marginBottom: 7 },
  qBlock: { gap: 7 },
  input: { backgroundColor: "#FFFEFA", borderWidth: 1, borderColor: "#CCD9C7", minHeight: 54, paddingHorizontal: spacing.md, paddingVertical: 13, borderRadius: radius.md, fontSize: 17, lineHeight: 23, color: "#23382C" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chip: { backgroundColor: "#E7EEE3", borderWidth: 1, borderColor: "#D2DDD0", minHeight: 44, paddingHorizontal: 14, paddingVertical: 9, borderRadius: radius.pill, justifyContent: "center" },
  chipActive: { backgroundColor: "#315440", borderColor: "#315440" },
  chipText: { color: "#385342", fontSize: 15, fontWeight: "700" },
  submit: { backgroundColor: "#315440", minHeight: 54, paddingHorizontal: 16, paddingVertical: 12, borderRadius: radius.lg, alignItems: "center", justifyContent: "center", marginTop: spacing.md, shadowColor: "#183326", shadowOpacity: 0.16, shadowRadius: 6, shadowOffset: { width: 0, height: 3 }, elevation: 2 },
  submitText: { color: "#FFFDF5", fontWeight: "800", fontSize: 17 },
  heroCard: { backgroundColor: "#DCE8D7", borderWidth: 1, borderColor: "#C4D5BD", padding: spacing.lg, borderRadius: radius.lg, marginBottom: spacing.lg, gap: 6 },
  heroTitle: { fontSize: 20, fontWeight: "800", color: "#214333" },
  heroSub: { fontSize: 16, lineHeight: 23, color: "#385342" },
  statsRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg },
  statCard: { flex: 1, backgroundColor: "#FFFEFA", borderWidth: 1, borderColor: "#DCE5D7", padding: spacing.md, borderRadius: radius.lg, gap: 5 },
  statValue: { fontSize: 24, fontWeight: "800", color: "#214333" },
  statLabel: { fontSize: 14, lineHeight: 19, color: "#5B6F61" },
  sectionTitle: { fontSize: 20, fontWeight: "800", color: "#214333", marginTop: spacing.lg, marginBottom: spacing.sm },
  muted: { color: "#5B6F61", fontSize: 16, lineHeight: 23, fontStyle: "italic" },
  bookCard: { flexDirection: "row", alignItems: "center", backgroundColor: "#FFFEFA", borderWidth: 1, borderColor: "#DCE5D7", padding: spacing.md, borderRadius: radius.lg, marginBottom: spacing.sm },
  bookKind: { fontSize: 12, fontWeight: "800", letterSpacing: 0.9, color: "#52705B" },
  bookName: { fontSize: 17, fontWeight: "800", color: "#294738", marginTop: 3 },
  bookSlot: { fontSize: 15, lineHeight: 21, color: "#5B6F61", marginTop: 2 },
  bookAmount: { fontSize: 20, fontWeight: "800", color: "#315440" },
  personaCard: { flexDirection: "row", gap: 11, alignItems: "center", backgroundColor: "#EEF4EA", borderWidth: 1, borderColor: "#D4E0CE", padding: spacing.md, borderRadius: radius.lg },
  personaText: { flex: 1, color: "#40554A", fontSize: 16, lineHeight: 23 },
});
