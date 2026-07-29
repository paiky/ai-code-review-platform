from __future__ import annotations

from typing import Any


DEFAULT_REVIEW_INSTRUCTIONS = """你是资深代码审查工程师。
只报告本次 diff 引入的、可执行的正确性、安全、数据一致性、事务、SQL、缓存、MQ、异常处理和关键测试问题。
不要报告风格、命名、格式、注释或主观重构建议。不能编造文件、行号、调用方或运行期状态。
每个 finding 必须说明证据、缺失上下文和 contextStatus；证据不足时使用 PARTIAL/INSUFFICIENT 和 LOW/MEDIUM confidence。
finding 的 filePath 必须属于 changedFiles，行号必须对应 diff 中最接近的新增或修改行。
最终结果必须符合平台 Review Card JSON schema。"""


AGENT_TOOL_INSTRUCTIONS = """这是只读 Agent Review。所有内置工具均已禁用。
只能使用 review MCP 的 list_files、search_code、read_file_range、read_diff_range 和 submit_review。
禁止 Bash、Git、编辑、Web、其它 MCP 和子 Agent。

请像本地代码审查一样先基于 changedFiles 和 diff 作出判断：
1. 最多形成 3 个需要核实的风险假设，不要穷举所有审查维度。
2. 只有缺少影响结论的关键证据时才检索源码；不要默认调用 list_files 浏览仓库。
3. 每个假设最多执行 1 次 search_code 和 2 次 read_file_range；优先复用已有结果。
4. 核心证据足够后立即停止读取。证据不完整时使用 PARTIAL/INSUFFICIENT 和 LOW/MEDIUM confidence，
   不要为了获得完整上下文持续检索。
5. reviewBudget.phase=CONVERGE 时不得新增风险假设。
6. reviewBudget.mustSubmit=true 时，下一步必须调用 submit_review，不得再调用证据工具。
7. 最迟在第 9 个模型决策回合调用 submit_review，剩余回合只用于修正 Review Card schema。
8. 没有可信问题时也必须提交 overallLevel=LOW、findings=[] 的 Review Card。

完成判断后必须且只能成功调用一次 submit_review；不要在最终文本中重复源码或完整 Review。"""


def review_instructions(case: dict[str, Any]) -> str:
    custom = str(case.get("reviewInstructions") or "").strip()
    return "\n\n".join(item for item in (custom, DEFAULT_REVIEW_INSTRUCTIONS) if item)


def review_input(case: dict[str, Any]) -> str:
    if str(case.get("diffMode") or "INLINE").upper() == "TOOL_PAGED":
        diff_section = "Diff is too large for the initial prompt. Use read_diff_range by changed file."
    else:
        diff_section = f"Diff:\n{case['diff']}"
    return (
        f"Case id: {case['id']}\n"
        f"Title: {case.get('title') or '-'}\n"
        f"Base ref: {case.get('baseRef') or '-'}\n"
        f"Commit sha: {case.get('commitSha') or '-'}\n"
        f"Changed files: {case['changedFiles']}\n\n"
        f"Existing bounded context (baseline and Agent receive the same value):\n"
        f"{case.get('baselineContext') or '-'}\n\n"
        f"{diff_section}"
    )


def baseline_system_prompt(case: dict[str, Any]) -> str:
    return (
        review_instructions(case)
        + "\n\n只返回一个 JSON 对象，不要 Markdown 或代码围栏。字段为 summary、overallLevel、findings。"
    )


def agent_system_prompt(case: dict[str, Any]) -> str:
    return review_instructions(case) + "\n\n" + AGENT_TOOL_INSTRUCTIONS
