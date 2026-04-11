import { Pressable, StyleSheet, Text, View } from "react-native";

import { theme } from "@/lib/theme/tokens";

export type FeedbackVerdict = "helpful" | "too_generic" | "not_grounded" | "unsafe";

type FeedbackRowProps = {
  onSelect: (verdict: FeedbackVerdict) => void;
  selected?: FeedbackVerdict | null;
  busy?: boolean;
};

const OPTIONS: { verdict: FeedbackVerdict; label: string }[] = [
  { verdict: "helpful", label: "Helpful" },
  { verdict: "too_generic", label: "Too generic" },
  { verdict: "not_grounded", label: "Not grounded" },
  { verdict: "unsafe", label: "Unsafe" },
];

export function FeedbackRow({ onSelect, selected = null, busy = false }: FeedbackRowProps) {
  if (selected) {
    return (
      <Text style={styles.confirmation}>
        Marked {selected.replace("_", " ")}.
      </Text>
    );
  }

  return (
    <View style={styles.wrap}>
      {OPTIONS.map((option) => (
        <Pressable
          disabled={busy}
          key={option.verdict}
          onPress={() => onSelect(option.verdict)}
          style={({ pressed }) => [
            styles.option,
            (pressed || busy) && styles.optionPressed,
          ]}
        >
          <Text style={styles.optionText}>{option.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 10,
  },
  option: {
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    minHeight: 38,
    justifyContent: "center",
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  optionPressed: {
    backgroundColor: theme.colors.surface3,
  },
  optionText: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.body,
    fontSize: 13,
  },
  confirmation: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.body,
    fontSize: 13,
    lineHeight: 18,
  },
});
