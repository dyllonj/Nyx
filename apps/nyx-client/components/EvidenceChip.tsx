import { Pressable, StyleSheet, Text, View } from "react-native";

import { theme } from "@/lib/theme/tokens";

type EvidenceChipProps = {
  label: string;
  text: string;
  onPress?: () => void;
};

export function EvidenceChip({ label, text, onPress }: EvidenceChipProps) {
  const content = (
    <View style={styles.base}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.text}>{text}</Text>
    </View>
  );

  if (!onPress) {
    return content;
  }

  return (
    <Pressable onPress={onPress} style={({ pressed }) => [pressed && styles.pressed]}>
      {content}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderLeftColor: theme.colors.borderStrong,
    borderLeftWidth: 1,
    gap: 4,
    paddingLeft: theme.spacing.md,
  },
  pressed: {
    opacity: 0.88,
  },
  label: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
  },
  text: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 14,
    lineHeight: 20,
  },
});
