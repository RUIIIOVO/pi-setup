#!/usr/bin/env python3
"""把本仓库里的 pi 配置基线装到当前机器。

幂等：重复执行不会产生副作用；已有文件先备份再改。
只碰 ~/.pi 下面的东西，不改 shell 配置、不写凭据。

    python3 install.py            # 装 settings / extension / patch
    python3 install.py --dry-run  # 只打印会做什么
    python3 install.py --seed-models  # 顺带铺一份模型表（仅当本地没有时）
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent
SRC = REPO / "pi"
PI_HOME = Path.home() / ".pi"
AGENT_DIR = PI_HOME / "agent"
PATCH_DIR = PI_HOME / "patches"

DRY_RUN = "--dry-run" in sys.argv
SEED_MODELS = "--seed-models" in sys.argv

STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")


def log(step: str, msg: str) -> None:
    # flush：补丁是子进程直写 stdout，不刷新会串行错位
    print(f"[{step}] {msg}", flush=True)


def backup(path: Path) -> Path:
    dest = path.with_name(f"{path.name}.bak-{STAMP}")
    log("backup", f"{path} -> {dest.name}")
    if not DRY_RUN:
        shutil.copy2(path, dest)
    return dest


def ensure_dir(path: Path) -> None:
    if path.is_dir():
        return
    log("mkdir", str(path))
    if not DRY_RUN:
        path.mkdir(parents=True, exist_ok=True)


def merge_settings() -> None:
    """仓库里的键写进本地 settings.json，本地独有的键原样保留。"""
    want = json.loads((SRC / "settings.json").read_text("utf-8"))
    target = AGENT_DIR / "settings.json"
    current: dict = {}
    if target.exists():
        try:
            current = json.loads(target.read_text("utf-8"))
        except json.JSONDecodeError:
            sys.exit(f"{target} 不是合法 JSON，先自己处理掉再重跑")

    changed = {k: v for k, v in want.items() if current.get(k) != v}
    if not changed:
        log("settings", "已是目标状态，跳过")
        return

    log("settings", f"写入 {len(changed)} 个键：{', '.join(changed)}")
    if target.exists():
        backup(target)
    merged = {**current, **want}
    if not DRY_RUN:
        target.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", "utf-8")


def link(src: Path, dest: Path) -> None:
    """把 dest 做成指向 src 的软链；已有内容先备份。"""
    ensure_dir(dest.parent)
    if dest.is_symlink() and dest.resolve() == src:
        log("link", f"{dest.name} 已指向仓库，跳过")
        return
    if dest.exists() or dest.is_symlink():
        if dest.is_symlink():
            log("unlink", f"{dest} -> {os.readlink(dest)}")
            if not DRY_RUN:
                dest.unlink()
        else:
            backup(dest)
            if not DRY_RUN:
                dest.unlink()
    log("link", f"{dest} -> {src}")
    if not DRY_RUN:
        dest.symlink_to(src)


def apply_patch() -> None:
    script = SRC / "patches" / "apply-billing-header.py"
    if DRY_RUN:
        log("patch", f"会执行 python3 {script}")
        return
    log("patch", "重写 pi 的 anthropic-messages 分块，注入计费归属块")
    result = subprocess.run([sys.executable, str(script)], text=True)
    if result.returncode != 0:
        sys.exit("补丁失败，见上方输出；pi 版本升级后锚点可能已经变了")


def seed_models() -> None:
    target = AGENT_DIR / "models-store.json"
    if target.exists():
        log("models", "本地已有 models-store.json，跳过（pi 会自己刷新）")
        return
    log("models", f"复制模型表模板到 {target}")
    if not DRY_RUN:
        shutil.copy2(SRC / "models-store.example.json", target)


def check_auth() -> None:
    target = AGENT_DIR / "auth.json"
    if not target.exists():
        log("auth", "没有 auth.json：进入 pi 后跑 /login 选 anthropic 走 OAuth")
        return
    try:
        data = json.loads(target.read_text("utf-8"))
    except json.JSONDecodeError:
        log("auth", "auth.json 存在但不是合法 JSON，自己看一眼")
        return
    kinds = {p: (c.get("type") if isinstance(c, dict) else "?") for p, c in data.items()}
    log("auth", f"已有凭据：{kinds}（内容不打印、不入库）")


def main() -> None:
    if DRY_RUN:
        print("== dry run，不落任何改动 ==")
    ensure_dir(AGENT_DIR)
    merge_settings()
    link(SRC / "extensions" / "collapse-tool-output.ts", AGENT_DIR / "extensions" / "collapse-tool-output.ts")
    link(SRC / "patches" / "apply-billing-header.py", PATCH_DIR / "apply-billing-header.py")
    apply_patch()
    if SEED_MODELS:
        seed_models()
    check_auth()

    print()
    print("装完了。验证：")
    print("  pi -p --no-session --model anthropic/claude-haiku-4-5 'say hi'")
    print()
    print("pi 每次升级后补丁都会被覆盖，重跑：")
    print(f"  python3 {PATCH_DIR / 'apply-billing-header.py'}")


if __name__ == "__main__":
    main()
