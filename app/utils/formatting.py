from html import escape as html_escape

def _tg(x) -> str:
    if x is None:
        return "-"
    return html_escape(str(x))

def format_recent_events(recent_events: list[dict], max_items: int = 5) -> str:
    if not recent_events:
        return ""

    items = list(recent_events)[:max_items]
    lines: list[str] = []

    for e in items:
        ts = e.get("ts")
        src = e.get("source")
        act = e.get("action")
        obj = e.get("object") or ""
        lines.append(f"• <code>{_tg(ts)}</code> {_tg(src)} {_tg(act)} {_tg(obj)}")

    return "\n".join(lines)
