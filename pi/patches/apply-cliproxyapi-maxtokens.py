#!/usr/bin/env python3
"""Re-apply the maxTokens fix to @router-for-me/pi-cliproxyapi-provider.

The plugin hardcodes `maxTokens: DEFAULT_MAX_TOKENS` (16384) for every model it
registers, so a 128k-output model such as claude-opus-5 is capped at 16k. The
CLIProxyAPI server (patched build, see pi-setup/clirelay) publishes
`max_completion_tokens` / `max_output_tokens` on /v1/models; this patch makes the
plugin honour them.

Idempotent. Run after every `pi update` / plugin reinstall.
"""

from __future__ import annotations

import sys
from pathlib import Path

LIB = (
    Path.home()
    / ".pi/agent/npm/node_modules/@router-for-me/pi-cliproxyapi-provider/extensions/lib.ts"
)

EDITS = [
    (
        "\tcontext_window?: number;\n\tmax_context_window?: number;\n\tinput_modalities?: string[];",
        "\tcontext_window?: number;\n\tmax_context_window?: number;\n"
        "\tmax_completion_tokens?: number;\n\tmax_output_tokens?: number;\n"
        "\tinput_modalities?: string[];",
    ),
    (
        "\tconst cost = costCatalog\n"
        "\t\t? matchModelCost(id, costCatalog, fastMode && supportsFastServiceTier(model))\n"
        "\t\t: { ...ZERO_COST };",
        "\tconst maxTokens =\n"
        "\t\t(typeof model.max_completion_tokens === \"number\" && model.max_completion_tokens > 0\n"
        "\t\t\t? model.max_completion_tokens\n"
        "\t\t\t: undefined) ??\n"
        "\t\t(typeof model.max_output_tokens === \"number\" && model.max_output_tokens > 0\n"
        "\t\t\t? model.max_output_tokens\n"
        "\t\t\t: undefined) ??\n"
        "\t\tDEFAULT_MAX_TOKENS;\n\n"
        "\tconst cost = costCatalog\n"
        "\t\t? matchModelCost(id, costCatalog, fastMode && supportsFastServiceTier(model))\n"
        "\t\t: { ...ZERO_COST };",
    ),
    (
        "\t\tmaxTokens: DEFAULT_MAX_TOKENS,\n\t\tthinkingLevelMap: buildThinkingLevelMap(efforts),",
        "\t\tmaxTokens,\n\t\tthinkingLevelMap: buildThinkingLevelMap(efforts),",
    ),
]


def main() -> int:
    if not LIB.exists():
        print(f"plugin not installed: {LIB}", file=sys.stderr)
        return 1

    source = LIB.read_text()
    if "max_completion_tokens" in source and "\t\tmaxTokens,\n" in source:
        print("already patched")
        return 0

    for old, new in EDITS:
        if old not in source:
            print(f"anchor not found, plugin changed upstream:\n{old[:80]}...", file=sys.stderr)
            return 1
        source = source.replace(old, new, 1)

    LIB.write_text(source)
    print(f"patched {LIB}")
    print("run `rm -f ~/.pi/agent/cliproxyapi-models.json` to force a catalog refresh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
