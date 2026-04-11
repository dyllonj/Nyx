import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { AppFrame } from "@/components/AppFrame";
import { MetricPill } from "@/components/MetricPill";
import { Surface } from "@/components/Surface";
import { api } from "@/lib/api/client";
import { theme } from "@/lib/theme/tokens";

type ChatTurn = {
  role: "user" | "assistant";
  content: string;
  structured?: {
    verdict: string;
    evidence: { label: string; text: string }[];
    next_step: string;
  };
};

const DEFAULT_PROMPTS = [
  "What should my easy pace be right now?",
  "Am I running my easy runs too hard?",
  "What should I do this week?",
  "Why did my last run feel harder?",
];

export default function CoachScreen() {
  const contextQuery = useQuery({
    queryKey: ["coach-context"],
    queryFn: api.getCoachContext,
  });
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(message: string) {
    if (!message.trim() || busy) {
      return;
    }

    const nextMessages = [...messages, { role: "user", content: message }];
    setMessages(nextMessages);
    setDraft("");
    setBusy(true);
    setError(null);

    try {
      const response = await api.postCoachMessage({
        message,
        conversation: nextMessages.slice(0, -1).map((turn) => ({
          role: turn.role,
          content: turn.content,
        })),
      });

      setMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: response.raw_text,
          structured: {
            verdict: response.verdict,
            evidence: response.evidence ?? [],
            next_step: response.next_step,
          },
        },
      ]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Coach request failed.");
    } finally {
      setBusy(false);
    }
  }

  const context = contextQuery.data;

  return (
    <AppFrame
      title="Coach"
      subtitle="Conversation stays grounded in athlete data, explicit evidence, and retrieved source labels."
    >
      <Surface>
        <View style={styles.contextStrip}>
          <MetricPill label="vdot" value={context?.current_vdot ? String(context.current_vdot) : "n/a"} />
          <MetricPill label="easy" value={context?.easy_pace ? `${context.easy_pace}/km` : "n/a"} />
          <MetricPill
            label="z2"
            value={context?.zone_2 ? `${context.zone_2.hr_low}-${context.zone_2.hr_high} bpm` : "n/a"}
          />
        </View>
      </Surface>

      <Surface>
        <ScrollView contentContainerStyle={styles.thread}>
          {messages.length === 0 ? (
            <Text style={styles.emptyCopy}>
              Nyx does not start with a blank mystical void. Ask about pace, load, or execution, and it will answer against the current athlete state.
            </Text>
          ) : null}

          {messages.map((message, index) =>
            message.role === "user" ? (
              <View key={index} style={styles.userBubble}>
                <Text style={styles.userText}>{message.content}</Text>
              </View>
            ) : (
              <View key={index} style={styles.assistantCard}>
                <Text style={styles.cardLabel}>Verdict</Text>
                <Text style={styles.cardBody}>{message.structured?.verdict ?? message.content}</Text>
                {message.structured?.evidence?.length ? (
                  <>
                    <Text style={styles.cardLabel}>Evidence</Text>
                    <View style={styles.evidenceList}>
                      {message.structured.evidence.map((item, evidenceIndex) => (
                        <View key={evidenceIndex} style={styles.evidenceItem}>
                          <Text style={styles.evidenceLabel}>{item.label}</Text>
                          <Text style={styles.evidenceText}>{item.text}</Text>
                        </View>
                      ))}
                    </View>
                  </>
                ) : null}
                {message.structured?.next_step ? (
                  <>
                    <Text style={styles.cardLabel}>Next step</Text>
                    <Text style={styles.cardBody}>{message.structured.next_step}</Text>
                  </>
                ) : null}
              </View>
            ),
          )}
        </ScrollView>
      </Surface>

      <Surface>
        <View style={styles.promptRow}>
          {DEFAULT_PROMPTS.map((prompt) => (
            <Pressable
              key={prompt}
              onPress={() => submit(prompt)}
              style={({ pressed }) => [styles.promptChip, pressed && styles.promptChipPressed]}
            >
              <Text style={styles.promptChipText}>{prompt}</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.composer}>
          <TextInput
            multiline
            onChangeText={setDraft}
            placeholder="Ask Nyx..."
            placeholderTextColor={theme.colors.textTertiary}
            style={styles.input}
            value={draft}
          />
          <Pressable
            disabled={busy}
            onPress={() => submit(draft)}
            style={({ pressed }) => [
              styles.sendButton,
              (busy || pressed) && styles.sendButtonPressed,
            ]}
          >
            <Text style={styles.sendButtonText}>{busy ? "Thinking" : "Send"}</Text>
          </Pressable>
        </View>
        {error ? <Text style={styles.errorText}>{error}</Text> : null}
      </Surface>
    </AppFrame>
  );
}

const styles = StyleSheet.create({
  contextStrip: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  thread: {
    gap: theme.spacing.lg,
  },
  emptyCopy: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    lineHeight: 22,
  },
  userBubble: {
    alignSelf: "flex-end",
    backgroundColor: theme.colors.textPrimary,
    borderRadius: 18,
    maxWidth: "90%",
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
  },
  userText: {
    color: theme.colors.textInverse,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    lineHeight: 22,
  },
  assistantCard: {
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    gap: 10,
    padding: theme.spacing.lg,
  },
  cardLabel: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1.2,
    marginTop: 2,
    textTransform: "uppercase",
  },
  cardBody: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    lineHeight: 22,
  },
  evidenceList: {
    gap: 8,
  },
  evidenceItem: {
    borderLeftColor: theme.colors.borderStrong,
    borderLeftWidth: 1,
    gap: 4,
    paddingLeft: theme.spacing.md,
  },
  evidenceLabel: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
  },
  evidenceText: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 20,
  },
  promptRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  promptChip: {
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderSubtle,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    minHeight: 48,
    justifyContent: "center",
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  promptChipPressed: {
    opacity: 0.9,
  },
  promptChipText: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
  },
  composer: {
    alignItems: "flex-end",
    flexDirection: "row",
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  input: {
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderStrong,
    borderRadius: 18,
    borderWidth: 1,
    color: theme.colors.textPrimary,
    flex: 1,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    lineHeight: 22,
    minHeight: 56,
    paddingHorizontal: theme.spacing.md,
    paddingTop: 14,
    textAlignVertical: "top",
  },
  sendButton: {
    alignItems: "center",
    backgroundColor: theme.colors.actionPrimaryBg,
    borderRadius: theme.radius.pill,
    justifyContent: "center",
    minHeight: 56,
    minWidth: 96,
    paddingHorizontal: 18,
  },
  sendButtonPressed: {
    opacity: 0.88,
  },
  sendButtonText: {
    color: theme.colors.actionPrimaryText,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    fontWeight: "600",
  },
  errorText: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    marginTop: theme.spacing.md,
  },
});
