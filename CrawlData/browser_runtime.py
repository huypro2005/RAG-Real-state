"""Shared undetected-Chromium lifecycle helpers for the crawlers."""
from __future__ import annotations

import filecmp
from pathlib import Path
import re
import shutil
import tempfile
import threading
import time
from typing import TypeAlias

import psutil
import undetected_chromedriver as uc
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.remote.webdriver import WebDriver
from webdriver_manager.chrome import ChromeDriverManager


Driver: TypeAlias = WebDriver


def installed_chrome_major() -> int | None:
    """Return the installed Chrome major version on Windows when available."""
    try:
        import winreg
    except ImportError:
        return None

    registry_locations = (
        (winreg.HKEY_CURRENT_USER, r"Software\Google\Chrome\BLBeacon"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\Google\Chrome\BLBeacon"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Google\Chrome\BLBeacon"),
    )
    for hive, key_path in registry_locations:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                version, _ = winreg.QueryValueEx(key, "version")
            return int(str(version).split(".", 1)[0])
        except (FileNotFoundError, OSError, TypeError, ValueError):
            continue
    return None


def create_chrome_options() -> uc.ChromeOptions:
    """Build a fresh options object for every browser session.

    undetected-chromedriver mutates the supplied options object, so it must not
    be shared between worker threads.
    """
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return options


def resolve_chromedriver(chrome_major: int | None) -> str:
    """Return a ChromeDriver compatible with the installed Chrome.

    ``webdriver-manager`` can reuse an old entry from its metadata cache after
    Chrome auto-updates.  Prefer an already-downloaded driver with the same
    major version, then explicitly request that major from webdriver-manager.
    """
    if chrome_major is None:
        return ChromeDriverManager().install()

    cache_dir = Path.home() / ".wdm" / "drivers" / "chromedriver" / "win64"
    matching_drivers: list[tuple[tuple[int, ...], Path]] = []
    if cache_dir.is_dir():
        for driver_path in cache_dir.glob(f"{chrome_major}.*/*/chromedriver.exe"):
            version_match = re.match(r"^(\d+(?:\.\d+)*)", driver_path.parents[1].name)
            if version_match:
                version = tuple(int(part) for part in version_match.group(1).split("."))
                matching_drivers.append((version, driver_path))
    if matching_drivers:
        return str(max(matching_drivers, key=lambda item: item[0])[1])

    return ChromeDriverManager(driver_version=str(chrome_major)).install()


