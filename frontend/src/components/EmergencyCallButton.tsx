import { Alert, Linking, Pressable, StyleSheet, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors, radius, spacing } from "@/src/theme";

type EmergencyCallButtonProps = {
  compact?: boolean;
};

export async function openEmergencyDialer() {
  try {
    await Linking.openURL("tel:999");
    return true;
  } catch {
    Alert.alert(
      "Call 999 now",
      "Use any available phone to call 999 immediately. Tell the call handler what has happened.",
    );
    return false;
  }
}

export function EmergencyCallButton({ compact = false }: EmergencyCallButtonProps) {
  return (
    <Pressable
      testID="alira-call-999"
      onPress={() => void openEmergencyDialer()}
      style={[styles.button, compact && styles.compactButton]}
      accessibilityRole="button"
      accessibilityLabel="Call 999"
      accessibilityHint="Opens the device dialler. You must confirm the call."
    >
      <Ionicons name="call" size={compact ? 18 : 22} color="#FFFFFF" />
      <Text style={[styles.label, compact && styles.compactLabel]}>Call 999</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: 52,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.sm,
    backgroundColor: colors.error,
  },
  compactButton: {
    alignSelf: "flex-start",
    minHeight: 42,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  label: {
    fontSize: 17,
    fontWeight: "900",
    color: "#FFFFFF",
  },
  compactLabel: {
    fontSize: 15,
  },
});
