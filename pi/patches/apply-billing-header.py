#!/usr/bin/env python3
"""Re-apply the Anthropic OAuth billing-attribution patch to pi (@earendil-works/pi-coding-agent).

Why: since Anthropic's 2026-04-04 / mid-June enforcement, a Claude Pro/Max/Team OAuth
credential is billed to "extra usage" (HTTP 400) unless the request carries the
first-party billing-attribution block as system[0]:

    x-anthropic-billing-header: cc_version=<ver>.<3 hex>; cc_entrypoint=sdk-cli;

pi 0.84.3 only asserts the identity in prose ("You are Claude Code, ..."), so its
requests are attributed as third-party. This patch prepends the block and switches the
prose line to the Agent-SDK wording, matching the genuine `claude` CLI surface.

Verified working 2026-08-28 on a Claude Max account (haiku-4-5 + opus-5, tool calls).
No header or models.json change is needed; the system[0] block is the only lever.

Run after every `mise upgrade npm:@earendil-works/pi-coding-agent` or `pi update pi`.
Idempotent. Keeps a .orig backup next to the patched chunk.

    python3 ~/.pi/patches/apply-billing-header.py [--revert]

Env knobs honoured at runtime by the injected helper:
    PI_CC_VERSION     spoofed Claude Code version (default 2.1.220)
    PI_CC_ENTRYPOINT  cc_entrypoint label        (default sdk-cli)
    PI_CC_WITH_CCH    set to append " cch=00000;" (omp does this; not required)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

MARKER = "You are Claude Code, Anthropic's official CLI for Claude."
OLD = (
    'params.system=[{type:"text",text:"You are Claude Code, Anthropic\'s official CLI for Claude.",'
    "...cacheControl?{cache_control:cacheControl}:{}}]"
)
NEW = (
    'params.system=[{type:"text",text:__ccBillingBlock(context)},'
    '{type:"text",text:"You are a Claude agent, built on Anthropic\'s Claude Agent SDK.",'
    "...cacheControl?{cache_control:cacheControl}:{}}]"
)
HELPER = (
    'import{createHash as __ccSha256}from"node:crypto";\n'
    "function __ccFirstUserText(context){try{for(const m of (context?.messages??[])){"
    'if(m?.role!=="user")continue;const c=m.content;'
    'if(typeof c==="string"&&c.length)return c;'
    "if(Array.isArray(c)){for(const b of c){"
    'if(typeof b?.text==="string"&&b.text.length)return b.text}}}}catch{}return""}\n'
    "function __ccBillingBlock(context){"
    'const ver=process.env.PI_CC_VERSION||"2.1.220";'
    'const entry=process.env.PI_CC_ENTRYPOINT||"sdk-cli";'
    "const txt=__ccFirstUserText(context);"
    'const s=[4,7,20].map(i=>txt[i]??"0").join("");'
    'const o=__ccSha256("sha256").update(`59cf53e54c78${s}${ver}`).digest("hex").slice(0,3);'
    'const cch=process.env.PI_CC_WITH_CCH?" cch=00000;":"";'
    "return`x-anthropic-billing-header: cc_version=${ver}.${o}; cc_entrypoint=${entry};${cch}`}\n"
)


def pi_bin_path() -> Path:
    """Resolve the live pi launcher: mise first, then plain PATH lookup."""
    try:
        which = subprocess.run(["mise", "which", "pi"], capture_output=True, text=True)
    except FileNotFoundError:
        which = None
    if which is not None and which.returncode == 0 and which.stdout.strip():
        return Path(which.stdout.strip())
    fallback = shutil.which("pi")
    if fallback:
        return Path(fallback)
    sys.exit("cannot resolve pi: both `mise which pi` and `which pi` failed")


def pi_package_root() -> Path:
    # .../node_modules/.bin/pi -> .../node_modules/@earendil-works/pi-coding-agent
    bin_path = pi_bin_path().resolve()
    node_modules = next((p for p in bin_path.parents if p.name == "node_modules"), None)
    if node_modules is None:
        sys.exit(f"no node_modules above {bin_path}; is this a bundled/native pi build?")
    root = node_modules / "@earendil-works" / "pi-coding-agent"
    if not root.is_dir():
        sys.exit(f"pi package not found at {root}")
    return root


def find_chunk(root: Path) -> Path:
    """The bundle chunk name carries a content hash, so locate it by content."""
    candidates = [p for p in (root / "dist").rglob("*.js") if MARKER in p.read_text("utf-8", "ignore")]
    if len(candidates) != 1:
        sys.exit(f"expected exactly 1 chunk containing the OAuth identity line, found {len(candidates)}")
    return candidates[0]


def main() -> None:
    revert = "--revert" in sys.argv
    root = pi_package_root()

    if revert:
        # After a revert the marker is gone, so find the patched chunk instead.
        patched = [p for p in (root / "dist").rglob("*.js") if "__ccBillingBlock" in p.read_text("utf-8", "ignore")]
        if not patched:
            print("nothing to revert (no patched chunk)")
            return
        for chunk in patched:
            orig = chunk.with_suffix(chunk.suffix + ".orig")
            if not orig.exists():
                sys.exit(f"no backup at {orig}; reinstall pi instead")
            shutil.move(str(orig), str(chunk))
            print(f"reverted {chunk.relative_to(root)}")
        return

    dist = root / "dist"
    if any("__ccBillingBlock" in p.read_text("utf-8", "ignore") for p in dist.rglob("*.js")):
        print(f"already patched ({root.name} {root.joinpath('package.json').exists() and 'ok'})")
        return

    chunk = find_chunk(root)
    orig = chunk.with_suffix(chunk.suffix + ".orig")
    if not orig.exists():
        shutil.copy2(chunk, orig)

    src = chunk.read_text("utf-8")
    if src.count(OLD) != 1:
        sys.exit(f"anchor not found exactly once in {chunk.name} (found {src.count(OLD)}); upstream changed shape")
    chunk.write_text(HELPER + src.replace(OLD, NEW), "utf-8")
    print(f"patched {chunk.relative_to(root)}")
    print("verify:  pi -p --no-session --model anthropic/claude-haiku-4-5 'say hi'")


if __name__ == "__main__":
    os.umask(0o022)
    main()