def prepare_uc_multi_process_driver(
    driver_path: str, chrome_major: int | None
) -> str:
    """Put the matched driver in UC's shared cache for concurrent workers.

    With ``user_multi_procs=True``, undetected-chromedriver deliberately
    selects its own roaming-cache binary and ignores ``driver_executable_path``.
    Keeping exactly one current binary in that cache preserves UC's
    multi-process cleanup behavior without allowing an old driver (for example
    ChromeDriver 151) to be selected after Chrome has updated.
    """
    cache_dir = Path(uc.Patcher.data_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_driver = cache_dir / "undetected_chromedriver.exe"

    # Do not touch a binary being used by another active worker when it already
    # is the exact patched driver selected for this Chrome version.
    try:
        if cache_driver.is_file() and filecmp.cmp(
            driver_path, cache_driver, shallow=False
        ):
            return str(cache_driver)
    except OSError:
        # If the cache cannot be read, copy2 below gives the caller the actual
        # filesystem error instead of silently selecting an unknown version.
        pass

    # BrowserRuntime is constructed before its worker threads start, so this
    # replacement happens before any of those workers can use the cache.
    shutil.copy2(driver_path, cache_driver)
    uc.Patcher(
        executable_path=str(cache_driver),
        version_main=chrome_major,
    ).auto()
    return str(cache_driver)


class BrowserRuntime:
    """Patch ChromeDriver once and control concurrent Chromium sessions."""

    def __init__(self, launch_delay: float) -> None:
        # webdriver-manager resolves/downloads a driver once; UC then patches
        # that exact executable before any worker thread starts.
        self.chrome_major = installed_chrome_major()
        self.driver_path = resolve_chromedriver(self.chrome_major)
        uc.Patcher(
            executable_path=self.driver_path,
            version_main=self.chrome_major,
        ).auto()
        self.driver_path = prepare_uc_multi_process_driver(
            self.driver_path, self.chrome_major
        )
        self.launch_delay = launch_delay
        self.stop_event = threading.Event()
        self._launch_lock = threading.Lock()
        self._drivers_lock = threading.Lock()
        self._next_launch_at = 0.0
        self._temp_root = Path(tempfile.mkdtemp(prefix="bds-crawler-"))
        self._drivers: dict[Driver, tuple[Path, int | None]] = {}

    @staticmethod
    def _remove_temp_dir(path: Path) -> None:
        """Remove a Chrome profile, retrying briefly for Windows file locks."""
        for attempt in range(5):
            try:
                shutil.rmtree(path)
                return
            except FileNotFoundError:
                return
            except OSError:
                if attempt == 4:
                    return
                time.sleep(0.2)

    def _wait_for_launch(self) -> None:
        with self._launch_lock:
            delay = self._next_launch_at - time.monotonic()
            if delay > 0 and self.stop_event.wait(delay):
                raise InterruptedError("Crawler is stopping")
            if self.stop_event.is_set():
                raise InterruptedError("Crawler is stopping")
            self._next_launch_at = time.monotonic() + self.launch_delay

    def start_driver(self) -> Driver:
        self._wait_for_launch()
        profile_dir = Path(tempfile.mkdtemp(prefix="profile-", dir=self._temp_root))
        try:
            driver = uc.Chrome(
                driver_executable_path=self.driver_path,
                options=create_chrome_options(),
                user_data_dir=str(profile_dir),
                use_subprocess=True,
                # The driver is already patched once in __init__. Enabling
                # user_multi_procs reuses the version-matched shared UC cache
                # prepared in __init__, preventing cache growth per worker.
                user_multi_procs=True,
                version_main=self.chrome_major,
            )
        except Exception:
            self._remove_temp_dir(profile_dir)
            raise
        browser_pid = getattr(driver, "browser_pid", None)
        with self._drivers_lock:
            self._drivers[driver] = (profile_dir, browser_pid)
        if self.stop_event.is_set():
            self.close_driver(driver)
            raise InterruptedError("Crawler is stopping")
        return driver

    def wait_for_element(self, driver: Driver, by: str, value: str) -> None:
        """Wait without a deadline until an element is rendered or stopping begins."""
        while not self.stop_event.is_set():
            try:
                driver.find_element(by, value)
                return
            except NoSuchElementException:
                self.stop_event.wait(0.2)
        raise InterruptedError("Crawler is stopping")

    def close_driver(self, driver: Driver | None) -> None:
        if driver is None:
            return
        with self._drivers_lock:
            driver_info = self._drivers.pop(driver, None)
        # stop() and a worker may try to close the same driver concurrently.
        # Only the caller that removed it from the registry owns its cleanup.
        if driver_info is None:
            return
        profile_dir, browser_pid = driver_info
        quit_failed = False
        try:
            driver.quit()
        except Exception:
            quit_failed = True
        finally:
            # UC's destructor calls quit() again; on Windows that can emit a
            # harmless "handle is invalid" error after a clean explicit quit.
            driver.quit = lambda: None  # type: ignore[method-assign]
            self._remove_temp_dir(profile_dir)
            # Explicit PID termination is only a fallback when WebDriver could
            # not shut down its own browser process cleanly.
            if quit_failed and browser_pid is not None:
                try:
                    p = psutil.Process(browser_pid)
                    if p.is_running():
                        p.kill()
                        p.wait(timeout=5)
                except (
                    psutil.NoSuchProcess,
                    psutil.AccessDenied,
                    psutil.TimeoutExpired,
                ):
                    pass

    def stop(self) -> None:
        self.stop_event.set()
        with self._drivers_lock:
            drivers = list(self._drivers)
        for driver in drivers:
            self.close_driver(driver)
        self._remove_temp_dir(self._temp_root)
