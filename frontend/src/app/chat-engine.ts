import { GLink, GNode } from './graph.model';

export interface ChatContext {
  nodes: GNode[];
  links: GLink[];                     // the real dependencies
  env: string;                        // 'all' or one environment
  selected: GNode | null;
  trace: (id: string, dir: 'up' | 'down') => Set<string>;
}
export interface Answer { text: string; focus?: string }

const scope = (env: string) => (env === 'all' ? 'in all environments' : `in ${env}`);
const plural = (n: number, one: string, many = one + 's') => `${n} ${n === 1 ? one : many}`;

/** Names a person might type for a node. */
function names(n: GNode): string[] {
  if (n.type === 'table') return [n.label.toLowerCase(), n.label.split('.').slice(1).join('.').toLowerCase()];
  return [n.label.toLowerCase()];
}

function findNodes(q: string, c: ChatContext): GNode[] {
  let best = 0, hits: GNode[] = [];
  for (const n of c.nodes) {
    if (n.type === 'packages') continue;
    for (const nm of names(n)) {
      if (nm.length < 3 || !q.includes(nm)) continue;
      if (nm.length > best) { best = nm.length; hits = [n]; }
      else if (nm.length === best && !hits.includes(n)) hits.push(n);
    }
  }
  return hits;
}

function impactRows(id: string, c: ChatContext) {
  const up = c.trace(id, 'up');
  const reach = new Set<string>([id, ...up]);
  const rows: { project: GNode; envs: string[]; failing: boolean; reasons: string[] }[] = [];
  for (const p of c.nodes.filter((n) => n.type === 'project' && up.has(n.id))) {
    const envs = new Set<string>(), reasons: string[] = [];
    let failing = false;
    for (const l of c.links) {
      if (l.source.id !== p.id || !reach.has(l.target.id)) continue;
      for (const e of l.edges) {
        if (!e.environment || (c.env !== 'all' && e.environment !== c.env)) continue;
        envs.add(e.environment);
        if (e.status === 'fail') { failing = true; if (e.status_reason) reasons.push(e.status_reason); }
      }
    }
    rows.push({ project: p, envs: [...envs].sort(), failing, reasons });
  }
  return rows;
}

function failingReport(c: ChatContext): string {
  const lines: string[] = [];
  for (const l of c.links) for (const e of l.edges) {
    if (e.status !== 'fail' || (c.env !== 'all' && e.environment !== c.env)) continue;
    lines.push(`• ${l.source.label} (${e.environment}) depends on ${l.target.label}: ${e.status_reason ?? 'failing'}`);
  }
  for (const n of c.nodes) {
    if (n.type === 'packages' && n.raw['valid'] === false && (c.env === 'all' || n.raw['environment'] === c.env)) {
      lines.push(`• Packages (${n.raw['environment']}) for ${String(n.raw['id']).split(':')[0]}: ${n.raw['reason'] ?? 'invalid'}`);
    }
  }
  const dep = c.nodes.filter((n) => n.type === 'model' && n.raw['deprecated']);
  for (const m of dep) lines.push(`• Model ${m.label} is deprecated (end of life ${m.raw['end_of_life_date'] ?? 'not set'})`);
  const uniq = [...new Set(lines)];
  return uniq.length ? `Here is what is failing ${scope(c.env)}:\n${uniq.join('\n')}` : `Nothing is failing ${scope(c.env)}.`;
}

export function answer(question: string, c: ChatContext): Answer {
  const q = question.toLowerCase().trim();
  if (!q) return { text: 'Ask me about impact, dependencies or what is failing.' };

  let hits = findNodes(q, c);
  if (!hits.length && c.selected && /\b(this|it|that)\b|selected/.test(q)) hits = [c.selected];

  if (hits.length) {
    const focus = hits[0];
    const label = focus.label;
    const wantsDeps = /(depend on|depends on|use|uses|using|built on|rely|relies|made of|connect)/.test(q) && /what|which|list|show/.test(q) && !/break|fail|affect|impact/.test(q);
    if (wantsDeps || (focus.type === 'project' && !/break|fail|affect|impact|deprecat|retire|remov|drop/.test(q))) {
      const down = c.trace(focus.id, 'down');
      const groups = new Map<string, string[]>();
      for (const n of c.nodes) if (down.has(n.id)) (groups.get(n.type) ?? groups.set(n.type, []).get(n.type)!).push(n.type === 'packages' ? `${n.label} (${n.raw['environment']}, ${n.raw['valid'] === true ? 'valid' : n.raw['valid'] === false ? 'invalid' : 'not checked'})` : n.label);
      if (!groups.size) return { text: `${label} doesn't depend on anything ${scope(c.env)}.`, focus: focus.id };
      const lines = [...groups].map(([t, v]) => `• ${t}: ${[...new Set(v)].sort().join(', ')}`);
      return { text: `${label} depends on, ${scope(c.env)}:\n${lines.join('\n')}`, focus: focus.id };
    }
    const all = hits.flatMap((h) => impactRows(h.id, c));
    const byProject = new Map<string, (typeof all)[number]>();
    for (const r of all) {
      const cur = byProject.get(r.project.id);
      if (!cur) byProject.set(r.project.id, { ...r });
      else { cur.envs = [...new Set([...cur.envs, ...r.envs])].sort(); cur.failing ||= r.failing; cur.reasons.push(...r.reasons); }
    }
    const rows = [...byProject.values()];
    if (!rows.length) return { text: `Nothing depends on ${label} ${scope(c.env)}, so nothing breaks if it fails.`, focus: focus.id };
    const lines = rows.map((r) => `• ${r.project.label} (${r.envs.join(', ') || 'no environment'})${r.failing ? ' is already failing' + (r.reasons[0] ? `: ${r.reasons[0]}` : '') : ''}`);
    const already = rows.filter((r) => r.failing).length;
    return {
      text: `If ${label} fails, ${plural(rows.length, 'project')} ${scope(c.env)} ${rows.length === 1 ? 'is' : 'are'} affected:\n${lines.join('\n')}`
        + (already ? `\n${plural(already, 'of these')} already ${already === 1 ? 'has' : 'have'} a failing dependency on it.` : ''),
      focus: focus.id,
    };
  }

  if (/fail|broken|risk|problem|health|wrong|unhealthy/.test(q)) return { text: failingReport(c) };
  if (/deprecat|end of life|retire/.test(q)) {
    const dep = c.nodes.filter((n) => n.type === 'model' && n.raw['deprecated']);
    if (!dep.length) return { text: 'No model is deprecated.' };
    return { text: dep.map((m) => `• ${m.label}: end of life ${m.raw['end_of_life_date'] ?? 'not set'}. ${impactRows(m.id, c).map((r) => r.project.label).join(', ') || 'No projects use it.'}`).join('\n'), focus: dep[0].id };
  }
  if (/package/.test(q)) {
    const bad = c.nodes.filter((n) => n.type === 'packages' && n.raw['valid'] === false);
    return { text: bad.length ? bad.map((n) => `• ${n.raw['id']}: ${n.raw['reason'] ?? 'invalid'}`).join('\n') : 'Every checked package set is valid.' };
  }
  if (/how many|count|total|list|which projects|what projects/.test(q) || /project/.test(q)) {
    const ps = c.nodes.filter((n) => n.type === 'project');
    return { text: `${plural(ps.length, 'project')}: ${ps.map((p) => p.label).join(', ')}.` };
  }
  return { text: 'I can answer from the graph. Try:\n• What breaks if Claude 3 Sonnet is deprecated?\n• How many projects depend on HoneyHive?\n• What does Vendor-spend assistant depend on?\n• What is failing right now?' };
}
