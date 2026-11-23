// Plain playback: no gain, no compression, no resampling.

interface WavInfo {
  sampleRate: number;
  channels: number;
}

export function parseWavHeader(buf: ArrayBuffer): WavInfo {
  const v = new DataView(buf);
  const tag = (o: number) => String.fromCharCode(v.getUint8(o), v.getUint8(o + 1), v.getUint8(o + 2), v.getUint8(o + 3));
  if (buf.byteLength < 12 || tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("not a RIFF/WAVE file");
  let off = 12;
  while (off + 8 <= buf.byteLength) {
    const id = tag(off);
    const size = v.getUint32(off + 4, true);
    if (id === "fmt ") {
      return { channels: v.getUint16(off + 10, true), sampleRate: v.getUint32(off + 12, true) };
    }
    off += 8 + size + (size % 2); // chunks are word-aligned
  }
  throw new Error("WAV file has no fmt chunk");
}

export class AudioEngine {
  readonly ctx: AudioContext;
  private buffers = new Map<string, AudioBuffer>();
  private pending = new Map<string, Promise<void>>();
  private current: AudioBufferSourceNode | null = null;

  constructor(readonly expectedSampleRate: number) {
    this.ctx = new AudioContext({ sampleRate: expectedSampleRate, latencyHint: "interactive" });
  }

  /**
   * Rate of the output device. Asking for an AudioContext at some rate always
   * works, the browser just resamples at the output, so check the device itself.
   */
  static deviceSampleRate(): number {
    const probe = new AudioContext();
    const rate = probe.sampleRate;
    void probe.close();
    return rate;
  }

  /** Call from a user gesture (autoplay policy). */
  async unlock(): Promise<void> {
    if (this.ctx.state !== "running") await this.ctx.resume();
  }

  isLoaded(url: string): boolean {
    return this.buffers.has(url);
  }

  load(url: string): Promise<void> {
    if (this.buffers.has(url)) return Promise.resolve();
    let p = this.pending.get(url);
    if (!p) {
      p = this.fetchAndDecode(url).finally(() => this.pending.delete(url));
      this.pending.set(url, p);
    }
    return p;
  }

  private async fetchAndDecode(url: string): Promise<void> {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`failed to fetch audio: ${resp.status}`);
    const data = await resp.arrayBuffer();
    const info = parseWavHeader(data);
    if (info.sampleRate !== this.expectedSampleRate) {
      throw new Error(`stimulus sample rate ${info.sampleRate} Hz, expected ${this.expectedSampleRate} Hz`);
    }
    if (info.channels !== 2) throw new Error(`stimulus has ${info.channels} channels, expected 2`);
    this.buffers.set(url, await this.ctx.decodeAudioData(data));
  }

  evictExcept(keep: Set<string>): void {
    for (const url of [...this.buffers.keys()]) if (!keep.has(url)) this.buffers.delete(url);
  }

  /** Resolves when playback has ended. */
  play(url: string): Promise<void> {
    const buffer = this.buffers.get(url);
    if (!buffer) return Promise.reject(new Error("stimulus not loaded"));
    return this.playBuffer(buffer);
  }

  playBuffer(buffer: AudioBuffer): Promise<void> {
    this.stop();
    const src = this.ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(this.ctx.destination);
    this.current = src;
    return new Promise((resolve) => {
      src.onended = () => {
        if (this.current === src) this.current = null;
        resolve();
      };
      src.start();
    });
  }

  stop(): void {
    this.current?.stop();
    this.current = null;
  }

  /** Three 1 kHz beeps in one channel (0 = left, 1 = right). */
  channelTestBuffer(channel: 0 | 1): AudioBuffer {
    const fs = this.ctx.sampleRate;
    const buf = this.ctx.createBuffer(2, Math.round(fs * 1.1), fs);
    const x = buf.getChannelData(channel);
    const beep = Math.round(fs * 0.2), gap = Math.round(fs * 0.25), ramp = Math.round(fs * 0.01);
    for (let k = 0; k < 3; k++) {
      const start = k * (beep + gap);
      for (let n = 0; n < beep; n++) {
        const env = Math.min(1, n / ramp, (beep - 1 - n) / ramp);
        x[start + n] = 0.1 * env * Math.sin((2 * Math.PI * 1000 * n) / fs);
      }
    }
    return buf;
  }
}
