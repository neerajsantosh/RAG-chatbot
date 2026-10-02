# Web app

Next.js 15 (App Router) + React 19 + TypeScript. Phase 1 renders the API's health and
readiness state and nothing else.

## Run it

```powershell
cd apps/web
npm ci
npm run dev          # http://localhost:3000
```

Against a running API:

```powershell
make up              # from the repository root; needs Docker
```

Without Docker, run the API directly:

```powershell
make run-api         # http://localhost:8000
```

## Check it

```powershell
npm run typecheck    # tsc --noEmit, strict
npm run lint         # next lint
npm run build
```

TypeScript is configured strict, plus `noUncheckedIndexedAccess` and
`exactOptionalPropertyTypes`. Those two are stricter than the Next.js default and catch real
bugs here: indexing a dependency array can be `undefined` under `noUncheckedIndexedAccess`,
and a partially-built status object must not be silently accepted where a complete one is
required.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `API_BASE_URL` | `http://localhost:8000` | Where the API is reachable from the browser. Read at build time. |

`API_BASE_URL` is a build-time variable because phase 1 has no authenticated browser session
and no chat endpoint, so there is nothing to proxy. Phase 4 replaces it with a Next.js
rewrite that forwards the `Authorization` header server-side — browser code must never hold
a token itself.

## What is deliberately absent

No chat UI, no question box, no citation rendering. All three depend on retrieval that does
not exist yet, and a static mock of them would be a screenshot of a feature rather than a
component of one. The placeholder card on the page lists what is still to come so the gap is
visible rather than implied.