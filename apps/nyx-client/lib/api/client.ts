const API_BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
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
  postCoachMessage: (payload: {
    message: string;
    conversation: { role: string; content: string }[];
  }) =>
    apiRequest<any>("/api/coach/message", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
