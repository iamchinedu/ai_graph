// The dependency map canvas: glowing nodes, signals flowing inward, zoom, pan and drag.
// Plain JavaScript, no build step. Python decides what exists, where it is and how bright it is (graph_view.View.scene);
// this file only paints it and reports clicks back with setTriggerValue("click", {id, n}).

const STATES = new WeakMap();   // one state per mounted map, so reruns reuse the same canvas, zoom and dragged nodes
const BAD = '#ff5f6d';
const rgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const rgba = (hex, a) => { const [r, g, b] = rgb(hex); return `rgba(${r},${g},${b},${a})`; };

function createState(root) {
  const stage = root.querySelector('.stage');
  const cv = root.querySelector('canvas');
  const legend = root.querySelector('.legend');
  const ctx = cv.getContext('2d');
  const s = {
    data: { nodes: [], links: [], legend: [], height: 680, fit_key: '' },
    byId: new Map(), pulses: [], pulseSig: '', legendSig: '', phases: new Map(), sprites: new Map(),
    over: new Map(),                     // nodes the person dragged: id -> [x, y]
    view: { k: 1, tx: 0, ty: 0 }, size: { w: 800, h: 600, dpr: 1 }, needFit: true, fitKey: null,
    hover: null, pressed: null, panning: false, moved: false, last: { x: 0, y: 0 }, seq: 0,
    trigger: () => {}, raf: 0,
  };

  const pos = (n) => s.over.get(n.id) || [n.x, n.y];

  // ---- data from Python ----------------------------------------------------------------------
  s.update = (data) => {
    s.data = data;
    s.byId = new Map(data.nodes.map((n) => [n.id, n]));
    if (data.fit_key !== s.fitKey) { s.fitKey = data.fit_key; s.over.clear(); s.needFit = true; }
    for (const n of data.nodes) if (!s.phases.has(n.id)) s.phases.set(n.id, Math.random() * Math.PI * 2);
    stage.style.height = `${data.height}px`;

    const sig = data.links.map((l) => `${l.s}>${l.t}:${l.count}:${l.feeds.join()}`).join('|');
    if (sig !== s.pulseSig) { s.pulseSig = sig; s.pulses = makePulses(data.links); }

    const lsig = data.legend.map((i) => i.label + i.color).join('|');
    if (lsig !== s.legendSig) {
      s.legendSig = lsig;
      legend.replaceChildren(...data.legend.map((item) => {
        const span = document.createElement('span');
        const dot = document.createElement('i');
        dot.style.background = item.color; dot.style.boxShadow = `0 0 8px ${item.color}`;
        span.append(dot, item.label);
        return span;
      }));
    }
    resize();
  };

  // a few signals per link, more where there are more calls; the account hands each family's signal on in its own color
  const makePulses = (links) => {
    const out = [];
    links.forEach((l, li) => {
      if (l.feeds.length) { for (const color of l.feeds) out.push({ li, speed: 0.12 + Math.random() * 0.1, phase: Math.random(), color }); return; }
      const c = l.count || 0, n = 1 + (c > 5 ? 1 : 0) + (c > 25 ? 1 : 0);
      for (let i = 0; i < n; i++) out.push({ li, speed: 0.12 + Math.random() * 0.14, phase: Math.random() });
    });
    return out;
  };

  // ---- size and fit --------------------------------------------------------------------------
  const resize = () => {
    const box = stage.getBoundingClientRect();
    if (box.width < 10 || box.height < 10) return;
    const dpr = window.devicePixelRatio || 1;
    s.size = { w: box.width, h: box.height, dpr };
    cv.width = box.width * dpr; cv.height = box.height * dpr;
    cv.style.width = `${box.width}px`; cv.style.height = `${box.height}px`;
    if (s.needFit) fit();
  };

  const fit = () => {
    const ns = s.data.nodes;
    if (!ns.length) return;
    const xs = ns.map((n) => pos(n)[0]), ys = ns.map((n) => pos(n)[1]);
    const x0 = Math.min(...xs) - 60, x1 = Math.max(...xs) + 60, y0 = Math.min(...ys) - 40, y1 = Math.max(...ys) + 70;
    const k = Math.min(s.size.w / (x1 - x0), s.size.h / (y1 - y0)) * 0.97;
    s.view = { k, tx: (s.size.w - (x1 - x0) * k) / 2 - x0 * k, ty: (s.size.h - (y1 - y0) * k) / 2 - y0 * k };
    s.needFit = false;
  };

  // ---- drawing -------------------------------------------------------------------------------
  const sprite = (color) => {                       // a soft round glow, drawn once per color
    let c = s.sprites.get(color);
    if (!c) {
      c = document.createElement('canvas'); c.width = c.height = 128;
      const g = c.getContext('2d'), grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
      grad.addColorStop(0, rgba(color, 0.95)); grad.addColorStop(0.25, rgba(color, 0.35)); grad.addColorStop(1, rgba(color, 0));
      g.fillStyle = grad; g.fillRect(0, 0, 128, 128);
      s.sprites.set(color, c);
    }
    return c;
  };

  const bend = (l) => {                              // links are gentle curves
    const [sx, sy] = pos(s.byId.get(l.s)), [tx, ty] = pos(s.byId.get(l.t));
    const dx = tx - sx, dy = ty - sy, len = Math.hypot(dx, dy) || 1;
    const sign = (l.s.charCodeAt(l.s.length - 1) + l.t.charCodeAt(l.t.length - 1)) % 2 ? 1 : -1;
    const off = Math.min(40, len * 0.12) * sign;
    return { sx, sy, tx, ty, cx: (sx + tx) / 2 - (dy / len) * off, cy: (sy + ty) / 2 + (dx / len) * off };
  };
  const at = (b, t) => {
    const u = 1 - t;
    return { x: u * u * b.sx + 2 * u * t * b.cx + t * t * b.tx, y: u * u * b.sy + 2 * u * t * b.cy + t * t * b.ty };
  };

  const draw = (t) => {
    const { w, h, dpr } = s.size, { k, tx, ty } = s.view, links = s.data.links;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const bg = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
    bg.addColorStop(0, '#0d1424'); bg.addColorStop(1, '#04060b');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * tx, dpr * ty);

    for (const l of links) {
      if (l.opacity < 0.035) continue;
      const b = bend(l);
      ctx.strokeStyle = rgba(l.color, 0.42 * l.opacity);
      ctx.lineWidth = (l.opacity > 0.9 ? 1.6 : 1) / Math.sqrt(k);
      ctx.setLineDash(l.bad ? [5, 4] : []);
      ctx.beginPath(); ctx.moveTo(b.sx, b.sy); ctx.quadraticCurveTo(b.cx, b.cy, b.tx, b.ty); ctx.stroke();
    }
    ctx.setLineDash([]);

    // signals flow INTO the project: from each dependency inward
    ctx.globalCompositeOperation = 'lighter';
    for (const p of s.pulses) {
      const l = links[p.li];
      if (!l || l.opacity < 0.2) continue;
      const f = 1 - ((p.phase + t * p.speed * (l.bad ? 0.6 : 1)) % 1);
      const pt = at(bend(l), f);
      const size = (l.bad ? 22 : 17) * (0.7 + 0.3 * Math.sin(t * 6 + p.phase * 9)) * l.opacity;
      ctx.drawImage(sprite(!l.bad && p.color ? p.color : l.color), pt.x - size / 2, pt.y - size / 2, size, size);
    }

    const nodes = [...s.data.nodes].sort((a, b) => a.opacity - b.opacity);
    for (const n of nodes) {
      const [x, y] = pos(n), o = n.opacity;
      const breathe = 1 + 0.07 * Math.sin(t * 1.6 + (s.phases.get(n.id) || 0));
      const r = n.r * 0.85 * breathe, halo = r * (n.selected ? 7 : 5);
      ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = o;
      ctx.drawImage(sprite(n.color), x - halo, y - halo, halo * 2, halo * 2);
      ctx.globalCompositeOperation = 'source-over';
      const body = ctx.createRadialGradient(x - r * 0.35, y - r * 0.4, r * 0.1, x, y, r);
      body.addColorStop(0, '#ffffff'); body.addColorStop(0.35, n.color); body.addColorStop(1, rgba(n.color, 0.55));
      ctx.fillStyle = body; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
      if (n.broken) { ctx.strokeStyle = BAD; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.arc(x, y, r + 4, 0, Math.PI * 2); ctx.stroke(); }
      if (n.selected) { ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(x, y, r + 6, 0, Math.PI * 2); ctx.stroke(); }
      ctx.globalAlpha = 1;
    }

    ctx.globalCompositeOperation = 'source-over';
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (const n of s.data.nodes) {
      const o = n.opacity;
      if (!(n.always || n.id === s.hover || k > 1.5) || o < 0.2) continue;
      const [x, y] = pos(n);
      ctx.font = `${n.big ? 500 : 400} ${n.big ? 12 : 10.5}px system-ui, sans-serif`;
      ctx.fillStyle = `rgba(232,238,248,${Math.min(1, o) * (n.big ? 0.95 : 0.78)})`;
      ctx.fillText(n.label, x, y + n.r + 6);
    }
    ctx.globalAlpha = 1;
  };

  // ---- pointer: drag a node, drag the background, scroll to zoom, click to select -------------
  const world = (ev) => {
    const r = cv.getBoundingClientRect(), px = ev.clientX - r.left, py = ev.clientY - r.top;
    return { px, py, x: (px - s.view.tx) / s.view.k, y: (py - s.view.ty) / s.view.k };
  };
  const hit = (x, y) => {
    let best = null, bd = Infinity;
    for (const n of s.data.nodes) {
      const [nx, ny] = pos(n), d = Math.hypot(nx - x, ny - y);
      if (d < Math.max(n.r + 8, 14) && d < bd && n.opacity > 0.15) { best = n; bd = d; }
    }
    return best;
  };

  cv.onpointerdown = (ev) => {
    const w = world(ev);
    cv.setPointerCapture(ev.pointerId);
    s.pressed = hit(w.x, w.y); s.panning = !s.pressed; s.moved = false;
    s.last = { x: ev.clientX, y: ev.clientY };
  };
  cv.onpointermove = (ev) => {
    const w = world(ev);
    if (!s.pressed && !s.panning) {
      const n = hit(w.x, w.y);
      s.hover = n ? n.id : null;
      cv.style.cursor = n ? 'pointer' : 'grab';
      return;
    }
    if (!s.moved && Math.hypot(ev.clientX - s.last.x, ev.clientY - s.last.y) < 4) return;
    s.moved = true;
    if (s.pressed) s.over.set(s.pressed.id, [w.x, w.y]);
    else { s.view.tx += ev.clientX - s.last.x; s.view.ty += ev.clientY - s.last.y; s.last = { x: ev.clientX, y: ev.clientY }; }
  };
  cv.onpointerup = () => {
    if (!s.moved) s.trigger('click', { id: s.pressed ? s.pressed.id : null, n: ++s.seq });   // a click, not a drag
    s.pressed = null; s.panning = false;
  };
  cv.onpointercancel = () => { s.pressed = null; s.panning = false; };
  cv.onpointerleave = () => { if (!s.pressed) s.hover = null; };
  cv.onwheel = (ev) => {
    ev.preventDefault();
    const w = world(ev), k = Math.max(0.3, Math.min(4, s.view.k * Math.exp(-ev.deltaY * 0.0012)));
    s.view = { k, tx: w.px - w.x * k, ty: w.py - w.y * k };
  };

  // ---- run -----------------------------------------------------------------------------------
  const ro = new ResizeObserver(resize);
  ro.observe(stage);
  const frame = (ms) => { draw(ms / 1000); s.raf = requestAnimationFrame(frame); };
  s.raf = requestAnimationFrame(frame);
  s.cleanup = () => { cancelAnimationFrame(s.raf); ro.disconnect(); };
  return s;
}

export default function (component) {
  const { data, parentElement, setTriggerValue } = component;
  let state = STATES.get(parentElement);
  if (!state) { state = createState(parentElement); STATES.set(parentElement, state); }
  state.trigger = setTriggerValue;
  state.update(data);
  return state.cleanup;
}
