# ether.fi Catalog MCP Deployment Notes

This document captures the current local MCP setup and the staged deployment
plan. It is intentionally limited to deployment hygiene and planning. The MCP
server runs locally over stdio by default, and can also be started in local
Streamable HTTP mode for remote-transport testing.

The recommended teammate onboarding path is local stdio install via `uvx`.
This command has been verified against the public GitHub repo:

```bash
uvx --from "git+https://github.com/henrystats/etherfi-data-catalog.git" etherfi-catalog-mcp
```

Docker and Cloud Run are advanced/private staging paths, not the default team
setup.

On Apple Silicon Macs, if `uvx` fails with an error like
`/usr/local/bin/git ... Bad CPU type in executable`, the shell is using an old
Intel Git binary. Prefer `/opt/homebrew/bin/git` or `/usr/bin/git`, and make
sure that path appears before `/usr/local/bin` in your shell `PATH`.

## Current runtime

The MCP server lives in `etherfi_catalog/server.py` and is registered as a FastMCP server:

```bash
etherfi-catalog-mcp
```

The default transport is stdio:

```bash
etherfi-catalog-mcp
```

That means a local MCP client must spawn the server process directly. This is
appropriate for local development, Codex-style local config, and other MCP
clients that support subprocess/stdio servers.

For local Streamable HTTP testing, run:

```bash
etherfi-catalog-mcp --transport streamable-http --host 127.0.0.1 --port 8001
```

The local MCP endpoint is:

```text
http://127.0.0.1:8001/mcp
```

You can also use environment variables for local testing:

```bash
MCP_TRANSPORT=streamable-http MCP_HOST=127.0.0.1 MCP_PORT=8001 etherfi-catalog-mcp
```

CLI arguments take priority over environment variables. HTTP mode defaults to
`127.0.0.1` and is for local/staging transport testing only. Hosted deployment
still needs deployment configuration, authentication, secrets handling, rate
limits, and live-tool hardening before external use.

## Local setup

Install the project for development:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

Run tests:

```bash
.venv/bin/python -m pytest
```

Start the local stdio MCP server:

```bash
etherfi-catalog-mcp
```

For Codex/local clients, configure the client to run that command from the repo
root during development. Installed package runs load bundled dataset/dashboard
metadata by default.

## Verified local smoke test

After installing from GitHub, confirm the console script is available:

```bash
etherfi-catalog-mcp --help
```

Optional Streamable HTTP smoke test:

```bash
etherfi-catalog-mcp --transport streamable-http --host 127.0.0.1 --port 8001
```

In another terminal, verify the MCP handshake, tool listing, and a metadata-only
tool call:

```bash
.venv/bin/python scripts/smoke_mcp_http.py --url http://127.0.0.1:8001/mcp
```

This checks the installed server over `/mcp` without requiring `DUNE_API_KEY`
and without making live Dune calls.

Start the local Streamable HTTP server for transport testing:

```bash
etherfi-catalog-mcp --transport streamable-http --host 127.0.0.1 --port 8001
```

The Streamable HTTP path is `/mcp`.

## Local Streamable HTTP verification

A plain browser or `GET` request to `/mcp` may return `406`. That only confirms
the endpoint is reachable; MCP clients use the MCP Streamable HTTP request and
session flow.

To start the server manually:

```bash
etherfi-catalog-mcp --transport streamable-http --host 127.0.0.1 --port 8001
```

In another terminal, verify the MCP handshake, tool listing, and a metadata-only
tool call:

```bash
.venv/bin/python scripts/smoke_mcp_http.py --url http://127.0.0.1:8001/mcp
```

Or let the helper start a temporary local server on a free port and stop it
after the smoke test:

```bash
.venv/bin/python scripts/smoke_mcp_http.py
```

