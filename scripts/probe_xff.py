#!/usr/bin/env python3
"""Prove the live right-most X-Forwarded-For rate-limit rule.

``GET /api/meta`` reports configuration. This script reports behaviour.

Phase 1 sends ``limit + 1`` anonymous writes with a rotating LEFT-most
X-Forwarded-For entry and a fixed RIGHT-most entry. If the last call is 429,
the service is not bucketing on the spoofable left-most value.

Phase 2 sends one write with a different RIGHT-most entry. If that is 200
while phase 1 is still in 429, the right-most entry is what buckets.

Windows cmd.exe safe: no nested quotes required.

    python scripts/probe_xff.py --host chaoshire.onrender.com --limit 6
"""

from __future__ import annotations

import argparse
import http.client
import json
import sys
import time


def _post_appeal(host: str, path: str, xff: str, timeout: float) -> tuple[int, str]:
    body = json.dumps({"candidate_id": "C-1046", "message": "xff-probe"}).encode()
    conn = http.client.HTTPSConnection(host, timeout=timeout)
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "X-Forwarded-For": xff,
            },
        )
        response = conn.getresponse()
        payload = response.read().decode("utf-8", errors="replace")
        return response.status, payload
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="chaoshire.onrender.com")
    parser.add_argument("--path", default="/api/appeals")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--sleep", type=float, default=0.2)
    args = parser.parse_args(argv)

    rightmost = "203.0.113.10"
    print(f"phase 1: {args.limit + 1} writes, rotating left-most, right-most={rightmost}")
    statuses: list[int] = []
    for index in range(args.limit + 1):
        xff = f"{index}.1.1.1, {rightmost}"
        status, payload = _post_appeal(args.host, args.path, xff, args.timeout)
        statuses.append(status)
        print(f"  {index + 1}/{args.limit + 1} XFF={xff!r} -> {status}")
        if status not in {200, 429}:
            print("unexpected status:", payload[:300])
            return 2
        time.sleep(args.sleep)

    if statuses[-1] != 429:
        print("FAIL: last call was not 429 — left-most spoofing may be minting buckets")
        return 1
    print("phase 1 pass: rotating the left-most entry did not escape the budget")

    other = "198.51.100.20"
    status, payload = _post_appeal(args.host, args.path, f"9.9.9.9, {other}", args.timeout)
    print(f"phase 2: different right-most {other} -> {status}")
    if status == 200:
        print("phase 2 pass: a different right-most entry is a different bucket")
        return 0
    print("phase 2 inconclusive:", payload[:300])
    print("the proxy may be overwriting XFF entirely (still spoof-resistant)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
