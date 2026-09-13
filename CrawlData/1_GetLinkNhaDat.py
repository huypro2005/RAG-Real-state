"""Collect Batdongsan.com.vn listing URLs from search-result pages."""
from __future__ import annotations

import argparse
import concurrent.futures
import os
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By

from browser_runtime import BrowserRuntime


BASE_DIR = Path(__file__).resolve().parent
URL_ROOT = "https://batdongsan.com.vn/"
SEARCH_URL = "https://batdongsan.com.vn/nha-dat-ban-tp-hcm/p{page}"


def is_listing_domain(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return hostname == "batdongsan.com.vn" or hostname.endswith(".batdongsan.com.vn")


def extract_links(html_text: str) -> list[str]:
    soup = BeautifulSoup(html_text, "html.parser")
    links: list[str] = []
    seen: set[str] = set()
    for item in soup.find_all("a", class_="js__product-link-for-product-id"):
        href = item.get("href")
        if not href:
            continue
        url = urljoin(URL_ROOT, href)
        if not is_listing_domain(url) or "lahome" in url.lower() or url in seen:
            continue
        seen.add(url)
        links.append(url)
    return links


def crawl_page(
    page: int,
    runtime: BrowserRuntime,
    *,
    retries: int,
) -> tuple[int, list[str], str | None]:
    url = SEARCH_URL.format(page=page)
    last_error: str | None = None

    for attempt in range(1, retries + 1):
        if runtime.stop_event.is_set():
            return page, [], "Đã dừng bởi người dùng"
        driver = None
        try:
            print(f"[Page {page}] Loading {url}")
            driver = runtime.start_driver()
            driver.get(url)
            runtime.wait_for_element(driver, By.TAG_NAME, "body")
            links = extract_links(driver.page_source)
            print(f"[Page {page}] Found {len(links)} links")
            return page, links, None
        except Exception as exc:
            if runtime.stop_event.is_set():
                return page, [], "Đã dừng bởi người dùng"
            last_error = f"{type(exc).__name__}: {exc}"
            print(f"[Page {page}] Attempt {attempt}/{retries} failed: {last_error}")
            if attempt < retries:
                runtime.stop_event.wait(2)
        finally:
            runtime.close_driver(driver)

    return page, [], last_error


def load_existing_links(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def append_links(path: Path, links: list[str], known_links: set[str]) -> int:
    new_links = [link for link in links if link not in known_links]
    if not new_links:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as output:
        for link in new_links:
            output.write(f"{link}\n")
            known_links.add(link)
        output.flush()
    return len(new_links)


def crawl_pages(
    start_page: int,
    end_page: int,
    output_file: Path,
    *,
    workers: int,
    retries: int,
    launch_delay: float,
) -> tuple[int, int]:
    runtime = BrowserRuntime(launch_delay)
    known_links = load_existing_links(output_file)
    saved_count = 0
    failed_count = 0
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=workers)
    future_to_page: dict[concurrent.futures.Future, int] = {}

    try:
        future_to_page = {
            executor.submit(
                crawl_page,
                page,
                runtime,
                retries=retries,
            ): page
            for page in range(start_page, end_page + 1)
        }
        for future in concurrent.futures.as_completed(future_to_page):
            page = future_to_page[future]
            try:
                _, links, error = future.result()
                if error:
                    failed_count += 1
                    print(f"[Page {page}] Skipped: {error}")
                else:
                    added = append_links(output_file, links, known_links)
                    saved_count += added
                    print(f"[Page {page}] Appended {added} new links")
            except Exception as exc:
                failed_count += 1
                print(f"[Page {page}] Unexpected error: {type(exc).__name__}: {exc}")
    except KeyboardInterrupt:
        print("\nCtrl+C received. Closing all Chrome profiles...")
        runtime.stop()
        for future in future_to_page:
            future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        executor.shutdown(wait=True)
    finally:
        runtime.stop()

    return saved_count, failed_count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect Batdongsan listing links")
    parser.add_argument("--start-page", type=int, default=1, help="First page, inclusive")
    parser.add_argument("--end-page", type=int, default=25, help="Last page, inclusive")
    parser.add_argument("--output", type=Path, default=BASE_DIR / "linkNhaDat.txt")
    parser.add_argument("--workers", type=int, default=6, help="Concurrent browsers")
    parser.add_argument("--retries", type=int, default=3, help="Retries per page")
    parser.add_argument(
        "--launch-delay",
        type=float,
        default=0.3,
        help="Minimum seconds between Chrome profile launches",
    )
    args = parser.parse_args()
    if args.start_page < 1 or args.end_page < args.start_page:
        parser.error("Require 1 <= --start-page <= --end-page")
    if min(args.workers, args.retries) < 1 or args.launch_delay < 0:
        parser.error("workers/retries must be positive; launch-delay cannot be negative")
    return args


def main() -> None:
    args = parse_args()
    print(f"Crawler PID: {os.getpid()}")
    print(f"Crawling pages {args.start_page}..{args.end_page}")
    try:
        saved, failed = crawl_pages(
            args.start_page,
            args.end_page,
            args.output,
            workers=args.workers,
            retries=args.retries,
            launch_delay=args.launch_delay,
        )
    except KeyboardInterrupt:
        print("Emergency stop complete. Previously appended links are preserved.")
        raise SystemExit(130)
    print(f"Done. Appended {saved} new links; failed pages: {failed}")


if __name__ == "__main__":
    main()
