/**
 * 折叠态下把内置工具压成恰好一行：调用行尾部直接挂结果摘要，结果槽渲染为空。
 *
 * pi 折叠态（默认）各工具仍会占多行，行数是硬编码常量，没有配置项：
 * - bash：保留最后 5 行输出（BASH_PREVIEW_LINES）
 * - edit：diff 挂在 renderCall 的组件上，折叠也照画
 * - write：renderCall 里打印文件内容预览
 * read 折叠本来就是一行，不动。
 *
 * 覆盖内置工具，只替换渲染 slot；execute / prompt 元数据全部沿用内置定义。
 * 展开态（ctrl+o）一律委托回内置渲染器，行为不变。
 */

import {
	createBashToolDefinition,
	createEditToolDefinition,
	createWriteToolDefinition,
	type ExtensionAPI,
	keyHint,
} from "@earendil-works/pi-coding-agent";
import { Container, Text } from "@earendil-works/pi-tui";
import { relative } from "node:path";

/** 折叠行里给命令/路径留的最大宽度，超出截断，避免 Text 自动换行破坏「一行」。 */
const MAX_HEAD = 88;

function textOf(result: any): string {
	const content = Array.isArray(result?.content) ? result.content : [];
	return content
		.filter((c: any) => c?.type === "text")
		.map((c: any) => c.text ?? "")
		.join("\n")
		.trim();
}

function oneLine(s: string, max = MAX_HEAD): string {
	const flat = s.replace(/\s+/g, " ").trim();
	return flat.length > max ? `${flat.slice(0, max - 1)}\u2026` : flat;
}

function shortPath(p: unknown, cwd: string): string {
	if (typeof p !== "string" || !p) return "";
	const rel = relative(cwd, p);
	return !rel || rel.startsWith("..") ? p : rel;
}

/** 折叠态和展开态各自缓存组件，避免组件类型在两态之间串台。 */
function reuseText(state: any, key: string, line: string): Text {
	const component: Text = state[key] ?? new Text("", 1, 0);
	component.setText(line);
	state[key] = component;
	return component;
}

function emptyContainer(state: any, key: string): Container {
	const component: Container = state[key] ?? new Container();
	component.clear();
	state[key] = component;
	return component;
}

function delegate(state: any, key: string, render: (ctx: any) => any, context: any) {
	const component = render({ ...context, lastComponent: state[key] });
	state[key] = component;
	return component;
}

/** 结果槽算出摘要后存进 state，由调用行拼在尾部；变化时才请求重绘。 */
function setSummary(state: any, summary: string | undefined, context: any) {
	if (state.summary === summary) return;
	state.summary = summary;
	context.invalidate();
}

function withSummary(head: string, state: any, theme: any): string {
	if (!state.summary) return head;
	return `${head}  ${theme.fg("muted", state.summary)} ${theme.fg("dim", `(${keyHint("app.tools.expand", "to expand")})`)}`;
}

export default function (pi: ExtensionAPI) {
	pi.on("session_start", (_event, ctx) => {
		const cwd = ctx.cwd;

		// ---- bash ----
		const bash: any = createBashToolDefinition(cwd);
		pi.registerTool({
			...bash,
			renderCall(args: any, theme: any, context: any) {
				const state = context.state;
				if (context.executionStarted && state.startedAt === undefined) {
					state.startedAt = Date.now();
					state.endedAt = undefined;
				}
				if (context.expanded) return delegate(state, "_x", (c) => bash.renderCall(args, theme, c), context);
				const command = oneLine(typeof args?.command === "string" ? args.command : "");
				return reuseText(state, "_c", withSummary(`${theme.fg("toolTitle", "$")} ${command}`, state, theme));
			},
			renderResult(result: any, options: any, theme: any, context: any) {
				const state = context.state;
				if (options.expanded) return delegate(state, "_xr", (c) => bash.renderResult(result, options, theme, c), context);

				if (!options.isPartial || context.isError) {
					state.endedAt ??= Date.now();
					if (state.interval) {
						clearInterval(state.interval);
						state.interval = undefined;
					}
				}

				const output = textOf(result);
				const lines = output ? output.split("\n").length : 0;
				const truncation = result?.details?.truncation;

				if (options.isPartial && !context.isError) {
					setSummary(state, lines ? `running, ${lines} lines` : "running", context);
					return emptyContainer(state, "_cr");
				}

				const parts: string[] = [
					truncation?.truncated
						? `${truncation.outputLines}/${truncation.totalLines} lines`
						: lines === 0
							? "no output"
							: `${lines} lines`,
				];
				if (state.startedAt !== undefined) {
					parts.push(`${(((state.endedAt ?? Date.now()) - state.startedAt) / 1000).toFixed(1)}s`);
				}
				const summary = parts.join(" \u00b7 ");
				setSummary(state, context.isError ? `failed \u00b7 ${summary}` : summary, context);
				return emptyContainer(state, "_cr");
			},
		} as any);

		// ---- edit ----
		const edit: any = createEditToolDefinition(cwd);
		pi.registerTool({
			...edit,
			renderCall(args: any, theme: any, context: any) {
				const state = context.state;
				if (context.expanded) return delegate(state, "_x", (c) => edit.renderCall(args, theme, c), context);
				const head = `${theme.fg("toolTitle", theme.bold("edit"))} ${theme.fg("toolOutput", oneLine(shortPath(args?.file_path ?? args?.path, context.cwd)))}`;
				return reuseText(state, "_c", withSummary(head, state, theme));
			},
			renderResult(result: any, options: any, theme: any, context: any) {
				const state = context.state;
				if (options.expanded)
					return delegate(state, "_xr", (c) => edit.renderResult(result, options, theme, c), context);
				if (options.isPartial) return emptyContainer(state, "_cr");

				if (context.isError) {
					setSummary(state, "failed", context);
					return emptyContainer(state, "_cr");
				}
				const diff: string = result?.details?.diff ?? "";
				let add = 0;
				let del = 0;
				for (const line of diff.split("\n")) {
					if (line.startsWith("+") && !line.startsWith("+++")) add++;
					else if (line.startsWith("-") && !line.startsWith("---")) del++;
				}
				setSummary(state, diff ? `+${add} \u2212${del}` : "done", context);
				return emptyContainer(state, "_cr");
			},
		} as any);

		// ---- write ----
		const write: any = createWriteToolDefinition(cwd);
		pi.registerTool({
			...write,
			renderCall(args: any, theme: any, context: any) {
				const state = context.state;
				if (context.expanded) return delegate(state, "_x", (c) => write.renderCall(args, theme, c), context);
				const head = `${theme.fg("toolTitle", theme.bold("write"))} ${theme.fg("toolOutput", oneLine(shortPath(args?.file_path ?? args?.path, context.cwd)))}`;
				return reuseText(state, "_c", withSummary(head, state, theme));
			},
			renderResult(result: any, options: any, theme: any, context: any) {
				const state = context.state;
				if (options.expanded)
					return delegate(state, "_xr", (c) => write.renderResult(result, options, theme, c), context);
				if (options.isPartial) return emptyContainer(state, "_cr");

				const content = typeof context.args?.content === "string" ? context.args.content : "";
				const lines = content ? content.replace(/\n$/, "").split("\n").length : 0;
				setSummary(state, context.isError ? "failed" : lines ? `${lines} lines` : "written", context);
				return emptyContainer(state, "_cr");
			},
		} as any);
	});
}
