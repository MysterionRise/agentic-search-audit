# SaaS layer (experimental)

`api/`, `jobs/` and `db/` are a REST API, a Redis-backed worker and a Postgres schema that
run the same audit as the command-line tool as a hosted service. They are **experimental**,
not needed by `search-audit`, and installed only with the `saas` extra:

```bash
uv sync --extra saas            # or: pip install 'agentic-search-audit[saas]'
```

Without the extra, `search-audit-api` and `search-audit-worker` exit with one line that
names the extra; `search-audit` is unaffected.

## Running it

```bash
docker compose --profile saas up          # postgres, redis, api (port 8000), worker
docker compose --profile monitoring up    # prometheus (9090) and grafana (3000)
```

Or locally with your own Postgres and Redis:

```bash
alembic upgrade head                              # apply the schema (single head 7d2e4f1a9c3b)
search-audit-api --host 0.0.0.0 --port 8000       # FastAPI, docs at /docs
search-audit-worker --concurrency 2               # pulls jobs from audit:queue
```

On startup the API also calls `create_all` as a development convenience; existing
databases should be migrated with Alembic.

## Settings

Read from the environment with the `AUDIT_` prefix (see `api/config.py`):
`AUDIT_ENVIRONMENT`, `AUDIT_SECRET_KEY`, `AUDIT_DATABASE_URL`, `AUDIT_REDIS_URL`,
`AUDIT_DEBUG`, plus `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` and `SENTRY_DSN`. The
LLM keys are the same as for the CLI (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`).

## What exists

- JWT (HS256) + bcrypt auth, users and organisations, API-key issuance
- Audit jobs: enqueue, status, cancel; the worker runs `SearchAuditOrchestrator`
- Stripe checkout, billing portal and webhook (plans hardcoded: Free, $29, $99, $499)
- GDPR export, consent and deletion endpoints
- Redis fixed-window rate limiting, Prometheus `/metrics`, optional Sentry

## Known gaps

These are known and unaddressed; the layer is kept behind the extra until someone needs it:

- `GET /audits/{id}/report` always returns 404: reports are never stored
  (`AuditRepository.add_report` has no caller).
- Issued API keys cannot authenticate: nothing reads the `X-API-Key` header.
- Cancelling a running audit never reaches the orchestrator (`cancel_event` is not passed).
- The worker writes artifacts to a temporary directory inside the container.
- `config_override` from the API request is merged into the audit config unvalidated.
- The monthly audit limit is hardcoded to 100 regardless of plan.
- The scheduled GDPR deletion is recorded but never executed.
