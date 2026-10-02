import { fetchHealth, fetchReadiness } from '@/lib/api';

export const dynamic = 'force-dynamic';

/**
 * Phase 1 landing page.
 *
 * Shows the two health signals rather than a chat box, because there is nothing to chat
 * about until phase 3. Both are fetched on every request with caching disabled: a page that
 * reports a stale "ready" is actively misleading during an incident, which is the one time
 * someone will be reading it.
 */
export default async function Home() {
  const [health, readiness] = await Promise.all([
    fetchHealth().catch(() => null),
    fetchReadiness().catch(() => null),
  ]);

  const readinessClass = readiness === null ? 'status-bad' : readiness.ready ? 'status-ok' : 'status-bad';

  return (
    <>
      <h1>RAG Chatbot</h1>
      <p className="subtitle">
        Phase 1 — scaffolding, configuration and observability. No questions can be asked yet.
      </p>

      <section className="card">
        <h2>Liveness</h2>
        <dl>
          <dt>Endpoint</dt>
          <dd>
            <code>/healthz</code>
          </dd>
          <dt>Status</dt>
          <dd>{health === null ? <span className="status-bad">unreachable</span> : <span className="status-ok">{health.status}</span>}</dd>
          {health ? (
            <>
              <dt>Service</dt>
              <dd>{health.service}</dd>
              <dt>Version</dt>
              <dd>{health.version}</dd>
              <dt>Phase</dt>
              <dd>{health.phase}</dd>
            </>
          ) : null}
        </dl>
      </section>

      <section className="card">
        <h2>Readiness</h2>
        <dl>
          <dt>Endpoint</dt>
          <dd>
            <code>/readyz</code>
          </dd>
          <dt>Status</dt>
          <dd>
            <span className={readinessClass}>
              {readiness === null ? 'unreachable' : readiness.ready ? 'ready' : 'not ready'}
            </span>
          </dd>
          {readiness ? (
            <>
              <dt>Environment</dt>
              <dd>{readiness.environment}</dd>
              <dt>Auth mode</dt>
              <dd>{readiness.auth_mode}</dd>
              <dt>Chat model</dt>
              <dd>{readiness.chat_model}</dd>
              <dt>Embeddings</dt>
              <dd>{readiness.embedding_model}</dd>
              {readiness.allow_fake_model_adapters ? (
                <>
                  <dt>Model adapters</dt>
                  <dd>
                    <span className="status-warn">fake — answers are not real</span>
                  </dd>
                </>
              ) : null}
              {readiness.dependencies.map((dependency) => (
                <div key={dependency.name} style={{ display: 'contents' }}>
                  <dt>{dependency.name}</dt>
                  <dd className={dependency.reachable ? 'status-ok' : 'status-bad'}>
                    {dependency.reachable ? 'reachable' : (dependency.detail ?? 'unreachable')}
                  </dd>
                </div>
              ))}
            </>
          ) : null}
        </dl>
      </section>

      <section className="card placeholder">
        <h2>Not implemented yet</h2>
        <p>The following arrive in later phases and are listed so the gaps are visible:</p>
        <ul>
          <li>Ask a question, with streaming answers and citations — phase 3</li>
          <li>Document administration and re-indexing — phase 4</li>
          <li>Evaluation dashboards — phase 5</li>
        </ul>
      </section>
    </>
  );
}