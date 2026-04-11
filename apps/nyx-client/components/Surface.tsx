import { ReactNode } from "react";
import { StyleSheet, View } from "react-native";

import { theme } from "@/lib/theme/tokens";

type SurfaceProps = {
  children: ReactNode;
  tone?: "base" | "raised" | "dense";
};

export function Surface({ children, tone = "base" }: SurfaceProps) {
  return <View style={[styles.base, styles[tone]]}>{children}</View>;
}

const styles = StyleSheet.create({
  base: {
    backgroundColor: theme.colors.surface1,
    borderWidth: 1,
    borderColor: theme.colors.borderStrong,
    borderRadius: theme.radius.card,
    padding: theme.spacing.lg,
  },
  raised: {
    backgroundColor: theme.colors.surface2,
  },
  dense: {
    backgroundColor: theme.colors.surface3,
  },
});
