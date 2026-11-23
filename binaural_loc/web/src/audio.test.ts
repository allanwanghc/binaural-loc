import { describe, expect, it } from "vitest";
import { parseWavHeader } from "./audio";

function wav(sampleRate: number, channels: number, extraChunk = false): ArrayBuffer {
  const parts: number[] = [];
  const str = (s: string) => [...s].forEach((c) => parts.push(c.charCodeAt(0)));
  const u32 = (n: number) => parts.push(n & 255, (n >> 8) & 255, (n >> 16) & 255, (n >>> 24) & 255);
  const u16 = (n: number) => parts.push(n & 255, (n >> 8) & 255);
  str("RIFF");
  u32(0);
  str("WAVE");
  if (extraChunk) {
    str("LIST");
    u32(3); // odd size -> one pad byte
    parts.push(1, 2, 3, 0);
  }
  str("fmt ");
  u32(16);
  u16(1);
  u16(channels);
  u32(sampleRate);
  u32(sampleRate * channels * 2);
  u16(channels * 2);
  u16(16);
  return new Uint8Array(parts).buffer;
}

describe("parseWavHeader", () => {
  it("reads rate and channels", () => {
    expect(parseWavHeader(wav(48000, 2))).toEqual({ sampleRate: 48000, channels: 2 });
  });
  it("skips other chunks including odd-sized ones", () => {
    expect(parseWavHeader(wav(44100, 1, true))).toEqual({ sampleRate: 44100, channels: 1 });
  });
  it("rejects non-WAV data", () => {
    expect(() => parseWavHeader(new Uint8Array(16).buffer)).toThrow();
  });
});
