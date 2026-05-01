import math
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks
from sqlalchemy import and_, desc, select
from sqlalchemy.orm import Session

from app.integrations.telegram import telegram_send
from app.models.event import Event
from app.models.alert import Alert
from app.models.profile import Profile
from app.rules_engine import RuleSet, evaluate_rules, severity_from_risk
from app.schemas.event import EventIn
from app.utils.formatting import format_recent_events

ALERT_COOLDOWN_MINUTES = 10
RECENT_EVENTS_LIMIT = 10
TAU_SECONDS = 3600.0


def decay_risk(prev: float, dt_seconds: float, tau: float = TAU_SECONDS) -> float:
    """Экспоненциальное затухание накопленного риск-скора.

    Реализует ``R_{n+1} = R_n * exp(-Δt / τ) + w`` без слагаемого ``w``
    (новый вес добавляется снаружи). Отрицательный ``Δt`` (out-of-order
    события) трактуется как ноль — это защита от рассинхронизации
    часов между сенсорами и core.
    """
    if dt_seconds < 0:
        dt_seconds = 0.0
    return float(prev) * math.exp(-float(dt_seconds) / float(tau))


def make_dedup_key(trap_id: str, src_ip: str, severity: str) -> str:
    """Ключ дедупликации для алертов.

    Алерты с одинаковыми ``(trap_id, src_ip, severity)`` в течение
    cooldown-окна агрегируются в один. Разные severity порождают
    разные алерты сознательно: эскалация (medium → high) должна
    быть видна как отдельное событие, а не как «обновление счётчика».
    """
    return f"{trap_id}:{src_ip}:{severity}"


def is_within_cooldown(
    now: datetime, last_updated: datetime, minutes: int
) -> bool:
    """Лежит ли ``last_updated`` в окне ``[now - minutes, now]``.

    Используется для подавления повторных алертов: если уже есть
    open-алерт с тем же dedup_key, обновлённый не позднее
    ``minutes`` минут назад, новый создавать не нужно.
    """
    if minutes <= 0:
        return False
    delta = (now - last_updated).total_seconds()
    return 0 <= delta <= minutes * 60


def ingest_event(
    event: EventIn,
    background_tasks: BackgroundTasks,
    session: Session,
    ruleset: RuleSet,
) -> dict:
    trap_id = event.trap_id or event.host or event.source or "unknown"
    src_ip = event.src_ip

    row = Event(
        id=event.event_id,
        ts=event.ts,
        source=event.source,
        trap_id=trap_id,
        src_ip=src_ip,
        action=event.action,
        object=event.object,
        user=event.user,
        host=event.host,
        raw=event.raw if isinstance(event.raw, dict) else {"raw": event.raw},
    )
    session.add(row)

    profile = session.get(Profile, (trap_id, src_ip))
    if profile is None:
        profile = Profile(trap_id=trap_id, src_ip=src_ip, risk_score=0.0, last_seen=None, state={})
        session.add(profile)

    risk_before = float(profile.risk_score)
    delta, hits = evaluate_rules(event.action, event.object, ruleset, event.ts)

    if isinstance(row.raw, dict):
        row.raw["rule_eval"] = {"delta": float(delta), "matched_rules": hits}

    if profile.last_seen is not None:
        dt = (event.ts - profile.last_seen).total_seconds()
        decayed = decay_risk(profile.risk_score, dt, tau=TAU_SECONDS)
        profile.risk_score = decayed + float(delta)
    else:
        profile.risk_score = float(profile.risk_score) + float(delta)

    profile.last_seen = event.ts
    risk_after = float(profile.risk_score)

    details_payload = {
        "risk_before": risk_before,
        "risk_after": risk_after,
        "delta": float(delta),
        "matched_rules": hits,
        "event": {
            "event_id": str(event.event_id),
            "ts": event.ts.isoformat(),
            "source": event.source,
            "src_ip": event.src_ip,
            "user": event.user,
            "action": event.action,
            "object": event.object,
        },
    }

    session.flush()

    recent_stmt = (
        select(Event)
        .where(and_(Event.trap_id == trap_id, Event.src_ip == src_ip))
        .order_by(desc(Event.ts))
        .limit(RECENT_EVENTS_LIMIT)
    )
    recent_rows = session.execute(recent_stmt).scalars().all()
    details_payload["recent_events"] = [
        {
            "event_id": str(e.id),
            "ts": e.ts.isoformat() if e.ts else None,
            "source": e.source,
            "src_ip": e.src_ip,
            "user": e.user,
            "host": e.host,
            "action": e.action,
            "object": e.object,
        }
        for e in recent_rows
    ]

    created_alert = False
    created_alert_text = None

    if risk_after >= float(ruleset.alert_threshold):
        sev = severity_from_risk(risk_after, ruleset)
        dedup_key = make_dedup_key(trap_id, src_ip, sev)
        cooldown_from = event.ts - timedelta(minutes=ALERT_COOLDOWN_MINUTES)

        stmt = (
            select(Alert)
            .where(
                and_(
                    Alert.dedup_key == dedup_key,
                    Alert.status == "open",
                    Alert.ts_updated >= cooldown_from,
                )
            )
            .order_by(desc(Alert.ts_updated))
            .limit(1)
        )
        existing = session.execute(stmt).scalars().first()

        if existing:
            existing.count += 1
            existing.risk_score = risk_after
            existing.details = {**details_payload, "note": "deduplicated (cooldown window)"}
        else:
            created_alert = True
            created_alert_text = (
                f"🚨 <b>Alert</b>\n"
                f"<b>severity</b>: {sev}\n"
                f"<b>trap</b>: {trap_id}\n"
                f"<b>src_ip</b>: {src_ip}\n"
                f"<b>risk</b>: {risk_after:.2f}\n"
                f"<b>action</b>: {event.action}\n"
                f"<b>object</b>: {event.object or '-'}\n"
            )

            recent_block = format_recent_events(details_payload.get("recent_events", []), max_items=5)
            if recent_block:
                created_alert_text += f"\n<b>recent events</b>:\n{recent_block}"

            session.add(
                Alert(
                    trap_id=trap_id,
                    src_ip=src_ip,
                    severity=sev,
                    status="open",
                    risk_score=risk_after,
                    count=1,
                    dedup_key=dedup_key,
                    details={**details_payload, "note": "threshold exceeded"},
                )
            )

    session.commit()

    if created_alert and created_alert_text:
        background_tasks.add_task(telegram_send, created_alert_text)

    return {
        "status": "ok",
        "event_id": str(row.id),
        "src_ip": src_ip,
        "risk_score": risk_after,
        "delta": float(delta),
        "matched_rules": hits,
    }
