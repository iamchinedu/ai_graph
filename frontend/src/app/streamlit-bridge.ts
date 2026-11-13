import { Injectable } from '@angular/core';
import { RawGraph } from './graph.model';

/**
 * Talks to Streamlit when this screen runs as a Streamlit component (inside its iframe).
 * Outside Streamlit `active` is false and nothing here is used.
 *
 * Streamlit sends us {graph, reply} on every render. We send back one request at a time:
 *   {id, action: 'ask', question, context}   the Python chat agent answers; the answer comes back as reply.text
 *   {id, action: 'refresh'}                  Python rebuilds the graph; the new graph comes back with the reply
 */
@Injectable({ providedIn: 'root' })
export class StreamlitBridge {
  readonly active = typeof window !== 'undefined' && window.parent !== window;
  private latest: RawGraph | null = null;
  private lastGraphText = '';
  private graphWaiters: ((g: RawGraph) => void)[] = [];
  private pending = new Map<string, (text: string) => void>();
  private counter = 0;

  constructor() {
    if (!this.active) return;
    window.addEventListener('message', (ev) => this.onMessage(ev));
    this.post('streamlit:componentReady', { apiVersion: 1 });
    this.fitHeight();
    window.parent.addEventListener?.('resize', () => this.fitHeight());
  }

  /** The graph Streamlit last sent; waits for the first one. */
  graph(): Promise<RawGraph> {
    return this.latest ? Promise.resolve(this.latest) : new Promise((resolve) => this.graphWaiters.push(resolve));
  }

  /** Ask the Python side to do something; resolves with its text answer. */
  request(body: { action: 'ask' | 'refresh'; question?: string; context?: string }): Promise<string> {
    const id = `${Date.now()}-${++this.counter}`;
    return new Promise((resolve) => {
      this.pending.set(id, resolve);
      this.post('streamlit:setComponentValue', { value: { id, ...body }, dataType: 'json' });
    });
  }

  private onMessage(ev: MessageEvent) {
    const d = ev.data;
    if (!d || d.type !== 'streamlit:render') return;
    const args = d.args ?? {};
    if (args.graph) {
      const text = JSON.stringify(args.graph);
      if (text !== this.lastGraphText) { this.lastGraphText = text; this.latest = args.graph; }
      for (const w of this.graphWaiters.splice(0)) w(this.latest!);
    }
    const reply = args.reply;
    if (reply?.id && this.pending.has(reply.id)) {
      const done = this.pending.get(reply.id)!;
      this.pending.delete(reply.id);
      done(reply.text ?? '');
    }
  }

  private fitHeight() {
    let h = window.innerHeight;
    try { h = window.parent.innerHeight; } catch { /* cross-origin parent: keep our own height */ }
    this.post('streamlit:setFrameHeight', { height: h });
  }

  private post(type: string, data: object) {
    window.parent.postMessage({ isStreamlitMessage: true, type, ...data }, '*');
  }
}
