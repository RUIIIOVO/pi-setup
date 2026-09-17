# CliRelay patch for the pi CLIProxyAPI provider

Target deployment: `vps-us-sj:/root/CliRelay` (base commit `1effc9b`).
Running image: `clirelay:patched-antigravity-pi-v8`.

The same changes are tracked as a real git branch (easier to rebase than a
flat patch file):

    https://github.com/RUIIIOVO/CliRelay  branch `fix/antigravity-hosts-and-pi-catalog`
    (based on `fix/disabled-models`, which is based on `pi-compat`)

`clirelay-pi-compat.patch` is the flattened form of that branch — everything
below, against the clean `1effc9b` tree — kept here so a machine without the
fork checked out can still reproduce the build. Verified with
`git apply --check` against `kittors/CliRelay` at `1effc9b`.

Deploy history (`.env` pins `CLI_PROXY_IMAGE`, `CLI_PROXY_PULL_POLICY=never`):

| image | what it added |
|---|---|
| `clirelay:patched-1effc9b-fable51-v3` | items 1-5 |
| `clirelay:patched-disabled-models-v6` | item 6 |
| `clirelay:patched-antigravity-pi-v8` | items 7-8 |

## What the patch changes

1. `internal/api/routes_public.go`
   Re-adds the Codex CLI direct route aliases that upstream CLIProxyAPI has and
   this fork dropped: `GET|POST /backend-api/codex/responses`,
   `/responses/compact`, `/alpha/search`, `/models`.
   The pi provider (and codex CLI with `chatgpt_base_url`) address inference at
   `{root}/backend-api/codex/...`; the WebSocket transport is the `GET` on that
   same path. Without it every WS handshake was a 404 -> "WebSocket error".

2. `internal/translator/claude/openai/responses/claude_openai-responses_response.go`
   `response.output_text.done` / `content_part.done` / `output_item.done` were
   emitted with a hardcoded empty `text`. Clients treat those payloads as
   authoritative and overwrite the text they accumulated from the deltas, so the
   final assistant message ended up empty. Now backfilled from `TextBuf`
   (tracked per text block via the new `TextBlockStart` offset).

3. `internal/api/server_models_endpoint.go`
   `enrichOpenAIModelsWithStaticCapabilities` publishes `context_window`,
   `max_completion_tokens` / `max_output_tokens`, `supported_reasoning_levels`,
   `input_modalities` and `display_name` on `/v1/models` from the static
   registry. Existing keys are never overwritten.

4. `internal/registry/model_definitions_claude_latest.go` (new file)
   Declares `claude-opus-5`, `claude-sonnet-5`, `claude-fable-5` and
   `claude-fable-5-1` with their context window, completion cap and reasoning
   levels. `model_definitions.go` routes the claude channel and the aggregate
   catalog through `ClaudeModelsWithLatest()`; Bedrock deliberately still uses
   `GetClaudeModels()` because these ids are Claude Code OAuth surface models
   and are not exposed through AWS Bedrock.

   Kept out of `model_definitions_static_data.go` on purpose: the structure
   ratchet in `scripts/check-backend-structure.py` freezes that file's size and
   only lets it shrink. Same convention as `model_definitions_commandcode.go`.

5. `internal/runtime/executor/claude_transport.go` +
   `internal/config/identity_fingerprint.go`
   Anthropic gates newer models on the reported Claude Code version and on the
   canonical `claude-cli/<version> (external, <entrypoint>)` User-Agent shape;
   a request that misses the gate is rejected with
   `claude_code_version_too_old`. CliRelay forwarded the client's own
   User-Agent verbatim, and its built-in default (`2.1.161`) was below the
   floor, so:

   - plain clients (curl, anything non-Claude-Code) were rejected, and
   - pi was rejected too, because it sends a bare `claude-cli/2.1.251`
     without the `(external, cli)` suffix, which upstream cannot parse.

   Now a client agent is forwarded only when it already satisfies the gate;
   otherwise the configured canonical agent is substituted. The default version
   was raised `2.1.161` -> `2.1.252` (and the matching test updated).

   > Earlier revisions of this file claimed `claude-fable-5-1` was "rejected
   > upstream — do not re-add". That was wrong: the model is served fine, the
   > 400 came from this User-Agent gate.

