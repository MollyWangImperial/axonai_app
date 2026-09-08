import { useEffect, useState } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useDisplayPreferences } from "@/src/displayPreferences";

type Props = {
  visible: boolean;
  points: number;
  earnedPoints: number;
  saving: boolean;
  error: string;
  onSave: (points: number | null) => void;
  onClose: () => void;
};

export function TestingPointsModal({ visible, points, earnedPoints, saving, error, onSave, onClose }: Props) {
  const { palette } = useDisplayPreferences();
  const [value, setValue] = useState("");
  useEffect(() => { if (visible) setValue(String(points)); }, [points, visible]);
  const valid = /^\d+$/.test(value.trim()) && Number(value) <= 1000000;
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <ScrollView style={[styles.card, { backgroundColor: palette.surface }]} contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled" testID="testing-points-modal">
          <Text style={styles.kicker}>TESTING ONLY</Text>
          <Text style={[styles.title, { color: palette.text }]}>Set points</Text>
          <Text style={[styles.body, { color: palette.muted }]}>Choose a total to try the rewards workflow. Setting 100 or more will replay the 100-point celebration.</Text>
          <TextInput testID="testing-points-input" accessibilityLabel="Points total" value={value} onChangeText={setValue} keyboardType="number-pad" inputMode="numeric" editable={!saving} maxLength={7} selectTextOnFocus style={[styles.input, { borderColor: palette.border, color: palette.text }]} />
          <View style={styles.choices}>
            {[0, 99, 100].map((total) => (
              <Pressable key={total} disabled={saving} testID={`testing-points-quick-${total}`} onPress={() => setValue(String(total))} style={[styles.choice, { backgroundColor: palette.soft, borderColor: palette.border }]}>
                <Text style={{ color: palette.brand, fontWeight: "700" }}>{total} points</Text>
              </Pressable>
            ))}
          </View>
          {!valid && value ? <Text style={styles.error}>Enter a whole number from 0 to 1,000,000.</Text> : null}
          {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
          <Pressable testID="testing-points-save" accessibilityRole="button" disabled={!valid || saving} onPress={() => onSave(Number(value))} style={[styles.primary, { backgroundColor: palette.brand }, (!valid || saving) && styles.disabled]}>
            <Text style={styles.primaryText}>{saving ? "Saving…" : "Set points"}</Text>
          </Pressable>
          <Pressable testID="testing-points-reset" accessibilityRole="button" disabled={saving} onPress={() => onSave(null)} style={styles.secondary}>
            <Text style={[styles.secondaryText, { color: palette.brand }]}>Restore earned points ({earnedPoints})</Text>
          </Pressable>
          <Pressable testID="testing-points-close" accessibilityRole="button" disabled={saving} onPress={onClose} style={styles.secondary}>
            <Text style={[styles.secondaryText, { color: palette.muted }]}>Cancel</Text>
          </Pressable>
        </ScrollView>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: "rgba(12, 25, 19, 0.65)", alignItems: "center", justifyContent: "center", padding: 20 },
  card: { width: "100%", maxWidth: 420, maxHeight: "90%", flexGrow: 0, borderRadius: 24 },
  content: { padding: 24, gap: 14 },
  kicker: { color: "#B65C09", fontSize: 12, fontWeight: "800", letterSpacing: 1 },
  title: { fontSize: 26, fontWeight: "800" },
  body: { fontSize: 16, lineHeight: 23 },
  input: { borderWidth: 1, borderRadius: 12, padding: 12, fontSize: 24, minHeight: 52 },
  choices: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  choice: { borderWidth: 1, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 10 },
  primary: { minHeight: 48, alignItems: "center", justifyContent: "center", borderRadius: 14 },
  primaryText: { color: "#FFFFFF", fontSize: 17, fontWeight: "800" },
  secondary: { minHeight: 40, alignItems: "center", justifyContent: "center" },
  secondaryText: { fontSize: 15, fontWeight: "700" },
  error: { color: "#B42318", fontSize: 14 },
  disabled: { opacity: 0.5 },
});