The smoke helper initializes an MCP client session, lists tools, verifies core
metadata/planning tools, and calls `search_datasets` with a safe metadata-only
query. It does not require `DUNE_API_KEY` and does not call live Dune-backed
tools. Live tools still require `DUNE_API_KEY` when `execute_live=true` and
should not be exposed publicly without auth, rate limits, and credit monitoring.

## Local container test

Build the local container image:

```bash
docker build -t etherfi-catalog-mcp:local .
```

Run the MCP server in Streamable HTTP mode inside the container:

```bash
docker run --rm -p 8001:8001 etherfi-catalog-mcp:local
```

In another terminal, run the MCP HTTP smoke helper against the container:

```bash
.venv/bin/python scripts/smoke_mcp_http.py --url http://127.0.0.1:8001/mcp
```

The container command binds to `0.0.0.0` inside the container and exposes port
`8001`; the local host mapping above exposes it at `127.0.0.1:8001`.

No `DUNE_API_KEY` is required for metadata-only smoke tests. To test live tools
locally, pass the key only at runtime:

```bash
docker run --rm -p 8001:8001 -e DUNE_API_KEY=... etherfi-catalog-mcp:local
```

Never bake `DUNE_API_KEY` or other secrets into the image. External/cloud
deployment still needs auth, rate limiting, secret management, and credit
monitoring before public exposure.

### Container freshness files

The image includes `status/dataset_freshness.example.yaml`, but intentionally
does not bake in the local generated `status/dataset_freshness.yaml` file.

If `status/dataset_freshness.yaml` is absent, the catalog loads an empty
freshness registry. Dataset discovery and metadata tools still work, but
freshness/status responses fall back to undocumented or unknown freshness rather
than live snapshot status.

For staging or production freshness, provide the generated runtime file at:

```text
/app/status/dataset_freshness.yaml
```

That can be done later by mounting the file into the container, generating it in
CI before building the image, or running the freshness importer as a separate
scheduled job before deployment. Do not implement scheduled freshness imports in
the container image itself until the deployment model is finalized.

## CI Docker smoke test

The manual GitHub Actions workflow `.github/workflows/docker-smoke.yml` verifies
the container in a Docker-enabled runner. It does not deploy anything and does
not push the image to a registry.

To run it after pushing a branch:

1. Open the repository's GitHub Actions tab.
2. Select `Docker MCP smoke test`.
3. Choose `Run workflow`.
4. Select the branch to test.

The workflow:

- checks out the repo
- installs the Python package needed by the smoke helper
- builds `etherfi-catalog-mcp:local`
- runs the container on local runner port `8001`
- calls `scripts/smoke_mcp_http.py --url http://127.0.0.1:8001/mcp`
- fails if an MCP client cannot initialize, list expected tools, or call
  `search_datasets`

The workflow does not use secrets, does not require `DUNE_API_KEY`, does not
call live Dune-backed tools, does not publish Docker images, and does not deploy
to cloud infrastructure. It proves the image can build and serve metadata tools
over Streamable HTTP in a Docker-enabled CI environment. It does not prove
production auth, rate limiting, cloud routing, TLS, or live-tool safety.

## Cloud Run private staging

This is the planned first remote staging path. It is metadata-only: do not set
`DUNE_API_KEY`, do not grant public unauthenticated access, and do not expose
live Dune-backed tools before auth, rate limiting, and credit controls are
reviewed.

Cloud Run authenticated services use IAM to decide who can invoke the service.
The container still serves the MCP endpoint at `/mcp` on port `8001`.

### Prerequisites

- Google Cloud project selected for staging.
- `gcloud` installed and authenticated locally.
- Artifact Registry API enabled.
- Cloud Run API enabled.
- Permission to create/push Artifact Registry Docker images.
- Permission to deploy and manage Cloud Run services.
- Permission to grant Cloud Run Invoker access to selected users or service
  accounts.
- A selected region, such as `us-central1`.

### Variables

Use placeholders first; do not paste secrets into these variables:

