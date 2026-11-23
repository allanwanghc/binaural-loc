import { api, type Ids, type PublicConfig, type TrialInfo, type TrialResponse } from "./api";
import type { AudioEngine } from "./audio";
import { ExternalizationRating } from "./externalization";
import { ResponsePanel } from "./responsePanel";
import { clicked, h, sleep } from "./ui";

const PRE_STIMULUS_MS = 600;

interface TrialEnv {
  app: HTMLElement;
  audio: AudioEngine;
  cfg: PublicConfig;
  ids: Ids;
  trial: TrialInfo;
  progress: string;
}

export async function runTrial({ app, audio, cfg, ids, trial, progress }: TrialEnv): Promise<void> {
  const startedAt = new Date().toISOString();
  const maxReplays = cfg.max_replays;

  app.replaceChildren();
  const status = h("div", { className: "status" });
  app.append(h("div", { className: "trial-header" }, h("div", { className: "progress", textContent: progress }), status));
  const panel = new ResponsePanel(app, cfg.response.mode);
  const rating = cfg.response.externalization === "rating"
    ? new ExternalizationRating(app, cfg.response.externalization_labels, cfg.text.externalization)
    : null;
  const replay = h("button", { textContent: "Play again", disabled: true });
  const confirm = h("button", { className: "primary", textContent: "Confirm", disabled: true });
  const error = h("div", { className: "status warning" });
  app.append(h("div", { className: "buttons" }, ...(maxReplays > 0 ? [replay] : []), confirm), error);

  let firstPlaybackEnd = 0;
  let replays = 0;
  let playing = false;
  let saving = false;

  const ready = () => panel.complete && (rating === null || rating.value !== null);
  const refresh = () => {
    confirm.disabled = playing || saving || !ready();
    replay.disabled = playing || saving || replays >= maxReplays;
    replay.textContent = maxReplays > 1 ? `Play again (${maxReplays - replays} left)` : "Play again";
  };
  panel.onChange = refresh;
  if (rating) rating.onChange = refresh;

  const setInputs = (on: boolean) => {
    panel.setEnabled(on);
    rating?.setEnabled(on);
  };

  const play = async () => {
    playing = true;
    setInputs(false);
    status.textContent = "Listen…";
    refresh();
    await audio.play(trial.audio);
    if (firstPlaybackEnd === 0) firstPlaybackEnd = performance.now(); // RT starts here
    playing = false;
    setInputs(true);
    status.textContent = "Where did the sound come from?";
    refresh();
  };

  replay.addEventListener("click", () => {
    replays++;
    void play();
  });

  setInputs(false);
  await sleep(PRE_STIMULUS_MS);
  await play();

  // stay on this trial until the answer is saved
  let feedback = null;
  for (;;) {
    await clicked(confirm);
    const s = panel.state;
    const response: TrialResponse = {
      response_azimuth: s.azimuth!,
      response_elevation: cfg.response.mode === "azimuth_only" ? null : s.elevation,
      response_externalization: rating?.value ?? null,
      rt_ms: Math.round(performance.now() - firstPlaybackEnd),
      n_replays: replays,
      n_azimuth_clicks: s.nAzimuthClicks,
      n_elevation_clicks: s.nElevationClicks,
      client_trial_started_at: startedAt,
      client_confirmed_at: new Date().toISOString(),
      audio_sample_rate: audio.ctx.sampleRate,
    };
    saving = true;
    setInputs(false);
    refresh();
    error.textContent = "";
    try {
      feedback = (await api.saveResponse(ids, trial.trial_index, response)).feedback;
      break;
    } catch (e) {
      error.textContent = `Could not save the answer (${(e as Error).message}). Please call the experimenter.`;
      saving = false;
      setInputs(true);
      refresh();
      confirm.textContent = "Try again";
    }
  }

  if (feedback) {
    panel.showFeedback(feedback);
    rating?.setEnabled(false);
    status.textContent = "";
    replay.remove();
    confirm.textContent = "Next";
    confirm.disabled = false;
    await clicked(confirm);
  }
}
