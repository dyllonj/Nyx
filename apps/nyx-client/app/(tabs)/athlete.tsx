import { useQuery } from "@tanstack/react-query";
import { StyleSheet, Text, View } from "react-native";

import { AppFrame } from "@/components/AppFrame";
import { SectionHeader } from "@/components/SectionHeader";
import { Surface } from "@/components/Surface";
import { api } from "@/lib/api/client";
import { theme } from "@/lib/theme/tokens";

export default function AthleteScreen() {
  const summaryQuery = useQuery({
    queryKey: ["athlete-summary"],
    queryFn: api.getAthleteSummary,
  });
  const runsQuery = useQuery({
    queryKey: ["runs", 8],
    queryFn: () => api.getRuns(8),
  });

  const athlete = summaryQuery.data;
  const runs = runsQuery.data?.runs ?? [];

  return (
    <AppFrame
      title="Athlete"
      subtitle="Recent load, current paces, and the signals Nyx is using to reason about progression."
    >
      <View style={styles.grid}>
        <Surface>
          <Text style={styles.label}>42-day load</Text>
          <Text style={styles.bigValue}>
            {athlete ? `${athlete.recent_42d_runs} runs / ${athlete.recent_42d_distance_km} km` : "Loading"}
          </Text>
        </Surface>
        <Surface>
          <Text style={styles.label}>REI trend</Text>
          <Text style={styles.bigValue}>
            {athlete?.rei_trend?.recent_avg ? athlete.rei_trend.recent_avg : "n/a"}
          </Text>
          <Text style={styles.subtle}>
            {athlete?.rei_trend?.delta_vs_prior
              ? `${athlete.rei_trend.delta_vs_prior > 0 ? "+" : ""}${athlete.rei_trend.delta_vs_prior} vs prior block`
              : "Need more runs for a stronger read."}
          </Text>
        </Surface>
      </View>

      <Surface>
        <SectionHeader
          eyebrow="Training paces"
          title={athlete?.vdot?.value ? `VDOT ${athlete.vdot.value}` : "VDOT not estimated yet"}
          subtitle="Daniels-derived paces stay front and center because they answer the most common coaching questions fast."
        />
        <View style={styles.metricStack}>
          <MetricRow label="Easy" value={athlete?.vdot?.easy_pace ? `${athlete.vdot.easy_pace}/km` : "n/a"} />
          <MetricRow label="Marathon" value={athlete?.vdot?.marathon_pace ? `${athlete.vdot.marathon_pace}/km` : "n/a"} />
          <MetricRow label="Threshold" value={athlete?.vdot?.threshold_pace ? `${athlete.vdot.threshold_pace}/km` : "n/a"} />
          <MetricRow label="Interval" value={athlete?.vdot?.interval_pace ? `${athlete.vdot.interval_pace}/km` : "n/a"} />
        </View>
      </Surface>

      <Surface>
        <SectionHeader
          eyebrow="Heart rate"
          title="Karvonen zones"
          subtitle="Zone 2 gets privileged visually because easy-day execution is the most common recreational failure mode."
        />
        <View style={styles.metricStack}>
          {athlete?.hr_zones?.zones?.map((zone: any) => (
            <MetricRow
              key={zone.zone}
              label={`Zone ${zone.zone} ${zone.name}`}
              value={`${zone.hr_low}-${zone.hr_high} bpm`}
              emphasized={zone.zone === 2}
            />
          ))}
        </View>
      </Surface>

      <Surface>
        <SectionHeader
          eyebrow="Recent runs"
          title="Raw sessions"
          subtitle="Recent runs remain directly visible so the UI never turns into a black-box summary wall."
        />
        <View style={styles.runStack}>
          {runs.map((run: any) => (
            <View key={run.activity_id} style={styles.runCard}>
              <Text style={styles.runDate}>{run.start_time.slice(0, 10)}</Text>
              <Text style={styles.runTitle}>{run.distance_km.toFixed(1)} km</Text>
              <Text style={styles.subtle}>
                {run.pace_min_per_km ? `${run.pace_min_per_km.toFixed(2)} min/km` : "n/a"} ·{" "}
                {run.avg_hr ? `${Math.round(run.avg_hr)} bpm` : "n/a"} ·{" "}
                {run.rei ? `REI ${run.rei.toFixed(0)}` : "REI n/a"}
              </Text>
            </View>
          ))}
        </View>
      </Surface>
    </AppFrame>
  );
}

function MetricRow({
  label,
  value,
  emphasized = false,
}: {
  label: string;
  value: string;
  emphasized?: boolean;
}) {
  return (
    <View style={[styles.row, emphasized && styles.rowEmphasized]}>
      <Text style={[styles.rowLabel, emphasized && styles.rowLabelEmphasized]}>{label}</Text>
      <Text style={[styles.rowValue, emphasized && styles.rowValueEmphasized]}>{value}</Text>
    </View>
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
  metricStack: {
    gap: 10,
    marginTop: theme.spacing.lg,
  },
  row: {
    alignItems: "center",
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderSubtle,
    borderRadius: 14,
    borderWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    minHeight: 52,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 12,
  },
  rowEmphasized: {
    backgroundColor: theme.colors.textPrimary,
  },
  rowLabel: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
  },
  rowLabelEmphasized: {
    color: theme.colors.textInverse,
  },
  rowValue: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.mono,
    fontSize: 13,
  },
  rowValueEmphasized: {
    color: theme.colors.textInverse,
  },
  runStack: {
    gap: 10,
    marginTop: theme.spacing.lg,
  },
  runCard: {
    borderBottomColor: theme.colors.borderSubtle,
    borderBottomWidth: 1,
    paddingBottom: theme.spacing.md,
  },
  runDate: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
  },
  runTitle: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 22,
    lineHeight: 26,
    marginTop: 4,
  },
});
