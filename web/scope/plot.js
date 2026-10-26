// Canvas drawing for the virtual instruments: an oscilloscope screen and general x-y charts.

import { formatEng } from "../editor/model.js";

export const CHANNEL_COLORS = ["#f5c518", "#2ec4ff", "#ff5fa2", "#7CFC00"];

function setup(canvas) {
  // Draw at the screen's real pixel density so lines stay sharp on high-DPI displays.
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(height * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { ctx, width, height };
}

// ---- oscilloscope ---------------------------------------------------------------------------------

// channels: [{label, times, values, color, voltsPerDiv, offset, dashed}]
export function drawScope(canvas, { timePerDiv, channels, cursor = null }) {
  const { ctx, width, height } = setup(canvas);
  const pad = 8;
  const w = width - 2 * pad;
  const h = height - 2 * pad - 18;
  ctx.fillStyle = "#06140c";
  ctx.fillRect(0, 0, width, height);

  // 10 x 8 divisions like a real scope, with finer ticks on the center lines.
  ctx.strokeStyle = "rgba(120, 200, 140, 0.25)";
  ctx.lineWidth = 1;
  for (let i = 0; i <= 10; i++) line(ctx, pad + (i * w) / 10, pad, pad + (i * w) / 10, pad + h);
  for (let j = 0; j <= 8; j++) line(ctx, pad, pad + (j * h) / 8, pad + w, pad + (j * h) / 8);
  ctx.strokeStyle = "rgba(120, 200, 140, 0.5)";
  for (let i = 0; i <= 50; i++) line(ctx, pad + (i * w) / 50, pad + h / 2 - 3, pad + (i * w) / 50, pad + h / 2 + 3);
  for (let j = 0; j <= 40; j++) line(ctx, pad + w / 2 - 3, pad + (j * h) / 40, pad + w / 2 + 3, pad + (j * h) / 40);

  const xOf = (t) => pad + (t / (timePerDiv * 10)) * w;
  for (const ch of channels) {
    const yOf = (v) => pad + h / 2 - ((v + (ch.offset || 0)) / ch.voltsPerDiv) * (h / 8);
    ctx.save();
    ctx.beginPath();
    ctx.rect(pad, pad, w, h);
    ctx.clip();
    ctx.strokeStyle = ch.color;
    ctx.lineWidth = ch.dashed ? 1.2 : 1.8;
    ctx.setLineDash(ch.dashed ? [5, 4] : []);
    ctx.shadowColor = ch.color;
    ctx.shadowBlur = ch.dashed ? 0 : 4;
    ctx.beginPath();
    ch.times.forEach((t, k) => {
      const x = xOf(t);
      const y = yOf(ch.values[k]);
      if (k === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
    ctx.restore();
  }

  // Readout line under the screen.
  ctx.font = "12px ui-monospace, monospace";
  ctx.fillStyle = "#9fe0b0";
  let x = pad;
  const y = height - 6;
  ctx.fillText(`${formatEng(timePerDiv, "s")}/div`, x, y);
  x += 90;
  for (const ch of channels) {
    if (ch.dashed) continue;
    ctx.fillStyle = ch.color;
    const text = `${ch.label} ${formatEng(ch.voltsPerDiv, "V")}/div`;
    ctx.fillText(text, x, y);
    x += ctx.measureText(text).width + 18;
  }
  if (cursor) {
    ctx.strokeStyle = "rgba(255,255,255,0.5)";
    line(ctx, cursor.x, pad, cursor.x, pad + h);
  }
  return { pad, w, h, timePerDiv };
}

// ---- general charts -------------------------------------------------------------------------------

// series: [{x, y, color, label}]; logX for frequency axes.
export function drawChart(canvas, { series, logX = false, xUnit = "", yUnit = "", yLabel = "", title = "", yRange = null }) {
  const { ctx, width, height } = setup(canvas);
  const left = 58;
  const right = 12;
  const top = title ? 24 : 10;
  const bottom = 28;
  const w = width - left - right;
  const h = height - top - bottom;
  // Colors come from the page's CSS, so charts follow light and dark mode.
  const css = getComputedStyle(canvas);
  const color = (name, fallback) => css.getPropertyValue(name).trim() || fallback;
  ctx.fillStyle = color("--chart-bg", "#ffffff");
  ctx.fillRect(0, 0, width, height);
  const fg = color("--chart-fg", "#222222");
  const gridColor = color("--chart-grid", "#dddddd");

  const xs = series.flatMap((s) => s.x).filter((v) => Number.isFinite(v) && (!logX || v > 0));
  const ys = series.flatMap((s) => s.y).filter(Number.isFinite);
  if (!xs.length || !ys.length) return;
  let [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  let [y0, y1] = yRange || niceRange(Math.min(...ys), Math.max(...ys));
  if (logX) { x0 = Math.log10(x0); x1 = Math.log10(x1); }
  if (x1 === x0) x1 = x0 + 1;
  const xOf = (v) => left + ((logX ? Math.log10(v) : v) - x0) / (x1 - x0) * w;
  const yOf = (v) => top + h - (v - y0) / (y1 - y0) * h;

  ctx.font = "11px system-ui, sans-serif";
  ctx.strokeStyle = gridColor;
  ctx.fillStyle = fg;
  ctx.lineWidth = 1;
  // Vertical grid: decades (and 2, 5 between them) on a log axis, nice steps on a linear one.
  const xTicks = logX ? logTicks(x0, x1) : linearTicks(x0, x1);
  for (const t of xTicks) {
    const x = xOf(t.value);
    ctx.strokeStyle = t.major ? gridColor : gridColor + "88";
    line(ctx, x, top, x, top + h);
    if (t.major) {
      ctx.textAlign = "center";
      ctx.fillText(formatEng(t.value, xUnit, 3), x, top + h + 16);
    }
  }
  for (const t of linearTicks(y0, y1)) {
    const y = yOf(t.value);
    ctx.strokeStyle = gridColor;
    line(ctx, left, y, left + w, y);
    ctx.textAlign = "right";
    ctx.fillText(yUnit === "dB" || yUnit === "°" ? `${round(t.value)}${yUnit}` : formatEng(t.value, yUnit, 3), left - 6, y + 4);
  }
  ctx.strokeStyle = fg;
  ctx.strokeRect(left, top, w, h);
  if (title) {
    ctx.textAlign = "left";
    ctx.font = "bold 12px system-ui, sans-serif";
    ctx.fillText(title, left, 15);
  }
  if (yLabel) {
    ctx.save();
    ctx.translate(12, top + h / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillText(yLabel, 0, 0);
    ctx.restore();
  }

  for (const s of series) {
    ctx.save();
    ctx.beginPath();
    ctx.rect(left, top, w, h);
    ctx.clip();
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    let started = false;
    s.x.forEach((xv, k) => {
      const yv = s.y[k];
      if (!Number.isFinite(yv) || (logX && !(xv > 0))) return;
      if (!started) { ctx.moveTo(xOf(xv), yOf(yv)); started = true; }
      else ctx.lineTo(xOf(xv), yOf(yv));
    });
    ctx.stroke();
    ctx.restore();
  }
  // Legend.
  ctx.textAlign = "left";
  ctx.font = "11px system-ui, sans-serif";
  let lx = left + 8;
  for (const s of series) {
    if (!s.label) continue;
    ctx.fillStyle = s.color;
    ctx.fillRect(lx, top + 6, 12, 3);
    ctx.fillStyle = fg;
    ctx.fillText(s.label, lx + 16, top + 11);
    lx += ctx.measureText(s.label).width + 34;
  }
}

function line(ctx, x1, y1, x2, y2) {
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
}

function round(v) {
  return Math.abs(v) >= 100 ? v.toFixed(0) : Number(v.toPrecision(3));
}

export function niceRange(lo, hi) {
  if (lo === hi) { lo -= 1; hi += 1; }
  const step = niceStep((hi - lo) / 5);
  return [Math.floor(lo / step) * step, Math.ceil(hi / step) * step];
}

function niceStep(raw) {
  const power = Math.pow(10, Math.floor(Math.log10(raw)));
  const unit = raw / power;
  return (unit <= 1 ? 1 : unit <= 2 ? 2 : unit <= 5 ? 5 : 10) * power;
}

function linearTicks(lo, hi) {
  const step = niceStep((hi - lo) / 6);
  const ticks = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) ticks.push({ value: Math.abs(v) < step * 1e-9 ? 0 : v, major: true });
  return ticks;
}

function logTicks(lo, hi) {
  const ticks = [];
  for (let d = Math.floor(lo); d <= Math.ceil(hi); d++) {
    for (const m of [1, 2, 5]) {
      const value = m * Math.pow(10, d);
      const lv = Math.log10(value);
      if (lv >= lo - 1e-9 && lv <= hi + 1e-9) ticks.push({ value, major: m === 1 });
    }
  }
  return ticks;
}

// Standard 1-2-5 steps for the scope knobs.
export const SCOPE_STEPS = [1e-6, 2e-6, 5e-6, 1e-5, 2e-5, 5e-5, 1e-4, 2e-4, 5e-4, 1e-3, 2e-3, 5e-3, 1e-2, 2e-2, 5e-2, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20];

export function autoVoltsPerDiv(values) {
  // The smallest knob setting that fits the whole trace within the 8 vertical divisions.
  const peak = Math.max(1e-6, ...values.map((v) => Math.abs(v)));
  return SCOPE_STEPS.find((s) => s * 4 >= peak) || SCOPE_STEPS[SCOPE_STEPS.length - 1];
}
