"""Extract normalized listing data from a configurable position in a URL file."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
from pathlib import Path
from typing import Any

from selenium.webdriver.common.by import By

from browser_runtime import BrowserRuntime
from listing_extractor import extract_listing, listing_skip_reason


BASE_DIR = Path(__file__).resolve().parent


def read_links(path: Path) -> list[str]:
    """Read non-empty unique links while preserving their original order."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return list(dict.fromkeys(line.strip() for line in lines if line.strip()))


def append_json_line(path: Path, record: Any) -> None:
    """Append and immediately flush one compact JSON record."""
    path.parent.mkdir(parents=True, exist_ok=True)
    needs_newline = False
    if path.exists() and path.stat().st_size > 0:
        with path.open("rb") as existing:
            existing.seek(-1, 2)
            needs_newline = existing.read(1) not in (b"\n", b"\r")
    with path.open("a", encoding="utf-8", newline="\n") as output:
        if needs_newline:
            output.write("\n")
        json.dump(record, output, ensure_ascii=False, separators=(",", ":"))
        output.write("\n")
        output.flush()


def extract_from_url(
    position: int,
    url: str,
    runtime: BrowserRuntime,
    *,
    retries: int,
) -> tuple[int, dict[str, Any] | None, str | None]:
    """Open one profile for one URL and return its extracted record."""
    if position == 1 or position % 50 == 0:
        print(f"Processing source link position {position}")
    last_error: str | None = None
    driver = None

    try:
        for attempt in range(1, retries + 1):
            if runtime.stop_event.is_set():
                return position, None, "Đã dừng bởi người dùng"
            try:
                driver = runtime.start_driver()
                driver.get(url)
                runtime.wait_for_element(
                    driver,
                    By.CSS_SELECTOR,
                    ".js__pr-short-info, .re__pr-specs-content-item",
                )
                record = extract_listing(driver.page_source)
                if not record.get("listing_url"):
                    record["listing_url"] = url
                skip_reason = listing_skip_reason(record)
                if skip_reason:
                    print(f"[Link {position}] Skipped: {skip_reason}")
                    return position, None, skip_reason
                return position, record, None
            except Exception as exc:
                if runtime.stop_event.is_set():
                    return position, None, "Đã dừng bởi người dùng"
                last_error = f"{type(exc).__name__}: {exc}"
                print(
                    f"[Link {position}] Attempt {attempt}/{retries} failed: "
                    f"{last_error}"
                )
                runtime.close_driver(driver)
                driver = None
                if attempt < retries:
                    runtime.stop_event.wait(2)
    finally:
        runtime.close_driver(driver)

    return position, None, last_error


def crawl_links(
    indexed_links: list[tuple[int, str]],
    output_file: Path,
    *,
    workers: int,
    retries: int,
    launch_delay: float,
) -> tuple[int, int]:
    """Crawl selected links and append each result as soon as it completes."""
    if not indexed_links:
        return 0, 0

    runtime = BrowserRuntime(launch_delay)
    error_file = output_file.with_name(f"{output_file.stem}_errors.json")
    saved_count = 0
    failed_count = 0
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    future_to_item: dict[concurrent.futures.Future, tuple[int, str]] = {}

    try:
        future_to_item = {
            executor.submit(
                extract_from_url,
                position,
                url,
                runtime,
                retries=retries,
            ): (position, url)
            for position, url in indexed_links
        }
        for future in concurrent.futures.as_completed(future_to_item):
            position, url = future_to_item[future]
            try:
                _, record, error = future.result()
            except Exception as exc:
                record = None
                error = f"{type(exc).__name__}: {exc}"

            if record is not None:
                append_json_line(output_file, record)
                saved_count += 1
            else:
                append_json_line(
                    error_file,
                    {"position": position, "url": url, "error": error or "Unknown error"},
                )
                failed_count += 1
    except KeyboardInterrupt:
        print("\nCtrl+C received. Stopping workers and closing all Chrome profiles...")
        runtime.stop()
        for future in future_to_item:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)
    finally:
        runtime.stop()

    return saved_count, failed_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract Batdongsan listing data to JSON Lines"
    )
    parser.add_argument("--input", type=Path, default=BASE_DIR / "linkNhaDat.txt")
    parser.add_argument("--output", type=Path, default=BASE_DIR / "data.json")
    parser.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="1-based position of the first unique link to process",
    )
    parser.add_argument("--limit", type=int, help="Maximum number of links to process")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent browsers")
    parser.add_argument("--retries", type=int, default=3, help="Retries per link")
    parser.add_argument(
        "--launch-delay",
        type=float,
        default=0.3,
        help="Minimum seconds between Chrome profile launches",
    )
    args = parser.parse_args()
    if min(args.start_index, args.workers, args.retries) < 1:
        parser.error("start-index/workers/retries must be positive")
    if args.launch_delay < 0 or (args.limit is not None and args.limit < 1):
        parser.error("launch-delay cannot be negative and limit must be positive")
    return args


def main() -> None:
    args = parse_args()
    print(f"Crawler PID: {os.getpid()}")
    all_links = read_links(args.input)
    selected = list(enumerate(all_links[args.start_index - 1:], start=args.start_index))
    if args.limit is not None:
        selected = selected[:args.limit]
    print(
        f"Loaded {len(all_links)} unique links; processing {len(selected)} "
        f"from position {args.start_index}."
    )

    try:
        saved, failed = crawl_links(
            selected,
            args.output,
            workers=args.workers,
            retries=args.retries,
            launch_delay=args.launch_delay,
        )
    except KeyboardInterrupt:
        print("Emergency stop complete. Previously appended records are preserved.")
        raise SystemExit(130)
    print(f"Done. Appended {saved} records; skipped/failed links: {failed}")


if __name__ == "__main__":
    main()
