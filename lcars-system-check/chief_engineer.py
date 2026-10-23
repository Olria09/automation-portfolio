#!/usr/bin/env python3
"""Local Linux diagnostics with optional manual AI-assisted explanation."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from diagnostics import ALLOWED_COMMANDS, _run_command, run_all_diagnostics, validate_suggested_commands
from prompts import COMMANDS_PROMPT, SYSTEM_PROMPT, analysis_prompt
from report import build_final_report, build_markdown, classify_all
from storage import save_report


def read_multiline(prompt: str) -> str:
    print(f"\n{prompt}\nEnter FIN on a line by itself when done.\n")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "FIN":
            break
        lines.append(line)
    return "\n".join(lines).strip()


def print_header() -> None:
    print("=" * 56)
    print("LCARS Chief Engineer — Linux System Check")
    print("=" * 56)


def finish_report(response: str, results: list[dict]) -> None:
    final_report = build_final_report(response, results)
    try:
        from rich.console import Console
        from rich.markdown import Markdown
        Console().print(Markdown(final_report))
    except ImportError:
        print(final_report)
    path = save_report(final_report, Path("reports/markdown"), "md")
    print(f"\nLocal report saved to: {path}")


def morning() -> int:
    print_header()
    results = classify_all(run_all_diagnostics())
    json_path = save_report(results, Path("reports/json"), "json")
    diagnostic_report = build_markdown(results)
    print(f"Diagnostic data saved locally to: {json_path}\n")
    print("Copy this prompt to your AI assistant only after reviewing it for private details:\n")
    print(f"{SYSTEM_PROMPT}\n\n{diagnostic_report}")
    response = read_multiline("Paste the assistant's explanation (or press Ctrl-D to skip)")
    if response:
        finish_report(response, results)
    return 0


def diagnose() -> int:
    problem = input("Describe the Linux issue (avoid passwords or private data): ").strip()
    print(f"\n{COMMANDS_PROMPT}\n\nProblem: {problem}")
    command_text = read_multiline("Paste the suggested command list")
    try:
        suggested = validate_suggested_commands(ast.literal_eval(command_text))
    except (SyntaxError, ValueError, TypeError) as exc:
        print(f"No commands were run: {exc}", file=sys.stderr)
        return 2

    results = classify_all([_run_command(command) for command in suggested])
    print("\nRead-only command results:\n")
    print(build_markdown(results))
    prompt = analysis_prompt(problem, results)
    print("\nReview and redact this prompt before sharing it with an AI assistant:\n")
    print(prompt)
    response = read_multiline("Paste the assistant's explanation")
    if response:
        finish_report(response, results)
    return 0


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "diagnose":
        return diagnose()
    if len(sys.argv) > 1 and sys.argv[1] in {"-h", "--help"}:
        print("Usage: python chief_engineer.py [diagnose]\nRun a local morning check, or diagnose a specific issue.")
        return 0
    return morning()


if __name__ == "__main__":
    raise SystemExit(main())