6. `internal/api/server_model_restriction.go`,
   `internal/management/modelcatalog/availability*.go`,
   `internal/management/settings/modelconfig/service.go`,
   `internal/api/server_models_endpoint.go`
   The catalog's disable toggle only ever *added* models: every consumer of
   `model_configs.Enabled` asked "should this row contribute a model?", and
   `managementVisibleModels` reads the static registry without consulting
   `Enabled` at all. For any model the registry already provides, an `enabled=0`
   row therefore subtracted nothing — which covers exactly the models an
   operator is most likely to switch off. Measured on this deployment: 23 of 147
   rows were disabled and all 23 were still listed and still callable.

   `DisabledModelIDsForTenant` adds the subtractive half, applied in three
   places: the management catalog (`ConfiguredAvailability`, `Models`), the
   `/v1/models` listing (unconditionally — whether a model is disabled does not
   depend on who is asking), and the request path
   (`modelRestrictionMiddleware` answers `404 model_not_found`, matching what the
   listing endpoints report; it checks the model actually routed to, so a CC
   Switch mapping cannot reach a disabled target).

7. `internal/runtime/executor/antigravity_{request,executor,nonstream,count_tokens}.go`
   Both daily hosts answer a share of otherwise-valid requests with
   `400 FAILED_PRECONDITION: User location is not supported for the API use.`
   Measured by calling Google directly with the account's own token, relay out
   of the picture: 10 sequential `gemini-3.8-flash-high` requests produced 5-7 of
   them, split across both hosts, with the same project id `loadCodeAssist`
   reports — and the same host served the identical request minutes later.

   Ruled out as causes: the sandbox host (not host-specific), the project id (a
   random fake project gates at the same rate), the account (it is onboarded,
   `free-tier`, project `aicode-consumers`), and production
   (`cloudcode-pa.googleapis.com` answers 6/6 with `429 Resource has been
   exhausted` for this account, so it stays out of the fallback list — a 429
   there trips the credential cool-down and fails the requests that follow).

   The gate is a per-attempt draw, and the executor treated it as
   request-fatal. `antigravityShouldRetryHost` now feeds it into the existing
   retry ladder — next host, then next attempt with backoff — so a request gets
   hosts × `request-retry` draws instead of one. Measured after deploy: 20/20
   where it was 16/20 before.

   > Residual risk: this is still a lottery, not a fix. If Google widens the
   > gate, the next lever is the egress IP — `proxy_url` / `proxy_id` on the
   > antigravity auth, no second deployment needed.

8. `internal/translator/gemini/openai/responses/*`
   Codex replays its own reasoning items with an empty `encrypted_content`, and
   the responses→gemini stage wrote that straight into a thought part's
   `thoughtSignature`. The gemini→antigravity stage injects
   `skip_thought_signature_validator` for every family *but* claude, so Claude
   models (only) forwarded a signature-less thinking block, which upstream
   rejects with `messages.N.content.M.thinking.signature: Field required` —
   every multi-turn Codex session against `claude-opus-4-6-thinking`.

   The request side now prefers the client signature, falls back to
   `internal/cache`'s thinking-signature cache (the mechanism the Claude Code
   path already uses), and drops the part entirely when neither source has one:
   an absent thinking block is always accepted, an unsigned one never is. Both
   response converters (streaming and non-streaming) publish into that cache.

