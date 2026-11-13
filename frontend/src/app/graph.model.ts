import { SimulationLinkDatum, SimulationNodeDatum } from 'd3-force';

export type NodeType = 'project' | 'account' | 'packages' | 'model' | 'profile' | 'tool' | 'platform' | 'database' | 'table';
export type Family = 'project' | 'account' | 'ai' | 'obs' | 'data' | 'packages';
export type EnvFilter = 'all' | 'dev' | 'test' | 'prod';
export type Layout = 'brain' | 'ladder';

export interface RawNode { node: string; type: NodeType; label: string; id: string | number; [key: string]: any }
export interface RawEdge {
  source: string; target: string; kind: string; environment: string | null;
  count?: number | null; last_seen?: string | null; status?: string | null; status_reason?: string | null;
}
export interface RawGraph { nodes: RawNode[]; edges: RawEdge[] }

export interface GNode extends SimulationNodeDatum { id: string; type: NodeType; label: string; raw: RawNode; r: number }
export interface GLink extends SimulationLinkDatum<GNode> {
  source: GNode; target: GNode; edges: RawEdge[]; envs: string[];
  /** view links only: calls through this link, and the environments where something below it is failing */
  count?: number; failEnvs?: Set<string>; kind?: string;
  /** project -> account links: which families feed into the account for this project (each gets its own colored signal) */
  feeds?: Set<string>;
}

export const TYPE_INFO: Record<NodeType, { label: string; plural: string; r: number }> = {
  project: { label: 'Project', plural: 'Projects', r: 15 },
  account: { label: 'AWS account', plural: 'AWS accounts', r: 11 },
  packages: { label: 'Packages', plural: 'Package checks', r: 11 },
  model: { label: 'Model', plural: 'Models', r: 14 },
  profile: { label: 'Inference profile', plural: 'Inference profiles', r: 9 },
  tool: { label: 'Observability tool', plural: 'Observability tools', r: 11 },
  platform: { label: 'Data platform', plural: 'Data platforms', r: 13 },
  database: { label: 'Database', plural: 'Databases', r: 11 },
  table: { label: 'Table', plural: 'Tables', r: 8 },
};

/** Ladder layout: the layers top to bottom. Change the order here and the ladder follows. */
export const LAYERS: NodeType[] = ['account', 'project', 'packages', 'model', 'tool', 'platform', 'database', 'table'];
export const TYPE_ORDER = LAYERS;

export const WORLD = { w: 1000, h: 860, cx: 500, cy: 430 };
export const layerY = (t: NodeType) => 60 + LAYERS.indexOf(t) * 105;

export const FAMILY_LABEL: Record<Family, string> = {
  project: 'Project', account: 'AWS account', ai: 'AI: model', obs: 'Observability tool', data: 'Data: platform, database, table', packages: 'Package check (per project)',
};
/** One color per family, so everything under a provider shares it and so does the signal flowing in from it. */
export const FAM_COLOR: Record<Family, string> = {
  project: '#b8a6ff', account: '#ffc247', ai: '#ff9b78', obs: '#6db8ff', data: '#4de8c4', packages: '#d4f25a',
};
export const OK_GLOW = '#7dffb0', BAD_GLOW = '#ff5f6d', IDLE_GLOW = '#9aa4b2';
export const familyOfType = (t: NodeType): Family =>
  t === 'model' || t === 'profile' ? 'ai' : t === 'tool' ? 'obs' : t === 'platform' || t === 'database' || t === 'table' ? 'data'
  : t === 'packages' ? 'packages' : t === 'account' ? 'account' : 'project';
