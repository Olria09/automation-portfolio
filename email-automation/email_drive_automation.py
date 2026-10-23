import os
import io
import json
import base64
import imaplib
import email
import re
from typing import List, Tuple
from email.message import Message
from email.header import decode_header
from email.utils import parseaddr
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

EMAIL_ADDRESS = os.getenv("GMAIL_EMAIL", "").strip()
APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").strip()
FOLDER_TEXT = os.getenv("DRIVE_TEXT_FOLDER_ID", "").strip()
FOLDER_ATTACH = os.getenv("DRIVE_ATTACHMENTS_FOLDER_ID", "").strip()
ALLOWED_SENDERS = {
    address.strip().lower()
    for address in os.getenv("ALLOWED_SENDERS", "").split(",")
    if address.strip()
}
MAILBOX_LABEL = os.getenv("GMAIL_MAILBOX_LABEL", "INBOX").strip() or "INBOX"

IGNORED_SUBJECTS = [
    "Delivery Status Notification (Failure)",
    "Mail delivery failed",
    "Undeliverable"
]
class EmailGDriveAutomation:
    def __init__(self, email_address: str, app_password: str):
        self.email_address = email_address
        self.app_password = app_password
        self.mail = None
        self.drive_service = None

    def authenticate_google_services(self):
        SCOPES = ['https://www.googleapis.com/auth/drive']
        creds = None
        script_dir = os.path.dirname(os.path.abspath(__file__))
        token_path = os.path.join(script_dir, 'token.json')
        credentials_path = os.path.join(script_dir, 'credentials.json')

        if not os.path.exists(credentials_path):
            raise FileNotFoundError(f"No se encontró el archivo de credenciales en: {credentials_path}")

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, 'w', encoding='utf-8') as token:
                token.write(creds.to_json())
            try:
                os.chmod(token_path, 0o600)
            except OSError:
                pass  # File permissions vary by operating system.

        self.drive_service = build('drive', 'v3', credentials=creds)

    def connect_to_gmail(self) -> bool:
        try:
            self.mail = imaplib.IMAP4_SSL("imap.gmail.com")
            self.mail.login(self.email_address, self.app_password)
            return True
        except Exception as e:
            print(f"Error conectando a Gmail: {e}")
            return False

    def disconnect_from_gmail(self):
        try:
            if self.mail:
                try:
                    self.mail.close()
                except:
                    pass
                self.mail.logout()
        except:
            pass

    def _subject_is_ok(self, subject: str) -> bool:
        return not any(ignored in subject for ignored in IGNORED_SUBJECTS)

    def _sender_is_allowed(self, from_header: str) -> bool:
        addr = parseaddr(from_header)[1].lower()
        return addr in {s.lower() for s in ALLOWED_SENDERS}

    def process_unread_emails(self, batch_size: int = None) -> List[Tuple[str, Message]]:
        if not self.connect_to_gmail():
            return []
        try:
            # Select the mailbox or label configured for this run.
            self.mail.select(MAILBOX_LABEL)
            _, search_data = self.mail.search(None, 'UNSEEN')
            email_numbers = search_data[0].split()
            if batch_size:
                email_numbers = email_numbers[:batch_size]
            processed = []
            for num in email_numbers:
                _, data = self.mail.fetch(num, '(RFC822)')
                raw_email = data[0][1]
                msg = email.message_from_bytes(raw_email)

                subject = msg.get("Subject", "")
                from_hdr = msg.get("From", "")

                # Filtrado por remitentes permitidos y subjects válidos
                if not self._sender_is_allowed(from_hdr):
                    continue
                if not self._subject_is_ok(subject):
                    continue

                processed.append((num.decode('utf-8'), msg))
            return processed
        except Exception as e:
            print(f"Error leyendo correos: {e}")
            return []
        finally:
            self.disconnect_from_gmail()

    def _extract_attachments(self, msg: Message) -> List[Tuple[str, bytes, str]]:
        attachments = []
        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue
            filename = part.get_filename()
            if filename:
                content = part.get_payload(decode=True)
                mime = part.get_content_type()
                attachments.append((filename, content, mime))
        return attachments

    def _extract_body(self, msg: Message) -> str:
        try:
            if msg.is_multipart():
                # Preferimos text/plain
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        return part.get_payload(decode=True).decode("utf-8", errors="replace")
                # Fallback a primer parte decodificable
                for part in msg.walk():
                    try:
                        return part.get_payload(decode=True).decode("utf-8", errors="replace")
                    except:
                        continue
                return "[Sin cuerpo legible]"
            else:
                return msg.get_payload(decode=True).decode("utf-8", errors="replace")
        except Exception as e:
            return f"[Error leyendo cuerpo del mensaje: {e}]"

    def save_emails_to_drive(self, messages: List[Tuple[str, Message]]):
        if not self.drive_service:
            self.authenticate_google_services()

        for msg_id, message in messages:
            try:
                from_addr = message.get("From", "")
                parsed_email = parseaddr(from_addr)[1]
                encoded_subject = message.get('Subject', 'SinAsunto')
                decoded_parts = decode_header(encoded_subject)
                subject = ""
                for part, charset in decoded_parts:
                    if isinstance(part, bytes):
                        subject += part.decode(charset or 'utf-8', errors='replace')
                    else:
                        subject += str(part)

                # Limpieza del subject y omitir prefijos tipo "Fwd-"
                subject_wo_fwd = re.sub(r'^\s*_?\s*(Fwd|Fw)\s*:\s*', '', subject, flags=re.IGNORECASE)
                clean_subject = re.sub(r'[\/:*?"<>|]', '-', subject_wo_fwd)
                clean_subject = re.sub(r'\s+', ' ', clean_subject)
                clean_subject = clean_subject[:80].strip('-').strip()
                if not clean_subject:
                    clean_subject = "SinAsunto"

                # Extraer cuerpo y adjuntos
                body = self._extract_body(message)
                attachments = self._extract_attachments(message)

                # Subir adjuntos a carpeta de adjuntos
                attachment_links = []
                for name, content, mime in attachments:
                    attach_meta = {
                        'name': f"Attachment_{name}",
                        'parents': [FOLDER_ATTACH]
                    }
                    attach_media = MediaIoBaseUpload(io.BytesIO(content), mimetype=mime)
                    uploaded = self.drive_service.files().create(
                        body=attach_meta, media_body=attach_media, fields='id'
                    ).execute()
                    attach_link = f"https://drive.google.com/file/d/{uploaded.get('id')}/view"
                    attachment_links.append((name, attach_link))

                links_text = "\n".join([f"Attachment: {n} - Link: {l}" for n, l in attachment_links]) or "No attachments"

                # Contenido del .txt
                content = (
                    f"From: {from_addr}\n"
                    f"From (parsed email): {parsed_email}\n"
                    f"Subject: {subject}\n"
                    f"Date: {message.get('Date')}\n\n"
                    f"{links_text}\n\n"
                    f"{body}"
                )

                media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype='text/plain')
                file_metadata = {'name': f"{clean_subject}.txt", 'parents': [FOLDER_TEXT]}
                self.drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                print(f"✔ Guardado: {clean_subject}.txt")
            except Exception as e:
                print(f"Error guardando mensaje {msg_id}: {e}")

if __name__ == "__main__":
    print("Iniciando proceso...")
    required = {
        "GMAIL_EMAIL": EMAIL_ADDRESS,
        "GMAIL_APP_PASSWORD": APP_PASSWORD,
        "DRIVE_TEXT_FOLDER_ID": FOLDER_TEXT,
        "DRIVE_ATTACHMENTS_FOLDER_ID": FOLDER_ATTACH,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise SystemExit("Faltan variables de entorno: " + ", ".join(missing))
    automation = EmailGDriveAutomation(EMAIL_ADDRESS, APP_PASSWORD)
    automation.authenticate_google_services()
    unread_emails = automation.process_unread_emails()
    if unread_emails:
        automation.save_emails_to_drive(unread_emails)
    else:
        print("No hay correos nuevos para procesar.")
