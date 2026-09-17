"""并发负载冒烟：对 API 服务打 health + ask，输出时延分位与成功率。

确认 Hugging Face Space 免费档在评审访问量（1–3 并发）下扛得住。

用法：:

    python scripts/load_test.py --base-url https://username-huidu-xingyun.hf.space
    python scripts/load_test.py --health 30 --asks 6 --concurrency 3
"""

from __future__ import annotations

import argparse
import concurrent.futures
import statistics
import sys
import time

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _quantile(values: list[float], q: float) -> float:
    data = sorted(values)
    if not data:
        return 0.0
    idx = min(len(data) - 1, int(q * len(data)))
    return data[idx]


def main() -> int:
    ap = argparse.ArgumentParser(description="并发负载冒烟")
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--health", type=int, default=20, help="health 请求数")
    ap.add_argument("--asks", type=int, default=4, help="ask 请求数")
    ap.add_argument("--concurrency", type=int, default=3, help="并发度（对齐评审访问量）")
    ap.add_argument("--query", default="慈悲与教育是什么关系？")
    args = ap.parse_args()

    # health 并发（轻量，验并发与单例复用）
    health_lat, health_ok = [], 0

    def hit_health(_):
        start = time.time()
        r = requests.get(f"{args.base_url}/api/v1/health", timeout=120)
        return time.time() - start, r.status_code

    with concurrent.futures.ThreadPoolExecutor(args.concurrency) as ex:
        for lat, code in ex.map(hit_health, range(args.health)):
            health_lat.append(lat)
            health_ok += code == 200

    print(
        f"health  n={args.health} 成功={health_ok} "
        f"p50={statistics.median(health_lat) if health_lat else 0:.2f}s "
        f"p95={_quantile(health_lat, .95):.2f}s"
    )

    # ask 并发（LLM 推理慢，少量）
    ask_lat, ask_ok = [], 0

    def hit_ask(_):
        start = time.time()
        r = requests.post(
            f"{args.base_url}/api/v1/ask",
            json={"query": args.query, "history": []},
            timeout=120,
        )
        return time.time() - start, r.status_code

    with concurrent.futures.ThreadPoolExecutor(args.concurrency) as ex:
        for lat, code in ex.map(hit_ask, range(args.asks)):
            ask_lat.append(lat)
            ask_ok += code == 200

    print(
        f"ask     n={args.asks} 成功={ask_ok} "
        f"p50={statistics.median(ask_lat) if ask_lat else 0:.2f}s "
        f"p95={_quantile(ask_lat, .95):.2f}s"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())