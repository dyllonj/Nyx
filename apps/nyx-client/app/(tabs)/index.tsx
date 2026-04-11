import { useEffect, useState } from "react";
import { useRouter } from "expo-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";

import { AppFrame } from "@/components/AppFrame";
import { MetricPill } from "@/components/MetricPill";
import { SectionHeader } from "@/components/SectionHeader";
import { SignalRow } from "@/components/SignalRow";
import { Surface } from "@/components/Surface";
import { api } from "@/lib/api/client";
import { theme } from "@/lib/theme/tokens";

export default function HomeScreen() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [syncJobId, setSyncJobId] = useState<string | null>(null);
  const [syncJob, setSyncJob] = useState<any>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const summaryQuery = useQuery({
    queryKey: ["athlete-summary"],
    queryFn: api.getAthleteSummary,
  });
  const doctorQuery = useQuery({
    queryKey: ["doctor"],
    queryFn: api.getDoctor,
  });
  const runsQuery = useQuery({
    queryKey: ["runs", 3],
    queryFn: () => api.getRuns(3),
  });

  useEffect(() => {
    if (!syncJobId) {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const job = await api.getSyncJob(syncJobId);
        setSyncJob(job);
        if (job.status === "success" || job.status === "failed") {
          clearInterval(interval);
          setSyncJobId(null);
          if (job.status === "success") {
            queryClient.invalidateQueries({ queryKey: ["athlete-summary"] });
            queryClient.invalidateQueries({ queryKey: ["doctor"] });
            queryClient.invalidateQueries({ queryKey: ["runs", 3] });
          }
        }
      } catch (error) {
        clearInterval(interval);
        setSyncJobId(null);
        setSyncError(error instanceof Error ? error.message : "Unable to poll sync job.");
      }
    }, 1000);

    return () => clearInterval(interval);
  }, [queryClient, syncJobId]);

  const athlete = summaryQuery.data;
  const recentRuns = runsQuery.data?.runs ?? [];
  const doctorCounts = doctorQuery.data?.counts;
  const actionLabel = athlete?.next_action?.label ?? "Open Coach";

  async function handlePrimaryAction() {
    if (athlete?.next_action?.action === "sync") {
      try {
        setSyncError(null);
        const job = await api.startSync();
        setSyncJob(job);
        setSyncJobId(job.job_id);
      } catch (error) {
        setSyncError(error instanceof Error ? error.message : "Unable to start sync.");
      }
      return;
    }

    if (athlete?.next_action?.action === "diagnostics") {
      router.push("/diagnostics" as any);
      return;
    }

    if (athlete?.next_action?.action === "metrics") {
      await apiRequestRefresh(queryClient);
      return;
    }

    if (athlete?.next_action?.action === "athlete") {
      router.push("/athlete" as any);
      return;
    }

    router.push("/coach" as any);
  }

  return (
    <AppFrame
      title="Home"
      subtitle="A calm control surface for sync state, current fitness, and the next move."
      actionLabel={actionLabel}
      onActionPress={handlePrimaryAction}
    >
      <Surface>
        <SectionHeader
          eyebrow="Nyx"
          title="Local-first running intelligence"
          subtitle={athlete?.next_action?.reason ?? "Load athlete state, sync Garmin, and ground coaching in current data."}
        />
        <View style={styles.heroMetrics}>
          <MetricPill label="sync" value={athlete?.last_sync_status ?? "unknown"} />
          <MetricPill label="vdot" value={athlete?.vdot?.value ? String(athlete.vdot.value) : "not set"} />
          <MetricPill
            label="z2"
            value={
              athlete?.zone_2 ? `${athlete.zone_2.hr_low}-${athlete.zone_2.hr_high} bpm` : "not set"
            }
          />
        </View>
        <Text style={styles.heroLead}>
          {athlete?.vdot?.easy_pace
            ? `Easy pace ${athlete.vdot.easy_pace}/km`
            : "Sync data and refresh metrics to unlock current training paces."}
        </Text>
        {syncJob?.status === "running" || syncJob?.status === "queued" ? (
          <View style={styles.inlineStatus}>
            <ActivityIndicator color={theme.colors.textPrimary} />
            <Text style={styles.inlineStatusText}>Syncing Garmin activity history...</Text>
          </View>
        ) : null}
        {syncJob?.logs?.length ? (
          <Text style={styles.syncLog}>{syncJob.logs[syncJob.logs.length - 1]}</Text>
        ) : null}
        {syncError ? <Text style={styles.errorText}>{syncError}</Text> : null}
      </Surface>

      <Surface>
        <SectionHeader
          eyebrow="Coach status"
          title="Is Nyx helping right now?"
          subtitle="Progress, guidance quality, and safety stay separate so this screen does not fake precision."
        />
        <View style={styles.signalStack}>
          <SignalRow
            label="Progress"
            status={athlete?.coach_status?.progress?.status ?? "unknown"}
            summary={athlete?.coach_status?.progress?.summary ?? "Need more data to read direction of travel."}
          />
          <SignalRow
            label="Quality"
            status={athlete?.coach_status?.quality?.status ?? "unknown"}
            summary={athlete?.coach_status?.quality?.summary ?? "No coach feedback has been captured yet."}
          />
          <SignalRow
            label="Safety"
            status={athlete?.coach_status?.safety?.status ?? "unknown"}
            summary={athlete?.coach_status?.safety?.summary ?? "Safety checks need more recent data."}
          />
        </View>
        <Text style={styles.nextMove}>
          Next move: {athlete?.coach_status?.next_action?.reason ?? "Open Coach and pressure-test the next training decision."}
        </Text>
      </Surface>

      <View style={styles.twoColumn}>
        <Surface>
          <Text style={styles.kicker}>Current state</Text>
          <Text style={styles.statValue}>
            {athlete ? `${athlete.recent_42d_runs} runs / ${athlete.recent_42d_distance_km} km` : "Loading"}
          </Text>
          <Text style={styles.statHint}>Recent 42-day load</Text>
          <View style={styles.rule} />
          <Text style={styles.statValue}>
            {doctorCounts ? `${doctorCounts.pass} pass / ${doctorCounts.warn} warn / ${doctorCounts.fail} fail` : "Loading"}
          </Text>
          <Text style={styles.statHint}>Harness readiness</Text>
        </Surface>

        <Surface>
          <Text style={styles.kicker}>Current fitness</Text>
          <Text style={styles.statValue}>{athlete?.vdot?.threshold_pace ? `${athlete.vdot.threshold_pace}/km` : "n/a"}</Text>
          <Text style={styles.statHint}>Threshold pace</Text>
          <View style={styles.rule} />
          <Text style={styles.statValue}>
            {athlete?.rei_trend?.recent_avg ? String(athlete.rei_trend.recent_avg) : "n/a"}
          </Text>
          <Text style={styles.statHint}>Recent REI average</Text>
        </Surface>
      </View>

      <Surface>
        <SectionHeader
          eyebrow="Recent runs"
          title="The last three sessions"
          subtitle="This is what Nyx will lean on first when reasoning about what changed."
        />
        <View style={styles.runList}>
          {recentRuns.map((run: any) => (
            <Pressable
              key={run.activity_id}
              onPress={() => router.push(`/run/${run.activity_id}` as any)}
              style={({ pressed }) => [styles.runRow, pressed && styles.runRowPressed]}
            >
              <Text style={styles.runDate}>{run.start_time.slice(0, 10)}</Text>
              <Text style={styles.runMain}>{run.distance_km.toFixed(1)} km</Text>
              <Text style={styles.runMetric}>{run.pace_min_per_km ? `${run.pace_min_per_km.toFixed(2)} min/km` : "n/a"}</Text>
              <Text style={styles.runMetric}>{run.avg_hr ? `${Math.round(run.avg_hr)} bpm` : "n/a"}</Text>
              <Text style={styles.runMetric}>{run.rei ? `REI ${run.rei.toFixed(0)}` : "REI n/a"}</Text>
            </Pressable>
          ))}
        </View>
      </Surface>
    </AppFrame>
  );
}

