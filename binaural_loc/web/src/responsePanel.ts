// Top view gives azimuth, side view gives elevation. The side view is the
// vertical half-plane through the chosen azimuth, so its head turns with it.

import type { Direction } from "./api";
import {
  azimuthToPoint,
  clickToAzimuth,
  clickToElevation,
  elevationToPoint,
  projectToSideView,
  type ClickResult,
  type Ring,
} from "./geometry";
import { h } from "./ui";

export type ResponseMode = "azimuth_only" | "azimuth_elevation";

export interface ResponseState {
  azimuth: number | null;
  elevation: number | null;
  // accepted clicks, including the first
  nAzimuthClicks: number;
  nElevationClicks: number;
}

const SVG_NS = "http://www.w3.org/2000/svg";
const R = 140;
const RING: Ring = { radius: R, inner: 0.6 * R, outer: 1.4 * R };
const VIEW = 215; // half of the viewBox
const HEAD_R = 42;

function el<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number> = {},
  parent?: Element,
): SVGElementTagNameMap[K] {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v));
  parent?.appendChild(e);
  return e;
}

function label(parent: Element, text: string, x: number, y: number, anchor = "middle"): SVGTextElement {
  const t = el("text", { x, y, "text-anchor": anchor, "dominant-baseline": "middle", class: "label" }, parent);
  t.textContent = text;
  return t;
}

function makeSvg(parent: HTMLElement, ariaLabel: string): SVGSVGElement {
  return el("svg", {
    viewBox: `${-VIEW} ${-VIEW} ${2 * VIEW} ${2 * VIEW}`,
    class: "view",
    role: "img",
    "aria-label": ariaLabel,
  }, parent);
}

/** Pointer position in SVG coordinates (origin at the centre). */
function localPoint(svg: SVGSVGElement, ev: PointerEvent): { x: number; y: number } {
  const ctm = svg.getScreenCTM();
  if (!ctm) return { x: 0, y: 0 };
  const p = new DOMPoint(ev.clientX, ev.clientY).matrixTransform(ctm.inverse());
  return { x: p.x, y: p.y };
}

// middle and width of the band where clicks are accepted
const BAND_R = (RING.inner + RING.outer) / 2;
const BAND_W = RING.outer - RING.inner;

/** Right half of a circle, from bottom to top. */
const halfCircle = (r: number) => `M 0 ${r} A ${r} ${r} 0 0 0 0 ${-r}`;

function line(parent: Element, cls: string, x1: number, y1: number, x2: number, y2: number): void {
  el("line", { x1, y1, x2, y2, class: cls }, parent);
}

/** Hidden marker pointing at (x, y); rotated into place by placeMarker. */
function makeMarker(parent: Element, x: number, y: number, cls = "marker"): SVGGElement {
  const g = el("g", { class: cls, visibility: "hidden" }, parent);
  line(g, "marker-line", 0, 0, x, y);
  el("circle", { cx: x, cy: y, r: 11, class: "marker-dot" }, g);
  return g;
}

// SVG rotates clockwise, our angles are counter-clockwise
function placeMarker(marker: SVGGElement, angle: number | null | undefined): void {
  const on = angle !== null && angle !== undefined;
  marker.setAttribute("visibility", on ? "visible" : "hidden");
  if (on) marker.setAttribute("transform", `rotate(${-angle})`);
}

export class ResponsePanel {
  readonly root: HTMLDivElement;
  private topSvg: SVGSVGElement;
  private sideSvg: SVGSVGElement;
  private azMarker: SVGGElement;
  private elMarker: SVGGElement;
  private sideHead: SVGGElement;
  private azTruth: SVGGElement;
  private elTruth: SVGGElement;
  private legend: HTMLDivElement;
  private feedback: Direction | null = null;
  private hint: HTMLDivElement;
  private hintTimer = 0;
  private enabled = false;
  private st: ResponseState = { azimuth: null, elevation: null, nAzimuthClicks: 0, nElevationClicks: 0 };

  onChange: () => void = () => {};

