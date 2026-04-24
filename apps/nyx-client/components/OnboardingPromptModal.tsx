import { Modal, Pressable, StyleSheet, Text, View } from "react-native";

import { theme } from "@/lib/theme/tokens";

type OnboardingPromptModalProps = {
  visible: boolean;
  currentStep: number;
  stepCount: number;
  onStartPress: () => void;
  onDismiss: () => void;
};

export function OnboardingPromptModal({
  visible,
  currentStep,
  stepCount,
  onStartPress,
  onDismiss,
}: OnboardingPromptModalProps) {
  const hasProgress = currentStep > 0;
  const resumeStep = Math.min(currentStep + 1, Math.max(stepCount, 1));

  return (
    <Modal animationType="fade" transparent visible={visible} onRequestClose={onDismiss}>
      <View style={styles.backdrop}>
        <Pressable aria-label="Dismiss onboarding prompt" onPress={onDismiss} style={StyleSheet.absoluteFill} />
        <View style={styles.card}>
          <Text style={styles.kicker}>First launch</Text>
          <Text style={styles.title}>
            {hasProgress ? "Resume onboarding before you settle into the dashboard" : "Start onboarding before you settle into the dashboard"}
          </Text>
          <Text style={styles.body}>
            This uses the same onboarding flow Nyx already saves for the CLI and coach. Your answers autosave as you move through it.
          </Text>
          <View style={styles.metaRow}>
            <Text style={styles.metaText}>{stepCount ? `${stepCount} prompts` : "Saved flow"}</Text>
            <Text style={styles.metaText}>
              {hasProgress ? `Resume at step ${resumeStep}` : "Starts at step 1"}
            </Text>
          </View>
          <View style={styles.actionRow}>
            <Pressable onPress={onDismiss} style={({ pressed }) => [styles.secondaryButton, pressed && styles.buttonPressed]}>
              <Text style={styles.secondaryButtonText}>Not now</Text>
            </Pressable>
            <Pressable onPress={onStartPress} style={({ pressed }) => [styles.primaryButton, pressed && styles.buttonPressed]}>
              <Text style={styles.primaryButtonText}>
                {hasProgress ? "Continue onboarding" : "Start onboarding"}
              </Text>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    alignItems: "center",
    backgroundColor: "rgba(5, 5, 5, 0.84)",
    flex: 1,
    justifyContent: "center",
    padding: theme.spacing.xl,
  },
  card: {
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    gap: theme.spacing.lg,
    maxWidth: 560,
    padding: theme.spacing.xl,
    width: "100%",
  },
  kicker: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1.3,
    textTransform: "uppercase",
  },
  title: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 30,
    lineHeight: 36,
  },
  body: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    lineHeight: 22,
  },
  metaRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  metaText: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  actionRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: theme.colors.actionPrimaryBg,
    borderRadius: theme.radius.pill,
    justifyContent: "center",
    minHeight: 48,
    minWidth: 168,
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  primaryButtonText: {
    color: theme.colors.actionPrimaryText,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    fontWeight: "600",
  },
  secondaryButton: {
    alignItems: "center",
    backgroundColor: theme.colors.surface3,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 48,
    minWidth: 116,
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  secondaryButtonText: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    fontWeight: "500",
  },
  buttonPressed: {
    opacity: 0.88,
  },
});
