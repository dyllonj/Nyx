const KM_TO_MI = 0.621371;
const MIN_PER_KM_TO_MIN_PER_MI = 1.60934;

/** Format km as miles string, e.g. "3.1 mi" */
export function fmtMi(km: number, decimals = 1): string {
  return `${(km * KM_TO_MI).toFixed(decimals)} mi`;
}

/** Convert numeric min/km pace to "MM:SS min/mi" */
export function fmtPaceMi(minPerKm: number): string {
  const totalSec = minPerKm * MIN_PER_KM_TO_MIN_PER_MI * 60;
  const mins = Math.floor(totalSec / 60);
  const secs = Math.round(totalSec % 60);
  return `${mins}:${secs.toString().padStart(2, "0")} min/mi`;
}

/**
 * Convert a backend pace string (min/km) to min/mi.
 * Handles single values ("4:25") and ranges ("5:19\u20136:22").
 */
export function convertPaceStr(paceStr: string): string {
  return paceStr
    .split("\u2013")
    .map((part) => {
      const [minStr, secStr] = part.trim().split(":");
      const totalSec =
        (parseInt(minStr, 10) * 60 + parseInt(secStr, 10)) * MIN_PER_KM_TO_MIN_PER_MI;
      const mins = Math.floor(totalSec / 60);
      const secs = Math.round(totalSec % 60);
      return `${mins}:${secs.toString().padStart(2, "0")}`;
    })
    .join("\u2013");
}
