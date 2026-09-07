import { useRef, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { getCachedUser, resetAccount } from "@/src/auth";
import { useDisplayPreferences } from "@/src/displayPreferences";

export function ResetAccountControl({ scale }: { scale: number }) {
  const { palette } = useDisplayPreferences();
  const router = useRouter();
  const [visible, setVisible] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [identity, setIdentity] = useState("");
  const submitting = useRef(false);

  const open = async () => {
    const user = await getCachedUser();
    setIdentity(user ? `${user.name} (${user.email})` : "Your signed-in account");
    setConfirmed(false);
    setError("");
    setVisible(true);
  };
  const close = () => { if (!submitting.current) setVisible(false); };
  const submit = async () => {
    if (!confirmed || submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError("");
    try {
      await resetAccount();
      if (Platform.OS === "web") {
        window.location.replace("/");
      } else {
        setVisible(false);
        router.dismissAll();
        router.replace("/");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Reset could not finish. Please retry.");
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  };

  return <>
    <Pressable testID="settings-reset-account" accessibilityRole="button" onPress={open} style={styles.row}>
      <View style={[styles.icon, { backgroundColor: palette.soft }]}><Ionicons name="refresh-outline" size={22} color={palette.brand} /></View>
      <View style={styles.copy}>
        <Text style={{ color: palette.text, fontWeight: "800", fontSize: 16 * scale }}>Reset account</Text>
        <Text style={{ color: palette.muted, fontSize: 12 * scale, lineHeight: 17 * scale }}>Start again with the same sign-in</Text>
      </View>
      <Ionicons name="chevron-forward" size={20} color={palette.muted} />
    </Pressable>
    <Modal visible={visible} transparent animationType="fade" onRequestClose={close}>
      <View style={styles.scrim}>
        <ScrollView style={[styles.modal, { backgroundColor: palette.surface, borderColor: palette.border }]} contentContainerStyle={styles.content}>
          <Ionicons name="warning-outline" size={32} color="#B42318" />
          <Text accessibilityRole="header" style={{ color: palette.text, fontSize: 22 * scale, fontWeight: "800" }}>Reset this account?</Text>
          <Text style={{ color: palette.text, fontSize: 14 * scale, lineHeight: 21 * scale }}>{identity}</Text>
          <Text style={{ color: palette.muted, fontSize: 15 * scale, lineHeight: 23 * scale }}>
            Your survey, assessments, recordings, rehab plans, check-ins, exercise history, points, medals and journals will be permanently cleared. You will start again with Terms and the setup survey.
          </Text>
          <Text style={{ color: palette.muted, fontSize: 14 * scale, lineHeight: 21 * scale }}>Your name, email, account ID, trial access and purchases stay. Other accounts are not changed.</Text>
          <Pressable testID="reset-account-confirmation" accessibilityRole="checkbox" accessibilityState={{ checked: confirmed, disabled: busy }} disabled={busy} onPress={() => setConfirmed(!confirmed)} style={styles.confirmation}>
            <Ionicons name={confirmed ? "checkbox" : "square-outline"} size={26} color={palette.brand} />
            <Text style={{ flex: 1, color: palette.text, fontSize: 14 * scale, lineHeight: 21 * scale }}>I understand that this cannot be undone.</Text>
          </Pressable>
          {error ? <Text testID="reset-account-error" accessibilityRole="alert" style={{ color: "#B42318", fontSize: 14 * scale, lineHeight: 21 * scale }}>{error}</Text> : null}
          <Pressable testID="reset-account-submit" accessibilityRole="button" accessibilityState={{ disabled: !confirmed || busy, busy }} disabled={!confirmed || busy} onPress={submit} style={[styles.button, { backgroundColor: "#B42318", opacity: !confirmed || busy ? 0.5 : 1 }]}>
            {busy ? <ActivityIndicator color="#FFFFFF" /> : <Ionicons name="refresh-outline" color="#FFFFFF" size={20} />}
            <Text style={{ color: "#FFFFFF", fontSize: 16 * scale, fontWeight: "800", flexShrink: 1 }}>{busy ? "Resetting account..." : "Reset account"}</Text>
          </Pressable>
          <Pressable accessibilityRole="button" testID="reset-account-cancel" disabled={busy} onPress={close} style={[styles.button, { borderWidth: 1, borderColor: palette.border }]}>
            <Text style={{ color: palette.text, fontSize: 16 * scale, fontWeight: "700" }}>Cancel</Text>
          </Pressable>
        </ScrollView>
      </View>
    </Modal>
  </>;
}

const styles = StyleSheet.create({
  row: { minHeight: 82, flexDirection: "row", alignItems: "center", gap: 12 },
  icon: { width: 44, height: 44, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  copy: { flex: 1, minWidth: 0, gap: 2 },
  scrim: { flex: 1, padding: 20, alignItems: "center", justifyContent: "center", backgroundColor: "rgba(8,18,14,0.6)" },
  modal: { flexGrow: 0, maxHeight: "90%", width: "100%", maxWidth: 480, borderWidth: 1, borderRadius: 8 },
  content: { padding: 22, gap: 16 },
  confirmation: { minHeight: 48, flexDirection: "row", gap: 12, alignItems: "center" },
  button: { minHeight: 50, padding: 12, borderRadius: 8, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8 },
});
