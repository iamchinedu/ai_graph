import { AfterViewInit, Component, ElementRef, OnDestroy, OnInit, ViewChild, computed, signal } from '@angular/core';
import { Simulation, forceCollide, forceLink, forceManyBody, forceRadial, forceSimulation, forceX, forceY } from 'd3-force';
import {
  BAD_GLOW, EnvFilter, FAMILY_LABEL, FAM_COLOR, Family, GLink, GNode, LAYERS, Layout, NodeType,
  RawGraph, TYPE_INFO, WORLD, familyOfType, layerY,
} from './graph.model';
import { GraphService } from './graph.service';
import { answer } from './chat-engine';

const LABEL_ALWAYS = new Set<NodeType>(['project', 'model', 'platform', 'tool', 'database', 'account']);
const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const rgba = (hex: string, a: number) => { const [r, g, b] = rgb(hex); return `rgba(${r},${g},${b},${a})`; };

interface Pulse { link: GLink; speed: number; phase: number; color?: string }

@Component({
  selector: 'app-graph',
  templateUrl: './graph.component.html',
  styleUrl: './graph.component.css',
})
export class GraphComponent implements OnInit, AfterViewInit, OnDestroy {
  readonly info = TYPE_INFO;
  readonly families = (Object.keys(FAMILY_LABEL) as (keyof typeof FAMILY_LABEL)[]).map((f) => ({ key: f, label: FAMILY_LABEL[f], color: FAM_COLOR[f] }));
  readonly envs: EnvFilter[] = ['all', 'dev', 'test', 'prod'];

  nodes = signal<GNode[]>([]);
  /** The real dependencies (which project uses what). Used for tracing and impact, so they stay accurate. */
  tlinks = signal<GLink[]>([]);
  /** What is drawn: account -> project -> its models, tools, platforms (-> databases -> tables) and package check. */
  vlinks = signal<GLink[]>([]);
  drawLinks = computed(() => this.vlinks());
  visibleNodes = computed(() => this.nodes());
  error = signal<string | null>(null);
  refreshing = signal(false);
  loadedAt = signal<Date | null>(null);
  env = signal<EnvFilter>('all');
  layout = signal<Layout>('brain');
  selectedId = signal<string | null>(null);
  hoverId = signal<string | null>(null);
  query = signal('');

  chatOpen = signal(false);
  /** The summary section is open by default; its Show/Hide button toggles it. */
  summaryOpen = signal(true);
  /** The chat body (messages and text box); its Show/Hide button toggles it. */
  chatBodyOpen = signal(true);
  messages = signal<{ role: 'user' | 'assistant'; text: string }[]>([]);
  draft = signal('');
  @ViewChild('thread') thread?: ElementRef<HTMLElement>;
  @ViewChild('ask') ask?: ElementRef<HTMLTextAreaElement>;
  @ViewChild('cv') cv!: ElementRef<HTMLCanvasElement>;
  private ctx!: CanvasRenderingContext2D;
  private sim?: Simulation<GNode, GLink>;
  private raf = 0;
  private view = { k: 1, tx: 0, ty: 0 };
  private size = { w: 800, h: 600, dpr: 1 };
  private vPulses: Pulse[] = [];
  private sprites = new Map<string, HTMLCanvasElement>();
  private phases = new Map<string, number>();
  private ro?: ResizeObserver;
  private pressed: GNode | null = null;
  private panning = false;
  private moved = false;
  private last = { x: 0, y: 0 };

  constructor(private graphs: GraphService) {}

  ngOnInit() { return this.refresh(); }

  /** Load the graph again. Keeps the selection, environment and view; the screen never refreshes on its own. */
  async refresh() {
    this.refreshing.set(true);
    try { this.build(await this.graphs.load()); this.error.set(null); this.loadedAt.set(new Date()); }
    catch (e: any) { this.error.set(e.message ?? String(e)); }
    finally { this.refreshing.set(false); }
  }
  ngAfterViewInit() {
    const el = this.cv.nativeElement;
    this.ctx = el.getContext('2d')!;
    this.ro = new ResizeObserver(() => this.resize());
    this.ro.observe(el.parentElement!);
    el.addEventListener('wheel', (e) => this.wheel(e), { passive: false });
    this.resize();
    const frame = (t: number) => { this.draw(t / 1000); this.raf = requestAnimationFrame(frame); };
    this.raf = requestAnimationFrame(frame);
  }
  ngOnDestroy() { cancelAnimationFrame(this.raf); this.sim?.stop(); this.ro?.disconnect(); }

