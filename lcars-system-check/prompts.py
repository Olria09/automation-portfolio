"""Prompts for optional, manual AI-assisted interpretation."""

SYSTEM_PROMPT = """
You are a practical Linux support engineer. Explain the diagnostic report in
clear, calm language for a non-specialist. Summarize the overall state, explain
warnings and errors, and distinguish missing optional software from real faults.
Suggest reversible next steps. Do not suggest destructive commands or ask the
user to share secrets. The user reviews and runs any repair command themselves.
""".strip()

COMMANDS_PROMPT = """
Suggest 1 to 4 relevant read-only diagnostic commands for the reported Linux
problem. Reply only as a Python list of lists of strings. Commands must be
chosen exactly from this allowlist; no other command or argument is permitted:

[["free", "-h"]]
[["df", "-h"]]
[["uname", "-r"]]
[["systemctl", "--failed", "--no-legend", "--no-pager"]]
[["ip", "-br", "addr"]]
[["lspci", "-nnk"]]
[["journalctl", "-p", "3", "-n", "20", "--no-pager"]]
""".strip()


def analysis_prompt(problem: str, results: list[dict]) -> str:
    blocks = []
    for result in results:
        blocks.append(
            f"Check: {result['title']}\nCommand: {result['command']}\n"
            f"Success: {result['success']}\nOutput: {result['output']}\n"
            f"Error: {result['error']}"
        )
    return (
        f"{SYSTEM_PROMPT}\n\nProblem reported:\n{problem}\n\n"
        "Results from approved read-only commands:\n\n" + "\n\n".join(blocks)
    )
