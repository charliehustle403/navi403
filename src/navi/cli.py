"""Thin CLI client (build spec §6.8): ``navi ask "..."`` and ``navi run <id>``.

Talks to the REST API over HTTP (default http://127.0.0.1:8000; override with NAVI_API_URL), so it
is a true client — start the server first (``uv run uvicorn navi.api:app``). The httpx client is
injectable so tests can drive it against the in-process app with no network.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import TextIO

import httpx


def _base_url() -> str:
    return os.getenv("NAVI_API_URL", "http://127.0.0.1:8000")


def _client(client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(base_url=_base_url(), timeout=120.0)


def cmd_ask(text: str, *, client: httpx.Client | None = None, out: TextIO | None = None) -> int:
    stream = out or sys.stdout
    resp = _client(client).post("/ask", json={"text": text})
    resp.raise_for_status()
    data = resp.json()
    print(data["answer"], file=stream)
    if data.get("evidence"):
        print("\nSources:", file=stream)
        for source in data["evidence"]:
            print(f"  - {source}", file=stream)
    flags = " TRUNCATED" if data.get("truncated") else ""
    print(
        f"\n[route={data['route']} cost=${data['cost_usd']:.4f} run={data['run_id']}{flags}]",
        file=stream,
    )
    return 0


def cmd_run(run_id: str, *, client: httpx.Client | None = None, out: TextIO | None = None) -> int:
    stream = out or sys.stdout
    resp = _client(client).get(f"/runs/{run_id}")
    if resp.status_code == 404:
        print(f"run {run_id} not found", file=sys.stderr)
        return 1
    resp.raise_for_status()
    data = resp.json()
    print(
        f"run {data['run_id']}  status={data['status']}  route={data['route']}  "
        f"cost=${data['cost_usd']:.4f}",
        file=stream,
    )
    for event in data["events"]:
        bits = [event["event_type"]]
        for key in ("route", "tool_name", "verdict"):
            if event.get(key):
                bits.append(f"{key}={event[key]}")
        if event.get("tokens_in") is not None:
            bits.append(f"tok={event['tokens_in']}/{event['tokens_out']}")
        print("  " + " ".join(bits), file=stream)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="navi", description="Navi CLI client")
    sub = parser.add_subparsers(dest="command", required=True)
    ask_p = sub.add_parser("ask", help="ask Navi a question")
    ask_p.add_argument("text", help="the request text")
    run_p = sub.add_parser("run", help="show a run's trace")
    run_p.add_argument("run_id", help="the run id from a previous ask")
    args = parser.parse_args(argv)

    try:
        if args.command == "ask":
            return cmd_ask(args.text)
        return cmd_run(args.run_id)
    except httpx.HTTPError as exc:
        print(f"error: could not reach Navi API at {_base_url()}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
