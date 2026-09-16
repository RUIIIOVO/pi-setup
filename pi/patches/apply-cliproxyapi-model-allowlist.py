#!/usr/bin/env python3
"""Restrict @router-for-me/pi-cliproxyapi-provider to a model allowlist.

The provider registers every model the CLIProxyAPI server returns from
/v1/models (currently 15 legacy + current Claude ids). This patch injects an
allowlist filter into `loadMappedModels` so only the newest generation models
survive into the /model picker. Older ids (4.x, 3.x, dated snapshots) are hidden.

The allowlist is overridable at runtime via the CLIPROXYAPI_MODEL_ALLOW env var
(comma-separated exact model ids). When unset, DEFAULT_ALLOW below is used.

Filtering happens on the freshly fetched remote list, so it survives the
background force-refresh that overwrites cliproxyapi-models.json on every start.

Idempotent. Run after every `pi update` / plugin reinstall, then
`rm -f ~/.pi/agent/cliproxyapi-models.json` to force a catalog refresh.
"""

from __future__ import annotations

import sys
from pathlib import Path

LIB = (
    Path.home()
    / ".pi/agent/npm/node_modules/@router-for-me/pi-cliproxyapi-provider/extensions/lib.ts"
)

MARKER = "CLIPROXYAPI_MODEL_ALLOW"

ANCHOR = (
    "\tconst [remoteModels, costCatalog] = await Promise.all([\n"
    "\t\tfetchCodexModels(endpoints.modelsUrl, apiKey, timeoutMs, signal),\n"
    "\t\tpricingEnabled ? fetchModelsDevCostMap(agentDir, false, signal) : Promise.resolve(undefined),\n"
    "\t]);\n"
)

INJECT = (
    "\tconst [remoteModelsAll, costCatalog] = await Promise.all([\n"
    "\t\tfetchCodexModels(endpoints.modelsUrl, apiKey, timeoutMs, signal),\n"
    "\t\tpricingEnabled ? fetchModelsDevCostMap(agentDir, false, signal) : Promise.resolve(undefined),\n"
    "\t]);\n"
    "\t// PATCH:CLIPROXYAPI_MODEL_ALLOW keep only newest-generation models.\n"
    "\tconst DEFAULT_ALLOW = [\n"
    '\t\t"claude-opus-5",\n'
    '\t\t"claude-sonnet-5",\n'
    '\t\t"claude-fable-5-1",\n'
    '\t\t"claude-fable-5",\n'
    "\t];\n"
    "\tconst allowRaw = (process.env.CLIPROXYAPI_MODEL_ALLOW ?? \"\").trim();\n"
    "\tconst allowList = allowRaw\n"
    "\t\t? allowRaw.split(\",\").map((s) => s.trim().toLowerCase()).filter(Boolean)\n"
    "\t\t: DEFAULT_ALLOW.map((s) => s.toLowerCase());\n"
    "\tconst allowSet = new Set(allowList);\n"
    "\tconst remoteModelsFiltered = remoteModelsAll.filter((m) => {\n"
    "\t\tconst id = codexModelId(m).toLowerCase();\n"
    "\t\treturn allowSet.has(id);\n"
    "\t});\n"
    "\tconst remoteModels = remoteModelsFiltered.length > 0 ? remoteModelsFiltered : remoteModelsAll;\n"
)


def main() -> int:
    if not LIB.exists():
        print(f"plugin not installed: {LIB}", file=sys.stderr)
        return 1

    source = LIB.read_text()
    if MARKER in source:
        print("already patched")
        return 0

    if ANCHOR not in source:
        print("anchor not found, plugin changed upstream", file=sys.stderr)
        return 1

    source = source.replace(ANCHOR, INJECT, 1)
    LIB.write_text(source)
    print(f"patched {LIB}")
    print("run `rm -f ~/.pi/agent/cliproxyapi-models.json` to force a catalog refresh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
