import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  useWindowDimensions,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { WebView, WebViewMessageEvent } from "react-native-webview";
import * as Haptics from "expo-haptics";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { authedFetch, getCachedUser } from "@/src/auth";
import { API_BASE } from "@/src/config";
import { colors, radius, spacing } from "@/src/theme";

type InfoTopic = "privacy" | "limitations" | null;

const FAST_STEPS = [
  { label: "Face", icon: "happy-outline" as const },
  { label: "Arms", icon: "body-outline" as const },
  { label: "Speech", icon: "chatbubble-ellipses-outline" as const },
];

export default function EmergencyFastScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [ready, setReady] = useState(false);
  const [started, setStarted] = useState(false);
  const [patientName, setPatientName] = useState("");
  const [infoTopic, setInfoTopic] = useState<InfoTopic>(null);
  const isWide = width >= 820;

  useEffect(() => {
    void getCachedUser().then((user) => setPatientName((user?.name || "").split(" ")[0] || ""));
  }, []);

  const recordResult = async (message: Record<string, unknown>) => {
    try {
      await authedFetch("/api/emergency/fast-check", {
        method: "POST",
        body: JSON.stringify({
          answers: message.answers,
          automated: message.automated,
          onset_time: message.onset_time || undefined,
          source: "guided_fast",
        }),
      });
    } catch {
      // An emergency result is shown immediately and never waits for audit logging.
    }
  };

  const onMessage = (event: WebViewMessageEvent) => {
    try {
      const message = JSON.parse(event.nativeEvent.data) as Record<string, unknown>;
      if (message.type === "fast_check_result") {
        const result = message.result as { call_999?: boolean } | undefined;
        void Haptics.notificationAsync(
          result?.call_999
            ? Haptics.NotificationFeedbackType.Error
            : Haptics.NotificationFeedbackType.Success,
        );
        void recordResult(message);
      } else if (message.type === "demo_911_started") {
        void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Warning);
      } else if (message.type === "exit") {
        router.back();
      }
    } catch {
      // Ignore non-Rehyn iframe messages.
    }
  };

  const query = `?autostart=1${patientName ? `&name=${encodeURIComponent(patientName)}` : ""}`;

  if (!started) {
    return (
      <View style={styles.introPage} testID="emergency-fast-intro">
        <View style={[styles.introHeader, { paddingTop: insets.top }]}>
          <Pressable onPress={() => router.back()} style={[styles.leaveButton, !isWide && styles.leaveButtonNarrow]} accessibilityRole="button" testID="fast-leave">
            <Ionicons name="chevron-back" size={28} color="#124C35" />
            <Text style={styles.leaveText}>Leave</Text>
          </Pressable>
          <Text style={[styles.introHeaderTitle, !isWide && styles.introHeaderTitleNarrow]}>Emergency FAST check</Text>
          <View style={[styles.headerBalance, !isWide && styles.headerBalanceNarrow]} />
        </View>

        <View style={styles.prototypeBar} testID="fast-prototype-warning">
          <Text style={styles.prototypeText}>Prototype only - use a phone for real emergency calls.</Text>
        </View>

        <ScrollView contentContainerStyle={[styles.introScroll, { paddingBottom: Math.max(insets.bottom, spacing.xl) }]}>
          <View style={styles.introContent}>
            <View style={[styles.emergencyCallout, !isWide && styles.emergencyCalloutNarrow]}>
              <View style={styles.phoneIcon}>
                <Ionicons name="call" size={isWide ? 50 : 38} color="#FFFFFF" />
              </View>
              <View style={styles.emergencyCopy}>
                <Text style={[styles.emergencyTitle, !isWide && styles.emergencyTitleNarrow]}>Are signs visible, or did symptoms start suddenly?</Text>
                <Text style={[styles.emergencyMessage, !isWide && styles.emergencyMessageNarrow]}>Call 999 by phone now. Do not wait for this check.</Text>
              </View>
            </View>

            <View style={styles.guidedDivider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>Otherwise, start the guided check</Text>
              <View style={styles.dividerLine} />
            </View>

            <View style={[styles.fastStepRow, !isWide && styles.fastStepRowNarrow]} testID="fast-step-overview">
              {FAST_STEPS.map((step, index) => (
                <View key={step.label} style={[styles.fastStepCard, !isWide && styles.fastStepCardNarrow]}>
                  <View style={styles.stepNumber}><Text style={styles.stepNumberText}>{index + 1}</Text></View>
                  <Ionicons name={step.icon} size={42} color="#0E5337" />
                  <Text style={styles.fastStepLabel}>{step.label}</Text>
                  {isWide && index < FAST_STEPS.length - 1 && <View style={styles.stepConnector} />}
                </View>
              ))}
            </View>

            <Pressable
              onPress={() => {
                setReady(false);
                setStarted(true);
              }}
              style={({ pressed }) => [styles.startButton, pressed && styles.startButtonPressed]}
              accessibilityRole="button"
              testID="fast-start-guided"
            >
              <Text style={styles.startButtonText}>Start guided FAST check</Text>
            </Pressable>

            <View style={[styles.privacyRow, !isWide && styles.privacyRowNarrow]}>
              <View style={styles.privacyItem}>
                <View style={styles.privacyIcon}><Ionicons name="lock-closed" size={31} color="#0F5638" /></View>
                <Text style={styles.privacyText}>Video is processed on this device and is not saved.</Text>
              </View>
              <View style={[styles.privacyDivider, !isWide && styles.privacyDividerNarrow]} />
              <View style={styles.privacyItem}>
                <View style={styles.privacyIcon}><Ionicons name="mic" size={32} color="#0F5638" /></View>
                <Text style={styles.privacyText}>A short speech recording is sent securely for transcription.</Text>
              </View>
            </View>

            <View style={styles.infoLinks}>
              <Pressable onPress={() => setInfoTopic("privacy")} style={styles.infoLinkButton} testID="fast-privacy-details">
                <Text style={styles.infoLinkText}>Privacy details</Text>
              </Pressable>
              <View style={styles.infoLinkDivider} />
              <Pressable onPress={() => setInfoTopic("limitations")} style={styles.infoLinkButton} testID="fast-technical-limitations">
                <Text style={styles.infoLinkText}>Technical limitations</Text>
              </Pressable>
            </View>
            <Text style={styles.guidanceSource}>Based on CDC FAST guidance.</Text>
          </View>
        </ScrollView>

        <Modal visible={infoTopic !== null} transparent animationType="fade" onRequestClose={() => setInfoTopic(null)}>
          <View style={styles.modalBackdrop}>
            <View style={styles.infoModal} testID="fast-information-modal">
              <View style={styles.infoModalHeader}>
                <Text style={styles.infoModalTitle}>{infoTopic === "privacy" ? "Privacy details" : "Technical limitations"}</Text>
                <Pressable onPress={() => setInfoTopic(null)} style={styles.modalClose} accessibilityLabel="Close">
                  <Ionicons name="close" size={24} color="#153E2E" />
                </Pressable>
              </View>
              <Text style={styles.infoModalText}>
                {infoTopic === "privacy"
                  ? "Face and arm video is analysed on this device and is not saved. A short speech recording is sent securely for transcription and is not retained by Rehyn."
                  : "This prototype cannot rule out a stroke or TIA. Camera, lighting, microphone, movement, or network problems can make a result inconclusive. Never delay calling 999 when symptoms are sudden or concerning."}
              </Text>
              <Pressable onPress={() => setInfoTopic(null)} style={styles.modalDone}><Text style={styles.modalDoneText}>Close</Text></Pressable>
            </View>
          </View>
        </Modal>
      </View>
    );
  }

  return (
    <View style={styles.container} testID="emergency-fast-screen">
      <WebView
        testID="emergency-fast-webview"
        source={{ uri: `${API_BASE}/api/emergency/fast-runner${query}` }}
        style={styles.webview}
        originWhitelist={["*"]}
        javaScriptEnabled
        domStorageEnabled
        mediaPlaybackRequiresUserAction={false}
        allowsInlineMediaPlayback
        {...(Platform.OS === "ios" ? { mediaCapturePermissionGrantType: "grant" as const } : {})}
        {...({ onPermissionRequest: (event: any) => { try { event?.grant(event?.resources || []); } catch {} } } as any)}
        onMessage={onMessage}
        onLoadEnd={() => setReady(true)}
      />
      {!ready ? (
        <View style={styles.loading} pointerEvents="none">
          <ActivityIndicator size="large" color={colors.error} />
          <Text style={styles.loadingText}>Opening emergency FAST check...</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: "#F7F8F6" },
  webview: { flex: 1, backgroundColor: "#F7F8F6" },
  introPage: { flex: 1, backgroundColor: "#FCFCFA" },
  introHeader: { minHeight: 76, paddingHorizontal: spacing.lg, paddingBottom: spacing.xs, flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: "#FFFFFF", borderBottomWidth: 1, borderBottomColor: "#D9DED8" },
  leaveButton: { width: 142, minHeight: 48, flexDirection: "row", alignItems: "center", gap: 2 },
  leaveButtonNarrow: { width: 90 },
  leaveText: { fontSize: 20, lineHeight: 26, color: "#123E2D", fontWeight: "500" },
  introHeaderTitle: { flex: 1, fontSize: 25, lineHeight: 32, fontWeight: "800", color: "#124C35", textAlign: "center", letterSpacing: 0 },
  introHeaderTitleNarrow: { fontSize: 16, lineHeight: 21 },
  headerBalance: { width: 142 },
  headerBalanceNarrow: { width: 30 },
  prototypeBar: { minHeight: 43, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, alignItems: "center", justifyContent: "center", backgroundColor: "#C80D12" },
  prototypeText: { color: "#FFFFFF", fontSize: 17, lineHeight: 23, fontWeight: "800", textAlign: "center", letterSpacing: 0 },
  introScroll: { flexGrow: 1, paddingHorizontal: spacing.md, paddingTop: 43 },
  introContent: { width: "100%", maxWidth: 1048, alignSelf: "center" },
  emergencyCallout: { minHeight: 194, borderWidth: 1, borderColor: "#F3A4A0", borderRadius: radius.sm, backgroundColor: "#FFF5F3", paddingHorizontal: 42, paddingVertical: 28, flexDirection: "row", alignItems: "center", gap: 36 },
  emergencyCalloutNarrow: { minHeight: 0, paddingHorizontal: spacing.md, paddingVertical: spacing.lg, gap: spacing.md },
  phoneIcon: { width: 108, height: 108, borderRadius: 54, alignItems: "center", justifyContent: "center", backgroundColor: "#C80D12", flexShrink: 0 },
  emergencyCopy: { flex: 1, minWidth: 0 },
  emergencyTitle: { fontSize: 32, lineHeight: 40, fontWeight: "800", color: "#B51B17", letterSpacing: 0 },
  emergencyTitleNarrow: { fontSize: 22, lineHeight: 29 },
  emergencyMessage: { marginTop: spacing.sm, fontSize: 25, lineHeight: 33, fontWeight: "400", color: "#B51B17", letterSpacing: 0 },
  emergencyMessageNarrow: { fontSize: 17, lineHeight: 24 },
  guidedDivider: { marginVertical: 42, flexDirection: "row", alignItems: "center", gap: spacing.lg },
  dividerLine: { flex: 1, height: 1, backgroundColor: "#77926E" },
  dividerText: { fontSize: 20, lineHeight: 26, color: "#153E2E", textAlign: "center", letterSpacing: 0 },
  fastStepRow: { flexDirection: "row", alignItems: "stretch", gap: 40 },
  fastStepRowNarrow: { flexDirection: "column", gap: spacing.sm },
  fastStepCard: { position: "relative", flex: 1, minHeight: 128, borderWidth: 1, borderColor: "#78926E", borderRadius: radius.sm, backgroundColor: "#FFFFFF", flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.md, paddingHorizontal: spacing.md },
  fastStepCardNarrow: { minHeight: 90, flex: 0, justifyContent: "flex-start", paddingHorizontal: spacing.lg },
  stepNumber: { width: 52, height: 52, borderRadius: 26, backgroundColor: "#075537", alignItems: "center", justifyContent: "center" },
  stepNumberText: { color: "#FFFFFF", fontSize: 28, lineHeight: 34, fontWeight: "800" },
  fastStepLabel: { fontSize: 23, lineHeight: 29, color: "#104C34", fontWeight: "800", letterSpacing: 0 },
  stepConnector: { position: "absolute", width: 42, height: 1, right: -42, top: "50%", backgroundColor: "#93A58F", zIndex: 2 },
  startButton: { minHeight: 90, marginTop: 36, borderRadius: radius.sm, backgroundColor: "#075537", alignItems: "center", justifyContent: "center", paddingHorizontal: spacing.lg },
  startButtonPressed: { opacity: 0.86 },
  startButtonText: { color: "#FFFFFF", fontSize: 28, lineHeight: 35, fontWeight: "800", textAlign: "center", letterSpacing: 0 },
  privacyRow: { marginTop: 36, alignSelf: "center", width: "90%", flexDirection: "row", alignItems: "center", justifyContent: "center" },
  privacyRowNarrow: { width: "100%", flexDirection: "column", alignItems: "stretch", gap: spacing.md },
  privacyItem: { flex: 1, minWidth: 0, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.md, paddingHorizontal: spacing.lg },
  privacyIcon: { width: 72, height: 72, borderRadius: 36, backgroundColor: "#EEF3EA", alignItems: "center", justifyContent: "center", flexShrink: 0 },
  privacyText: { flex: 1, maxWidth: 280, fontSize: 18, lineHeight: 27, color: "#1D2822", letterSpacing: 0 },
  privacyDivider: { width: 1, height: 82, backgroundColor: "#80977A" },
  privacyDividerNarrow: { width: "100%", height: 1 },
  infoLinks: { marginTop: 34, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.lg },
  infoLinkButton: { minHeight: 44, justifyContent: "center" },
  infoLinkText: { fontSize: 17, lineHeight: 23, color: "#143E2E", textDecorationLine: "underline" },
  infoLinkDivider: { width: 1, height: 32, backgroundColor: "#80977A" },
  guidanceSource: { marginTop: spacing.md, fontSize: 17, lineHeight: 23, color: "#59655E", textAlign: "center" },
  modalBackdrop: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.md, backgroundColor: "rgba(13, 28, 20, 0.62)" },
  infoModal: { width: "100%", maxWidth: 560, borderRadius: radius.sm, backgroundColor: "#FFFFFF", padding: spacing.lg },
  infoModalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.md },
  infoModalTitle: { flex: 1, fontSize: 23, lineHeight: 30, fontWeight: "800", color: "#153E2E" },
  modalClose: { width: 44, height: 44, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: "#D4DCD6", borderRadius: 22 },
  infoModalText: { marginTop: spacing.md, fontSize: 16, lineHeight: 24, color: "#35443C" },
  modalDone: { minHeight: 50, marginTop: spacing.lg, borderRadius: radius.sm, backgroundColor: "#075537", alignItems: "center", justifyContent: "center" },
  modalDoneText: { color: "#FFFFFF", fontSize: 16, lineHeight: 22, fontWeight: "800" },
  loading: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    backgroundColor: "#F7F8F6",
  },
  loadingText: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
});
