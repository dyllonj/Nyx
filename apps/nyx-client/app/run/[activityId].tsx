import { useLocalSearchParams } from "expo-router";
import { useQuery } from "@tanstack/react-query";
import { StyleSheet, Text, View } from "react-native";

import { AppFrame } from "@/components/AppFrame";
import { SectionHeader } from "@/components/SectionHeader";
import { Surface } from "@/components/Surface";
import { api } from "@/lib/api/client";
import { theme } from "@/lib/theme/tokens";

export default function RunDetailScreen() {
  const { activityId } = useLocalSearchParams<{ activityId: string }>();
  const runQuery = useQuery({
    queryKey: ["run", activityId],
    queryFn: () => api.getRun(activityId ?? ""),
    enabled: Boolean(activityId),
  });

  const run = runQuery.data?.run;
  const laps = runQuery.data?.laps ?? [];

  return (
    <AppFrame
      title="Run detail"
      subtitle="A single session view for the evidence chips and the athlete screen."
    >
      <Surface>
        <SectionHeader
          eyebrow={run?.start_time?.slice(0, 10) ?? "run"}
          title={run?.name ?? "Loading run"}
          subtitle="This screen is intentionally sparse: the point is to give evidence items somewhere factual to land."
        />
        {run ? (
          <View style={styles.metrics}>
            <MetricLine label="Distance" value={`${run.distance_km.toFixed(1)} km`} />
            <MetricLine label="Pace" value={run.pace_min_per_km ? `${run.pace_min_per_km.toFixed(2)} min/km` : "n/a"} />
            <MetricLine label="Average HR" value={run.avg_hr ? `${Math.round(run.avg_hr)} bpm` : "n/a"} />
            <MetricLine label="REI" value={run.rei ? run.rei.toFixed(1) : "n/a"} />
            <MetricLine label="HR drift" value={run.hr_drift_pct ? `${run.hr_drift_pct.toFixed(1)}%` : "n/a"} />
            <MetricLine label="Cadence CV" value={run.cadence_cv ? `${run.cadence_cv.toFixed(1)}%` : "n/a"} />
          </View>
        ) : null}
      </Surface>

      <Surface>
        <SectionHeader
          eyebrow="Laps"
          title="Split detail"
          subtitle="Lap data stays close to the raw session so coaching claims can point back to concrete pacing behavior."
        />
        <View style={styles.lapList}>
          {laps.map((lap: any) => (
            <View key={lap.lap_index} style={styles.lapRow}>
              <Text style={styles.lapTitle}>Lap {lap.lap_index + 1}</Text>
              <Text style={styles.lapText}>
                {lap.distance_m ? `${(lap.distance_m / 1000).toFixed(2)} km` : "n/a"} ·{" "}
                {lap.avg_hr ? `${Math.round(lap.avg_hr)} bpm` : "n/a"} ·{" "}
                {lap.avg_cadence_spm ? `${Math.round(lap.avg_cadence_spm)} spm` : "n/a"}
              </Text>
            </View>
          ))}
        </View>
      </Surface>
    </AppFrame>
  );
}

function MetricLine({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.metricRow}>
      <Text style={styles.metricLabel}>{label}</Text>
      <Text style={styles.metricValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  metrics: {
    gap: 10,
    marginTop: theme.spacing.lg,
  },
  metricRow: {
    alignItems: "center",
    borderBottomColor: theme.colors.borderSubtle,
    borderBottomWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingBottom: theme.spacing.md,
  },
  metricLabel: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
  },
  metricValue: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.mono,
    fontSize: 13,
  },
  lapList: {
    gap: 10,
    marginTop: theme.spacing.lg,
  },
  lapRow: {
    borderBottomColor: theme.colors.borderSubtle,
    borderBottomWidth: 1,
    paddingBottom: theme.spacing.md,
  },
  lapTitle: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    fontWeight: "600",
  },
  lapText: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 20,
    marginTop: 4,
  },
});
