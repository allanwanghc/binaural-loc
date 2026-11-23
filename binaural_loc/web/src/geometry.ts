// Click <-> angle geometry for the two response views.
//
// Angles follow SOFA (vertical-polar): azimuth 0 = front, counter-clockwise
// positive seen from above (+90 = left), elevation +90 = up.
// Positions are in SVG user units relative to the view centre, with screen y
// pointing DOWN (SVG convention).
//
// Top view: nose points up the screen, the participant's left is screen-left.
// Side view: the vertical half-plane through the chosen azimuth. Screen-right
// is the chosen horizontal direction, screen-up is up; the head is drawn as
// seen from the horizontal direction perpendicular to that plane.

export type ClickResult =
  | { ok: true; angle: number }
  | { ok: false; reason: "too_close" | "too_far" | "wrong_half" };

export interface Ring {
  radius: number;
  /** Clicks closer to the centre than this are rejected. */
  inner: number;
  /** Clicks further from the centre than this are rejected. */
  outer: number;
}

const DEG = 180 / Math.PI;
const RAD = Math.PI / 180;

/** Wrap to [0, 360). */
export function wrap360(deg: number): number {
  const w = deg % 360;
  return w < 0 ? w + 360 : w === 0 ? 0 : w; // avoid -0
}

function checkRing(dx: number, dy: number, ring: Ring): ClickResult | null {
  const r = Math.hypot(dx, dy);
  if (r < ring.inner) return { ok: false, reason: "too_close" };
  if (r > ring.outer) return { ok: false, reason: "too_far" };
  return null;
}

export function clickToAzimuth(dx: number, dy: number, ring: Ring): ClickResult {
  const bad = checkRing(dx, dy, ring);
  if (bad) return bad;
  return { ok: true, angle: wrap360(Math.atan2(-dx, -dy) * DEG) };
}

export function azimuthToPoint(azimuth: number, r: number): { x: number; y: number } {
  const a = azimuth * RAD;
  return { x: -r * Math.sin(a), y: -r * Math.cos(a) };
}

// How far (fraction of the radius) a click may be left of the arc; clamped to +-90.
const CROSS_AXIS_TOLERANCE = 0.15;

export function clickToElevation(dx: number, dy: number, ring: Ring): ClickResult {
  const bad = checkRing(dx, dy, ring);
  if (bad) return bad;
  if (dx < -CROSS_AXIS_TOLERANCE * ring.radius) return { ok: false, reason: "wrong_half" };
  return { ok: true, angle: Math.atan2(-dy, Math.max(dx, 0)) * DEG + 0 }; // + 0 avoids -0
}

export function elevationToPoint(elevation: number, r: number): { x: number; y: number } {
  const e = elevation * RAD;
  return { x: r * Math.cos(e), y: -r * Math.sin(e) };
}

/**
 * Project a head-fixed point into the side view for a given azimuth.
 * Head coordinates follow SOFA: x = front, y = left, z = up.
 * Returns screen x (towards the chosen direction), screen y (down) and depth
 * (> 0 = on the viewer's side of the head, i.e. visible).
 */
export function projectToSideView(
  azimuth: number,
  p: { x: number; y: number; z: number },
): { x: number; y: number; depth: number } {
  const c = Math.cos(azimuth * RAD);
  const s = Math.sin(azimuth * RAD);
  // screen-right d = (c, s, 0); towards viewer = d x up = (s, -c, 0)
  return { x: p.x * c + p.y * s, y: -p.z, depth: p.x * s - p.y * c };
}