  constructor(parent: HTMLElement, readonly mode: ResponseMode) {
    const topWrap = h("div", { className: "view-wrap" });
    const sideWrap = h("div", { className: "view-wrap", hidden: mode === "azimuth_only" });
    this.legend = h("div", { className: "legend", hidden: true },
      h("span", { className: "key answer" }), "Your answer",
      h("span", { className: "key truth" }), "Correct direction");
    this.hint = h("div", { className: "hint" });
    this.root = h("div", { className: "response-panel" },
      h("div", { className: "views" }, topWrap, sideWrap), this.legend, this.hint);
    parent.appendChild(this.root);

    this.topSvg = makeSvg(topWrap, "Top view: click the direction around the head");
    const t = this.topSvg;
    el("circle", { r: BAND_R, class: "band", "stroke-width": BAND_W }, t);
    line(t, "axis", 0, -R, 0, R);
    line(t, "axis", -R, 0, R, 0);
    el("circle", { r: R, class: "ring" }, t);
    for (let d = 0; d < 360; d += 45) {
      const a = azimuthToPoint(d, R - 6), b = azimuthToPoint(d, R + 6);
      line(t, "tick", a.x, a.y, b.x, b.y);
    }
    el("ellipse", { cx: -HEAD_R - 2, cy: 0, rx: 7, ry: 14, class: "head" }, t);
    el("ellipse", { cx: HEAD_R + 2, cy: 0, rx: 7, ry: 14, class: "head" }, t);
    el("path", { d: `M -10 ${-HEAD_R + 3} L 0 ${-HEAD_R - 14} L 10 ${-HEAD_R + 3} Z`, class: "head" }, t);
    el("circle", { r: HEAD_R, class: "head" }, t);
    label(t, "L", -HEAD_R + 14, 0).classList.add("ear-label");
    label(t, "R", HEAD_R - 14, 0).classList.add("ear-label");
    label(t, "Front", 0, -R - 26);
    label(t, "Back", 0, R + 26);
    label(t, "Left", -R - 12, 0, "end");
    label(t, "Right", R + 12, 0, "start");
    this.azMarker = makeMarker(t, 0, -R);
    this.azTruth = makeMarker(t, 0, -R, "marker truth");
    t.addEventListener("pointerdown", (ev) => this.onTopClick(ev));

    this.sideSvg = makeSvg(sideWrap, "Side view: click the height of the sound");
    const s = this.sideSvg;
    el("path", { d: halfCircle(BAND_R), class: "band", "stroke-width": BAND_W }, s);
    line(s, "axis", 0, -R, 0, R);
    line(s, "axis", 0, 0, R, 0);
    el("path", { d: halfCircle(R), class: "ring" }, s);
    for (let d = -90; d <= 90; d += 45) {
      const a = elevationToPoint(d, R - 6), b = elevationToPoint(d, R + 6);
      line(s, "tick", a.x, a.y, b.x, b.y);
    }
    this.sideHead = el("g", {}, s);
    label(s, "Up", 0, -R - 26);
    label(s, "Down", 0, R + 26);
    label(s, "Level", R + 12, 0, "start");
    this.elMarker = makeMarker(s, R, 0);
    this.elTruth = makeMarker(s, R, 0, "marker truth");
    s.addEventListener("pointerdown", (ev) => this.onSideClick(ev));

    this.render();
    this.setEnabled(false);
  }

  get state(): ResponseState {
    return { ...this.st };
  }

  get complete(): boolean {
    return this.st.azimuth !== null && (this.mode === "azimuth_only" || this.st.elevation !== null);
  }

  /** Show the true direction too; the side view turns to the true azimuth. */
  showFeedback(target: Direction): void {
    this.feedback = target;
    this.setEnabled(false);
    this.root.classList.add("feedback");
    this.render();
  }

  setEnabled(on: boolean): void {
    this.enabled = on;
    this.root.classList.toggle("disabled", !on);
  }

  private onTopClick(ev: PointerEvent): void {
    const angle = this.accept(this.topSvg, ev, clickToAzimuth);
    if (angle === null) return;
    this.st.azimuth = angle;
    this.st.nAzimuthClicks++;
    this.changed();
  }

