# pi-setup

给 [pi](https://www.npmjs.com/package/@earendil-works/pi-coding-agent)（`@earendil-works/pi-coding-agent`）用的一套个人配置基线。解决三件事：

1. **Claude 订阅账号（Pro / Max / Team）在 pi 里被算成 extra usage**，请求直接 400
2. **工具调用折叠态还是占好几行**，屏幕很快被 bash 输出和 diff 淹没
3. 思考块默认展开，读起来更吵

换机器时 clone 下来跑一条命令，不用再翻记忆。

> **先读这段再决定用不用。**
> 第 1 项通过改写 pi 的 npm 产物，在请求里加上官方客户端的计费归属标识。这个做法是否符合 Anthropic 的服务条款，请你自己判断，风险自负。本仓库只记录做法，不提供任何保证。不需要这一项的话，删掉 `pi/patches/` 再装，其余部分互不依赖。

---

## 目录

- [效果](#效果)
- [环境要求](#环境要求)
- [安装](#安装)
- [每一项分别做了什么](#每一项分别做了什么)
- [验证](#验证)
- [pi 升级之后](#pi-升级之后)
- [卸载](#卸载)
- [FAQ](#faq)
- [兼容性](#兼容性)
- [相关](#相关)

## 效果

工具调用折叠态，装之前（bash 保留最后 5 行输出、edit 照画 diff、write 打印文件预览）：

```
$ rg --files-with-matches "billing" dist/
dist/core/model-runtime.js
dist/core/usage.js
dist/providers/anthropic.js
dist/providers/openai.js
dist/modes/interactive/status-line.js
```

装之后，一行，尾部挂摘要，`ctrl+o` 照样能展开看全文：

```
$ rg --files-with-matches "billing" dist/    7 lines · 0.3s (ctrl+o to expand)
```

## 环境要求

- macOS（已验证）；Linux 理论上也能跑，脚本只用到 `python3` 标准库，没有第三方依赖，但我没测过
- Python 3.9+
- pi 已安装，且能通过 `mise which pi` 或 `which pi` 找到
- pi 是 npm 包形式安装的（脚本要定位 `node_modules/@earendil-works/pi-coding-agent`）

## 安装

```bash
git clone <this-repo> ~/Code/pi-setup
cd ~/Code/pi-setup

python3 install.py --dry-run   # 先看会改什么，零改动
python3 install.py             # 执行
```

安装是幂等的，重复跑不会有副作用；任何被覆盖的文件都会先备份成 `<原名>.bak-<时间戳>`。

用 coding agent 的话，把仓库丢给它，说一句「按 pi-setup 的 install.py 把这台机器的 pi 配好」即可，根目录的 `AGENTS.md` 写了执行步骤和禁止事项。

install.py 会做这些事，仅此而已：

| 动作 | 目标 |
|---|---|
| 合并 settings | `~/.pi/agent/settings.json` |
| 建软链 | `~/.pi/agent/extensions/collapse-tool-output.ts` |
| 建软链 | `~/.pi/patches/apply-billing-header.py` |
| 执行补丁 | pi 包内的 `dist/bundle/chunks/anthropic-messages-*.js` |
| 只读检查 | `~/.pi/agent/auth.json` 是否存在（不读内容） |

它**不会**改你的 shell 配置，**不会**碰凭据，**不会**联网。

## 每一项分别做了什么

### 1. Anthropic OAuth 计费归属补丁

文件：`pi/patches/apply-billing-header.py`

Anthropic 从 2026-04-04 起收紧了归属判定：拿 Claude 订阅账号的 OAuth 凭据发请求，如果第一条 system 块里没有官方客户端的计费归属声明，就会被算成 extra usage，表现为 HTTP 400。pi 0.84.3 只在提示词里写了一句「You are Claude Code, Anthropic's official CLI for Claude.」，属于第三方归属。

补丁改两处：

- `system[0]` 换成带 `x-anthropic-billing-header: cc_version=<版本>.<3 位 hex>; cc_entrypoint=sdk-cli;` 的文本块
- 身份句改成 Agent SDK 的措辞

做法参考了 [oh-my-pi](https://www.npmjs.com/package/@oh-my-pi/pi-coding-agent)。

特性：

- 幂等，已打过会直接跳过
- 打补丁前把原 chunk 备份成同名 `.orig`
- 回退：`python3 ~/.pi/patches/apply-billing-header.py --revert`
- 靠字符串锚点定位，锚点对不上就报 `anchor not found` 并退出，不会乱改

运行时可调的环境变量：

| 变量 | 默认 | 作用 |
|---|---|---|
| `PI_CC_VERSION` | `2.1.220` | 声明的 Claude Code 版本 |
| `PI_CC_ENTRYPOINT` | `sdk-cli` | `cc_entrypoint` 标签 |
| `PI_CC_WITH_CCH` | 未设置 | 设了就追加 ` cch=00000;` |

### 2. 工具调用折叠成一行

文件：`pi/extensions/collapse-tool-output.ts`，软链到 `~/.pi/agent/extensions/`

pi 折叠态下每个工具仍占多行，行数写死在代码里，没有配置项：

| 工具 | 折叠态原本的行为 |
|---|---|
| bash | 保留最后 5 行输出（`BASH_PREVIEW_LINES`） |
| edit | diff 挂在 `renderCall` 上，折叠也照画 |
| write | `renderCall` 里打印文件内容预览 |
| read | 本来就是一行，不动 |

这个 extension 覆盖 bash / edit / write 三个内置工具，**只替换渲染槽**，`execute` 和提示词元数据全部沿用内置定义。折叠态压成一行，结果摘要（行数、耗时、`+12 −3`）挂在调用行尾部；按 `ctrl+o` 展开时一律委托回内置渲染器，行为和原版完全一致。

它依赖 pi 导出的 `createBashToolDefinition` / `createEditToolDefinition` / `createWriteToolDefinition`。升级后如果这几个导出变了，TUI 里会看到工具渲染异常，删掉软链就回到默认。

### 3. settings

`pi/settings.json` 里的键会合并进 `~/.pi/agent/settings.json`，你本地独有的键（`lastChangelogVersion` 这类运行时状态）原样保留：

```json
{
  "defaultProvider": "anthropic",
  "defaultModel": "claude-opus-5",
  "theme": "dark",
  "hideThinkingBlock": true,
  "defaultThinkingLevel": "high"
}
```

不想要某一项就直接改这个文件，前四个键按自己的习惯换掉即可。

### 4. 凭据（不入库）

**仓库里没有、也不会有任何真实凭据。** `pi/auth.example.json` 只给结构：

```jsonc
{
  "anthropic": { "type": "oauth",   "refresh": "…", "access": "…", "expires": 0 },
  "deepseek":  { "type": "api_key", "key": "…" }
}
```

真实文件是 `~/.pi/agent/auth.json`，权限 0600，由 pi 自己写。新机器上：

```bash
pi        # 进 TUI 后 /login，选 anthropic，走浏览器 OAuth
```

install.py 只会打印「有哪些 provider、各是什么类型」，不读取、不打印、不复制 token。`.gitignore` 里也挡了 `auth.json`。

### 5. 模型表（默认不装）

`pi/models-store.example.json` 是 `~/.pi/agent/models-store.json` 的快照，剥掉了 `etag` / `checkedAt` / `lastModified` 这些缓存字段，里面只有模型 id、定价、上下文长度，没有任何密钥。

默认**不装**，因为 pi 自己会从远端刷新，铺一份旧的只会制造冲突。离线机器确实需要再加参数：

```bash
python3 install.py --seed-models   # 仅当本地还没有 models-store.json 时才写
```

## 验证

```bash
# 1. 补丁在位
grep -rl __ccBillingBlock "$(dirname "$(mise which pi)")/../@earendil-works/pi-coding-agent/dist"

# 2. 订阅账号正常出账（不是 HTTP 400）
pi -p --no-session --model anthropic/claude-haiku-4-5 'say hi'

# 3. 折叠生效：起 pi 跑一条 bash，应该只占一行，ctrl+o 能展开
```

## pi 升级之后

**补丁会被覆盖，必须重跑**，其余两项不受影响：

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

## 卸载

```bash
python3 ~/.pi/patches/apply-billing-header.py --revert   # 还原 npm 产物
rm ~/.pi/agent/extensions/collapse-tool-output.ts        # 移除折叠 extension
rm ~/.pi/patches/apply-billing-header.py
```

settings 的改动手动回滚：备份在 `~/.pi/agent/settings.json.bak-<时间戳>`。

## FAQ

**装了之后 pi 起不来 / 工具渲染报错？**
先删软链 `rm ~/.pi/agent/extensions/collapse-tool-output.ts` 再起。多半是 pi 升级后 extension API 变了。

**补丁报 `anchor not found exactly once`？**
上游 bundle 变形了，脚本不会硬改，直接退出。需要重新对一遍 pi 里 `params.system=[{...}]` 附近的代码，改 `apply-billing-header.py` 顶部的 `OLD` / `NEW` 常量。

**`no node_modules above …`？**
你的 pi 不是 npm 包形式安装的（比如单文件二进制），这个补丁不适用。

**改了仓库里的文件怎么生效？**
extension 和补丁脚本都是软链，改完即生效；改了 `pi/settings.json` 要重跑 `python3 install.py`。

**会上传我的什么数据吗？**
不会。install.py 不联网，只读写 `~/.pi` 下的文件。

## 兼容性

对着以下版本验证过：

| 组件 | 版本 |
|---|---|
| `@earendil-works/pi-coding-agent` | 0.84.3 |
| `@earendil-works/pi-tui` | 0.83.0 |
| Python | 3.9+ |
| 平台 | macOS（Apple Silicon） |

pi 迭代很快，跨版本用之前先跑 `python3 install.py --dry-run`。

## 相关

**omp（`@oh-my-pi/pi-coding-agent`）不需要这里的 extension**，同样的折叠效果它内置支持，`~/.omp/agent/config.yml` 里两行搞定：

```yaml
hideThinkingBlock: true
display:
  hideToolActivity: true
```

**在 herdr 这类终端复用器里读图片会看到一大片空白**：pi 看到宿主是 Ghostty / kitty / WezTerm 就按 kitty graphics 协议发图并预留行高（对 tmux 它会主动关掉图片，所以 tmux 没这个问题），而复用器若不转发图形序列，就只剩下空行。两条路：

- 让复用器自己画图（herdr：`~/.config/herdr/config.toml` 里 `[experimental] kitty_graphics = true`；**实测 `herdr server reload-config` 不足以生效，要重启 server**）
- 或者关掉 pi 的图片渲染：`~/.pi/agent/settings.json` 加 `"terminal": { "showImages": false }`，图片退化成 `[image/png 3024x1746]` 一行文本，**模型照样收得到图**，只是 TUI 不画

## 致谢

计费归属那部分的思路来自 [oh-my-pi](https://www.npmjs.com/package/@oh-my-pi/pi-coding-agent)。

---

本仓库与 Anthropic、pi 官方无关。
