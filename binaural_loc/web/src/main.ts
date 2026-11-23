import "./style.css";
import { api, type Ids, type PublicConfig, type SessionInfo, type TrialInfo } from "./api";
import { AudioEngine } from "./audio";
import { ExternalizationRating } from "./externalization";
import { ResponsePanel } from "./responsePanel";
import { runTrial } from "./trial";
import { clicked, h, paragraph, screen, sleep } from "./ui";

const PREFETCH = 6; // trials decoded ahead

const app = document.getElementById("app")!;

function warnBeforeLeaving(ev: BeforeUnloadEvent): void {
  ev.preventDefault();
}

// Only a log, so a failed write must not stop the session.
async function logEvent(ids: Ids, event: string, data: Record<string, unknown> = {}): Promise<void> {
  try {
    await api.event(ids, event, data);
  } catch (e) {
    console.warn(`event "${event}" not logged`, e);
  }
}

function fatal(message: string): never {
  window.removeEventListener("beforeunload", warnBeforeLeaving);
  screen(app, h("h1", { textContent: "Something went wrong" }), h("p", { className: "warning", textContent: message }),
    paragraph("Please call the experimenter. Reloading the page resumes after the last saved answer."));
  throw new Error(message);
}

async function startPage(cfg: PublicConfig, audio: AudioEngine): Promise<{ ids: Ids; session: SessionInfo }> {
  const pid = h("input", { id: "pid", autocomplete: "off", spellcheck: false });
  const sid = h("input", { id: "sid", autocomplete: "off", spellcheck: false, value: "S1" });
  const start = h("button", { className: "primary", textContent: "Start", type: "submit" });
  const status = h("div", { className: "status" });
  const form = h("form", { className: "form" },
    h("label", { htmlFor: "pid", textContent: "Participant ID" }), pid,
    h("label", { htmlFor: "sid", textContent: "Session ID" }), sid,
    start);
  screen(app, h("h1", { textContent: cfg.title }), h("div", { className: "subtle", textContent: "Experimenter setup" }),
    form, status);
  pid.focus();

  const problems: string[] = [];
  const deviceRate = AudioEngine.deviceSampleRate();
  if (deviceRate !== cfg.sample_rate || audio.ctx.sampleRate !== cfg.sample_rate) {
    problems.push(`The audio output device runs at ${deviceRate} Hz but the stimuli are ${cfg.sample_rate} Hz, ` +
      `so the browser would resample. Set the output device to ${cfg.sample_rate} Hz ` +
      `(macOS: Audio MIDI Setup) and reload this page.`);
  }
  if (audio.ctx.destination.maxChannelCount < 2) problems.push("The audio output is not stereo.");
  if (problems.length) {
    status.className = "status warning";
    status.textContent = problems.join(" ");
    start.disabled = true;
    return new Promise(() => {}); // dead end until reload
  }

  for (;;) {
    await new Promise<void>((resolve) => form.addEventListener("submit", (e) => { e.preventDefault(); resolve(); }, { once: true }));
    const unlocked = audio.unlock();
    const ids = { participant_id: pid.value.trim(), session_id: sid.value.trim() };
    start.disabled = true;
    status.className = "status";
    status.textContent = "Loading…";
    try {
      await unlocked;
      const session = await api.openSession(ids);
      return { ids, session };
    } catch (e) {
      status.className = "status warning";
      status.textContent = (e as Error).message;
      start.disabled = false;
    }
  }
}

async function resumePage(done: number, total: number): Promise<void> {
  const go = h("button", { className: "primary", textContent: "Continue" });
  screen(app, h("h1", { textContent: "Resuming session" }),
    paragraph(`${done} of ${total} answers are already saved. The session continues with the next trial.`), go);
  await clicked(go);
}

async function lrCheckPage(audio: AudioEngine, ids: Ids): Promise<void> {
  const left = h("button", { textContent: "Play LEFT" });
  const right = h("button", { textContent: "Play RIGHT" });
  const ok = h("input", { type: "checkbox", id: "lr-ok" });
  const go = h("button", { className: "primary", textContent: "Continue", disabled: true });
  left.onclick = () => void audio.playBuffer(audio.channelTestBuffer(0));
  right.onclick = () => void audio.playBuffer(audio.channelTestBuffer(1));
  ok.onchange = () => (go.disabled = !ok.checked);
  screen(app, h("h1", { textContent: "Left / right check" }), h("div", { className: "subtle", textContent: "Experimenter" }),
    paragraph("Put the headphones on yourself. Each button plays three beeps in one ear only."),
    h("div", { className: "buttons" }, left, right),
    h("label", { className: "check" }, ok, " LEFT beeps came from the left ear cup and RIGHT beeps from the right"),
    go);
  await clicked(go);
  audio.stop();
  await logEvent(ids, "lr_check_confirmed");
}

async function volumePage(cfg: PublicConfig, audio: AudioEngine, ids: Ids, url: string): Promise<void> {
  const play = h("button", { textContent: "Play reference sound" });
  const go = h("button", { className: "primary", textContent: "Continue", disabled: true });
  const error = h("div", { className: "status warning" });
  let plays = 0;
  play.onclick = async () => {
    play.disabled = true;
    error.textContent = "";
    try {
      await audio.load(url);
      await audio.play(url);
      plays++;
      go.disabled = false;
    } catch (e) {
      error.textContent = `Could not play the sound (${(e as Error).message}).`;
    }
    play.disabled = false;
  };
  screen(app, h("h1", { textContent: "Volume" }), paragraph(cfg.text.volume),
    h("div", { className: "buttons" }, play, go), error);
  await clicked(go);
  audio.stop();
  await logEvent(ids, "volume_confirmed", { reference_plays: plays });
}

