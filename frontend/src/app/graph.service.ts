import { Injectable } from '@angular/core';
import { RawGraph } from './graph.model';

@Injectable({ providedIn: 'root' })
export class GraphService {
  /** The saved snapshot written by `python -m backend.graph build` (copied to public/graph.json on start). */
  async load(): Promise<RawGraph> {
    const res = await fetch('graph.json', { cache: 'no-store' });
    if (!res.ok) throw new Error(`Couldn't load graph.json (${res.status}). Run "python -m backend.graph build", then npm run sync:graph.`);
    return res.json();
  }
}