  // ---- data -> real links, then the account-rooted view ------------------------------------
  private build(g: RawGraph) {
    const nodes: GNode[] = g.nodes.map((n) => ({ id: n.node, type: n.type, label: n.label, raw: n, r: TYPE_INFO[n.type].r }));
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const merged = new Map<string, GLink>();
    for (const e of g.edges) {
      const s = byId.get(e.source), t = byId.get(e.target);
      if (!s || !t) continue;
      const key = `${s.id}>${t.id}`;
      let l = merged.get(key);
      if (!l) merged.set(key, (l = { source: s, target: t, edges: [], envs: [] }));
      l.edges.push(e);
      if (e.environment && !l.envs.includes(e.environment)) l.envs.push(e.environment);
    }
    // The inference profile is just the way a project reaches a model, so show project -> model directly.
    const modelOf = new Map<string, GNode>();
    for (const l of merged.values()) if (l.source.type === 'profile' && l.target.type === 'model') modelOf.set(l.source.id, l.target);
    const collapsed = new Map<string, GLink>();
    for (const l of merged.values()) {
      if (l.source.type === 'profile' && modelOf.has(l.source.id)) continue;
      let link = l;
      if (l.target.type === 'profile' && modelOf.has(l.target.id)) link = { source: l.source, target: modelOf.get(l.target.id)!, edges: l.edges, envs: l.envs };
      const key = `${link.source.id}>${link.target.id}`;
      const have = collapsed.get(key);
      if (!have) collapsed.set(key, link);
      else { have.edges.push(...link.edges); for (const e of link.envs) if (!have.envs.includes(e)) have.envs.push(e); }
    }
    const tlinks = [...collapsed.values()];
    const hidden = new Set([...modelOf.keys()]);
    const shown = nodes.filter((n) => !hidden.has(n.id));
    const vlinks = this.deriveView(shown, tlinks);
    const all = shown;
    this.seedPositions(all);
    this.nodes.set(all);
    this.tlinks.set(tlinks);
    this.vlinks.set(vlinks);
    for (const n of all) this.phases.set(n.id, Math.random() * Math.PI * 2);
    this.vPulses = this.makePulses(vlinks, (l) => l.count ?? 0);
    this.startSimulation();
  }

  private makePulses(links: GLink[], calls: (l: GLink) => number): Pulse[] {
    const out: Pulse[] = [];
    for (const l of links) {
      if (l.kind === 'project_account' && l.feeds?.size) {   // the account hands each family's signal on to the project
        for (const f of l.feeds) out.push({ link: l, speed: 0.12 + Math.random() * 0.1, phase: Math.random(), color: FAM_COLOR[f as Family] });
        continue;
      }
      const c = calls(l), n = 1 + (c > 5 ? 1 : 0) + (c > 25 ? 1 : 0);
      for (let i = 0; i < n; i++) out.push({ link: l, speed: 0.12 + Math.random() * 0.14, phase: Math.random() });
    }
    return out;
  }

  private isBadIn(n: GNode, env: string, failNodes: Map<string, Set<string>>) {
    return this.isBroken(n) || !!failNodes.get(env)?.has(n.id);
  }

  /**
   * The tree the graph draws: AWS workload account -> project -> what the project uses.
   * Under a project: models, observability tools, data platforms (platform -> database -> table) and its package check.
   * Signals flow the other way: dependencies feed the project, and the project feeds its account.
   */
  private deriveView(nodes: GNode[], tlinks: GLink[]): GLink[] {
    const out = new Map<string, GLink[]>();
    for (const l of tlinks) (out.get(l.source.id) ?? out.set(l.source.id, []).get(l.source.id)!).push(l);
    const failNodes = new Map<string, Set<string>>();
    for (const l of tlinks) for (const e of l.edges) if (e.status === 'fail' && e.environment) {
      (failNodes.get(e.environment) ?? failNodes.set(e.environment, new Set()).get(e.environment)!).add(l.target.id);
    }
    const reach = (start: string, env: string) => {
      const seen = new Set<string>(), stack = [start];
      while (stack.length) for (const l of out.get(stack.pop()!) ?? []) {
        if ((l.envs.length === 0 || l.envs.includes(env)) && !seen.has(l.target.id)) { seen.add(l.target.id); stack.push(l.target.id); }
      }
      return seen;
    };
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const vmap = new Map<string, GLink>();
    const callsTo = (p: GNode, target: GNode, env: string) =>
      (out.get(p.id) ?? []).filter((l) => l.target === target).flatMap((l) => l.edges)
        .filter((e) => e.environment === env).reduce((s, e) => s + (e.count ?? 0), 0);

    for (const p of nodes.filter((n) => n.type === 'project')) {
      for (const env of Object.keys(p.raw['environments'] ?? {})) {
        const acctLink = (out.get(p.id) ?? []).find((l) => l.target.type === 'account' && l.envs.includes(env));
        if (!acctLink) continue;
        const acct = acctLink.target, D = reach(p.id, env);
        const mine: GLink[] = [];
        const link = (parent: GNode, child: GNode, count: number, kind: string) => {
          const key = `${parent.id}>${child.id}`;
          let l = vmap.get(key);
          if (!l) vmap.set(key, (l = { source: parent, target: child, edges: [], envs: [], count: 0, failEnvs: new Set(), kind }));
          if (!l.envs.includes(env)) l.envs.push(env);
          l.count = (l.count ?? 0) + count;
          if (!mine.includes(l)) mine.push(l);
          return l;
        };
        const root = link(acct, p, 0, 'account_project');   // signal flows project -> account
        root.feeds ??= new Set();
        for (const id of D) {
          const n = byId.get(id);
          if (!n) continue;
          const calls = callsTo(p, n, env);
          if (n.type === 'packages') { link(p, n, 0, 'project_packages'); root.feeds.add('packages'); }
          else if (n.type === 'model') { link(p, n, calls, 'model'); root.feeds.add('ai'); }
          else if (n.type === 'tool') { link(p, n, calls, 'tool'); root.feeds.add('obs'); }
          else if (n.type === 'platform') { link(p, n, 0, 'platform'); root.feeds.add('data'); }
          else if (n.type === 'database') { for (const l of out.get(n.id) ?? []) if (l.target.type === 'platform') link(l.target, n, 0, 'database'); }
          else if (n.type === 'table') { for (const l of out.get(n.id) ?? []) if (l.target.type === 'database') link(l.target, n, calls, 'table'); }
        }
        // a failing thing marks every link on its way inward, up to the account
        const kids = new Map<string, GLink[]>();
        for (const l of mine) (kids.get(l.source.id) ?? kids.set(l.source.id, []).get(l.source.id)!).push(l);
        const bad = (n: GNode): boolean => this.isBadIn(n, env, failNodes) || (kids.get(n.id) ?? []).some((c) => bad(c.target));
        for (const l of mine) if (bad(l.target)) l.failEnvs!.add(env);
      }
    }
    return [...vmap.values()];
  }