async function tutorialPage(cfg: PublicConfig, ids: Ids): Promise<void> {
  const azOnly = cfg.response.mode === "azimuth_only";
  const go = h("button", { className: "primary", textContent: "Continue", disabled: true });
  const s = screen(app, h("h1", { textContent: "How to answer" }),
    paragraph(azOnly ? cfg.text.tutorial_azimuth_only : cfg.text.tutorial));
  const panel = new ResponsePanel(s, cfg.response.mode);
  panel.setEnabled(true);
  const rating = cfg.response.externalization === "rating"
    ? new ExternalizationRating(s, cfg.response.externalization_labels, cfg.text.externalization)
    : null;
  const refresh = () => (go.disabled = !panel.complete || (rating !== null && rating.value === null));
  panel.onChange = refresh;
  if (rating) rating.onChange = refresh;
  s.append(go);
  await clicked(go);
  await logEvent(ids, "tutorial_done");
}

async function messagePage(title: string, text: string, button = "Start", minSeconds = 0): Promise<void> {
  const go = h("button", { className: "primary", textContent: button, disabled: minSeconds > 0 });
  const countdown = h("div", { className: "status" });
  screen(app, h("h1", { textContent: title }), ...(text ? [paragraph(text)] : []), countdown, go);
  for (let left = Math.ceil(minSeconds); left > 0; left--) {
    countdown.textContent = `You can continue in ${left} s`;
    await sleep(1000);
  }
  countdown.textContent = "";
  go.disabled = false;
  await clicked(go);
}

function progressLabel(trials: TrialInfo[], t: TrialInfo): string {
  const group = trials.filter((x) => x.is_training === t.is_training);
  const n = group.indexOf(t) + 1;
  return t.is_training ? `Practice ${n} / ${group.length}` : `${n} / ${group.length}`;
}

async function ensureAudio(audio: AudioEngine, trials: TrialInfo[], i: number): Promise<void> {
  const upcoming = trials.slice(i, i + 1 + PREFETCH).map((t) => t.audio);
  audio.evictExcept(new Set(upcoming));
  for (const url of upcoming.slice(1)) audio.load(url).catch((e) => console.warn("prefetch failed", e));
  if (!audio.isLoaded(trials[i].audio)) {
    screen(app, h("div", { className: "status", textContent: "Loading…" }));
    await audio.load(trials[i].audio);
  }
}

async function main(): Promise<void> {
  let cfg: PublicConfig;
  try {
    cfg = await api.config();
  } catch (e) {
    fatal(`Cannot reach the experiment server (${(e as Error).message}). Is \`python -m binaural_loc serve\` running?`);
  }
  document.title = cfg.title;
  const audio = new AudioEngine(cfg.sample_rate);

  const { ids, session } = await startPage(cfg, audio);
  const done = new Set(session.completed);
  const trials = session.trials;
  const todo = trials.filter((t) => !done.has(t.trial_index));
  const resumed = done.size > 0;
  await logEvent(ids, "client_info", {
    audio_sample_rate: audio.ctx.sampleRate,
    audio_base_latency: audio.ctx.baseLatency,
    device_sample_rate: AudioEngine.deviceSampleRate(),
    user_agent: navigator.userAgent,
    resumed,
  });

  if (todo.length === 0) {
    screen(app, h("h1", { textContent: "This session is already complete" }),
      paragraph(`All ${trials.length} answers for ${ids.participant_id} / ${ids.session_id} are saved.`));
    return;
  }
  if (resumed) await resumePage(done.size, trials.length);
  await lrCheckPage(audio, ids);
  await volumePage(cfg, audio, ids, session.volume_reference);
  if (!resumed) await tutorialPage(cfg, ids);

  window.addEventListener("beforeunload", warnBeforeLeaving);
  const hasTraining = trials.some((t) => t.is_training);
  for (let k = 0; k < todo.length; k++) {
    const t = todo[k];
    const prev = k > 0 ? todo[k - 1] : null;
    if (prev === null) {
      if (t.is_training) await messagePage("Practice", cfg.text.training_intro);
      else await messagePage(hasTraining ? "Main part" : "Ready?", hasTraining ? cfg.text.main_intro : "");
    } else if (prev.is_training && !t.is_training) {
      await messagePage("Main part", cfg.text.main_intro);
    } else if (t.block !== prev.block) {
      await logEvent(ids, "rest_started", { after_block: prev.block });
      await messagePage("Break", cfg.text.rest, "Continue", cfg.rest_min_seconds);
    }
    try {
      await ensureAudio(audio, todo, k);
    } catch (e) {
      fatal(`Could not load a sound (${(e as Error).message}).`);
    }
    await runTrial({ app, audio, cfg, ids, trial: t, progress: progressLabel(trials, t) });
  }
  window.removeEventListener("beforeunload", warnBeforeLeaving);
  await logEvent(ids, "session_complete");
  screen(app, h("h1", { textContent: "Finished" }), paragraph(cfg.text.end));
}

void main();
