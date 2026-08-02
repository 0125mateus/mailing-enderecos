import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from django.conf import settings
from playwright.sync_api import Browser, BrowserContext, Playwright

STEALTH_ARGS = (
    "--disable-blink-features=AutomationControlled",
)

LINUX_ARGS = (
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
)

STEALTH_IGNORE_DEFAULT_ARGS = ("--enable-automation",)


def is_render_runtime() -> bool:
    return bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_HOSTNAME"))


def get_user_data_dir() -> Path:
    configured = getattr(settings, "PLAYWRIGHT_USER_DATA_DIR", "") or os.environ.get(
        "PLAYWRIGHT_USER_DATA_DIR", ""
    )
    if configured:
        return Path(configured).resolve()
    return (Path(settings.BASE_DIR) / "playwright" / "chrome-profile").resolve()


def get_browser_channel() -> str:
    return getattr(settings, "PLAYWRIGHT_BROWSER_CHANNEL", "") or os.environ.get(
        "PLAYWRIGHT_BROWSER_CHANNEL", ""
    )


def get_storage_state_path() -> Path | None:
    path = getattr(settings, "PLAYWRIGHT_STORAGE_STATE", "") or os.environ.get(
        "PLAYWRIGHT_STORAGE_STATE", ""
    )
    if path and Path(path).is_file():
        return Path(path).resolve()
    return None


def _browser_args(*, headless: bool) -> list[str]:
    args = list(STEALTH_ARGS)
    if not headless:
        args.append("--start-maximized")
    if is_render_runtime() or headless:
        args.extend(LINUX_ARGS)
    return args


def _context_display_kwargs(*, headless: bool) -> dict[str, Any]:
    if headless:
        return {"viewport": {"width": 1366, "height": 768}}
    return {"no_viewport": True}


def _should_use_persistent_profile(channel: str) -> bool:
    return bool(channel) and not is_render_runtime()


def _launch_kwargs(*, headless: bool) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "headless": headless,
        "args": _browser_args(headless=headless),
        "ignore_default_args": list(STEALTH_IGNORE_DEFAULT_ARGS),
    }
    channel = get_browser_channel()
    if channel:
        kwargs["channel"] = channel
    return kwargs


def _persistent_launch_kwargs(*, headless: bool) -> dict[str, Any]:
    profile_dir = get_user_data_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)

    kwargs = _launch_kwargs(headless=headless)
    kwargs["user_data_dir"] = str(profile_dir)
    kwargs["locale"] = "pt-BR"
    kwargs.update(_context_display_kwargs(headless=headless))
    return kwargs


@contextmanager
def maps_browser_session(
    playwright: Playwright,
    *,
    headless: bool,
) -> Iterator[BrowserContext]:
    browser: Browser | None = None
    context: BrowserContext | None = None
    storage_state = get_storage_state_path()
    channel = get_browser_channel()
    use_persistent = (
        _should_use_persistent_profile(channel)
        and not storage_state
        and getattr(settings, "PLAYWRIGHT_WAIT_FOR_MANUAL_LOGIN", False)
        and not headless
    )

    if use_persistent:
        context = playwright.chromium.launch_persistent_context(
            **_persistent_launch_kwargs(headless=headless)
        )
    else:
        browser = playwright.chromium.launch(**_launch_kwargs(headless=headless))
        context_kwargs: dict[str, Any] = {
            "locale": "pt-BR",
            **_context_display_kwargs(headless=headless),
        }
        if storage_state:
            context_kwargs["storage_state"] = str(storage_state)
        context = browser.new_context(**context_kwargs)

    try:
        yield context
    finally:
        try:
            if context:
                context.close()
        except Exception:
            pass
        if browser:
            try:
                browser.close()
            except Exception:
                pass


def open_maps_context(
    playwright: Playwright,
    *,
    headless: bool,
    prefer_persistent: bool = True,
) -> BrowserContext:
    channel = get_browser_channel()
    if prefer_persistent and _should_use_persistent_profile(channel):
        return playwright.chromium.launch_persistent_context(
            **_persistent_launch_kwargs(headless=headless)
        )

    browser = playwright.chromium.launch(**_launch_kwargs(headless=headless))
    context_kwargs: dict[str, Any] = {
        "locale": "pt-BR",
        **_context_display_kwargs(headless=headless),
    }
    storage_state = get_storage_state_path()
    if storage_state:
        context_kwargs["storage_state"] = str(storage_state)

    return browser.new_context(**context_kwargs)


def get_or_create_page(context: BrowserContext):
    if context.pages:
        return context.pages[0]
    return context.new_page()


def connect_over_cdp(playwright: Playwright, cdp_url: str) -> BrowserContext:
    browser = playwright.chromium.connect_over_cdp(cdp_url)
    if not browser.contexts:
        raise RuntimeError(
            "Nenhum contexto encontrado no Chrome remoto. "
            "Abra o Chrome com --remote-debugging-port e tente novamente."
        )
    return browser.contexts[0]
