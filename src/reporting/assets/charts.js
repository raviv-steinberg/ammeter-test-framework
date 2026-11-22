/**
 * Tiny SVG chart library for the ammeter report. No dependencies, works offline.
 * Colors of axes and grid come from CSS classes, so charts follow the light or dark theme by themselves.
 */
const Charts = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  let tipNode = null;

  /** Create an SVG element with attributes and append it to a parent. */
  function svgEl(name, attrs, parent) {
    const node = document.createElementNS(NS, name);
    for (const key in attrs) node.setAttribute(key, attrs[key]);
    if (parent) parent.appendChild(node);
    return node;
  }

  /** The single floating tooltip shared by all charts. */
  function tip() {
    if (!tipNode) {
      tipNode = document.createElement('div');
      tipNode.className = 'chart-tip';
      document.body.appendChild(tipNode);
    }
    return tipNode;
  }

  /** Show a tooltip with the given HTML while the mouse is over the node. */
  function bindTip(node, html) {
    node.addEventListener('mouseenter', () => { const t = tip(); t.innerHTML = html; t.classList.add('show'); });
    node.addEventListener('mousemove', (e) => {
      const t = tip();
      const x = Math.min(e.clientX + 14, window.innerWidth - t.offsetWidth - 8);
      t.style.left = x + 'px';
      t.style.top = (e.clientY + 14) + 'px';
    });
    node.addEventListener('mouseleave', () => tip().classList.remove('show'));
  }

  /** Format a current value with a sensible number of digits. */
  function fmt(value, digits) {
    if (value === null || value === undefined || Number.isNaN(value)) return '–';
    if (digits !== undefined) return value.toFixed(digits);
    const a = Math.abs(value);
    if (a === 0) return '0';
    if (a >= 100) return value.toFixed(1);
    if (a >= 1) return value.toFixed(2);
    if (a >= 0.01) return value.toFixed(4);
    return value.toFixed(5);
  }

  /** Format an axis tick and drop trailing zeros, so 0.5000 becomes 0.5. */
  function tick(value, digits) {
    const text = fmt(value, digits);
    return text.includes('.') ? text.replace(/0+$/, '').replace(/\.$/, '') : text;
  }

  /** Round axis limits to friendly numbers and return the tick positions. */
  function niceTicks(min, max, count = 5) {
    if (min === max) { min -= 1; max += 1; }
    const raw = (max - min) / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const norm = raw / mag;
    const step = (norm < 1.5 ? 1 : norm < 3 ? 2 : norm < 7 ? 5 : 10) * mag;
    const lo = Math.floor(min / step) * step;
    const hi = Math.ceil(max / step) * step;
    const ticks = [];
    for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toPrecision(12));
    return { lo, hi, ticks };
  }

  /** Redraw the chart whenever its container changes size, so charts are always sharp and responsive. */
  function responsive(container, draw) {
    let lastWidth = -1;
    const run = () => {
      const width = container.clientWidth;
      // Hidden charts have no width, they are drawn when they become visible again.
      if (width === 0 || width === lastWidth) return;
      lastWidth = width;
      container.innerHTML = '';
      draw(width);
    };
    new ResizeObserver(run).observe(container);
    run();
  }

  /** Create an SVG with a plot area and return helpers for it. */
  function frame(container, width, height, pad) {
    const svg = svgEl('svg', { viewBox: `0 0 ${width} ${height}`, width, height, class: 'chart-svg' }, container);
    return { svg, x0: pad.left, x1: width - pad.right, y0: height - pad.bottom, y1: pad.top };
  }

  /** Draw horizontal grid lines with value labels on the left. */
  function yAxis(f, scale, ticks, unit) {
    for (const t of ticks) {
      const y = scale(t);
      svgEl('line', { x1: f.x0, x2: f.x1, y1: y, y2: y, class: 'grid' }, f.svg);
      const label = svgEl('text', { x: f.x0 - 8, y: y + 4, class: 'axis-text', 'text-anchor': 'end' }, f.svg);
      label.textContent = tick(t) + (unit || '');
    }
  }

  /**
   * Line chart of one or more series.
   * options: series [{name, color, points: [{x, y, label}]}], xLabel, refLines [{y, label, color}], height
   */
  function line(container, options) {
    responsive(container, (width) => {
      const height = options.height || 240;
      const f = frame(container, width, height, { top: 14, right: 16, bottom: 30, left: 58 });
      const all = options.series.flatMap((s) => s.points.filter((p) => p.y !== null));
      const xs = all.map((p) => p.x);
      const ys = all.map((p) => p.y).concat((options.refLines || []).map((r) => r.y));
      const xMin = Math.min(...xs), xMax = Math.max(...xs);
      const yt = niceTicks(options.zeroBased ? 0 : Math.min(...ys), Math.max(...ys));
      const sx = (x) => f.x0 + (xMax === xMin ? 0.5 : (x - xMin) / (xMax - xMin)) * (f.x1 - f.x0);
      const sy = (y) => f.y0 - (y - yt.lo) / (yt.hi - yt.lo) * (f.y0 - f.y1);
      yAxis(f, sy, yt.ticks, options.unit);

      // A few x labels, evenly spread.
      const xt = niceTicks(xMin, xMax, Math.max(2, Math.floor(width / 110)));
      for (const t of xt.ticks) {
        if (t < xMin || t > xMax) continue;
        // Index based axes (runs) only get whole numbers, so labels are never repeated.
        if (options.xFormat && !Number.isInteger(t)) continue;
        const label = svgEl('text', { x: sx(t), y: f.y0 + 18, class: 'axis-text', 'text-anchor': 'middle' }, f.svg);
        label.textContent = options.xFormat ? options.xFormat(t) : tick(t) + (options.xUnit || '');
      }

      for (const ref of options.refLines || []) {
        svgEl('line', { x1: f.x0, x2: f.x1, y1: sy(ref.y), y2: sy(ref.y), class: 'ref-line', stroke: ref.color || 'currentColor' }, f.svg);
        const label = svgEl('text', { x: f.x1 - 4, y: sy(ref.y) - 5, class: 'ref-text', 'text-anchor': 'end', fill: ref.color || 'currentColor' }, f.svg);
        label.textContent = ref.label;
      }

      for (const s of options.series) {
        // Break the line where a sample failed.
        let path = '';
        let pen = false;
        for (const p of s.points) {
          if (p.y === null) { pen = false; continue; }
          path += (pen ? 'L' : 'M') + sx(p.x).toFixed(1) + ' ' + sy(p.y).toFixed(1);
          pen = true;
        }
        if (options.area && s.points.length) {
          const ok = s.points.filter((p) => p.y !== null);
          const area = `M${sx(ok[0].x)} ${f.y0}` + ok.map((p) => `L${sx(p.x)} ${sy(p.y)}`).join('') + `L${sx(ok[ok.length - 1].x)} ${f.y0}Z`;
          svgEl('path', { d: area, fill: s.color, opacity: 0.12 }, f.svg);
        }
        svgEl('path', { d: path, fill: 'none', stroke: s.color, 'stroke-width': 2, 'stroke-linejoin': 'round' }, f.svg);
        for (const p of s.points) {
          if (p.y === null) {
            const cross = svgEl('text', { x: sx(p.x), y: f.y0 - 4, class: 'fail-mark', 'text-anchor': 'middle' }, f.svg);
            cross.textContent = '✕';
            bindTip(cross, `<b>${s.name}</b><br>${p.label || ''}<br><span class="tip-bad">failed</span>`);
            continue;
          }
          const dot = svgEl('circle', { cx: sx(p.x), cy: sy(p.y), r: options.dots === false ? 0 : 3.2, fill: s.color, class: 'dot' }, f.svg);
          const hit = svgEl('circle', { cx: sx(p.x), cy: sy(p.y), r: 9, fill: 'transparent' }, f.svg);
          bindTip(hit, `<b>${s.name}</b><br>${p.label || ''}<br>${fmt(p.y)}${options.unit || ''}`);
          hit.addEventListener('mouseenter', () => dot.setAttribute('r', 5.5));
          hit.addEventListener('mouseleave', () => dot.setAttribute('r', options.dots === false ? 0 : 3.2));
        }
      }
      if (options.legend !== false && options.series.length > 1) legend(container, options.series);
    });
  }

  /** Small legend under a chart. */
  function legend(container, series) {
    const box = document.createElement('div');
    box.className = 'chart-legend';
    box.innerHTML = series.map((s) => `<span><i style="background:${s.color}"></i>${s.name}</span>`).join('');
    container.appendChild(box);
  }

  /**
   * Histogram of values.
   * options: values, color, bins, refLines [{x, label, color}], unit
   */
  function histogram(container, options) {
    responsive(container, (width) => {
      const height = options.height || 220;
      const f = frame(container, width, height, { top: 14, right: 16, bottom: 30, left: 40 });
      const values = options.values.filter((v) => v !== null);
      const bins = options.bins || 12;
      let min = Math.min(...values), max = Math.max(...values);
      // A single value or identical values still need a range to draw.
      if (min === max) { const pad = Math.abs(min) * 0.1 || 1; min -= pad; max += pad; }
      const size = (max - min) / bins;
      const counts = new Array(bins).fill(0);
      for (const v of values) counts[Math.min(bins - 1, Math.floor((v - min) / size))] += 1;
      const yt = niceTicks(0, Math.max(...counts), 4);
      const sy = (c) => f.y0 - c / yt.hi * (f.y0 - f.y1);
      const sx = (v) => f.x0 + (v - min) / (max - min) * (f.x1 - f.x0);
      for (const t of yt.ticks) {
        svgEl('line', { x1: f.x0, x2: f.x1, y1: sy(t), y2: sy(t), class: 'grid' }, f.svg);
        svgEl('text', { x: f.x0 - 8, y: sy(t) + 4, class: 'axis-text', 'text-anchor': 'end' }, f.svg).textContent = t;
      }
      const barWidth = (f.x1 - f.x0) / bins;
      counts.forEach((c, i) => {
        const x = f.x0 + i * barWidth;
        const bar = svgEl('rect', { x: x + 1.5, y: sy(c), width: Math.max(1, barWidth - 3), height: f.y0 - sy(c), rx: 3, fill: options.color, class: 'bar' }, f.svg);
        const from = min + i * size, to = from + size;
        bindTip(bar, `${fmt(from)} – ${fmt(to)}${options.unit || ''}<br><b>${c}</b> sample${c === 1 ? '' : 's'}`);
      });
      for (const v of [min, (min + max) / 2, max]) {
        svgEl('text', { x: sx(v), y: f.y0 + 18, class: 'axis-text', 'text-anchor': v === min ? 'start' : v === max ? 'end' : 'middle' }, f.svg).textContent = fmt(v);
      }
      for (const ref of options.refLines || []) {
        const x = sx(ref.x);
        svgEl('line', { x1: x, x2: x, y1: f.y1, y2: f.y0, class: 'ref-line', stroke: ref.color }, f.svg);
        svgEl('text', { x: x + 4, y: f.y1 + 10 + (ref.offset || 0), class: 'ref-text', fill: ref.color }, f.svg).textContent = ref.label;
      }
    });
  }

  /**
   * Bar chart with one bar per item.
   * options: items [{label, value, color, note}], unit, digits, horizontal, refValue {value, label}
   */
  function bars(container, options) {
    responsive(container, (width) => {
      const items = options.items;
      if (options.horizontal) {
        const rowHeight = 38;
        const height = items.length * rowHeight + 30;
        const f = frame(container, width, height, { top: 8, right: 60, bottom: 22, left: 96 });
        const maxValue = Math.max(...items.map((i) => Math.abs(i.value)), options.refValue ? options.refValue.value : 0);
        const xt = niceTicks(0, maxValue, 4);
        const sx = (v) => f.x0 + v / xt.hi * (f.x1 - f.x0);
        for (const t of xt.ticks) {
          svgEl('line', { x1: sx(t), x2: sx(t), y1: f.y1, y2: f.y0, class: 'grid' }, f.svg);
          svgEl('text', { x: sx(t), y: f.y0 + 16, class: 'axis-text', 'text-anchor': 'middle' }, f.svg).textContent = tick(t, options.digits) + (options.unit || '');
        }
        items.forEach((item, i) => {
          const y = f.y1 + i * rowHeight + 6;
          svgEl('text', { x: f.x0 - 10, y: y + 17, class: 'bar-label', 'text-anchor': 'end' }, f.svg).textContent = item.label;
          const bar = svgEl('rect', { x: f.x0, y, width: Math.max(2, sx(Math.abs(item.value)) - f.x0), height: 24, rx: 6, fill: item.color, class: 'bar' }, f.svg);
          svgEl('text', { x: sx(Math.abs(item.value)) + 8, y: y + 17, class: 'bar-value' }, f.svg).textContent = fmt(item.value, options.digits) + (options.unit || '');
          bindTip(bar, `<b>${item.label}</b><br>${fmt(item.value, options.digits)}${options.unit || ''}${item.note ? '<br>' + item.note : ''}`);
        });
        if (options.refValue) {
          const x = sx(options.refValue.value);
          svgEl('line', { x1: x, x2: x, y1: f.y1, y2: f.y0, class: 'ref-line', stroke: 'currentColor' }, f.svg);
        }
        return;
      }
      const height = options.height || 240;
      const f = frame(container, width, height, { top: 24, right: 16, bottom: 30, left: 52 });
      const maxValue = Math.max(...items.map((i) => i.value));
      const yt = niceTicks(0, maxValue, 4);
      const sy = (v) => f.y0 - v / yt.hi * (f.y0 - f.y1);
      yAxis(f, sy, yt.ticks, options.unit);
      const slot = (f.x1 - f.x0) / items.length;
      const barWidth = Math.min(64, slot * 0.56);
      items.forEach((item, i) => {
        const cx = f.x0 + slot * (i + 0.5);
        const bar = svgEl('rect', { x: cx - barWidth / 2, y: sy(item.value), width: barWidth, height: f.y0 - sy(item.value), rx: 8, fill: item.color, class: 'bar' }, f.svg);
        svgEl('text', { x: cx, y: sy(item.value) - 7, class: 'bar-value', 'text-anchor': 'middle' }, f.svg).textContent = fmt(item.value, options.digits) + (options.unit || '');
        svgEl('text', { x: cx, y: f.y0 + 18, class: 'axis-text', 'text-anchor': 'middle' }, f.svg).textContent = item.label;
        bindTip(bar, `<b>${item.label}</b><br>${fmt(item.value, options.digits)}${options.unit || ''}${item.note ? '<br>' + item.note : ''}`);
      });
    });
  }

  /** Quartile of sorted values with linear interpolation. */
  function quantile(sorted, q) {
    const pos = (sorted.length - 1) * q;
    const base = Math.floor(pos);
    const rest = pos - base;
    return sorted[base + 1] !== undefined ? sorted[base] + rest * (sorted[base + 1] - sorted[base]) : sorted[base];
  }

  /**
   * Box plot with jittered points, one box per group.
   * options: groups [{label, color, values}], unit
   */
  function box(container, options) {
    responsive(container, (width) => {
      const height = options.height || 260;
      const f = frame(container, width, height, { top: 14, right: 16, bottom: 30, left: 52 });
      const all = options.groups.flatMap((g) => g.values);
      const yt = niceTicks(Math.min(...all), Math.max(...all));
      const sy = (v) => f.y0 - (v - yt.lo) / (yt.hi - yt.lo) * (f.y0 - f.y1);
      yAxis(f, sy, yt.ticks, options.unit);
      if (options.refLine !== undefined) {
        svgEl('line', { x1: f.x0, x2: f.x1, y1: sy(options.refLine), y2: sy(options.refLine), class: 'ref-line', stroke: 'currentColor' }, f.svg);
      }
      const slot = (f.x1 - f.x0) / options.groups.length;
      options.groups.forEach((g, i) => {
        const sorted = [...g.values].sort((a, b) => a - b);
        const q1 = quantile(sorted, 0.25), q2 = quantile(sorted, 0.5), q3 = quantile(sorted, 0.75);
        const cx = f.x0 + slot * (i + 0.5);
        const w = Math.min(70, slot * 0.42);
        svgEl('line', { x1: cx, x2: cx, y1: sy(sorted[0]), y2: sy(sorted[sorted.length - 1]), stroke: g.color, 'stroke-width': 1.5 }, f.svg);
        const rect = svgEl('rect', { x: cx - w / 2, y: sy(q3), width: w, height: Math.max(2, sy(q1) - sy(q3)), rx: 6, fill: g.color, 'fill-opacity': 0.22, stroke: g.color, 'stroke-width': 1.5 }, f.svg);
        svgEl('line', { x1: cx - w / 2, x2: cx + w / 2, y1: sy(q2), y2: sy(q2), stroke: g.color, 'stroke-width': 3 }, f.svg);
        bindTip(rect, `<b>${g.label}</b><br>Q1 ${fmt(q1)} · median ${fmt(q2)} · Q3 ${fmt(q3)}<br>min ${fmt(sorted[0])} · max ${fmt(sorted[sorted.length - 1])}`);
        // Deterministic jitter so the points do not move between redraws.
        g.values.forEach((v, j) => {
          const jitter = ((j * 37) % 17 / 17 - 0.5) * w * 0.9;
          const dot = svgEl('circle', { cx: cx + jitter, cy: sy(v), r: 2.6, fill: g.color, opacity: 0.75 }, f.svg);
          bindTip(dot, `<b>${g.label}</b><br>${fmt(v)}${options.unit || ''}`);
        });
        svgEl('text', { x: cx, y: f.y0 + 18, class: 'axis-text', 'text-anchor': 'middle' }, f.svg).textContent = g.label;
      });
    });
  }

  /** Tiny line without axes, for stat cards. */
  function spark(container, values, color) {
    responsive(container, (width) => {
      const height = container.clientHeight || 40;
      const svg = svgEl('svg', { viewBox: `0 0 ${width} ${height}`, width, height }, container);
      const ok = values.filter((v) => v !== null);
      const min = Math.min(...ok), max = Math.max(...ok);
      const sx = (i) => i / (values.length - 1) * (width - 4) + 2;
      const sy = (v) => height - 3 - (v - min) / (max - min || 1) * (height - 6);
      let d = '';
      values.forEach((v, i) => { if (v !== null) d += (d ? 'L' : 'M') + sx(i) + ' ' + sy(v); });
      svgEl('path', { d, fill: 'none', stroke: color, 'stroke-width': 1.8, 'stroke-linejoin': 'round' }, svg);
    });
  }

  /** Ring gauge for a value between 0 and 1. */
  function ring(container, value, color, label) {
    const size = 96, r = 40, c = 2 * Math.PI * r;
    const svg = svgEl('svg', { viewBox: `0 0 ${size} ${size}`, width: size, height: size, class: 'ring' }, container);
    svgEl('circle', { cx: 48, cy: 48, r, fill: 'none', class: 'ring-track', 'stroke-width': 9 }, svg);
    svgEl('circle', { cx: 48, cy: 48, r, fill: 'none', stroke: color, 'stroke-width': 9, 'stroke-linecap': 'round', 'stroke-dasharray': `${c * value} ${c}`, transform: 'rotate(-90 48 48)' }, svg);
    const text = svgEl('text', { x: 48, y: 53, 'text-anchor': 'middle', class: 'ring-text' }, svg);
    text.textContent = label;
  }

  return { line, histogram, bars, box, spark, ring, fmt };
})();

