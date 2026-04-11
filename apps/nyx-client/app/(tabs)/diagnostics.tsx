import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AppFrame } from "@/components/AppFrame";
import { SectionHeader } from "@/components/SectionHeader";
import { SignalRow } from "@/components/SignalRow";
import { Surface } from "@/components/Surface";
import { api } from "@/lib/api/client";
import { theme } from "@/lib/theme/tokens";

const CATEGORY_ORDER = ["grounding", "safety", "structure", "coverage"];

export default function DiagnosticsScreen() {
  const statusQuery = useQuery({
    queryKey: ["status"],
    queryFn: api.getStatus,
  });
  const doctorQuery = useQuery({
    queryKey: ["doctor"],
    queryFn: api.getDoctor,
  });
  const athleteQuery = useQuery({
    queryKey: ["athlete-summary"],
    queryFn: api.getAthleteSummary,
  });
  const [evals, setEvals] = useState<any>(null);
  const [evalError, setEvalError] = useState<string | null>(null);

  async function runOfflineEvals() {
    try {
      setEvalError(null);
      setEvals(await api.runOfflineEvals());
    } catch (error) {
      setEvalError(error instanceof Error ? error.message : "Unable to run evals.");
    }
  }

  const status = statusQuery.data;
  const doctor = doctorQuery.data;
  const athlete = athleteQuery.data;
  const feedbackCounts = athlete?.coach_status?.quality?.counts;
  const groupedResults = groupEvalResults(evals?.results ?? []);

  return (
    <AppFrame
      title="Diagnostics"
      subtitle="Harness readiness, doctor output, evals, and sync state without dropping back to the terminal."
      actionLabel="Run Offline Evals"
      onActionPress={runOfflineEvals}
    >
      <View style={styles.grid}>
        <Surface>
          <Text style={styles.label}>Last sync</Text>
          <Text style={styles.bigValue}>{status?.last_sync_status ?? "unknown"}</Text>
          <Text style={styles.subtle}>{status?.last_sync_completed_at ?? "No successful sync yet."}</Text>
        </Surface>
        <Surface>
          <Text style={styles.label}>Doctor</Text>
          <Text style={styles.bigValue}>
            {doctor ? `${doctor.counts.pass} / ${doctor.counts.warn} / ${doctor.counts.fail}` : "Loading"}
          </Text>
          <Text style={styles.subtle}>pass / warn / fail</Text>
        </Surface>
      </View>

      <Surface>
        <SectionHeader
          eyebrow="Checks"
          title="Doctor output"
          subtitle="Warnings and failures should be legible enough here that terminal access becomes optional."
        />
        <View style={styles.list}>
          {doctor?.checks?.map((check: any) => (
            <View key={check.name} style={styles.item}>
              <Text style={styles.itemStatus}>[{check.status}]</Text>
              <View style={styles.itemText}>
                <Text style={styles.itemTitle}>{check.name}</Text>
                <Text style={styles.subtle}>{check.summary}</Text>
                {check.hint ? <Text style={styles.hint}>{check.hint}</Text> : null}
              </View>
            </View>
          ))}
        </View>
      </Surface>

      <Surface>
        <SectionHeader
          eyebrow="Eval categories"
          title="Where the coach is weak"
          subtitle="Grounding, safety, structure, and coverage stay separate so one failure type does not hide another."
        />
        <View style={styles.list}>
          {orderedCategoryEntries(evals?.counts_by_category ?? {}).map(([category, counts]) => (
            <SignalRow
              key={category}
              label={formatCategoryName(category)}
              status={categoryStatus(counts as { pass: number; warn: number; fail: number })}
              summary={`${(counts as any).pass} pass / ${(counts as any).warn} warn / ${(counts as any).fail} fail`}
            />
          ))}
          {!evals?.counts_by_category ? (
            <Text style={styles.subtle}>Run an eval sweep to populate category summaries.</Text>
          ) : null}
        </View>
      </Surface>

      <Surface>
        <SectionHeader
          eyebrow="Evals"
          title="Harness checks"
          subtitle="Offline evals run quickly and validate that the coach contract is still intact."
        />
        <View style={styles.actionRow}>
          <Pressable onPress={runOfflineEvals} style={({ pressed }) => [styles.secondaryAction, pressed && styles.secondaryActionPressed]}>
            <Text style={styles.secondaryActionText}>Run offline evals</Text>
          </Pressable>
          <Pressable
            onPress={async () => {
              try {
                setEvalError(null);
                setEvals(await api.runLiveEvals());
              } catch (error) {
                setEvalError(error instanceof Error ? error.message : "Unable to run live evals.");
              }
            }}
            style={({ pressed }) => [styles.secondaryAction, pressed && styles.secondaryActionPressed]}
          >
            <Text style={styles.secondaryActionText}>Run live evals</Text>
          </Pressable>
        </View>
        {evals?.results?.length ? (
          <View style={styles.list}>
            {orderedCategoryEntries(groupedResults).map(([category, results]) => (
              <View key={category} style={styles.group}>
                <Text style={styles.groupTitle}>{formatCategoryName(category)}</Text>
                {results.map((result: any) => (
                  <View key={result.eval_id} style={styles.item}>
                    <Text style={styles.itemStatus}>[{result.status}]</Text>
                    <View style={styles.itemText}>
                      <Text style={styles.itemTitle}>{result.eval_id}</Text>
                      <Text style={styles.subtle}>{result.summary}</Text>
                    </View>
                  </View>
                ))}
              </View>
            ))}
          </View>
        ) : null}
        {evalError ? <Text style={styles.hint}>{evalError}</Text> : null}
      </Surface>

      <Surface>
        <SectionHeader
          eyebrow="Feedback"
          title="Response feedback summary"
          subtitle="This is the user-facing check on whether coach answers are landing as helpful, grounded, and safe."
        />
        <View style={styles.list}>
          <MetricLine label="Helpful" value={formatFeedbackCount(feedbackCounts?.helpful, feedbackCounts?.total)} />
          <MetricLine label="Too generic" value={formatFeedbackCount(feedbackCounts?.too_generic, feedbackCounts?.total)} />
          <MetricLine label="Not grounded" value={formatFeedbackCount(feedbackCounts?.not_grounded, feedbackCounts?.total)} />
          <MetricLine label="Unsafe" value={formatFeedbackCount(feedbackCounts?.unsafe, feedbackCounts?.total)} />
        </View>
      </Surface>
    </AppFrame>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricLine}>
      <Text style={styles.itemTitle}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

function categoryStatus(
  counts: { pass: number; warn: number; fail: number },
): "on_track" | "mixed" | "at_risk" | "unknown" {
  if (counts.fail > 0) {
    return "at_risk";
  }
  if (counts.warn > 0) {
    return "mixed";
  }
  if (counts.pass > 0) {
    return "on_track";
  }
  return "unknown";
}

function formatCategoryName(category: string): string {
  return category.charAt(0).toUpperCase() + category.slice(1);
}

function groupEvalResults(results: any[]): Record<string, any[]> {
  return results.reduce((groups: Record<string, any[]>, result) => {
    const category = result.category ?? "coverage";
    groups[category] = groups[category] ?? [];
    groups[category].push(result);
    return groups;
  }, {});
}

function orderedCategoryEntries(record: Record<string, any>) {
  return Object.entries(record).sort(([left], [right]) => {
    const leftIndex = CATEGORY_ORDER.indexOf(left);
    const rightIndex = CATEGORY_ORDER.indexOf(right);
    const normalizedLeft = leftIndex === -1 ? Number.MAX_SAFE_INTEGER : leftIndex;
    const normalizedRight = rightIndex === -1 ? Number.MAX_SAFE_INTEGER : rightIndex;
    return normalizedLeft - normalizedRight || left.localeCompare(right);
  });
}

function formatFeedbackCount(value?: number, total?: number) {
  if (!total) {
    return "n/a";
  }
  const percent = Math.round(((value ?? 0) / total) * 100);
  return `${value ?? 0} (${percent}%)`;
}

const styles = StyleSheet.create({
  grid: {
    gap: theme.spacing.lg,
  },
  label: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  bigValue: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 28,
    lineHeight: 32,
    marginTop: theme.spacing.md,
  },
  subtle: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 6,
  },
  hint: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.body,
    fontSize: 13,
    lineHeight: 19,
    marginTop: 8,
  },
  list: {
    gap: 12,
    marginTop: theme.spacing.lg,
  },
  item: {
    borderBottomColor: theme.colors.borderSubtle,
    borderBottomWidth: 1,
    flexDirection: "row",
    gap: theme.spacing.md,
    paddingBottom: theme.spacing.md,
  },
  itemStatus: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    marginTop: 2,
  },
  itemText: {
    flex: 1,
  },
  itemTitle: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    fontWeight: "600",
  },
  metricLine: {
    alignItems: "center",
    borderBottomColor: theme.colors.borderSubtle,
    borderBottomWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingBottom: theme.spacing.md,
  },
  metricValue: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.mono,
    fontSize: 13,
  },
  actionRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
    marginTop: theme.spacing.lg,
  },
  secondaryAction: {
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    minHeight: 48,
    justifyContent: "center",
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  secondaryActionPressed: {
    backgroundColor: theme.colors.surface2,
  },
  secondaryActionText: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
  },
  group: {
    gap: 12,
  },
  groupTitle: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 20,
    lineHeight: 24,
  },
});
