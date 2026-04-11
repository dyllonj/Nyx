import { StyleSheet, Text, View } from "react-native";

import { theme } from "@/lib/theme/tokens";

type MetricPillProps = {
  label: string;
  value: string;
};

export function MetricPill({ label, value }: MetricPillProps) {
  return (
    <View style={styles.pill}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    backgroundColor: theme.colors.surface3,
    borderColor: theme.colors.borderSubtle,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  label: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
  },
  value: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
  },
});
