import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
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

type CoachThread = {
  id: number;
  title: string | null;
  created_at: string;
  updated_at: string;
};

type PersistedCoachMessage = {
  id: number;
  thread_id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

type CoachThreadPayload = {
  thread: CoachThread;
  messages: PersistedCoachMessage[];
  message_count: number;
};

const DEFAULT_PROMPTS = [
  "What should my easy pace be right now?",
  "Am I running my easy runs too hard?",
  "What should I do this week?",
  "Why did my last run feel harder?",
];

export default function CoachScreen() {
  const queryClient = useQueryClient();
  const contextQuery = useQuery({
    queryKey: ["coach-context"],
    queryFn: api.getCoachContext,
  });
  const threadQuery = useQuery<CoachThreadPayload>({
    queryKey: ["coach-thread-current"],
    queryFn: api.getCurrentCoachThread,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  const [threadId, setThreadId] = useState<number | null>(null);
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!threadQuery.data) {
      return;
    }

    setThreadId(threadQuery.data.thread.id);
    setMessages(hydrateConversation(threadQuery.data.messages));
  }, [threadQuery.data]);

  async function ensureThreadId() {
    if (threadId) {
      return threadId;
    }

    const payload = threadQuery.data ?? (await api.getCurrentCoachThread());
    if (!threadQuery.data) {
      queryClient.setQueryData(["coach-thread-current"], payload);
    }
    setThreadId(payload.thread.id);
    return payload.thread.id;
  }

  async function handleNewChat() {
    if (busy) {
      return;
    }

    try {
      setError(null);
      const payload: CoachThreadPayload = await api.createCoachThread();
      setThreadId(payload.thread.id);
      setMessages([]);
      setDraft("");
      queryClient.setQueryData(["coach-thread-current"], payload);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to start a new chat.");
    }
  }

  async function submit(message: string) {
    const trimmed = message.trim();
    if (!trimmed || busy) {
      return;
    }

    const activeThreadId = await ensureThreadId();
    const previousMessages = messages;
    const nextMessages: ChatTurn[] = [
      ...messages,
      { role: "user", content: trimmed },
    ];
    setMessages(nextMessages);
    setDraft("");
    setBusy(true);
    setError(null);

    try {
      const response = await api.postCoachMessage({
        message: trimmed,
        thread_id: activeThreadId,
      });

      setThreadId(response.thread?.id ?? activeThreadId);
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
      queryClient.invalidateQueries({ queryKey: ["coach-thread-current"] });
    } catch (requestError) {
      setMessages(previousMessages);
      setError(requestError instanceof Error ? requestError.message : "Coach request failed.");
    } finally {
      setBusy(false);
    }
  }

  const context = contextQuery.data;
  const thread = threadQuery.data?.thread;
  const threadMeta = threadQuery.isLoading && !threadId
    ? "Loading saved chat..."
    : messages.length > 0
      ? `Resuming ${thread?.title ?? "latest chat"} · ${formatTimestamp(thread?.updated_at)}`
      : "This chat persists across refreshes and backend restarts.";
  const visibleError =
    error ??
    (threadQuery.error instanceof Error ? threadQuery.error.message : null);

  return (
    <AppFrame
      title="Coach"
      subtitle="Conversation stays grounded in athlete data, explicit evidence, and retrieved source labels."
      actionLabel="New chat"
      onActionPress={handleNewChat}
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
        <Text style={styles.threadMeta}>{threadMeta}</Text>
      </Surface>

      <Surface>
        <ScrollView contentContainerStyle={styles.thread}>
          {messages.length === 0 ? (
            <Text style={styles.emptyCopy}>
              {threadQuery.isLoading
                ? "Loading saved coach thread."
                : "Nyx now restores your active coach thread automatically. Ask about pace, load, or execution, and the conversation will still be here on refresh."}
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
        {visibleError ? <Text style={styles.errorText}>{visibleError}</Text> : null}
      </Surface>
    </AppFrame>
  );
}

function hydrateConversation(messages: PersistedCoachMessage[]): ChatTurn[] {
  return messages.map((message) => ({
    role: message.role,
    content: message.content,
    structured: message.role === "assistant" ? parseStructuredMessage(message.content) : undefined,
  }));
}

function parseStructuredMessage(content: string): ChatTurn["structured"] | undefined {
  let verdict = "";
  const evidence: { label: string; text: string }[] = [];
  let nextStep = "";
  let section: "verdict" | "evidence" | "next_step" | null = null;

  for (const rawLine of content.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) {
      continue;
    }

    const lowered = line.toLowerCase();
    if (lowered.startsWith("verdict:")) {
      section = "verdict";
      verdict = line.split(":", 2)[1]?.trim() ?? "";
      continue;
    }
    if (lowered.startsWith("evidence:")) {
      section = "evidence";
      continue;
    }
    if (lowered.startsWith("next step:")) {
      section = "next_step";
      nextStep = line.split(":", 2)[1]?.trim() ?? "";
      continue;
    }

    if (section === "verdict") {
      verdict = `${verdict} ${line}`.trim();
    } else if (section === "evidence" && (line.startsWith("-") || line.startsWith("*"))) {
      const evidenceText = line.slice(1).trim();
      evidence.push({
        label: evidenceLabel(evidenceText),
        text: evidenceText,
      });
    } else if (section === "next_step") {
      nextStep = `${nextStep} ${line}`.trim();
    }
  }

  if (!verdict && evidence.length === 0 && !nextStep) {
    return undefined;
  }

  return {
    verdict: verdict || content,
    evidence,
    next_step: nextStep,
  };
}

function evidenceLabel(text: string): string {
  const sourceMatch = text.match(/\[Source:\s*([^\]]+)\]/i);
  if (sourceMatch) {
    return sourceMatch[1].trim();
  }

  const dateMatch = text.match(/\b20\d{2}-\d{2}-\d{2}\b/);
  if (dateMatch) {
    return dateMatch[0];
  }

  if (/VDOT|Zone\b|pace/i.test(text)) {
    return "Current metrics";
  }

  return "Evidence";
}

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return "just now";
  }
  return value.replace("T", " ");
}

const styles = StyleSheet.create({
  contextStrip: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
  },
  threadMeta: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 20,
    marginTop: theme.spacing.md,
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
    marginBottom: theme.spacing.lg,
  },
  promptChip: {
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  promptChipPressed: {
    backgroundColor: theme.colors.surface3,
  },
  promptChipText: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
  },
  composer: {
    alignItems: "flex-end",
    flexDirection: "row",
    gap: theme.spacing.md,
  },
  input: {
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.card,
    borderWidth: 1,
    color: theme.colors.textPrimary,
    flex: 1,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    lineHeight: 22,
    maxHeight: 160,
    minHeight: 72,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.md,
    textAlignVertical: "top",
  },
  sendButton: {
    alignItems: "center",
    backgroundColor: theme.colors.actionPrimaryBg,
    borderRadius: theme.radius.pill,
    justifyContent: "center",
    minHeight: 48,
    minWidth: 96,
    paddingHorizontal: 18,
  },
  sendButtonPressed: {
    opacity: 0.72,
  },
  sendButtonText: {
    color: theme.colors.actionPrimaryText,
    fontFamily: theme.fonts.mono,
    fontSize: 13,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  errorText: {
    color: "#ff8d8d",
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 20,
    marginTop: theme.spacing.md,
  },
});
