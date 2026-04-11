import { useEffect, useState } from "react";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { Surface } from "@/components/Surface";
import { api } from "@/lib/api/client";
import { theme } from "@/lib/theme/tokens";

type OnboardingStep = {
  key: string;
  text: string;
};

type FlagMessage = {
  id: string;
  message: string;
};

type OnboardingState = {
  completed: boolean;
  mode: "mvp" | "full";
  current_step: number;
  steps: OnboardingStep[];
  answers: Record<string, string>;
  active_flag_messages?: FlagMessage[];
  new_flag_messages?: FlagMessage[];
};

function resolveReturnPath(returnTo?: string | string[]) {
  if (returnTo === "coach") {
    return "/coach";
  }
  return "/";
}

export default function OnboardingScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { returnTo } = useLocalSearchParams<{ returnTo?: string }>();
  const onboardingQuery = useQuery<OnboardingState>({
    queryKey: ["onboarding"],
    queryFn: api.getOnboarding,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [stepIndex, setStepIndex] = useState(0);
  const [flagNotice, setFlagNotice] = useState<FlagMessage[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<"nav" | "complete" | "reset" | null>(null);

  useEffect(() => {
    if (!onboardingQuery.data) {
      return;
    }
    setDrafts(onboardingQuery.data.answers ?? {});
    setStepIndex(onboardingQuery.data.completed ? 0 : (onboardingQuery.data.current_step ?? 0));
  }, [onboardingQuery.data]);

  const state = onboardingQuery.data;
  const steps = state?.steps ?? [];
  const currentStep = steps[stepIndex];
  const progress = steps.length ? (stepIndex + 1) / steps.length : 0;
  const hasSavedAnswers = Object.values(drafts).some((value) => value.trim().length > 0);

  async function saveCurrentStep(nextStep: number, answerOverride?: string) {
    if (!state || !currentStep) {
      return null;
    }

    const answer = answerOverride ?? drafts[currentStep.key] ?? "";
    const response = await api.saveOnboarding({
      answers: {
        [currentStep.key]: answer,
      },
      current_step: nextStep,
      mode: state.mode,
    });
    queryClient.setQueryData(["onboarding"], response);
    setDrafts((current) => ({
      ...current,
      [currentStep.key]: answer,
      ...(response.answers ?? {}),
    }));
    setStepIndex(response.current_step ?? nextStep);
    setFlagNotice(response.new_flag_messages ?? []);
    return response as OnboardingState;
  }

  async function handleBack() {
    if (!state || !currentStep || busyAction || stepIndex === 0) {
      return;
    }

    try {
      setBusyAction("nav");
      setError(null);
      await saveCurrentStep(stepIndex - 1);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to save this step.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleAdvance(answerOverride?: string) {
    if (!state || !currentStep || busyAction) {
      return;
    }

    const lastStep = stepIndex >= steps.length - 1;
    const nextStep = lastStep ? stepIndex : stepIndex + 1;

    try {
      setBusyAction(lastStep ? "complete" : "nav");
      setError(null);
      await saveCurrentStep(nextStep, answerOverride);

      if (lastStep) {
        const completed = await api.completeOnboarding();
        queryClient.setQueryData(["onboarding"], completed);
        queryClient.invalidateQueries({ queryKey: ["athlete-summary"] });
        queryClient.invalidateQueries({ queryKey: ["coach-context"] });
        queryClient.invalidateQueries({ queryKey: ["coach-thread-current"] });
        router.replace(resolveReturnPath(returnTo) as any);
      }
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to continue onboarding.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleReset() {
    if (busyAction) {
      return;
    }

    try {
      setBusyAction("reset");
      setError(null);
      const resetState = await api.resetOnboarding();
      queryClient.setQueryData(["onboarding"], resetState);
      queryClient.invalidateQueries({ queryKey: ["athlete-summary"] });
      queryClient.invalidateQueries({ queryKey: ["coach-context"] });
      setDrafts(resetState.answers ?? {});
      setStepIndex(resetState.current_step ?? 0);
      setFlagNotice([]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to reset onboarding.");
    } finally {
      setBusyAction(null);
    }
  }

  if (onboardingQuery.isLoading) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.loading}>
          <ActivityIndicator color={theme.colors.textPrimary} />
        </View>
      </SafeAreaView>
    );
  }

  if (!state || !currentStep) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.loading}>
          <Text style={styles.errorTitle}>Onboarding is unavailable.</Text>
          <Text style={styles.errorText}>
            {error ?? (onboardingQuery.error instanceof Error ? onboardingQuery.error.message : "No onboarding steps were returned by the server.")}
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Text style={styles.kicker}>Nyx onboarding</Text>
          <Text style={styles.title}>
            {state.completed ? "Update your athlete profile" : "Give Nyx the context behind the data"}
          </Text>
          <Text style={styles.subtitle}>
            Same onboarding state as the CLI, just a quieter UI. Each answer is saved locally on this device.
          </Text>
        </View>

        <Surface tone="raised">
          <View style={styles.metaRow}>
            <Text style={styles.metaText}>
              Step {stepIndex + 1} of {steps.length}
            </Text>
            <Text style={styles.metaText}>{state.mode === "full" ? "Full intake" : "MVP intake"}</Text>
          </View>
          <View style={styles.progressTrack}>
            <View style={[styles.progressFill, { width: `${Math.max(progress * 100, 6)}%` }]} />
          </View>
          <Text style={styles.question}>{currentStep.text}</Text>
          <TextInput
            multiline
            value={drafts[currentStep.key] ?? ""}
            onChangeText={(value) =>
              setDrafts((current) => ({
                ...current,
                [currentStep.key]: value,
              }))
            }
            placeholder="Type as much or as little as you like."
            placeholderTextColor={theme.colors.textTertiary}
            style={styles.input}
            textAlignVertical="top"
          />
          {flagNotice.length ? (
            <View style={styles.noticeStack}>
              {flagNotice.map((flag) => (
                <View key={flag.id} style={styles.noticeCard}>
                  <Text style={styles.noticeLabel}>Coaching note</Text>
                  <Text style={styles.noticeText}>{flag.message}</Text>
                </View>
              ))}
            </View>
          ) : null}
          {error ? <Text style={styles.errorText}>{error}</Text> : null}
        </Surface>

        <Surface>
          <View style={styles.actionRow}>
            <Pressable
              onPress={handleBack}
              disabled={stepIndex === 0 || Boolean(busyAction)}
              style={({ pressed }) => [
                styles.secondaryButton,
                (pressed || stepIndex === 0 || busyAction) && styles.buttonDisabled,
              ]}
            >
              <Text style={styles.secondaryButtonText}>Back</Text>
            </Pressable>
            <Pressable
              onPress={() => handleAdvance("")}
              disabled={Boolean(busyAction)}
              style={({ pressed }) => [
                styles.secondaryButton,
                (pressed || busyAction) && styles.buttonDisabled,
              ]}
            >
              <Text style={styles.secondaryButtonText}>Skip</Text>
            </Pressable>
            <Pressable
              onPress={() => handleAdvance()}
              disabled={Boolean(busyAction)}
              style={({ pressed }) => [
                styles.primaryButton,
                (pressed || busyAction) && styles.buttonDisabled,
              ]}
            >
              <Text style={styles.primaryButtonText}>
                {stepIndex >= steps.length - 1 ? "Finish" : "Next"}
              </Text>
            </Pressable>
          </View>
          <View style={styles.footerRow}>
            <Text style={styles.footerText}>
              Skip is allowed. Missing answers stay editable later.
            </Text>
            {state.completed || hasSavedAnswers ? (
              <Pressable onPress={handleReset} disabled={Boolean(busyAction)}>
                <Text style={styles.resetText}>Start over</Text>
              </Pressable>
            ) : null}
          </View>
        </Surface>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: {
    backgroundColor: theme.colors.bg,
    flex: 1,
  },
  loading: {
    alignItems: "center",
    flex: 1,
    justifyContent: "center",
    padding: theme.spacing.xl,
  },
  content: {
    alignSelf: "center",
    gap: theme.spacing.lg,
    maxWidth: 860,
    paddingHorizontal: theme.spacing.xl,
    paddingTop: theme.spacing.xxl,
    paddingBottom: theme.spacing.xxl,
    width: "100%",
  },
  header: {
    gap: 10,
  },
  kicker: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  title: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 34,
    lineHeight: 40,
    maxWidth: 720,
  },
  subtitle: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    lineHeight: 22,
    maxWidth: 700,
  },
  metaRow: {
    flexDirection: "row",
    justifyContent: "space-between",
  },
  metaText: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  progressTrack: {
    backgroundColor: theme.colors.surface3,
    borderRadius: theme.radius.pill,
    height: 8,
    marginTop: theme.spacing.md,
    overflow: "hidden",
  },
  progressFill: {
    backgroundColor: theme.colors.textPrimary,
    borderRadius: theme.radius.pill,
    height: 8,
  },
  question: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 26,
    lineHeight: 32,
    marginTop: theme.spacing.xl,
  },
  input: {
    backgroundColor: theme.colors.surface3,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 16,
    lineHeight: 24,
    marginTop: theme.spacing.lg,
    minHeight: 220,
    padding: theme.spacing.lg,
  },
  noticeStack: {
    gap: theme.spacing.md,
    marginTop: theme.spacing.lg,
  },
  noticeCard: {
    backgroundColor: theme.colors.surface1,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    padding: theme.spacing.md,
  },
  noticeLabel: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1.1,
    textTransform: "uppercase",
  },
  noticeText: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 21,
    marginTop: 6,
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
    minWidth: 132,
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
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 48,
    minWidth: 100,
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  secondaryButtonText: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    fontWeight: "500",
  },
  buttonDisabled: {
    opacity: 0.55,
  },
  footerRow: {
    alignItems: "center",
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.md,
    justifyContent: "space-between",
    marginTop: theme.spacing.lg,
  },
  footerText: {
    color: theme.colors.textSecondary,
    flex: 1,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 20,
  },
  resetText: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1,
    textTransform: "uppercase",
  },
  errorTitle: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 24,
    lineHeight: 28,
  },
  errorText: {
    color: "#d9a3a3",
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 21,
    marginTop: 8,
  },
});