  private onSideClick(ev: PointerEvent): void {
    const angle = this.accept(this.sideSvg, ev, clickToElevation);
    if (angle === null) return;
    this.st.elevation = angle;
    this.st.nElevationClicks++;
    this.changed();
  }

  /** Angle of a valid click, or null (with a hint if the click was off target). */
  private accept(
    svg: SVGSVGElement,
    ev: PointerEvent,
    toAngle: (dx: number, dy: number, ring: Ring) => ClickResult,
  ): number | null {
    if (!this.enabled) return null;
    const p = localPoint(svg, ev);
    const r = toAngle(p.x, p.y, RING);
    if (r.ok) {
      this.showHint("");
      return r.angle;
    }
    this.showHint(
      r.reason === "wrong_half"
        ? "Click on the half-circle (it points in the direction chosen in the top view)."
        : "Please click on the circle.",
    );
    return null;
  }

  private showHint(msg: string): void {
    this.hint.textContent = msg;
    window.clearTimeout(this.hintTimer);
    if (msg) this.hintTimer = window.setTimeout(() => (this.hint.textContent = ""), 2500);
  }

  private changed(): void {
    this.render();
    this.onChange();
  }

  private render(): void {
    const { azimuth, elevation } = this.st;
    const fb = this.feedback;
    placeMarker(this.azMarker, azimuth);
    placeMarker(this.elMarker, elevation);
    placeMarker(this.azTruth, fb?.azimuth);
    placeMarker(this.elTruth, fb?.elevation);
    this.legend.hidden = fb === null;
    this.drawSideHead(fb?.azimuth ?? azimuth ?? 0);
  }

  /** Profile for front/back, face for left, back of the head for right. */
  private drawSideHead(azimuth: number): void {
    const g = this.sideHead;
    g.replaceChildren();
    const P = (x: number, y: number, z: number) => projectToSideView(azimuth, { x, y, z });
    const parts: { depth: number; draw: (parent: Element) => void }[] = [];

    for (const side of [1, -1]) {
      const ear = P(0, side * (HEAD_R + 2), 0);
      const facing = Math.abs(ear.depth) / (HEAD_R + 2);
      parts.push({
        depth: ear.depth,
        draw: (pa) => {
          el("ellipse", { cx: ear.x, cy: ear.y, rx: 3 + 5 * facing, ry: 13, class: "head" }, pa);
          // label on the ear if it faces us, next to it if it is on the outline
          const name = side > 0 ? "L" : "R";
          if (ear.depth > 0.35 * HEAD_R) label(pa, name, ear.x, ear.y + 1).classList.add("ear-label");
          else if (ear.depth > -0.25 * HEAD_R) {
            const out = P(0, side * (HEAD_R + 17), 0);
            label(pa, name, out.x, out.y + 1).classList.add("ear-label");
          }
        },
      });
    }

    const tip = P(HEAD_R + 13, 0, 2), top = P(HEAD_R - 3, 0, 12), bottom = P(HEAD_R - 3, 0, -10);
    parts.push({
      depth: P(HEAD_R, 0, 0).depth,
      draw: (pa) => el("path", { d: `M ${top.x} ${top.y} L ${tip.x} ${tip.y} L ${bottom.x} ${bottom.y} Z`, class: "head" }, pa),
    });

    for (const side of [1, -1]) {
      const a = (35 * Math.PI) / 180;
      const eye = P(0.92 * HEAD_R * Math.cos(a), side * 0.92 * HEAD_R * Math.sin(a), 12);
      if (eye.depth > 0.15 * HEAD_R) {
        parts.push({ depth: eye.depth + HEAD_R, draw: (pa) => el("circle", { cx: eye.x, cy: eye.y, r: 3.5, class: "eye" }, pa) });
      }
    }

    // back to front, with the head itself in the middle
    parts.sort((p, q) => p.depth - q.depth);
    for (const p of parts) if (p.depth < 0) p.draw(g);
    el("circle", { r: HEAD_R, class: "head" }, g);
    for (const p of parts) if (p.depth >= 0) p.draw(g);
  }
}
