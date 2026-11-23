import { describe, expect, it } from "vitest";
import {
  azimuthToPoint,
  clickToAzimuth,
  clickToElevation,
  elevationToPoint,
  projectToSideView,
  wrap360,
  type ClickResult,
  type Ring,
} from "./geometry";

const ring: Ring = { radius: 100, inner: 60, outer: 130 };

function angle(r: ClickResult): number {
  if (!r.ok) throw new Error(`click rejected: ${r.reason}`);
  return r.angle;
}

describe("wrap360", () => {
  it.each([
    [0, 0],
    [360, 0],
    [-90, 270],
    [450, 90],
    [-360, 0],
    [359.5, 359.5],
  ])("%f -> %f", (x, y) => {
    expect(wrap360(x)).toBeCloseTo(y, 10);
    expect(Object.is(wrap360(x), -0)).toBe(false);
  });
});

describe("top view: clickToAzimuth (SOFA convention, screen y down)", () => {
  it.each([
    ["front (screen up)", 0, -100, 0],
    ["left (screen left)", -100, 0, 90],
    ["back (screen down)", 0, 100, 180],
    ["right (screen right)", 100, 0, 270],
    ["front-left", -70.71, -70.71, 45],
    ["front-right", 70.71, -70.71, 315],
    ["back-left", -70.71, 70.71, 135],
    ["back-right", 70.71, 70.71, 225],
  ])("%s", (_name, dx, dy, az) => {
    expect(angle(clickToAzimuth(dx, dy, ring))).toBeCloseTo(az, 2);
  });

  it("is continuous (no snapping)", () => {
    const p = azimuthToPoint(12.345, 100);
    expect(angle(clickToAzimuth(p.x, p.y, ring))).toBeCloseTo(12.345, 8);
  });

  it("rejects clicks too close to the centre or too far out", () => {
    expect(clickToAzimuth(0, -30, ring)).toEqual({ ok: false, reason: "too_close" });
    expect(clickToAzimuth(0, -150, ring)).toEqual({ ok: false, reason: "too_far" });
  });

  it("round-trips through azimuthToPoint for every degree", () => {
    for (let az = 0; az < 360; az += 1) {
      const p = azimuthToPoint(az, 100);
      expect(angle(clickToAzimuth(p.x, p.y, ring))).toBeCloseTo(az, 8);
    }
  });
});

describe("side view: clickToElevation (arc on the right = chosen direction)", () => {
  it.each([
    ["level", 100, 0, 0],
    ["up", 0.001, -100, 90],
    ["down", 0.001, 100, -90],
    ["+45", 70.71, -70.71, 45],
    ["-30", 86.6, 50, -30],
  ])("%s", (_name, dx, dy, el) => {
    expect(angle(clickToElevation(dx, dy, ring))).toBeCloseTo(el, 1);
  });

  it("clamps small overshoots across the vertical axis to +-90", () => {
    expect(angle(clickToElevation(-10, -95, ring))).toBe(90);
    expect(angle(clickToElevation(-10, 95, ring))).toBe(-90);
  });

  it("rejects clicks clearly on the left (non-arc) half", () => {
    expect(clickToElevation(-100, 0, ring)).toEqual({ ok: false, reason: "wrong_half" });
  });

  it("rejects clicks off the ring", () => {
    expect(clickToElevation(20, 0, ring)).toEqual({ ok: false, reason: "too_close" });
    expect(clickToElevation(200, 0, ring)).toEqual({ ok: false, reason: "too_far" });
  });

  it("round-trips through elevationToPoint", () => {
    for (let el = -90; el <= 90; el += 1) {
      const p = elevationToPoint(el, 100);
      expect(angle(clickToElevation(p.x, p.y, ring))).toBeCloseTo(el, 8);
    }
  });
});

describe("projectToSideView (head x = front, y = left, z = up)", () => {
  const nose = { x: 1, y: 0, z: 0 };
  const leftEar = { x: 0, y: 1, z: 0 };
  const rightEar = { x: 0, y: -1, z: 0 };
  const top = { x: 0, y: 0, z: 1 };

  function proj(az: number, p: { x: number; y: number; z: number }) {
    const q = projectToSideView(az, p);
    return [q.x, q.y, q.depth].map((v) => Math.round(v * 1e9) / 1e9 + 0);
  }

  it("front: profile, nose towards the arc, right ear facing the viewer", () => {
    expect(proj(0, nose)).toEqual([1, 0, 0]);
    expect(proj(0, rightEar)).toEqual([0, 0, 1]);
    expect(proj(0, leftEar)).toEqual([0, 0, -1]);
  });

  it("left: face towards the viewer, left ear towards the arc", () => {
    expect(proj(90, nose)).toEqual([0, 0, 1]);
    expect(proj(90, leftEar)).toEqual([1, 0, 0]);
    expect(proj(90, rightEar)).toEqual([-1, 0, 0]);
  });

  it("back: profile, nose away from the arc", () => {
    expect(proj(180, nose)).toEqual([-1, 0, 0]);
    expect(proj(180, leftEar)).toEqual([0, 0, 1]);
  });

  it("right: back of the head towards the viewer, right ear towards the arc", () => {
    expect(proj(270, nose)).toEqual([0, 0, -1]);
    expect(proj(270, rightEar)).toEqual([1, 0, 0]);
  });

  it("up stays up (SVG y down)", () => {
    expect(proj(123, top)).toEqual([0, -1, 0]);
  });
});