  private seedPositions(all: GNode[]) {
    const accounts = all.filter((n) => n.type === 'account');
    accounts.forEach((a, i) => {
      const ang = (i / Math.max(1, accounts.length)) * Math.PI * 2 - Math.PI / 2;
      a.x = WORLD.cx + Math.cos(ang) * 140; a.y = WORLD.cy + Math.sin(ang) * 140;
    });
    for (const n of all) if (n.x === undefined) {
      const ang = Math.random() * Math.PI * 2, r = 120 + Math.random() * 260;
      n.x = WORLD.cx + Math.cos(ang) * r; n.y = WORLD.cy + Math.sin(ang) * r;
    }
  }

  private startSimulation() {
    this.sim?.stop();
    const brain = this.layout() === 'brain';
    const nodes = this.visibleNodes(), links = this.drawLinks();
    const adj = new Map<string, GNode[]>();
    for (const l of links) {
      (adj.get(l.source.id) ?? adj.set(l.source.id, []).get(l.source.id)!).push(l.target);
      (adj.get(l.target.id) ?? adj.set(l.target.id, []).get(l.target.id)!).push(l.source);
    }
    const pull = Object.assign((alpha: number) => {
      for (const n of nodes) {
        n.x = Math.max(40, Math.min(960, n.x ?? 500));
        if (!brain) n.y = Math.max(20, Math.min(WORLD.h - 20, n.y ?? 0));
      }
      if (brain) return;
      for (const n of nodes) {
        const nb = adj.get(n.id);
        if (!nb?.length) continue;
        n.vx = (n.vx ?? 0) + (nb.reduce((s, m) => s + (m.x ?? 0), 0) / nb.length - (n.x ?? 0)) * 0.05 * alpha;
      }
    }, { initialize() {} });
    const dist = (l: GLink) => ({ account_project: 85, project_packages: 36, tool: 90, platform: 90, model: 90, database: 62, table: 46 } as Record<string, number>)[l.kind ?? ''] ?? 80;
    this.sim = forceSimulation<GNode>(nodes)
      .force('link', forceLink<GNode, GLink>(links).id((n) => n.id).distance(brain ? dist : 80).strength(brain ? 0.55 : 0.015))
      .force('charge', forceManyBody<GNode>().strength((n) => (brain ? (n.type === 'table' ? -55 : -170) : -130)))
      .force('collide', forceCollide<GNode>((n) => n.r + (brain ? (n.type === 'table' ? 9 : 15) : 40)).strength(0.9))
      .force('pull', pull)
      .alphaDecay(0.012).velocityDecay(0.38);
    if (brain) {
      // accounts in the middle, projects around them, then models / tools / platforms, then databases and tables
      const R: Partial<Record<NodeType, [number, number]>> = { account: [40, 0.3], project: [190, 0.25], model: [310, 0.1], tool: [310, 0.1], platform: [310, 0.1], database: [380, 0.08], table: [440, 0.08] };
      this.sim.force('radial', forceRadial<GNode>((n) => R[n.type]?.[0] ?? 0, WORLD.cx, WORLD.cy).strength((n) => R[n.type]?.[1] ?? 0))
        .force('x', forceX<GNode>(WORLD.cx).strength(0.02)).force('y', forceY<GNode>(WORLD.cy).strength(0.02));
    } else {
      this.sim.force('x', forceX<GNode>(WORLD.cx).strength(0.012)).force('y', forceY<GNode>((n) => layerY(n.type)).strength(0.9));
    }
    this.sim.tick(300);
    this.sim.alpha(0.5).restart();
    this.fit();
  }

  setLayout(l: Layout) { this.layout.set(l); this.startSimulation(); }
  reset() { this.selectedId.set(null); this.query.set(''); this.env.set('all'); this.startSimulation(); }