async function apiRequestRefresh(queryClient: ReturnType<typeof useQueryClient>) {
  await api.recalcMetrics();
  queryClient.invalidateQueries({ queryKey: ["athlete-summary"] });
  queryClient.invalidateQueries({ queryKey: ["doctor"] });
}

const styles = StyleSheet.create({
  heroMetrics: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: theme.spacing.sm,
    marginTop: theme.spacing.lg,
  },
  heroLead: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 24,
    lineHeight: 28,
    marginTop: theme.spacing.lg,
  },
  inlineStatus: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    marginTop: theme.spacing.lg,
  },
  inlineStatusText: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
  },
  syncLog: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    marginTop: theme.spacing.md,
  },
  errorText: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    marginTop: theme.spacing.md,
  },
  twoColumn: {
    gap: theme.spacing.lg,
  },
  signalStack: {
    gap: theme.spacing.md,
    marginTop: theme.spacing.lg,
  },
  nextMove: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 20,
    marginTop: theme.spacing.lg,
  },
  kicker: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1.4,
    textTransform: "uppercase",
  },
  statValue: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 30,
    lineHeight: 34,
    marginTop: theme.spacing.md,
  },
  statHint: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    marginTop: 6,
  },
  rule: {
    backgroundColor: theme.colors.borderSubtle,
    height: 1,
    marginVertical: theme.spacing.lg,
  },
  runList: {
    gap: 10,
    marginTop: theme.spacing.lg,
  },
  runRow: {
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderSubtle,
    borderRadius: 14,
    borderWidth: 1,
    gap: 4,
    padding: theme.spacing.md,
  },
  runRowPressed: {
    opacity: 0.92,
  },
  runDate: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
  },
  runMain: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 22,
    lineHeight: 26,
  },
  runMetric: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
  },
});