9. `internal/api/server_models_endpoint.go` (pi catalog)
   `GET /v1/models` is what the pi CLIProxyAPI provider registers as its model
   picker. A pi request (`client_version=pi`) now gets the same catalog the
   management panel and ccswitch show — configured availability ∩ root path
   availability — instead of the raw static registry, so the stale Claude
   snapshot ids the panel already hides cannot reappear as usable pi models.
   The list stays live: toggling a model in the panel changes what the next pi
   refresh registers, with no client-side id list to maintain.

   This replaced the client-side `apply-cliproxyapi-model-allowlist.py` patch
   (deleted; see `../README.md`), which hardcoded four Claude ids into the
   plugin and hid every Gemini model.

## Model catalog

The Claude OAuth channel merges the static definitions above with the tenant
model library (`model_configs` table, `owned_by='anthropic'`, `enabled=1`,
`source` in user/seed/openrouter). Adding a row there exposes a model without a
rebuild, but the row carries no context window or reasoning levels — those come
from the static definitions in item 4.

Two caveats found while deploying item 9:

- `gemini-3.1-pro-high` is advertised in the catalog but rejected by Google
  itself with `400 Request contains an invalid argument.` — reproduced by
  calling `streamGenerateContent` directly with the account token, for every
  `thinkingLevel`. The working 3.1 Pro (high) id is `gemini-pro-agent`
  (`-low` works). Disable `gemini-3.1-pro-high` in the panel and it disappears
  from pi on the next refresh.
- `gemini-3.1-pro-*`, `gemini-3.1-flash-image` and `gpt-oss-120b-medium` get no
  `context_window` from the upstream discovery payload, so the relay's static
  registry cannot enrich them (item 3) and pi falls back to 128k. The static
  definitions would need the same treatment as item 4 to publish 1M.

## Rebuild + redeploy

Preferred: work from the fork so conflicts surface in git instead of in a
flat patch.

```bash
git clone git@github.com:RUIIIOVO/CliRelay.git && cd CliRelay
git checkout fix/antigravity-hosts-and-pi-catalog
# to pick up upstream changes:  git fetch upstream && git rebase upstream/main
```

Fallback, from a clean upstream tree:

```bash
git clone https://github.com/kittors/CliRelay && cd CliRelay
git apply /path/to/clirelay-pi-compat.patch
```

Then build and ship. Only the Go binary is rebuilt; the image is a one-layer
overlay on the previous one, so the bundled management panel is preserved and
no frontend toolchain is needed.

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -ldflags="-s -w" \
  -o CLIProxyAPI ./cmd/server/

scp CLIProxyAPI vps-us-sj:/tmp/ccbuild/CLIProxyAPI
ssh vps-us-sj 'cd /tmp/ccbuild \
  && printf "FROM clirelay:patched-antigravity-pi-v8\nCOPY --chown=clirelay:clirelay CLIProxyAPI /CLIProxyAPI/CLIProxyAPI\n" > Dockerfile \
  && docker build -t clirelay:patched-<tag> . \
  && cd /root/CliRelay \
  && sed -i "s|^CLI_PROXY_IMAGE=.*|CLI_PROXY_IMAGE=clirelay:patched-<tag>|" .env \
  && docker compose up -d --no-deps --force-recreate cli-proxy-api'
```

Do **not** rebuild the binary from a clean upstream tree without applying this
patch: the pi-facing `/v1/models` fields live here, and dropping them silently
strips `context_window` / `max_output_tokens` / reasoning levels from every
model.

## Auto-update

Disabled on purpose: `clirelay-updater` is stopped, `.env` pins
`CLI_PROXY_IMAGE` to the locally built tag and sets
`CLI_PROXY_PULL_POLICY=never`.

`config.yaml` still has `auto-update.enabled: true`, so triggering an update
from the management panel will repoint `CLI_PROXY_IMAGE` at
`ghcr.io/kittors/clirelay:latest` and drop every patch above. Note also that
the app rewrites `config.yaml` on startup — hand-edits to that file are lost;
change it through the management panel.
