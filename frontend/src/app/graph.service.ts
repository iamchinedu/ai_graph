import { Injectable } from '@angular/core';
import { RawGraph } from './graph.model';

/** THE one place the screen gets its data. Point this at a file or an endpoint that returns the graph JSON
 *  (see RawGraph in graph.model.ts for the shape). Nothing else in the app reads data. */
export const GRAPH_URL = 'graph.json';

@Injectable({ providedIn: 'root' })
export class GraphService {
  /** Fetch the graph JSON. Called once on open and again each time Refresh is pressed; never on a timer. */
  async load(): Promise<RawGraph> {
    const res = await fetch(GRAPH_URL, { cache: 'no-store' });
    if (!res.ok) throw new Error(`Couldn't load graph.json (${res.status}). Run "python -m backend.graph build", then npm run sync:graph.`);
    return res.json();
  }
}
