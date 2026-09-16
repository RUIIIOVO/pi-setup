# CliRelay patch for the pi CLIProxyAPI provider

Target deployment: `vps-us-sj:/root/CliRelay` (base commit `1effc9b`).
Running image: `clirelay:patched-1effc9b-fable51-v3`.

The same changes are tracked as a real git branch (easier to rebase than a
flat patch file):

    https://github.com/RUIIIOVO/CliRelay  branch `pi-compat`

`clirelay-pi-compat.patch` is the flattened form of that branch, kept here so a
machine without the fork checked out can still reproduce the build.

## What `clirelay-pi-compat.patch` changes

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

## Rebuild + redeploy

Preferred: work from the fork so conflicts surface in git instead of in a
flat patch.

```bash
git clone git@github.com:RUIIIOVO/CliRelay.git && cd CliRelay
git checkout pi-compat
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
  && printf "FROM clirelay:patched-1effc9b\nCOPY --chown=clirelay:clirelay CLIProxyAPI /CLIProxyAPI/CLIProxyAPI\n" > Dockerfile \
  && docker build -t clirelay:patched-<tag> . \
  && cd /root/CliRelay \
  && sed -i "s|^CLI_PROXY_IMAGE=.*|CLI_PROXY_IMAGE=clirelay:patched-<tag>|" .env \
  && docker compose up -d --no-deps --force-recreate cli-proxy-api'
```

Do **not** rebuild the binary from a clean upstream tree without applying this
patch: the pi-facing `/v1/models` fields live here, and dropping them silently
strips `context_window` / `max_output_tokens` / reasoning levels from every
model.

## Model catalog

The Claude OAuth channel merges the static definitions above with the tenant
model library (`model_configs` table, `owned_by='anthropic'`, `enabled=1`,
`source` in user/seed/openrouter). Adding a row there exposes a model without a
rebuild, but the row carries no context window or reasoning levels — those come
from the static definitions in item 4.

## Auto-update

Disabled on purpose: `clirelay-updater` is stopped, `.env` pins
`CLI_PROXY_IMAGE` to the locally built tag and sets
`CLI_PROXY_PULL_POLICY=never`.

`config.yaml` still has `auto-update.enabled: true`, so triggering an update
from the management panel will repoint `CLI_PROXY_IMAGE` at
`ghcr.io/kittors/clirelay:latest` and drop every patch above. Note also that
the app rewrites `config.yaml` on startup — hand-edits to that file are lost;
change it through the management panel.
