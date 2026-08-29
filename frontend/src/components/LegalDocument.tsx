import { Text, View, StyleSheet } from "react-native";

import { LegalSection } from "@/src/legalContent";
import { spacing } from "@/src/theme";
import { DisplayPalette } from "@/src/displayPreferences";

export function LegalDocument({
  intro,
  sections,
  palette,
}: {
  intro: string;
  sections: LegalSection[];
  palette: DisplayPalette;
}) {
  return (
    <View>
      <Text style={[styles.intro, { color: palette.muted }]}>{intro}</Text>
      {sections.map((section, sectionIndex) => (
        <View key={section.title} style={styles.section} testID={`legal-section-${sectionIndex}`}>
          <Text style={[styles.heading, { color: palette.text }]}>{section.title}</Text>
          {section.paragraphs.map((paragraph, paragraphIndex) => (
            <Text key={`${section.title}-p-${paragraphIndex}`} style={[styles.body, { color: palette.muted }]}>
              {paragraph}
            </Text>
          ))}
          {section.bullets?.map((bullet, bulletIndex) => (
            <View key={`${section.title}-b-${bulletIndex}`} style={styles.bulletRow}>
              <Text style={[styles.bullet, { color: palette.text }]}>•</Text>
              <Text style={[styles.bulletBody, { color: palette.muted }]}>{bullet}</Text>
            </View>
          ))}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  intro: { fontSize: 16, lineHeight: 24, marginBottom: spacing.xl },
  section: { marginBottom: spacing.xl },
  heading: { fontSize: 19, lineHeight: 25, fontWeight: "800", marginBottom: spacing.sm },
  body: { fontSize: 15, lineHeight: 23, marginBottom: spacing.sm },
  bulletRow: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, marginBottom: spacing.xs },
  bullet: { fontSize: 16, lineHeight: 23, fontWeight: "800" },
  bulletBody: { flex: 1, fontSize: 15, lineHeight: 23 },
});
