"""Collect a small set of read-only Linux diagnostics."""

from __future__ import annotations

import shutil
import subprocess


ALLOWED_COMMANDS: dict[str, tuple[str, ...]] = {
    "Memory": ("free", "-h"),
    "Disk": ("df", "-h"),
    "Kernel": ("uname", "-r"),
    "Failed services": ("systemctl", "--failed", "--no-legend", "--no-pager"),
    "Network interfaces": ("ip", "-br", "addr"),
    "GPU devices": ("lspci", "-nnk"),
    "Recent system errors": ("journalctl", "-p", "3", "-n", "20", "--no-pager"),
}
COMMAND_TITLES = {command: title for title, command in ALLOWED_COMMANDS.items()}


def _run_command(command: list[str] | tuple[str, ...], timeout: int = 8) -> dict:
    """Run only a predefined read-only command, without a shell or user arguments."""
    normalized = tuple(command)
    title = COMMAND_TITLES.get(normalized)
    if title is None:
        return {
            "title": "Blocked command",
            "command": " ".join(str(part) for part in command),
            "output": "",
            "error": "This command is not on the approved read-only list and was not executed.",
            "success": False,
            "exit_code": None,
        }

    if shutil.which(normalized[0]) is None:
        return {
            "title": title,
            "command": " ".join(normalized),
            "output": "",
            "error": f"Required command is not installed: {normalized[0]}",
            "success": False,
            "exit_code": None,
        }

    try:
        result = subprocess.run(
            list(normalized),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "title": title,
            "command": " ".join(normalized),
            "output": result.stdout[:8000],
            "error": result.stderr[:4000],
            "success": result.returncode == 0,
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "title": title,
            "command": " ".join(normalized),
            "output": "",
            "error": f"Command timed out after {timeout} seconds.",
            "success": False,
            "exit_code": None,
        }
    except OSError as exc:
        return {
            "title": title,
            "command": " ".join(normalized),
            "output": "",
            "error": str(exc),
            "success": False,
            "exit_code": None,
        }


def run_all_diagnostics() -> list[dict]:
    commands = [
        ALLOWED_COMMANDS["Memory"],
        ALLOWED_COMMANDS["Disk"],
        ALLOWED_COMMANDS["Kernel"],
        ALLOWED_COMMANDS["Failed services"],
        ALLOWED_COMMANDS["Network interfaces"],
    ]
    return [_run_command(command) for command in commands]


def validate_suggested_commands(value: object) -> list[list[str]]:
    """Accept only a short list of exact allowlisted commands from the AI."""
    if not isinstance(value, list) or not 1 <= len(value) <= 4:
        raise ValueError("Provide a list of 1 to 4 approved commands.")
    commands: list[list[str]] = []
    for item in value:
        if not isinstance(item, list) or not item or not all(isinstance(part, str) for part in item):
            raise ValueError("Each command must be a list of text arguments.")
        if tuple(item) not in COMMAND_TITLES:
            raise ValueError(f"Command is not approved and will not run: {' '.join(item)}")
        commands.append(item)
    if len({tuple(command) for command in commands}) != len(commands):
        raise ValueError("Duplicate commands are not needed.")
    return commands