```bash
PROJECT_ID="your-gcp-project"
REGION="us-central1"
REPOSITORY="etherfi"
IMAGE="etherfi-catalog-mcp"
SERVICE="etherfi-catalog-mcp-staging"
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${IMAGE}:staging"
```

### Enable required APIs

```bash
gcloud services enable artifactregistry.googleapis.com run.googleapis.com \
  --project "$PROJECT_ID"
```

### Create an Artifact Registry repository

Run this once per project/region/repository:

```bash
gcloud artifacts repositories create "$REPOSITORY" \
  --project "$PROJECT_ID" \
  --repository-format docker \
  --location "$REGION" \
  --description "ether.fi catalog MCP container images"
```

Configure Docker auth for the region:

```bash
gcloud auth configure-docker "${REGION}-docker.pkg.dev"
```

### Build and push the image

```bash
docker build -t "$IMAGE_URI" .
docker push "$IMAGE_URI"
```

This should be run only from a clean local checkout or CI job. The Docker image
must not contain `.env`, `.codex/`, `status/dataset_freshness.yaml`, or any
`DUNE_API_KEY` value.

### Deploy the private Cloud Run service

```bash
gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --image "$IMAGE_URI" \
  --port 8001 \
  --no-allow-unauthenticated
```

Important staging defaults:

- Do not pass `--allow-unauthenticated`.
- Do not set `DUNE_API_KEY`.
- Do not add GitHub/cloud secrets yet.
- Keep the service metadata-only until a later hardening task approves live
  Dune-backed tools.

### Grant invoker access

Grant access only to selected users, groups, or service accounts:

```bash
INVOKER="user:teammate@example.com"

gcloud run services add-iam-policy-binding "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --member "$INVOKER" \
  --role "roles/run.invoker"
```

Repeat for each approved principal. Do not grant `allUsers` or
`allAuthenticatedUsers` for staging.

### Smoke test the deployed MCP endpoint

Fetch the service URL:

```bash
SERVICE_URL="$(gcloud run services describe "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --format 'value(status.url)')"
```

Generate a Google-signed identity token for the active `gcloud` user:

```bash
TOKEN="$(gcloud auth print-identity-token)"
```

Run the MCP Streamable HTTP smoke helper against the authenticated Cloud Run
URL:

```bash
.venv/bin/python scripts/smoke_mcp_http.py \
  --url "$SERVICE_URL/mcp" \
  --bearer-token "$TOKEN"
```

The helper sends the token as:

```text
Authorization: Bearer <token>
```

If a proxy or serverless integration expects the Cloud Run-specific serverless
header, use:

```bash
.venv/bin/python scripts/smoke_mcp_http.py \
  --url "$SERVICE_URL/mcp" \
  --bearer-token "$TOKEN" \
  --auth-header-name X-Serverless-Authorization
```

The smoke helper never prints the token or auth headers.

You can also test through the Google Cloud CLI local proxy:

```bash
gcloud run services proxy "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --port 8001

.venv/bin/python scripts/smoke_mcp_http.py --url http://127.0.0.1:8001/mcp
```

### Expected staging behavior

- MCP initialize/session handshake works over Streamable HTTP.
- Tool listing works.
- Metadata tools such as `search_datasets`, `get_dataset_status`, and
  `search_dashboards` work.
- Live tools called with `execute_live=true` fail clearly because no
  `DUNE_API_KEY` is configured.
- No Dune credits are consumed.

If the service is reachable but the MCP handshake fails with host/origin
security errors, keep the service private and update the server's Streamable
HTTP allowed-host/allowed-origin configuration in a separate reviewed task. Do
not disable auth or make the service public to work around transport security.

### Freshness behavior in staging

The image includes `status/dataset_freshness.example.yaml`, but intentionally
does not include the local generated `status/dataset_freshness.yaml`.

Until a runtime freshness file is provided, staging may show unknown freshness.
That is expected for metadata-only staging. Scheduled freshness import and
runtime file delivery are future work.

### Logs and rollback

Read recent logs:

```bash
gcloud run services logs read "$SERVICE" \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --limit 50
```

