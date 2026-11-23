// Nothing in this API may reveal a condition or (before a response) a target.

export interface PublicConfig {
  title: string;
  sample_rate: number;
  max_replays: number;
  rest_min_seconds: number;
  response: {
    mode: "azimuth_only" | "azimuth_elevation";
    externalization: "off" | "rating";
    externalization_labels: string[];
  };
  text: Record<string, string>;
}

export interface TrialInfo {
  trial_index: number;
  block: number;
  is_training: boolean;
  audio: string;
}

export interface SessionInfo {
  trials: TrialInfo[];
  completed: number[];
  volume_reference: string;
}

export interface Ids {
  participant_id: string;
  session_id: string;
}

export interface TrialResponse {
  response_azimuth: number;
  response_elevation: number | null;
  response_externalization: number | null;
  rt_ms: number;
  n_replays: number;
  n_azimuth_clicks: number;
  n_elevation_clicks: number;
  client_trial_started_at: string;
  client_confirmed_at: string;
  audio_sample_rate: number;
}

export interface Direction {
  azimuth: number;
  elevation: number;
}

export interface SaveResult {
  status: "saved" | "duplicate";
  feedback: Direction | null;
}

async function call<T>(method: string, url: string, body?: unknown): Promise<T> {
  const resp = await fetch(url, {
    method,
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`;
    try {
      const j = await resp.json();
      if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      // not JSON
    }
    throw new Error(detail);
  }
  return resp.json() as Promise<T>;
}

export const api = {
  config: () => call<PublicConfig>("GET", "/api/config"),
  openSession: (ids: Ids) => call<SessionInfo>("POST", "/api/session", ids),
  saveResponse: (ids: Ids, trialIndex: number, r: TrialResponse) =>
    call<SaveResult>("POST", `/api/trials/${trialIndex}/response`, { ...ids, ...r }),
  event: (ids: Ids, event: string, data: Record<string, unknown> = {}) =>
    call<{ status: string }>("POST", "/api/event", { ...ids, event, data }),
};
