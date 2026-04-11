import { StyleSheet, Text, View } from "react-native";

import { theme } from "@/lib/theme/tokens";

type StatusBadgeProps = {
  status: "on_track" | "mixed" | "at_risk" | "unknown";
};

const LABELS: Record<StatusBadgeProps["status"], string> = {
  on_track: "On track",
  mixed: "Mixed",
  at_risk: "At risk",
  unknown: "Unknown",
};

export function StatusBadge({ status }: StatusBadgeProps) {
  return (
    <View style={[styles.base, styles[status]]}>
      <Text style={[styles.text, status === "on_track" && styles.textInverse]}>
        {LABELS[status]}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: "center",
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 32,
    minWidth: 84,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  on_track: {
    backgroundColor: theme.colors.textPrimary,
    borderColor: theme.colors.textPrimary,
  },
  mixed: {
    backgroundColor: theme.colors.surface3,
    borderColor: theme.colors.borderStrong,
  },
  at_risk: {
    backgroundColor: theme.colors.surface1,
    borderColor: theme.colors.textPrimary,
  },
  unknown: {
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderSubtle,
  },
  text: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: "uppercase",
  },
  textInverse: {
    color: theme.colors.textInverse,
  },
});
