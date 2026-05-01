import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse

TRAP_ID = os.getenv("TRAP_ID", "http-bait-1")
LOG_PATH = os.getenv("LOG_PATH", "/logs/http_events.jsonl")
BAIT_DIR = Path(os.getenv("BAIT_DIR", "/bait"))

app = FastAPI()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def append_event(event: dict) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def log_request(req: Request, action: str, obj: str | None = None, user: str | None = None, extra: dict | None = None):
    src_ip = req.client.host if req.client else "unknown"
    ua = req.headers.get("user-agent")
    payload = {
        "ts": now_iso(),
        "trap_id": TRAP_ID,
        "source": "http",
        "src_ip": src_ip,
        "action": action,
        "object": obj,
        "user": user,
        "raw": {
            "method": req.method,
            "path": req.url.path,
            "query": str(req.url.query) if req.url.query else "",
            "user_agent": ua,
            **(extra or {}),
        },
    }
    append_event(payload)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    log_request(request, action="honeypot_hit", obj="/")
    return """
    <html><body>
      <h3>Internal Portal</h3>
      <ul>
        <li><a href="/login">Login</a></li>
        <li><a href="/admin">Admin</a></li>
        <li><a href="/files/">Files</a></li>
      </ul>
    </body></html>
    """

@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    log_request(request, action="honeypot_hit", obj="/login")
    return """
    <html><body>
      <h3>Sign in</h3>
      <form method="post">
        <input name="username" placeholder="username"/><br/>
        <input name="password" placeholder="password" type="password"/><br/>
        <button type="submit">Login</button>
      </form>
    </body></html>
    """

@app.post("/login", response_class=PlainTextResponse)
async def login_post(request: Request, username: str = Form(""), password: str = Form("")):
    log_request(
        request,
        action="login_failed",
        obj="http_login",
        user=username[:128] if username else None,
        extra={"password_len": len(password or "")},
    )
    return PlainTextResponse("Invalid credentials", status_code=401)

@app.get("/admin", response_class=PlainTextResponse)
async def admin(request: Request):
    log_request(request, action="honeypot_hit", obj="/admin", extra={"status": 404})
    return PlainTextResponse("Not found", status_code=404)


@app.get("/files/", response_class=HTMLResponse)
async def files_index(request: Request):
    log_request(request, action="honeypot_hit", obj="/files/")
    items = []
    if BAIT_DIR.exists():
        for p in sorted(BAIT_DIR.iterdir()):
            if p.is_file():
                items.append(f'<li><a href="/files/{p.name}">{p.name}</a></li>')
    return "<html><body><h3>Files</h3><ul>" + "".join(items) + "</ul></body></html>"

@app.get("/files/{filename}", response_class=FileResponse)
async def files_get(request: Request, filename: str):
    path = BAIT_DIR / filename
    if not path.exists() or not path.is_file():
        log_request(request, action="honeypot_hit", obj=f"/files/{filename}", extra={"status": 404})
        return PlainTextResponse("Not found", status_code=404)

    log_request(request, action="file_download", obj=filename)
    return FileResponse(str(path))

@app.get("/{path:path}", response_class=PlainTextResponse)
async def catch_all(request: Request, path: str):
    full = "/" + path
    log_request(request, action="honeypot_hit", obj=full, extra={"status": 404})
    return PlainTextResponse("Not found", status_code=404)