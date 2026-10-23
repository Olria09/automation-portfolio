# LCARS Chief Engineer — Linux System Check

A small, local-first Linux diagnostic tool with an optional manual AI-assisted explanation. It gathers a few read-only system checks, classifies results, and saves reports locally. It does not call an AI API or apply repairs.

## Safety and privacy

- The program runs only exact commands from a short allowlist. Commands suggested in diagnose mode are validated against that list; anything else is rejected without execution.
- Commands run without a shell, have an 8-second timeout, and return capped output.
- The report can contain device names, network addresses, service names, and log text. Review and redact it before sharing with an AI assistant or publishing it.
- Generated JSON and Markdown reports are kept in the ignored `reports/` directory.
- The program never runs repair commands. Review any suggested fix before running it yourself.

## Requirements

- Linux
- Python 3.10+
- Optional: `rich` for colored Markdown rendering
- System utilities such as `free`, `df`, `uname`, `systemctl`, and `ip`; unavailable checks are reported.

Install the optional display dependency:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows is not supported; this tool checks Linux.
python -m pip install -r requirements.txt
```

## Run

Run the standard morning check:

```bash
python chief_engineer.py
```

Investigate a specific issue with approved read-only checks:

```bash
python chief_engineer.py diagnose
```

Both modes print a prompt that can be copied to an AI assistant manually. Review it first for private information. Paste the assistant response back into the terminal to create a local Markdown report, or end input to skip saving that response.

## Command allowlist

The current allowlist contains `free -h`, `df -h`, `uname -r`, a summary of failed systemd services, `ip -br addr`, `lspci -nnk`, and a short system error journal query. The morning check runs only the first five. The diagnose mode accepts only exact allowlisted command and argument combinations.
