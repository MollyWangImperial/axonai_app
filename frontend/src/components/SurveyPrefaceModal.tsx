import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { colors, radius, spacing } from "@/src/theme";

export const SURVEY_PREFACE_PARAGRAPHS = [
  "A few short questions about how you have been getting on. Your answers help Rehyn adjust your plan to suit you better.",
  "This takes about two minutes. Every question is optional and you can stop at any point. Skipping the check in does not change anything about your plan or your access to Rehyn.",
  "This is not a way to get help. If something is wrong, contact your GP or physiotherapist. In an emergency, call 999.",
] as const;

type SurveyPrefaceModalProps = {
  visible: boolean;
  onBegin: () => void;
  onClose: () => void;
};

export function SurveyPrefaceModal({ visible, onBegin, onClose }: SurveyPrefaceModalProps) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View style={styles.panel} testID="survey-preface">
          <View style={styles.iconWrap}>
            <Ionicons name="chatbubble-ellipses-outline" size={25} color={colors.brandPrimary} />
          </View>
          <Text style={styles.title}>Before your check-in</Text>
          {SURVEY_PREFACE_PARAGRAPHS.map((paragraph, index) => (
            <Text key={paragraph} style={[styles.body, index === 2 && styles.safety]}>{paragraph}</Text>
          ))}
          <Pressable testID="survey-preface-begin" onPress={onBegin} style={styles.beginButton}>
            <Text style={styles.beginText}>Begin check-in</Text>
            <Ionicons name="arrow-forward" size={19} color={colors.onBrandPrimary} />
          </Pressable>
          <Pressable testID="survey-preface-close" onPress={onClose} style={styles.notNowButton}>
            <Text style={styles.notNowText}>Not now</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    justifyContent: "center",
    padding: spacing.lg,
    backgroundColor: "rgba(8, 35, 27, 0.48)",
  },
  panel: {
    width: "100%",
    maxWidth: 520,
    alignSelf: "center",
    padding: spacing.lg,
    borderRadius: radius.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  iconWrap: {
    width: 48,
    height: 48,
    borderRadius: 24,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brandTertiary,
  },
  title: {
    marginTop: spacing.md,
    color: colors.onSurface,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: "800",
  },
  body: {
    marginTop: spacing.sm,
    color: colors.onSurfaceSecondary,
    fontSize: 15,
    lineHeight: 22,
  },
  safety: {
    color: colors.onSurface,
    fontWeight: "700",
  },
  beginButton: {
    minHeight: 52,
    marginTop: spacing.lg,
    paddingHorizontal: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    borderRadius: radius.md,
    backgroundColor: colors.brandPrimary,
  },
  beginText: {
    color: colors.onBrandPrimary,
    fontSize: 16,
    fontWeight: "800",
  },
  notNowButton: {
    minHeight: 46,
    alignItems: "center",
    justifyContent: "center",
    marginTop: spacing.xs,
  },
  notNowText: {
    color: colors.brandPrimary,
    fontSize: 15,
    fontWeight: "700",
  },
});
