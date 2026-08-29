import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";

import { colors, radius, spacing } from "@/src/theme";
import { storage } from "@/src/utils/storage";

type SessionActor = "patient" | "carer";

export default function SessionCheckScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const params = useLocalSearchParams<{ target?: string; id?: string; mode?: string }>();
  const [actor, setActor] = useState<SessionActor | null>(null);
  const [safetyAck, setSafetyAck] = useState(false);

  const continueToSession = async () => {
    if (!actor || !safetyAck) return;
    await storage.setItem("current_session_actor_v1", actor);
    Haptics.selectionAsync();
    if (params.target === "rehab" && params.id) {
      router.replace({ pathname: "/rehab-plan", params: { id: params.id, session_actor: actor } });
      return;
    }
    router.replace({ pathname: "/task-intro", params: { mode: params.mode || "initial", session_actor: actor } });
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top + spacing.md, paddingBottom: Math.max(insets.bottom, spacing.lg) }]}>
      <Pressable onPress={() => router.back()} style={styles.backButton} accessibilityLabel="Go back">
        <Ionicons name="chevron-back" size={25} color={colors.onSurface} />
      </Pressable>
      <View style={styles.content}>
        <View style={styles.icon}><Ionicons name="people-outline" size={30} color={colors.brandPrimary} /></View>
        <Text style={styles.title}>Who is starting this session?</Text>
        <Text style={styles.subtitle}>This helps Alira give the right instructions and keeps the session record clear.</Text>
        <View style={styles.options}>
          <Pressable testID="session-actor-patient" onPress={() => setActor("patient")} style={[styles.option, actor === "patient" && styles.optionActive]}>
            <Ionicons name="person" size={25} color={actor === "patient" ? colors.brandPrimary : colors.onSurfaceSecondary} />
            <View style={{ flex: 1 }}><Text style={styles.optionTitle}>I am the patient</Text><Text style={styles.optionBody}>I will follow the guidance and complete the session.</Text></View>
            {actor === "patient" && <Ionicons name="checkmark-circle" size={23} color={colors.brandPrimary} />}
          </Pressable>
          <Pressable testID="session-actor-carer" onPress={() => setActor("carer")} style={[styles.option, actor === "carer" && styles.optionActive]}>
            <Ionicons name="heart" size={25} color={actor === "carer" ? colors.brandPrimary : colors.onSurfaceSecondary} />
            <View style={{ flex: 1 }}><Text style={styles.optionTitle}>I am helping the patient</Text><Text style={styles.optionBody}>I am a family member, friend, or carer supporting this session.</Text></View>
            {actor === "carer" && <Ionicons name="checkmark-circle" size={23} color={colors.brandPrimary} />}
          </Pressable>
        </View>
        <Pressable testID="session-safety-ack" onPress={() => setSafetyAck((v) => !v)} style={[styles.safetyCard, safetyAck && styles.safetyCardActive]}>
          <Ionicons name={safetyAck ? "checkbox" : "square-outline"} size={24} color={safetyAck ? colors.brandPrimary : colors.onSurfaceTertiary} />
          <View style={{ flex: 1 }}>
            <Text style={styles.safetyTitle}>Safety check</Text>
            <Text style={styles.safetyBody}>I am seated or have a clear, safe space, my walking aid if I use one, and someone nearby for standing or walking. I will stop if I feel pain, dizziness, or unwell.</Text>
          </View>
        </Pressable>
      </View>
      <Pressable testID="session-actor-continue" disabled={!actor || !safetyAck} onPress={continueToSession} style={[styles.continueButton, (!actor || !safetyAck) && { opacity: 0.4 }]}>
        <Text style={styles.continueText}>Continue</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, paddingHorizontal: spacing.lg, backgroundColor: colors.surface },
  backButton: { width: 44, height: 44, alignItems: "center", justifyContent: "center", marginLeft: -spacing.sm },
  content: { flex: 1, justifyContent: "center", width: "100%", maxWidth: 560, alignSelf: "center" },
  icon: { width: 58, height: 58, borderRadius: 29, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary, marginBottom: spacing.md },
  title: { fontSize: 28, lineHeight: 34, fontWeight: "800", color: colors.onSurface },
  subtitle: { fontSize: 15, lineHeight: 22, color: colors.onSurfaceSecondary, marginTop: spacing.sm },
  options: { gap: spacing.sm, marginTop: spacing.xl },
  option: { flexDirection: "row", alignItems: "center", gap: spacing.md, minHeight: 86, padding: spacing.md, borderRadius: radius.md, borderWidth: 2, borderColor: colors.border, backgroundColor: colors.surface },
  optionActive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  optionTitle: { fontSize: 16, fontWeight: "800", color: colors.onSurface },
  optionBody: { fontSize: 13, lineHeight: 18, color: colors.onSurfaceSecondary, marginTop: 2 },
  continueButton: { width: "100%", maxWidth: 560, alignSelf: "center", minHeight: 56, borderRadius: radius.md, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  continueText: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "800" },
  safetyCard: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, borderWidth: 2, borderColor: colors.border, backgroundColor: colors.surface },
  safetyCardActive: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  safetyTitle: { fontSize: 15, fontWeight: "800", color: colors.onSurface },
  safetyBody: { fontSize: 13, lineHeight: 18, color: colors.onSurfaceSecondary, marginTop: 2 },
});
