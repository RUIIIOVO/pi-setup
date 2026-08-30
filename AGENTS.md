# 给 agent 的说明

这个仓库是一台机器上 pi（`@earendil-works/pi-coding-agent`）的配置基线。用户说「把 pi 配好 / 按这个仓库装 pi」时，执行：

```bash
python3 install.py --dry-run   # 先给用户看会改什么
python3 install.py             # 用户点头后再执行
```

装完把 `install.py` 打印的验证命令跑一遍，把结果贴给用户。

## 硬规则

1. **不要把任何真实凭据写进这个仓库**。`~/.pi/agent/auth.json` 里是 OAuth token 和 API key，不读、不打印、不复制。要给结构就改 `pi/auth.example.json` 里的占位符。
2. **不要替用户改 shell 配置**。`piup` 那段 zsh 函数只在 README 里给出，由用户自己决定要不要加。
3. `pi/patches/apply-billing-header.py` 会改写 pi 的 npm 产物。改这个脚本前先确认锚点字符串还在当前 pi 版本里；报 `anchor not found` 说明上游 bundle 变了，要重新定位，不要瞎改正则。
4. 改了 `pi/` 下任何文件之后，重跑 `python3 install.py` 让软链和 settings 同步。

## 目录

```
install.py                          幂等安装入口
pi/settings.json                    合并进 ~/.pi/agent/settings.json 的键
pi/extensions/collapse-tool-output.ts   软链到 ~/.pi/agent/extensions/
pi/patches/apply-billing-header.py      软链到 ~/.pi/patches/，安装时执行一次
pi/auth.example.json                凭据结构示例（占位符）
pi/models-store.example.json        模型表快照，默认不装
```

每项改动的来龙去脉写在 README.md，别在这里重复。
