export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: Partial<HTMLElementTagNameMap[K]> = {},
  ...children: (Node | string)[]
): HTMLElementTagNameMap[K] {
  const e = Object.assign(document.createElement(tag), props);
  e.append(...children);
  return e;
}

export function screen(app: HTMLElement, ...children: (Node | string)[]): HTMLDivElement {
  const s = h("div", { className: "screen" }, ...children);
  app.replaceChildren(s);
  return s;
}

export function clicked(button: HTMLButtonElement): Promise<void> {
  return new Promise((resolve) => button.addEventListener("click", () => resolve(), { once: true }));
}

export function paragraph(text: string): HTMLParagraphElement {
  return h("p", { textContent: text });
}

export const sleep = (ms: number) => new Promise<void>((r) => window.setTimeout(r, ms));
