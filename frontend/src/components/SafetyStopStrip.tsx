import { StyleSheet, Text, View } from "react-native";

import { EmergencyCallButton } from "@/src/components/EmergencyCallButton";
import { spacing } from "@/src/theme";

// Spec 9.1: every assessment and exercise screen carries explicit stop rules
// and an always-available emergency pathway, visible mid-task.
export function SafetyStopStrip() {
  return (
    <View style={styles.strip} testID="safety-stop-strip">
      <Text style={styles.text}>
        Stop immediately for chest pain, severe breathlessness, dizziness, new or severe pain, or any new symptom.
      </Text>
      <EmergencyCallButton compact />
    </View>
  );
}

const styles = StyleSheet.create({
  strip: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    minHeight: 46,
    backgroundColor: "#2B1614",
    borderTopWidth: 1,
    borderTopColor: "#5B2B24",
  },
  text: { flex: 1, color: "#F4D9D4", fontSize: 12, lineHeight: 16, fontWeight: "600" },
});
