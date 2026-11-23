// Optional externalization rating, 1-based in label order.

import { h } from "./ui";

export class ExternalizationRating {
  private buttons: HTMLButtonElement[];
  private _value: number | null = null;
  onChange: () => void = () => {};

  constructor(parent: HTMLElement, labels: string[], prompt: string) {
    this.buttons = labels.map((label, i) => {
      const b = h("button", { type: "button", textContent: label, className: "rating-option" });
      b.setAttribute("aria-pressed", "false");
      b.addEventListener("click", () => this.select(i + 1));
      return b;
    });
    parent.appendChild(h("div", { className: "externalization" },
      h("div", { className: "rating-prompt", textContent: prompt }),
      h("div", { className: "rating-options" }, ...this.buttons)));
  }

  get value(): number | null {
    return this._value;
  }

  setEnabled(on: boolean): void {
    for (const b of this.buttons) b.disabled = !on;
  }

  private select(value: number): void {
    this._value = value;
    this.buttons.forEach((b, i) => b.setAttribute("aria-pressed", String(i + 1 === value)));
    this.onChange();
  }
}
