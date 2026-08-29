import { StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { radius, spacing } from "@/src/theme";

export const CONSENT_VERSION = "1.0";

// Compact, non-diagnostic disclaimer shown on results, plans, and summaries.
export function DisclaimerBanner({ testID = "medical-disclaimer" }: { testID?: string }) {
  return (
    <View style={styles.banner} testID={testID}>
      <Ionicons name="information-circle-outline" size={18} color="#7A6A2F" />
      <Text style={styles.text}>
        Rehyn offers movement coaching and wellness tracking — it is not a medical
        diagnosis and does not replace your clinical team. Stop and seek help if you
        feel pain, dizziness, or unwell.
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginBottom: spacing.md,
    borderRadius: radius.sm,
    backgroundColor: "#FBF6E7",
    borderWidth: 1,
    borderColor: "#E9DDB4",
  },
  text: { flex: 1, fontSize: 12, lineHeight: 17, fontWeight: "600", color: "#7A6A2F" },
});