  // ---- what is visible, impacted, matched --------------------------------------------------
  private linkVisible(l: GLink, env: EnvFilter) { return env === 'all' || l.envs.length === 0 || l.envs.includes(env); }

  activeSet = computed(() => {
    const env = this.env();
    if (env === 'all') return null;
    const out = new Map<string, GLink[]>();
    for (const l of this.tlinks()) if (this.linkVisible(l, env)) (out.get(l.source.id) ?? out.set(l.source.id, []).get(l.source.id)!).push(l);
    const seen = new Set<string>();
    const stack = this.nodes().filter((n) => n.type === 'project' && out.has(n.id)).map((n) => n.id);
    while (stack.length) {
      const id = stack.pop()!;
      if (seen.has(id)) continue;
      seen.add(id);
      for (const l of out.get(id) ?? []) stack.push(l.target.id);
    }
    return seen;
  });

  trace = (start: string, dir: 'up' | 'down') => this.walk(start, dir);
  private walk(start: string, dir: 'up' | 'down'): Set<string> {
    const env = this.env();
    const adj = new Map<string, string[]>();
    for (const l of this.tlinks()) {
      if (!this.linkVisible(l, env)) continue;
      const [a, b] = dir === 'down' ? [l.source.id, l.target.id] : [l.target.id, l.source.id];
      (adj.get(a) ?? adj.set(a, []).get(a)!).push(b);
    }
    const seen = new Set<string>(), stack = [start];
    while (stack.length) for (const nxt of adj.get(stack.pop()!) ?? []) if (!seen.has(nxt)) { seen.add(nxt); stack.push(nxt); }
    return seen;
  }

  impacted = computed(() => { const id = this.selectedId(); return id ? this.walk(id, 'up') : new Set<string>(); });
  dependsOn = computed(() => { const id = this.selectedId(); return id ? this.walk(id, 'down') : new Set<string>(); });
  selected = computed(() => this.nodes().find((n) => n.id === this.selectedId()) ?? null);
  impactedProjects = computed(() => this.nodes().filter((n) => this.impacted().has(n.id) && n.type === 'project'));
  dependsOnByType = computed(() => {
    const groups: { type: NodeType; items: GNode[] }[] = [];
    for (const t of LAYERS) {
      const items = this.nodes().filter((n) => this.dependsOn().has(n.id) && n.type === t);
      if (items.length) groups.push({ type: t, items });
    }
    return groups;
  });
  failing = computed(() => this.tlinks().filter((l) => this.edgeStatus(l) === 'fail' && this.linkVisible(l, this.env())).length);

  /** Headline numbers for the whole map (shown when nothing is selected). */
  overview = computed(() => {
    const env = this.env(), act = this.activeSet(), ns = this.nodes();
    const inEnv = (e: string | null | undefined) => env === 'all' || !e || e === env;
    const projects = ns.filter((n) => n.type === 'project' && (!act || act.has(n.id)));
    const dependencies = this.drawLinks().filter((l) => this.linkVisible(l, env) && (!act || (act.has(l.source.id) && act.has(l.target.id)))).length;

    const byPackages = new Set<string>(), byModel = new Set<string>(), byOther = new Set<string>();
    for (const n of ns) if (n.type === 'packages' && n.raw['valid'] === false && inEnv(n.raw['environment'])) {
      const proj = ns.find((p) => p.type === 'project' && p.raw['id'] === String(n.raw['id']).split(':')[0]);
      if (proj) byPackages.add(proj.id);
    }
    for (const l of this.tlinks()) {
      if (!l.edges.some((e) => e.status === 'fail' && inEnv(e.environment))) continue;
      if (l.target.type === 'model') byModel.add(l.source.id);
      else if (l.target.type === 'packages') byPackages.add(l.source.id);
      else byOther.add(l.source.id);
    }
    for (const l of this.tlinks()) if (l.target.type === 'model' && l.target.raw['deprecated'] && this.linkVisible(l, env)) byModel.add(l.source.id);
    const pick = (ids: Set<string>) => projects.filter((p) => ids.has(p.id));

    const horizon = new Date(); horizon.setMonth(horizon.getMonth() + 3);
    const soon = ns.filter((n) => n.type === 'model' && n.raw['deprecated'] && n.raw['end_of_life_date'] && new Date(n.raw['end_of_life_date']) <= horizon)
      .map((m) => ({
        model: m, ends: String(m.raw['end_of_life_date']), over: new Date(m.raw['end_of_life_date']) < new Date(),
        projects: new Set(this.tlinks().filter((l) => l.target === m && this.linkVisible(l, env)).map((l) => l.source.id)).size,
      }))
      .sort((a, b) => a.ends.localeCompare(b.ends));
    return { projects: projects.length, dependencies, riskPackages: pick(byPackages), riskModels: pick(byModel), riskOther: pick(byOther),
             atRisk: new Set([...byPackages, ...byModel, ...byOther]).size, soon };
  });
  /** One line for the collapsed summary. */
  brief = computed(() => {
    const n = this.selected();
    if (!n) { const o = this.overview(); return `${o.projects} projects · ${o.dependencies} dependencies · ${o.atRisk} at risk`; }
    if (n.type === 'project') { const e = this.envRuns(n), i = this.issuesOf(n).length; return `${e.reduce((s, r) => s + (r.runs ?? 0), 0)} runs · ${i ? `${i} issue${i === 1 ? '' : 's'}` : 'no issues'}`; }
    const p = this.impactedProjects().length;
    return `${p} project${p === 1 ? '' : 's'} depend${p === 1 ? 's' : ''} on this`;
  });
  /** Sample questions: about the selected node when there is one, otherwise general. */
  suggestions = computed(() => {
    const n = this.selected();
    if (n?.type === 'project') return [`What does ${n.label} depend on?`, 'Which projects are at risk?', 'What breaks if Claude 3 Sonnet is deprecated?'];
    if (n) return [`What breaks if ${n.label} fails?`, 'Which projects are at risk?', 'How many projects depend on HoneyHive?'];
    return ['What breaks if Claude 3 Sonnet is deprecated?', 'How many projects depend on HoneyHive?', 'Which projects are at risk?', 'What does HR policy bot depend on?'];
  });

