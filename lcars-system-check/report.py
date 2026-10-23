"""Turn diagnostic results into readable Markdown reports."""

from datetime import datetime, timezone


def classify_result(result: dict) -> str:
    if result["title"] == "Failed services" and result["output"].strip():
        return "red"
    if not result["success"] or result["error"]:
        return "yellow"
    return "green"


def classify_all(results: list[dict]) -> list[dict]:
    for result in results:
        result["status"] = classify_result(result)
    return results


def overall_status(results: list[dict]) -> str:
    if any(result["status"] == "red" for result in results):
        return "red"
    if any(result["status"] == "yellow" for result in results):
        return "yellow"
    return "green"


def build_markdown(results: list[dict]) -> str:
    emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
    status = overall_status(results)
    lines = [
        "# LCARS Chief Engineer — System Report",
        "",
        f"## Overall status: {emoji[status]} {status.upper()}",
        "",
        "*This summarizes whether checks ran and whether systemd reports failed units; it is not a full health assessment.*",
        "",
        "| Check | Status | Command |",
        "|---|---|---|",
    ]
    for result in results:
        lines.append(
            f"| {result['title']} | {emoji[result['status']]} {result['status'].upper()} | `"
            f"{result['command']}` |"
        )
    lines.extend(["", "## Diagnostic details", ""])
    for result in results:
        if result["output"] or result["error"]:
            lines.extend([
                f"### {result['title']}",
                f"Command: `{result['command']}`",
                "",
                "```text",
                (result["output"] or result["error"]).rstrip(),
                "```",
                "",
            ])
    return "\n".join(lines)


def build_final_report(ai_response: str, results: list[dict]) -> str:
    status = overall_status(results)
    emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴"}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return "\n".join([
        "# LCARS Chief Engineer — Engineering Log",
        "",
        f"**Generated:** {stamp}  ",
        f"**System status:** {emoji[status]} {status.upper()}",
        "",
        ai_response.strip(),
        "",
        "---",
        "*Review diagnostic output before sharing; it can include device and network details.*",
        "",
    ])
