import { useEffect, useState } from "react";
import { useRouter } from "expo-router";
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
import { EvidenceChip } from "@/components/EvidenceChip";
import { FeedbackRow, type FeedbackVerdict } from "@/components/FeedbackRow";
import { MetricPill } from "@/components/MetricPill";
import { StatusBadge } from "@/components/StatusBadge";
import { Surface } from "@/components/Surface";
import { api } from "@/lib/api/client";
import { theme } from "@/lib/theme/tokens";

type EvidenceItem = {
  label: string;
  text: string;
  kind?: "run" | "metric" | "knowledge";
  activity_id?: number;
  source?: string;
};

type StructuredMessage = {
  verdict: string;
  evidence: EvidenceItem[];
  next_step: string;
};

type CoachFeedback = {
  id: number;
  thread_id: number;
  message_id: number;
  verdict: FeedbackVerdict;
  created_at: string;
  updated_at: string;
};

type ChatTurn = {
  id?: number;
  thread_id?: number;
  role: "user" | "assistant";
  content: string;
  structured?: StructuredMessage;
  feedback?: CoachFeedback | null;
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
  structured?: StructuredMessage;
  feedback?: CoachFeedback | null;
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
  const router = useRouter();
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
  const [feedbackBusyId, setFeedbackBusyId] = useState<number | null>(null);
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
        response.assistant_message
          ? {
              id: response.assistant_message.id,
              thread_id: response.assistant_message.thread_id,
              role: "assistant",
              content: response.raw_text,
              structured: response.assistant_message.structured ?? {
                verdict: response.verdict,
                evidence: response.evidence ?? [],
                next_step: response.next_step,
              },
              feedback: response.assistant_message.feedback ?? null,
            }
          : {
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

  async function submitFeedback(messageId: number, verdict: FeedbackVerdict, targetThreadId?: number) {
    const activeThreadId = targetThreadId ?? threadId;
    if (!activeThreadId || feedbackBusyId) {
      return;
    }

    try {
      setError(null);
      setFeedbackBusyId(messageId);
      const response = await api.postCoachFeedback({
        thread_id: activeThreadId,
        message_id: messageId,
        verdict,
      });

      setMessages((current) =>
        current.map((message) =>
          message.id === messageId
            ? {
                ...message,
                feedback: response.feedback,
              }
            : message,
        ),
      );
      queryClient.invalidateQueries({ queryKey: ["coach-context"] });
      queryClient.invalidateQueries({ queryKey: ["athlete-summary"] });
      queryClient.invalidateQueries({ queryKey: ["coach-thread-current"] });
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "Unable to save coach feedback.");
    } finally {
      setFeedbackBusyId(null);
    }
  }

  function handleEvidencePress(item: EvidenceItem) {
    if (item.kind === "run" && item.activity_id) {
      router.push(`/run/${item.activity_id}` as any);
      return;
    }

    if (item.kind === "metric") {
      router.push("/athlete" as any);
    }
  }

  const context = contextQuery.data;
  const thread = threadQuery.data?.thread;
  const qualitySummary = context?.quality_summary;
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
        <View style={styles.qualityRow}>
          <Text style={styles.qualityLabel}>Guidance quality</Text>
          <StatusBadge status={qualitySummary?.status ?? "unknown"} />
        </View>
        <Text style={styles.threadMeta}>
          {qualitySummary?.summary ?? "No coach feedback has been captured yet."}
        </Text>
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
              <View key={message.id ?? `${message.role}-${index}`} style={styles.userBubble}>
                <Text style={styles.userText}>{message.content}</Text>
              </View>
            ) : (
              <View key={message.id ?? `${message.role}-${index}`} style={styles.assistantCard}>
                <Text style={styles.cardLabel}>Verdict</Text>
                <Text style={styles.cardBody}>{message.structured?.verdict ?? message.content}</Text>
                {message.structured?.evidence?.length ? (
                  <>
                    <Text style={styles.cardLabel}>Evidence</Text>
                    <View style={styles.evidenceList}>
                      {message.structured.evidence.map((item, evidenceIndex) => (
                        <EvidenceChip
                          key={`${message.id ?? index}-${evidenceIndex}`}
                          label={item.label}
                          onPress={
                            item.kind === "run" || item.kind === "metric"
                              ? () => handleEvidencePress(item)
                              : undefined
                          }
                          text={item.text}
                        />
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
                <Text style={styles.cardLabel}>Was this useful?</Text>
                <FeedbackRow
                  busy={feedbackBusyId === message.id}
                  onSelect={(verdict) => {
                    if (message.id) {
                      void submitFeedback(message.id, verdict, message.thread_id);
                    }
                  }}
                  selected={message.feedback?.verdict ?? null}
                />
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
    id: message.id,
    thread_id: message.thread_id,
    role: message.role,
    content: message.content,
    structured:
      message.role === "assistant"
        ? message.structured ?? parseStructuredMessage(message.content)
        : undefined,
    feedback: message.feedback ?? null,
  }));
}

function parseStructuredMessage(content: string): StructuredMessage | undefined {
  let verdict = "";
  const evidence: EvidenceItem[] = [];
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
  qualityRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    marginTop: theme.spacing.lg,
  },
  qualityLabel: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 16,
    fontWeight: "600",
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
    maxHeight: 140,
    minHeight: 56,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 14,
    textAlignVertical: "top",
  },
  sendButton: {
    alignItems: "center",
    backgroundColor: theme.colors.textPrimary,
    borderRadius: theme.radius.pill,
    justifyContent: "center",
    minHeight: 48,
    minWidth: 92,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  sendButtonPressed: {
    opacity: 0.88,
  },
  sendButtonText: {
    color: theme.colors.textInverse,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    fontWeight: "600",
  },
  errorText: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    marginTop: theme.spacing.md,
  },
});