  openChat() { this.chatOpen.set(true); this.chatBodyOpen.set(true); setTimeout(() => this.ask?.nativeElement.focus()); }
  /** Enter sends; Shift+Enter adds a new line. */
  onEnter(ev: Event) { if (!(ev as KeyboardEvent).shiftKey) { ev.preventDefault(); this.send(); } }
  /** Put a sample question in the text box so the person can edit it, then send it. */
  fill(q: string) { this.draft.set(q); setTimeout(() => { const el = this.ask?.nativeElement; if (el) { el.focus(); el.setSelectionRange(q.length, q.length); } }); }
  send(text?: string) {
    const q = (text ?? this.draft()).trim();
    if (!q) return;
    this.draft.set('');
    if (!this.chatOpen()) this.openChat();
    const res = answer(q, { nodes: this.nodes(), links: this.tlinks(), env: this.env(), selected: this.selected(), trace: this.trace });
    this.messages.update((m) => [...m, { role: 'user', text: q }, { role: 'assistant', text: res.text }]);
    if (res.focus) this.selectedId.set(res.focus);
    setTimeout(() => { const el = this.thread?.nativeElement; if (el) el.scrollTop = el.scrollHeight; });
  }

  /** Everything lit up when a node is selected: the real path plus the accounts and categories it passes through. */
  focusSet = computed(() => {
    const sel = this.selected();
    if (!sel) return null;
    const env = this.env(), S = new Set<string>([sel.id, ...this.impacted(), ...this.dependsOn()]);
    if (sel.type === 'account') {
      // the whole world of this account: its projects, and what they use in the environments that run under it
      for (const l of this.vlinks()) {
        if (l.source.id !== sel.id) continue;
        const envs = new Set(l.envs), stack = [l.target.id];
        S.add(l.target.id);
        while (stack.length) {
          const cur = stack.pop()!;
          for (const v of this.vlinks()) if (v.source.id === cur && v.envs.some((e) => envs.has(e)) && !S.has(v.target.id)) { S.add(v.target.id); stack.push(v.target.id); }
        }
      }
      return S;
    }
    for (const l of this.tlinks()) if (l.target.type === 'account' && S.has(l.source.id) && this.linkVisible(l, env)) S.add(l.target.id);
    return S;
  });

  nodeOpacity(n: GNode): number {
    const act = this.activeSet();
    if (act && !act.has(n.id)) return 0.08;
    const q = this.query().trim().toLowerCase();
    if (q && !n.label.toLowerCase().includes(q)) return 0.12;
    const f = this.focusSet();
    return f && !f.has(n.id) ? 0.1 : 1;
  }

  /** Real links: failing when the last check says so. */
  edgeStatus(l: GLink): string | null {
    const env = this.env();
    const rel = l.edges.filter((e) => env === 'all' || !e.environment || e.environment === env);
    if (rel.some((e) => e.status === 'fail')) return 'fail';
    return rel.some((e) => e.status === 'pass') ? 'pass' : null;
  }
  private isFailing(l: GLink) {
    const env = this.env(), f = l.failEnvs!;
    return env === 'all' ? f.size > 0 : f.has(env);
  }
  linkOpacity(l: GLink): number {
    const env = this.env(), act = this.activeSet();
    if (!this.linkVisible(l, env) || (act && !(act.has(l.source.id) && act.has(l.target.id)))) return 0.03;
    const f = this.focusSet();
    if (f) return f.has(l.source.id) && f.has(l.target.id) ? 1 : 0.04;
    return 0.6;
  }

