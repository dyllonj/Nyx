const DEFAULT_API_PORT = "8000";

function resolveApiToken(): string | null {
  const token = process.env.EXPO_PUBLIC_API_TOKEN?.trim();
  return token ? token : null;
}

function resolveApiBaseUrl(): string {
  if (process.env.EXPO_PUBLIC_API_BASE_URL) {
    return process.env.EXPO_PUBLIC_API_BASE_URL;
  }

  if (typeof window !== "undefined") {
    if (process.env.NODE_ENV === "development") {
      return `${window.location.protocol}//${window.location.hostname}:${DEFAULT_API_PORT}`;
    }

    return window.location.origin;
  }

  return `http://127.0.0.1:${DEFAULT_API_PORT}`;
}

const API_BASE_URL = resolveApiBaseUrl();
const API_TOKEN = resolveApiToken();

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(API_TOKEN ? { Authorization: `Bearer ${API_TOKEN}` } : {}),
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    const message =
      payload?.error?.message ??
      payload?.detail ??
      `Request failed with status ${response.status}`;
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export const api = {
  getStatus: () => apiRequest<any>("/api/status"),
  getDoctor: () => apiRequest<any>("/api/doctor"),
  getAthleteSummary: () => apiRequest<any>("/api/athlete/summary"),
  getRuns: (limit = 10) => apiRequest<any>(`/api/runs?limit=${limit}`),
  getRun: (activityId: number | string) => apiRequest<any>(`/api/runs/${activityId}`),
  getCoachContext: () => apiRequest<any>("/api/coach/context"),
  getCurrentCoachThread: () => apiRequest<any>("/api/coach/thread/current"),
  createCoachThread: () =>
    apiRequest<any>("/api/coach/thread", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  recalcMetrics: () =>
    apiRequest<any>("/api/vdot/recalc", {
      method: "POST",
      body: JSON.stringify({}),
    }),
  startSync: () =>
    apiRequest<any>("/api/sync", {
      method: "POST",
      body: JSON.stringify({ interactive: false }),
    }),
  getSyncJob: (jobId: string) => apiRequest<any>(`/api/sync/${jobId}`),
  runOfflineEvals: () =>
    apiRequest<any>("/api/evals/run", {
      method: "POST",
      body: JSON.stringify({ live: false }),
    }),
  runLiveEvals: () =>
    apiRequest<any>("/api/evals/run", {
      method: "POST",
      body: JSON.stringify({ live: true }),
    }),
  generateTrainingPlan: (payload: {
    goal: string;
    weeks?: number;
    days_per_week?: number;
    current_vdot?: number;
  }) =>
    apiRequest<any>("/api/training-plan", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  postCoachFeedback: (payload: {
    thread_id: number;
    message_id: number;
    verdict: "helpful" | "too_generic" | "not_grounded" | "unsafe";
  }) =>
    apiRequest<any>("/api/coach/feedback", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  postCoachMessage: (payload: {
    message: string;
    thread_id?: number;
    conversation?: { role: string; content: string }[];
  }) =>
    apiRequest<any>("/api/coach/message", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
