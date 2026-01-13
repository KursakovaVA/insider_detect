import json
import os
from datetime import datetime, timezone

from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer

HOST = "0.0.0.0"
PORT = int(os.getenv("FTP_PORT", "2121"))

TRAP_ID = os.getenv("TRAP_ID", "ftp-bait-1")

FTP_USER = os.getenv("FTP_USER", "ftp")
FTP_PASS = os.getenv("FTP_PASS", "ftp")

BAIT_DIR = os.getenv("BAIT_DIR", "/bait")
LOG_PATH = os.getenv("LOG_PATH", "/logs/ftp_events.jsonl")

PASV_MIN = int(os.getenv("PASV_MIN", "30000"))
PASV_MAX = int(os.getenv("PASV_MAX", "30010"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def append_event(event: dict) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

class HoneyFTPHandler(FTPHandler):
    def on_connect(self):
        append_event(
            {
                "ts": now_iso(),
                "trap_id": TRAP_ID,
                "source": "ftp",
                "src_ip": self.remote_ip,
                "action": "connect",
                "object": None,
                "user": None,
                "raw": {"event": "connect"},
            }
        )

    def on_login(self, username):
        append_event(
            {
                "ts": now_iso(),
                "trap_id": TRAP_ID,
                "source": "ftp",
                "src_ip": self.remote_ip,
                "action": "login_success",
                "object": None,
                "user": username,
                "raw": {"event": "login_success"},
            }
        )

    def on_login_failed(self, username, password):
        append_event(
            {
                "ts": now_iso(),
                "trap_id": TRAP_ID,
                "source": "ftp",
                "src_ip": self.remote_ip,
                "action": "login_failed",
                "object": None,
                "user": username,
                "raw": {"event": "login_failed", "password": password},
            }
        )

    def on_file_sent(self, file):
        append_event(
            {
                "ts": now_iso(),
                "trap_id": TRAP_ID,
                "source": "ftp",
                "src_ip": self.remote_ip,
                "action": "file_download",
                "object": os.path.basename(file),
                "user": getattr(self, "username", None),
                "raw": {"event": "file_sent", "path": file},
            }
        )

    def on_incomplete_file_sent(self, file):
        append_event(
            {
                "ts": now_iso(),
                "trap_id": TRAP_ID,
                "source": "ftp",
                "src_ip": self.remote_ip,
                "action": "file_download",
                "object": os.path.basename(file),
                "user": getattr(self, "username", None),
                "raw": {"event": "file_sent_incomplete", "path": file},
            }
        )


def main():
    os.makedirs(BAIT_DIR, exist_ok=True)

    authorizer = DummyAuthorizer()

    authorizer.add_user(FTP_USER, FTP_PASS, BAIT_DIR, perm="elr")

    handler = HoneyFTPHandler
    handler.authorizer = authorizer
    handler.banner = "220 FTP Service Ready"

    handler.passive_ports = range(PASV_MIN, PASV_MAX + 1)

    server = FTPServer((HOST, PORT), handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
