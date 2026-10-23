# Gmail → Google Drive automation

A configurable Python example that filters unread Gmail messages by sender and subject, extracts message text and attachments, and archives them in Google Drive. It uses Gmail IMAP for reading and Google Drive OAuth for uploads.

## Safety and setup

1. Use a dedicated Gmail account or a test mailbox. The script reads unread messages and uploads message contents and attachments to Drive.
2. Create a new Google app password only if your account permits IMAP app passwords. Store it in a local `.env` file; never commit that file. The previously embedded credential from the source copy must be revoked and must not be reused.
3. Create a Google OAuth desktop client, save its client configuration as `credentials.json`, and enable the Drive API. OAuth token data is stored locally in `token.json` and is ignored by Git.
4. Copy `.env.example` to `.env`, then provide your own account, folder IDs and sender allowlist. Use `INBOX` or the exact Gmail label/folder you intend to process.
5. Install dependencies and run the script locally:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .env.example .env  # edit .env with your own values before running
set -a && source .env && set +a
python email_drive_automation.py
```

The code reads environment variables directly. For Windows PowerShell, set them in the session with `$env:NAME = "value"` or use a local dotenv loader that is not committed.

## Before running on a real mailbox

- Confirm the sender allowlist and Gmail label. An empty allowlist rejects all senders.
- Run against a test mailbox first. The script processes unread mail and can upload message bodies and attachments containing personal or business data.
- Keep `credentials.json`, `token.json`, `.env`, exports and logs out of version control. Review Drive sharing permissions for destination folders.
- Check Google's current OAuth verification and Gmail IMAP requirements for your account and organization.

This repository contains no real credentials, personal email addresses, sender allowlists, folder IDs, or OAuth files. The example values are placeholders.
