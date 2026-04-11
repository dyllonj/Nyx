import { Platform } from "react-native";

export const theme = {
  colors: {
    bg: "#050505",
    surface1: "#0b0b0b",
    surface2: "#121212",
    surface3: "#1a1a1a",
    borderSubtle: "#202020",
    borderStrong: "#2b2b2b",
    textPrimary: "#f5f5f5",
    textSecondary: "#b8b8b8",
    textTertiary: "#7a7a7a",
    textInverse: "#050505",
    actionPrimaryBg: "#f5f5f5",
    actionPrimaryText: "#050505",
  },
  spacing: {
    xs: 8,
    sm: 12,
    md: 16,
    lg: 20,
    xl: 24,
    xxl: 32,
  },
  radius: {
    card: 18,
    pill: 999,
  },
  fonts: {
    heading: Platform.select({
      web: "'Space Grotesk', sans-serif",
      default: "SpaceGrotesk_700Bold",
    }),
    body: Platform.select({
      web: "'IBM Plex Sans', sans-serif",
      default: "IBMPlexSans_400Regular",
    }),
    mono: Platform.select({
      web: "'IBM Plex Mono', monospace",
      default: "IBMPlexMono_500Medium",
    }),
  },
  shadows: {
    none: {
      shadowOpacity: 0,
      elevation: 0,
    },
  },
};