  // ---- node look ---------------------------------------------------------------------------
  family(n: GNode): Family { return familyOfType(n.type); }
  color(n: GNode): string {
    return FAM_COLOR[this.family(n)];
  }
  /** A signal takes the color of the family it comes from; red when something on the way is failing. */
  signalColor(l: GLink): string { return this.isFailing(l) ? BAD_GLOW : this.color(l.target); }
  shortLabel(n: GNode) {
    if (n.type === 'packages') return `Packages · ${n.raw['environment']}`;
    if (n.type === 'account') return `AWS ${n.label}`;
    return n.type === 'table' ? n.label.split('.').slice(1).join('.') || n.label : n.label;
  }
  packagesState(n: GNode) { return n.raw['valid'] === true ? 'valid' : n.raw['valid'] === false ? 'invalid' : 'not checked'; }
  isDeprecated(n: GNode) { return n.type === 'model' && n.raw['deprecated'] === true; }
  isBroken(n: GNode) {
    return (n.type === 'packages' && n.raw['valid'] === false) || (n.type === 'table' && n.raw['table_exists'] === false)
      || n.raw['status'] === 'unregistered' || (n.type === 'profile' && !!n.raw['status'] && n.raw['status'] !== 'active')
      || this.isDeprecated(n);
  }
  envRuns(n: GNode): { env: string; runs: number | null; last: string | null; pkgs: boolean | null; reason: string | null }[] {
    const e = n.raw['environments'] ?? {};
    return Object.keys(e).map((k) => ({ env: k, runs: e[k].run_count ?? null, last: e[k].last_init_at ?? null,
      pkgs: e[k].packages_valid ?? null, reason: e[k].packages_reason ?? null }));
  }
  impactedEdges(_n: GNode) {
    return this.impactedProjects().map((p) => {
      const envs = new Set<string>();
      let status: string | null = null;
      for (const l of this.tlinks()) {
        if (l.source.id !== p.id) continue;
        for (const e of l.edges) if (e.environment && (this.env() === 'all' || e.environment === this.env())) {
          envs.add(e.environment);
          if (e.status === 'fail') status = 'fail'; else if (!status) status = e.status ?? null;
        }
      }
      return { project: p, envs: [...envs].sort(), status };
    });
  }
  /** "End of life 2026-12-01 (in 19 days)" or "Ended on ... (12 days ago)". */
  eolText(date: string | null | undefined): string {
    if (!date) return 'End-of-life date not set';
    const days = Math.ceil((new Date(date).getTime() - Date.now()) / 86400000);
    return days < 0 ? `Ended on ${date} (${-days} ${-days === 1 ? 'day' : 'days'} ago)` : `End of life ${date} (in ${days} ${days === 1 ? 'day' : 'days'})`;
  }
  /** Why a project is at risk: invalid packages, deprecated models, missing tables and other failed checks. */
  issuesOf(n: GNode): { title: string; detail: string; id: string }[] {
    if (n.type !== 'project') return [];
    const env = this.env(), out: { title: string; detail: string; id: string }[] = [];
    for (const r of this.envRuns(n)) {
      if (r.pkgs === false && (env === 'all' || r.env === env)) {
        out.push({ title: `Package dependency conflict (${r.env})`, detail: r.reason ?? 'A package requirement is not met.', id: `packages:${n.raw['id']}:${r.env}` });
      }
    }
    for (const l of this.tlinks()) {
      if (l.source.id !== n.id || l.target.type === 'packages') continue;
      const bad = l.edges.filter((e) => e.status === 'fail' && (env === 'all' || e.environment === env));
      const t = l.target;
      if (!bad.length && !(t.type === 'model' && this.isDeprecated(t) && this.linkVisible(l, env))) continue;
      const envs = [...new Set((bad.length ? bad : l.edges).map((e) => e.environment).filter((e) => env === 'all' || e === env))].join(', ');
      if (t.type === 'model') out.push({ title: `Model deprecated: ${t.label}`, detail: `${this.eolText(t.raw['end_of_life_date'])}. Used in ${envs || 'this project'}.`, id: t.id });
      else out.push({ title: `${TYPE_INFO[t.type].label} failing: ${t.label}`, detail: bad[0]?.status_reason ?? 'The last check failed.', id: t.id });
    }
    return out;
  }
  /** Pill text for a dependency: broken ones say why. */
  pillLabel(d: GNode): string {
    if (d.type === 'model' && this.isDeprecated(d)) return `${d.label} · ends ${d.raw['end_of_life_date'] ?? 'unknown'}`;
    if (d.type === 'packages') return `${this.shortLabel(d)} · ${d.raw['valid'] === false ? 'invalid' : d.raw['valid'] === true ? 'valid' : 'not checked'}`;
    if (d.type === 'table' && d.raw['table_exists'] === false) return `${this.shortLabel(d)} · missing`;
    return this.shortLabel(d);
  }
  fmt(ts: string | null) { return ts ? ts.replace('T', ' ').replace('Z', ' UTC') : 'never'; }

  // ---- canvas ------------------------------------------------------------------------------
  private resize() {
    const el = this.cv.nativeElement, box = el.parentElement!.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.size = { w: Math.max(300, box.width), h: Math.max(300, box.height), dpr };
    el.width = this.size.w * dpr; el.height = this.size.h * dpr;
    el.style.width = `${this.size.w}px`; el.style.height = `${this.size.h}px`;
    this.fit();
  }

