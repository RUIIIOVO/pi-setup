# pi-setup

我自己那套 pi（`@earendil-works/pi-coding-agent`）的配置基线：Claude 订阅账号的计费归属补丁、工具调用折叠成一行、思考块默认收起。

换机器时不用再翻记忆，clone 下来跑一条命令。

## 一句话装

```bash
git clone <this-repo> ~/Code/pi-setup && python3 ~/Code/pi-setup/install.py
```

丢给 agent 的说法：**「按 pi-setup 仓库的 install.py 把这台机器的 pi 配好」**（仓库根目录的 `AGENTS.md` 会告诉它怎么做）。

先看会改什么：

```bash
python3 install.py --dry-run
```

## 装了哪些东西

| # | 改动 | 落到哪 | 性质 | pi 升级后 |
|---|---|---|---|---|
| 1 | Anthropic OAuth 计费归属补丁 | 改写 pi 包内 `dist/bundle/chunks/anthropic-messages-*.js` | 侵入式改 npm 产物 | **失效，必须重跑** |
| 2 | 工具调用折叠成一行 | `~/.pi/agent/extensions/collapse-tool-output.ts`（软链到本仓库） | 官方 extension API | 不失效，但 API 变了会挂 |
| 3 | 思考块默认收起 + 默认 high | `~/.pi/agent/settings.json` | 官方配置 | 不失效 |
| 4 | Claude 账号 | `~/.pi/agent/auth.json` | 凭据 | **不入库**，新机器重新 `/login` |
| 5 | 模型表 | `~/.pi/agent/models-store.json` | 本地缓存 | 默认不动，见下 |

### 1. 计费归属补丁

`pi/patches/apply-billing-header.py`。

Anthropic 从 2026-04-04 起收紧：拿 Claude Pro/Max/Team 的 OAuth 凭据发请求，如果第一条 system 块里没有官方客户端的计费归属声明，会被算成 extra usage（HTTP 400）。pi 0.84.3 只在提示词里写了一句「You are Claude Code…」，属于第三方归属。

补丁做两件事：把 `system[0]` 换成带 `x-anthropic-billing-header: cc_version=…; cc_entrypoint=sdk-cli;` 的文本块，并把身份句改成 Agent SDK 的措辞。做法参考 oh-my-pi。

- 幂等，重复跑会自己识别已打补丁
- 打补丁前把原 chunk 备份成同名 `.orig`
- 回退：`python3 ~/.pi/patches/apply-billing-header.py --revert`
- 运行时可用环境变量微调：`PI_CC_VERSION`、`PI_CC_ENTRYPOINT`、`PI_CC_WITH_CCH`

**每次 pi 升级后必须重跑**，否则又回到第三方归属：

```bash
mise upgrade npm:@earendil-works/pi-coding-agent
python3 ~/.pi/patches/apply-billing-header.py
```

嫌麻烦就往 `~/.zshrc` 里塞一个（install.py 不会自动改你的 shell 配置）：

```zsh
piup() {
  mise upgrade npm:@earendil-works/pi-coding-agent && \
  python3 ~/.pi/patches/apply-billing-header.py
}
```

补丁靠字符串锚点定位，pi 换了 bundle 形状就会报 `anchor not found`，那时要重新对一遍 `params.system=[{...}]` 附近的代码。

### 2. 工具调用折叠成一行

`pi/extensions/collapse-tool-output.ts`，软链到 `~/.pi/agent/extensions/`。

pi 折叠态下每个工具仍占多行，行数写死在代码里没有配置项：bash 留最后 5 行输出、edit 照画 diff、write 打印文件预览。这个 extension 覆盖 bash / edit / write 三个内置工具的渲染槽（execute 和提示词元数据全部沿用内置定义），折叠态压成一行，结果摘要挂在调用行尾部；按 `ctrl+o` 展开时一律委托回内置渲染器。

它依赖 pi 导出的 `createBashToolDefinition` / `createEditToolDefinition` / `createWriteToolDefinition`，升级后如果这几个导出改了签名，TUI 里会看到工具渲染报错，删掉软链即可恢复默认。

### 3. settings

`pi/settings.json` 里的键会合并进本地 `~/.pi/agent/settings.json`，本地独有的键（`lastChangelogVersion` 这类运行时状态）保留不动。

```json
{
  "defaultProvider": "anthropic",
  "defaultModel": "claude-opus-5",
  "theme": "dark",
  "hideThinkingBlock": true,
  "defaultThinkingLevel": "high"
}
```

### 4. 凭据

**仓库里没有也不会有真实凭据。** `pi/auth.example.json` 只给结构：`type: "oauth"` 走订阅账号，`type: "api_key"` 走 key。真实文件是 `~/.pi/agent/auth.json`，权限 0600，由 pi 自己写。

新机器：

```bash
pi          # 进 TUI 后 /login，选 anthropic，走浏览器 OAuth
```

install.py 只会打印「有哪些 provider、是什么类型」，不读也不打印 token。

### 5. 模型表

`pi/models-store.example.json` 是 `~/.pi/agent/models-store.json` 的快照（去掉了 `etag` / `checkedAt` 这些缓存字段），里面没有任何密钥。

默认**不装**，因为 pi 自己会从远端刷新，铺一份旧的反而制造冲突。确实需要（比如离线机器）再加参数：

```bash
python3 install.py --seed-models   # 仅当本地还没有 models-store.json 时才写
```

## 验证

```bash
# 补丁在位
grep -rl __ccBillingBlock "$(dirname "$(mise which pi)")/../@earendil-works/pi-coding-agent/dist"

# 订阅账号能正常出账（不是 HTTP 400）
pi -p --no-session --model anthropic/claude-haiku-4-5 'say hi'

# 折叠：起 pi 跑一条 bash，应该只占一行，ctrl+o 能展开
```

## 卸载

```bash
python3 ~/.pi/patches/apply-billing-header.py --revert
rm ~/.pi/agent/extensions/collapse-tool-output.ts
# settings.json 的备份在 ~/.pi/agent/settings.json.bak-<时间戳>
```

## 相关但不归本仓库管

- **herdr 里读图片留一大片空白**：pi 检测到宿主是 Ghostty 就按 kitty graphics 协议发图并预留行高，而 herdr 默认丢弃图形序列。开 herdr 的 `~/.config/herdr/config.toml` → `[experimental] kitty_graphics = true`，然后 `herdr server reload-config`；不想开就把 pi 的 `terminal.showImages` 关掉（图片会退化成 `[image/png WxH]` 一行文本，模型照样收得到图）。
- **omp（`@oh-my-pi/pi-coding-agent`）**：同样的折叠效果它内置支持，`~/.omp/agent/config.yml` 里 `hideThinkingBlock: true` + `display.hideToolActivity: true` 就够了，不需要 extension。

## 版本

补丁与 extension 对着 pi `0.84.3` / pi-tui `0.83.0` 验证过。