List revisions:

```bash
gcloud run revisions list \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --service "$SERVICE"
```

Rollback can be done by moving traffic back to a previous known-good revision in
the Cloud Run console or with `gcloud run services update-traffic` after
identifying the revision. Do not automate rollback until staging behavior is
verified.

### Security reminders

- Do not grant public unauthenticated access.
- Do not set `DUNE_API_KEY` in metadata-only staging.
- Do not bake secrets into the Docker image.
- Rotate any Dune key that was ever committed, pasted, or shared before adding
  live-tool staging.
- Before any broader external usage, add auth review, rate limits, live-tool
  credit controls, logging expectations, and incident rollback steps.

## Local smoke tests

Run the server smoke tests before changing transport or deployment behavior:

```bash
.venv/bin/python -m pytest tests/test_server.py -q
```

Run the full suite before opening a PR:

```bash
.venv/bin/python -m pytest -q
```

These tests do not require `DUNE_API_KEY` and do not make live Dune API calls.
They verify that the FastMCP server imports, expected metadata/planning tools
are registered, metadata tools can run without Dune credentials, and live-capable
tools either stay in planning mode or fail clearly when credentials are missing.

## Secret hygiene

Never commit a real `DUNE_API_KEY`.

Use one of these patterns instead:

- Local development: set `DUNE_API_KEY` in `.env`, a shell environment, or a
  private local MCP client config that is ignored by git.
- CI or deployment: store `DUNE_API_KEY` in GitHub Secrets, the deployment
  platform secret manager, or another managed secret store.
- Examples/docs: use placeholders such as `DUNE_API_KEY=...`; never paste a
  real key into tracked docs or configs.

`.env` is ignored by git. If a Dune API key was ever committed, pushed, pasted
into a shared thread, or otherwise exposed, rotate it before deployment.

## Tool modes

Metadata and planning tools work without Dune credentials:

- `search_datasets`
- `get_dataset_details`
- `compare_datasets`
- `get_catalog_health_summary`
- `search_dashboards`
- `get_dashboard_details`
- `get_dashboard_status`
- `get_dataset_status`
- `list_stale_datasets`
- `plan_etherfi_query`

Live Dune-backed tools require `DUNE_API_KEY` only when the caller requests live
execution with `execute_live=true`:

- `get_assets_under_management_balances`
- `get_cash_events`
- `get_cash_holdings_timeseries`
- `get_cash_safe_profile`
- `get_cash_token_totals`
- `get_top_cash_users`
- `get_protocol_token_holders`
- `get_protocol_events`
- `get_protocol_token_tvl`
- `get_protocol_token_tvl_timeseries`
- `get_token_price`
- `find_price_tokens`
- `get_token_price_by_symbol`
- `get_token_prices_batch`
- `diagnose_token_price_coverage`

Before remote deployment, live Dune-backed tools should be protected with auth,
rate limits, timeout limits, and Dune credit monitoring. Metadata/planning tools
are safer, but should still start behind private access until the deployment
model is finalized.

## Staged deployment checklist

- [x] Task 1: secret hygiene and local stdio docs.
- [x] Task 2: server smoke tests for local MCP startup/tool registration.
- [x] Task 3: Streamable HTTP entrypoint while preserving stdio behavior.
- [x] Task 3.5: local Streamable HTTP MCP handshake smoke test.
- [x] Task 4: Docker/container setup with no baked-in secrets.
- [x] Task 4.5: Docker-enabled CI smoke verification workflow.
- [x] Task 5A: Cloud Run private staging docs and authenticated smoke helper.
- [ ] Task 5B: manual private Cloud Run staging deployment after approval.
- [ ] Task 6: auth, rate limit, and live-tool hardening.
- [ ] Task 7: website MCP setup docs update after deployment is verified.

Each task should be reviewed and approved before implementation. Do not deploy
or expose live Dune-backed tools publicly until auth and key handling are
settled.
