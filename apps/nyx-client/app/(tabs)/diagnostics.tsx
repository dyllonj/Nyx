import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { AppFrame } from "@/components/AppFrame";
import { SectionHeader } from "@/components/SectionHeader";
import { Surface } from "@/components/Surface";
import { api } from "@/lib/api/client";
import { theme } from "@/lib/theme/tokens";

export default function DiagnosticsScreen() {
  const statusQuery = useQuery({
    queryKey: ["status"],
    queryFn: api.getStatus,
  });
  const doctorQuery = useQuery({
    queryKey: ["doctor"],
    queryFn: api.getDoctor,
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
            {evals.results.map((result: any) => (
              <View key={result.eval_id} style={styles.item}>
                <Text style={styles.itemStatus}>[{result.status}]</Text>
                <View style={styles.itemText}>
                  <Text style={styles.itemTitle}>{result.eval_id}</Text>
                  <Text style={styles.subtle}>{result.summary}</Text>
                </View>
              </View>
            ))}
          </View>
        ) : null}
        {evalError ? <Text style={styles.hint}>{evalError}</Text> : null}
      </Surface>
    </AppFrame>
  );
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
});
