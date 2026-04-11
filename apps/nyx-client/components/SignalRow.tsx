import { StyleSheet, Text, View } from "react-native";

import { StatusBadge } from "@/components/StatusBadge";
import { theme } from "@/lib/theme/tokens";

type SignalRowProps = {
  label: string;
  status: "on_track" | "mixed" | "at_risk" | "unknown";
  summary: string;
};

export function SignalRow({ label, status, summary }: SignalRowProps) {
  return (
    <View style={styles.row}>
      <View style={styles.header}>
        <Text style={styles.label}>{label}</Text>
        <StatusBadge status={status} />
      </View>
      <Text style={styles.summary}>{summary}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    borderBottomColor: theme.colors.borderSubtle,
    borderBottomWidth: 1,
    gap: 8,
    paddingBottom: theme.spacing.md,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  label: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 16,
    fontWeight: "600",
  },
  summary: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 20,
    maxWidth: 520,
  },
});
