/**
 * Typed client for the API.
 *
 * Phase 1 fetches only `/healthz` and `/readyz`. The types mirror the API's Pydantic models
 * field for field, deliberately: a hand-written interface that drifts from the server model
 * is worse than no interface at all, because it compiles while being wrong.
 *
 * `ReadinessReport` reflects the shape that matters operationally -- the API can be alive
 * while unable to serve questions, which is precisely what the readiness endpoint exists to
 * distinguish. A UI that only checked `/healthz` would report "everything is fine" during a
 * database outage.
 */

export interface HealthReport {
  readonly status: string;
  readonly service: string;
  readonly version: string;
  readonly phase: string;
}

export interface DependencyStatus {
  readonly name: string;
  readonly reachable: boolean;
  readonly required: boolean;
  readonly detail: string;
}

export interface ReadinessReport {
  readonly status: string;
  readonly ready: boolean;
  readonly environment: string;
  readonly auth_mode: string;
  readonly allow_fake_model_adapters: boolean;
  readonly chat_model: string;
  readonly embedding_model: string;
  readonly dependencies: readonly DependencyStatus[];
}

export interface ApiErrorBody {
  readonly error?: {
    readonly code?: string;
    readonly message?: string;
  };
}

const API_BASE_URL = process.env.API_BASE_URL ?? 'http://localhost:8000';

/** Raised for any non-2xx response. Carries the API's stable error code, not its prose. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    // Explicitly not cached: a stale readiness reading is worse than a slow one.
    cache: 'no-store',
  });

  if (!response.ok) {
    // `/readyz` answers 503 with a fully populated body, so the payload is parsed even on
    // failure rather than discarded -- the body is the reason it is ready to call.
    const body = (await response.json().catch(() => ({}))) as ApiErrorBody;
    throw new ApiError(
      response.status,
      body.error?.code ?? 'unknown_error',
      body.error?.message ?? `request to ${path} failed with ${response.status}`,
    );
  }

  return (await response.json()) as T;
}

export function fetchHealth(): Promise<HealthReport> {
  return getJson<HealthReport>('/healthz');
}

/**
 * Returns the report even when the API answers 503.
 *
 * `/readyz` puts a complete `ReadinessReport` in the body of its 503 response, so the body
 * is parsed rather than discarded -- it names which dependency is unreachable, which is the
 * only part of an outage worth showing a human. Throws only when the API cannot be reached
 * at all.
 */
export async function fetchReadiness(): Promise<ReadinessReport> {
  try {
    return await getJson<ReadinessReport>('/readyz');
  } catch (error) {
    if (error instanceof ApiError && error.status === 503) {
      const report = await fetchReportBody();
      if (report) {
        return report;
      }
      return unreachableReport();
    }
    throw error;
  }
}

/** Re-reads the body of a 503 readiness response, which carries the detail we need. */
async function fetchReportBody(): Promise<ReadinessReport | null> {
  try {
    const response = await fetch(`${API_BASE_URL}/readyz`, { cache: 'no-store' });
    const parsed = (await response.json()) as Partial<ReadinessReport>;
    // Only trust it if it looks like a readiness report rather than an error envelope.
    return typeof parsed.ready === 'boolean' ? (parsed as ReadinessReport) : null;
  } catch {
    return null;
  }
}

function unreachableReport(): ReadinessReport {
  return {
    status: 'not_ready',
    ready: false,
    environment: 'unknown',
    auth_mode: 'unknown',
    allow_fake_model_adapters: false,
    chat_model: 'unknown',
    embedding_model: 'unknown',
    dependencies: [
      {
        name: 'api',
        reachable: false,
        required: true,
        detail: 'the API did not respond; it may be restarting or unreachable',
      },
    ],
  };
}