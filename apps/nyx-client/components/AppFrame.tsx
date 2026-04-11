import { Link, usePathname } from "expo-router";
import { ReactNode } from "react";
import {
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
} from "react-native";

import { theme } from "@/lib/theme/tokens";

type AppFrameProps = {
  title: string;
  subtitle: string;
  actionLabel?: string;
  onActionPress?: () => void;
  children: ReactNode;
};

const NAV_ITEMS = [
  { href: "/", label: "Home" },
  { href: "/athlete", label: "Athlete" },
  { href: "/coach", label: "Coach" },
  { href: "/diagnostics", label: "Diagnostics" },
];

export function AppFrame({
  title,
  subtitle,
  actionLabel,
  onActionPress,
  children,
}: AppFrameProps) {
  const pathname = usePathname();
  const { width } = useWindowDimensions();
  const wide = width >= 960;

  return (
    <SafeAreaView style={styles.safe}>
      <View style={[styles.root, wide && styles.rootWide]}>
        {wide ? <NavigationRail pathname={pathname} /> : null}
        <View style={styles.main}>
          <View style={styles.header}>
            <View style={styles.headerText}>
              <Text style={styles.headerTitle}>{title}</Text>
              <Text style={styles.headerSubtitle}>{subtitle}</Text>
            </View>
            {actionLabel && onActionPress ? (
              <Pressable onPress={onActionPress} style={({ pressed }) => [styles.primaryAction, pressed && styles.primaryActionPressed]}>
                <Text style={styles.primaryActionText}>{actionLabel}</Text>
              </Pressable>
            ) : null}
          </View>

          <ScrollView contentContainerStyle={styles.content}>{children}</ScrollView>
        </View>
      </View>
      {!wide ? <BottomNavigation pathname={pathname} /> : null}
    </SafeAreaView>
  );
}

function NavigationRail({ pathname }: { pathname: string }) {
  return (
    <View style={styles.rail}>
      <Text style={styles.brand}>NYX</Text>
      <Text style={styles.railCaption}>local running intelligence</Text>
      <View style={styles.navList}>
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link href={item.href as any} key={item.href} asChild>
              <Pressable style={[styles.navItem, active && styles.navItemActive]}>
                <Text style={[styles.navLabel, active && styles.navLabelActive]}>{item.label}</Text>
              </Pressable>
            </Link>
          );
        })}
      </View>
    </View>
  );
}

function BottomNavigation({ pathname }: { pathname: string }) {
  return (
    <View style={styles.bottomBar}>
      {NAV_ITEMS.map((item) => {
        const active = pathname === item.href;
        return (
          <Link href={item.href as any} key={item.href} asChild>
            <Pressable style={styles.bottomItem}>
              <Text style={[styles.bottomLabel, active && styles.bottomLabelActive]}>{item.label}</Text>
            </Pressable>
          </Link>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: {
    backgroundColor: theme.colors.bg,
    flex: 1,
  },
  root: {
    backgroundColor: theme.colors.bg,
    flex: 1,
  },
  rootWide: {
    flexDirection: "row",
  },
  rail: {
    borderRightColor: theme.colors.borderSubtle,
    borderRightWidth: 1,
    gap: 10,
    paddingHorizontal: theme.spacing.xl,
    paddingTop: theme.spacing.xxl,
    width: 240,
  },
  brand: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 34,
    letterSpacing: 1.6,
  },
  railCaption: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 1.2,
    textTransform: "uppercase",
  },
  navList: {
    gap: 8,
    marginTop: theme.spacing.xl,
  },
  navItem: {
    borderColor: theme.colors.borderSubtle,
    borderRadius: theme.radius.pill,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  navItemActive: {
    backgroundColor: theme.colors.surface2,
    borderColor: theme.colors.borderStrong,
  },
  navLabel: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
  },
  navLabelActive: {
    color: theme.colors.textPrimary,
  },
  main: {
    flex: 1,
  },
  header: {
    alignItems: "flex-start",
    borderBottomColor: theme.colors.borderSubtle,
    borderBottomWidth: 1,
    flexDirection: "row",
    gap: theme.spacing.lg,
    justifyContent: "space-between",
    paddingHorizontal: theme.spacing.xl,
    paddingVertical: theme.spacing.xl,
  },
  headerText: {
    flex: 1,
    gap: 6,
  },
  headerTitle: {
    color: theme.colors.textPrimary,
    fontFamily: theme.fonts.heading,
    fontSize: 30,
    lineHeight: 34,
  },
  headerSubtitle: {
    color: theme.colors.textSecondary,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    lineHeight: 22,
    maxWidth: 720,
  },
  primaryAction: {
    alignItems: "center",
    backgroundColor: theme.colors.actionPrimaryBg,
    borderRadius: theme.radius.pill,
    justifyContent: "center",
    minHeight: 48,
    minWidth: 144,
    paddingHorizontal: 18,
    paddingVertical: 12,
  },
  primaryActionPressed: {
    opacity: 0.88,
  },
  primaryActionText: {
    color: theme.colors.actionPrimaryText,
    fontFamily: theme.fonts.body,
    fontSize: 15,
    fontWeight: "600",
  },
  content: {
    alignSelf: "center",
    gap: theme.spacing.lg,
    maxWidth: 1120,
    paddingHorizontal: theme.spacing.xl,
    paddingTop: theme.spacing.xl,
    paddingBottom: 120,
    width: "100%",
  },
  bottomBar: {
    backgroundColor: theme.colors.surface1,
    borderTopColor: theme.colors.borderSubtle,
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-around",
    paddingBottom: theme.spacing.md,
    paddingTop: theme.spacing.sm,
  },
  bottomItem: {
    alignItems: "center",
    minHeight: 48,
    justifyContent: "center",
    paddingHorizontal: 10,
  },
  bottomLabel: {
    color: theme.colors.textTertiary,
    fontFamily: theme.fonts.mono,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: "uppercase",
  },
  bottomLabelActive: {
    color: theme.colors.textPrimary,
  },
});