/** Shared helpers used by every report layout. */
const Report = (() => {
  /** Switch between light and dark theme and remember the choice. */
  function initTheme() {
    const root = document.documentElement;
    let saved = null;
    try { saved = localStorage.getItem('ammeter-report-theme'); } catch (e) { /* storage may be blocked */ }
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.dataset.theme = saved || (prefersDark ? 'dark' : 'light');
    document.querySelectorAll('[data-theme-toggle]').forEach((button) => {
      button.addEventListener('click', () => {
        root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
        try { localStorage.setItem('ammeter-report-theme', root.dataset.theme); } catch (e) { /* ignore */ }
      });
    });
  }

  /** Connect every checkbox with data-toggle="id" to the element with that data-chart id. */
  function initToggles() {
    document.querySelectorAll('[data-toggle]').forEach((box) => {
      const apply = () => document.querySelectorAll(`[data-chart="${box.dataset.toggle}"]`).forEach((node) => {
        node.classList.toggle('is-hidden', !box.checked);
      });
      box.addEventListener('change', apply);
      apply();
    });
  }

  /** Ammeters sorted from most to least consistent, by coefficient of variation. Ammeters without a cv are left out. */
  function ranking(data) {
    return data.ammeters.filter((a) => a.stats.cv_percent !== null).sort((a, b) => a.stats.cv_percent - b.stats.cv_percent);
  }

  /** Relative difference between the measured mean and the theoretical mean, in percent. */
  function accuracyError(meter) {
    // Without a theoretical mean, or without measurements, there is nothing to compare.
    if (!meter.expected_mean || meter.stats.mean === null) return null;
    return (meter.stats.mean - meter.expected_mean) / meter.expected_mean * 100;
  }

  /** Mean divided by median, above 1.5 means a few large values pull the mean up. */
  function skew(meter) {
    return meter.stats.median ? meter.stats.mean / meter.stats.median : null;
  }

  /** Points for a time series chart. */
  function points(meter) {
    return meter.samples.map((s) => ({ x: s.t, y: s.v, label: `#${s.i} · t = ${s.t.toFixed(3)} s` }));
  }

  /** Every value divided by the mean, so ammeters on different scales can share one chart. */
  function normalized(meter) {
    return meter.samples.filter((s) => s.v !== null).map((s) => s.v / meter.stats.mean);
  }

  /** Short run time like 14:30:05. */
  function clock(iso) {
    return iso.slice(11, 19);
  }

  /** Short date like 22 Nov. */
  function day(iso) {
    const d = new Date(iso);
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  }

  /** Sun and moon icons for the theme button. */
  const themeIcon = `
    <svg class="icon-sun" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
    <svg class="icon-moon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z"/></svg>`;

  return { initTheme, initToggles, ranking, accuracyError, skew, points, normalized, clock, day, themeIcon };
})();
