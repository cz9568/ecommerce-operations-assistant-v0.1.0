import argparse
import signal
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

from backend.app.database import SessionLocal
from backend.app.logging_config import configure_logging
from backend.app.services.settings import resolve_runtime_settings
from backend.app.workers import GenerationWorker


def main() -> None:
    parser = argparse.ArgumentParser(description="电商运营助手媒体生成 Worker")
    parser.add_argument("--once", action="store_true", help="处理当前可领取任务后退出")
    parser.add_argument("--scan-only", action="store_true", help="仅扫描超时任务和过期锁后退出")
    parser.add_argument("--max-jobs", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=None)
    args = parser.parse_args()
    with SessionLocal() as session:
        settings = resolve_runtime_settings(session)
    settings.validate_runtime()
    configure_logging(settings.app_debug)
    concurrency = max(1, args.concurrency or settings.job_worker_concurrency)
    stop_event = threading.Event()

    def request_stop(*_args) -> None:
        stop_event.set()

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    worker_name = socket.gethostname()

    if args.scan_only:
        timed_out, recovered = GenerationWorker(
            worker_id=f"{worker_name}-scanner"
        ).scan_timeouts_and_recover_locks()
        print(f"GENERATION_WORKER_SCAN_DONE timed_out={timed_out} recovered={recovered}")
        return

    if args.once:
        total = 0
        workers = [
            GenerationWorker(worker_id=f"{worker_name}-{index + 1}") for index in range(concurrency)
        ]
        while total < args.max_jobs:
            with ThreadPoolExecutor(max_workers=concurrency) as executor:
                results = list(executor.map(lambda item: item.run_once(), workers))
            processed = sum(1 for result in results if result)
            total += processed
            if processed == 0:
                break
        print(f"GENERATION_WORKER_DONE processed={total}")
        return

    workers = [
        GenerationWorker(worker_id=f"{worker_name}-{index + 1}") for index in range(concurrency)
    ]
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(worker.run_forever, stop_event) for worker in workers]
        for future in futures:
            future.result()


if __name__ == "__main__":
    main()