  /** Zoom and pan so every visible node is on screen. */
  private fit() {
    const ns = this.visibleNodes();
    let x0 = 0, y0 = 0, x1 = WORLD.w, y1 = WORLD.h;
    if (this.layout() === 'brain' && ns.length) {
      x0 = Math.min(...ns.map((n) => n.x ?? 0)) - 60; x1 = Math.max(...ns.map((n) => n.x ?? 0)) + 60;
      y0 = Math.min(...ns.map((n) => n.y ?? 0)) - 40; y1 = Math.max(...ns.map((n) => n.y ?? 0)) + 50;
    }
    const k = Math.min(this.size.w / (x1 - x0), this.size.h / (y1 - y0)) * 0.97;
    this.view = { k, tx: (this.size.w - (x1 - x0) * k) / 2 - x0 * k, ty: (this.size.h - (y1 - y0) * k) / 2 - y0 * k };
  }

  private sprite(color: string): HTMLCanvasElement {
    let c = this.sprites.get(color);
    if (!c) {
      c = document.createElement('canvas'); c.width = c.height = 128;
      const g = c.getContext('2d')!, grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
      grad.addColorStop(0, rgba(color, 0.95)); grad.addColorStop(0.25, rgba(color, 0.35)); grad.addColorStop(1, rgba(color, 0));
      g.fillStyle = grad; g.fillRect(0, 0, 128, 128);
      this.sprites.set(color, c);
    }
    return c;
  }

  private bend(l: GLink) {
    const sx = l.source.x ?? 0, sy = l.source.y ?? 0, tx = l.target.x ?? 0, ty = l.target.y ?? 0;
    const dx = tx - sx, dy = ty - sy, len = Math.hypot(dx, dy) || 1;
    const sign = (l.source.id.charCodeAt(l.source.id.length - 1) + l.target.id.charCodeAt(l.target.id.length - 1)) % 2 ? 1 : -1;
    const off = Math.min(40, len * 0.12) * sign;
    return { sx, sy, tx, ty, cx: (sx + tx) / 2 - (dy / len) * off, cy: (sy + ty) / 2 + (dx / len) * off };
  }
  private at(b: { sx: number; sy: number; tx: number; ty: number; cx: number; cy: number }, t: number) {
    const u = 1 - t;
    return { x: u * u * b.sx + 2 * u * t * b.cx + t * t * b.tx, y: u * u * b.sy + 2 * u * t * b.cy + t * t * b.ty };
  }

  private draw(t: number) {
    const ctx = this.ctx; if (!ctx) return;
    const { w, h, dpr } = this.size, { k, tx, ty } = this.view;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const bg = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
    bg.addColorStop(0, '#0d1424'); bg.addColorStop(1, '#04060b');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
    ctx.setTransform(dpr * k, 0, 0, dpr * k, dpr * tx, dpr * ty);
    if (this.layout() === 'ladder') this.drawBands(ctx);

    const links = this.drawLinks(), brain = this.layout() === 'brain';
    for (const l of links) {
      const o = this.linkOpacity(l); if (o < 0.035) continue;
      const b = this.bend(l), bad = this.isFailing(l);
      ctx.strokeStyle = rgba(this.signalColor(l), 0.42 * o);
      ctx.lineWidth = (o > 0.9 ? 1.6 : 1) / Math.sqrt(k);
      ctx.setLineDash(bad ? [5, 4] : []);
      ctx.beginPath(); ctx.moveTo(b.sx, b.sy); ctx.quadraticCurveTo(b.cx, b.cy, b.tx, b.ty); ctx.stroke();
    }
    ctx.setLineDash([]);

    // signals flow INTO the project: from each dependency inward
    ctx.globalCompositeOperation = 'lighter';
    for (const p of this.vPulses) {
      const o = this.linkOpacity(p.link); if (o < 0.2) continue;
      const bad = this.isFailing(p.link);
      const f = 1 - ((p.phase + t * p.speed * (bad ? 0.6 : 1)) % 1);
      const pt = this.at(this.bend(p.link), f);
      const s = (bad ? 22 : 17) * (0.7 + 0.3 * Math.sin(t * 6 + p.phase * 9)) * o;
      ctx.drawImage(this.sprite(!bad && p.color ? p.color : this.signalColor(p.link)), pt.x - s / 2, pt.y - s / 2, s, s);
    }

    const nodes = [...this.visibleNodes()].sort((a, b) => this.nodeOpacity(a) - this.nodeOpacity(b));
    for (const n of nodes) {
      const o = this.nodeOpacity(n), col = this.color(n), x = n.x ?? 0, y = n.y ?? 0, hub = false;
      const breathe = 1 + 0.07 * Math.sin(t * 1.6 + (this.phases.get(n.id) ?? 0));
      const r = n.r * 0.85 * breathe, halo = r * (n.id === this.selectedId() ? 7 : hub ? 3.5 : 5);
      ctx.globalCompositeOperation = 'lighter'; ctx.globalAlpha = o * (hub ? 0.6 : 1);
      ctx.drawImage(this.sprite(col), x - halo, y - halo, halo * 2, halo * 2);
      ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = o * (hub ? 0.75 : 1);
      const body = ctx.createRadialGradient(x - r * 0.35, y - r * 0.4, r * 0.1, x, y, r);
      body.addColorStop(0, '#ffffff'); body.addColorStop(0.35, col); body.addColorStop(1, rgba(col, 0.55));
      ctx.fillStyle = body; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = o;
      if (this.isBroken(n)) { ctx.strokeStyle = BAD_GLOW; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.arc(x, y, r + 4, 0, Math.PI * 2); ctx.stroke(); }
      if (n.id === this.selectedId()) { ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 1.4; ctx.beginPath(); ctx.arc(x, y, r + 6, 0, Math.PI * 2); ctx.stroke(); }
      ctx.globalAlpha = 1;
    }

    ctx.globalCompositeOperation = 'source-over';
    ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    for (const n of this.visibleNodes()) {
      const o = this.nodeOpacity(n);
      const show = LABEL_ALWAYS.has(n.type) || n.id === this.hoverId() || n.id === this.selectedId() || (this.selectedId() && o > 0.9) || k > 1.5;
      if (!show || o < 0.2) continue;
      const big = n.type === 'project' || n.type === 'model' || n.type === 'account', hub = false;
      ctx.font = `${big ? 500 : 400} ${big ? 12 : hub ? 10 : 10.5}px system-ui, sans-serif`;
      ctx.fillStyle = hub ? rgba(this.color(n), Math.min(1, o) * 0.9) : `rgba(232,238,248,${Math.min(1, o) * (big ? 0.95 : 0.78)})`;
      ctx.fillText(this.shortLabel(n), n.x ?? 0, (n.y ?? 0) + n.r + 6);
    }
    ctx.globalAlpha = 1;
  }

