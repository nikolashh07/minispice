// Explain mode in the browser (Phase 32): step through the solution while the parts each step
// talks about light up in the editor.

import { escapeHtml } from "./editor/editor.js";

const $ = (id) => document.getElementById(id);

export class ExplainPanel {
  constructor(app) {
    this.app = app;
    this.steps = [];
    this.index = 0;
    $("explain-run").addEventListener("click", () => this.run());
    $("explain-prev").addEventListener("click", () => this.show(this.index - 1));
    $("explain-next").addEventListener("click", () => this.show(this.index + 1));
  }

  async run() {
    this.app.status("Working out the explanation…");
    const result = await this.app.engine.explain(this.app.netlist());
    if (!result.ok) {
      this.app.status(result.error, true);
      return;
    }
    this.steps = result.steps;
    $("explain-title").textContent = result.title;
    this.app.status("Use Next and Back to step through the solution.");
    this.show(0);
  }

  show(index) {
    if (!this.steps.length) return;
    this.index = Math.max(0, Math.min(this.steps.length - 1, index));
    const step = this.steps[this.index];
    $("explain-counter").textContent = `Step ${this.index + 1} of ${this.steps.length}`;
    // Indented lines are equations; show them in a fixed-width font.
    const body = step.lines.map((line) => (line.startsWith("    ")
      ? `<pre>${escapeHtml(line.trim())}</pre>`
      : `<p>${escapeHtml(line)}</p>`)).join("");
    $("explain-step").innerHTML = `<h3>${escapeHtml(step.title)}</h3><p class="law">${escapeHtml(step.law)}</p>${body}`;
    $("explain-prev").disabled = this.index === 0;
    $("explain-next").disabled = this.index === this.steps.length - 1;
    this.app.editor.setHighlight(step.parts);
  }

  reset() {
    this.steps = [];
    $("explain-step").innerHTML = "";
    $("explain-counter").textContent = "";
    this.app.editor.setHighlight([]);
  }
}