  private drawBands(ctx: CanvasRenderingContext2D) {
    ctx.textBaseline = 'alphabetic'; ctx.textAlign = 'left';
    LAYERS.forEach((t, i) => {
      const y = layerY(t);
      ctx.fillStyle = i % 2 ? 'rgba(160,190,255,0.02)' : 'rgba(160,190,255,0.05)';
      ctx.fillRect(0, y - 46, WORLD.w, 92);
      ctx.fillStyle = 'rgba(160,190,255,0.4)'; ctx.font = '12px system-ui, sans-serif';
      ctx.fillText(`${i + 1}. ${TYPE_INFO[t].plural}`, 12, y - 30);
    });
  }

  // ---- pointer interaction -----------------------------------------------------------------
  private world(ev: PointerEvent | WheelEvent) {
    const r = this.cv.nativeElement.getBoundingClientRect();
    return { px: ev.clientX - r.left, py: ev.clientY - r.top, x: (ev.clientX - r.left - this.view.tx) / this.view.k, y: (ev.clientY - r.top - this.view.ty) / this.view.k };
  }
  private hit(x: number, y: number): GNode | null {
    let best: GNode | null = null, bd = Infinity;
    for (const n of this.visibleNodes()) {
      const d = Math.hypot((n.x ?? 0) - x, (n.y ?? 0) - y);
      if (d < Math.max(n.r + 8, 14) && d < bd && this.nodeOpacity(n) > 0.15) { best = n; bd = d; }
    }
    return best;
  }
  down(ev: PointerEvent) {
    const w = this.world(ev);
    (ev.currentTarget as Element).setPointerCapture(ev.pointerId);
    this.pressed = this.hit(w.x, w.y); this.panning = !this.pressed; this.moved = false;
    this.last = { x: ev.clientX, y: ev.clientY };
  }
  move(ev: PointerEvent) {
    const w = this.world(ev);
    if (!this.pressed && !this.panning) {
      const n = this.hit(w.x, w.y);
      this.hoverId.set(n?.id ?? null);
      this.cv.nativeElement.style.cursor = n ? 'pointer' : 'grab';
      return;
    }
    if (!this.moved && Math.hypot(ev.clientX - this.last.x, ev.clientY - this.last.y) < 4) return;
    if (!this.moved && this.pressed) this.sim?.alphaTarget(0.25).restart();
    this.moved = true;
    if (this.pressed) { this.pressed.fx = w.x; this.pressed.fy = w.y; }
    else { this.view.tx += ev.clientX - this.last.x; this.view.ty += ev.clientY - this.last.y; this.last = { x: ev.clientX, y: ev.clientY }; }
  }
  up() {
    const n = this.pressed;
    if (n && this.moved) { n.fx = null; n.fy = null; this.sim?.alphaTarget(0); }
    else if (n) this.selectedId.update((s) => (s === n.id ? null : n.id));
    else if (!n && !this.moved) this.selectedId.set(null);
    this.pressed = null; this.panning = false;
  }
  leave() { if (!this.pressed) this.hoverId.set(null); }
  private wheel(ev: WheelEvent) {
    ev.preventDefault();
    const w = this.world(ev), f = Math.exp(-ev.deltaY * 0.0012);
    const k = Math.max(0.3, Math.min(4, this.view.k * f));
    this.view = { k, tx: w.px - w.x * k, ty: w.py - w.y * k };
  }
}
