import os
from pathlib import Path
from typing import Any

from django.conf import settings
from playwright.sync_api import BrowserContext, Playwright

STEALTH_ARGS = (
    "--disable-blink-features=AutomationControlled",
)

STEALTH_IGNORE_DEFAULT_ARGS = ("--enable-automation",)


def get_user_data_dir() -> Path:
    configured = getattr(settings, "PLAYWRIGHT_USER_DATA_DIR", "") or os.environ.get(
        "PLAYWRIGHT_USER_DATA_DIR", ""
    )
    if configured:
        return Path(configured).resolve()
    return (Path(settings.BASE_DIR) / "playwright" / "chrome-profile").resolve()


def get_browser_channel() -> str:
    return getattr(settings, "PLAYWRIGHT_BROWSER_CHANNEL", "") or os.environ.get(
        "PLAYWRIGHT_BROWSER_CHANNEL", "chrome"
    )


def get_storage_state_path() -> Path | None:
    path = getattr(settings, "PLAYWRIGHT_STORAGE_STATE", "") or os.environ.get(
        "PLAYWRIGHT_STORAGE_STATE", ""
    )
    if path and Path(path).is_file():
        return Path(path).resolve()
    return None


def _persistent_launch_kwargs(*, headless: bool) -> dict[str, Any]:
    profile_dir = get_user_data_dir()
    profile_dir.mkdir(parents=True, exist_ok=True)

    kwargs: dict[str, Any] = {
        "user_data_dir": str(profile_dir),
        "headless": headless,
        "args": list(STEALTH_ARGS),
        "ignore_default_args": list(STEALTH_IGNORE_DEFAULT_ARGS),
        "locale": "pt-BR",
        "viewport": {"width": 1366, "height": 768},
    }

    channel = get_browser_channel()
    if channel:
        kwargs["channel"] = channel

    return kwargs


def open_maps_context(
    playwright: Playwright,
    *,
    headless: bool,
    prefer_persistent: bool = True,
) -> BrowserContext:
    if prefer_persistent:
        try:
            return playwright.chromium.launch_persistent_context(
                **_persistent_launch_kwargs(headless=headless)
            )
        except Exception as exc:
            channel = get_browser_channel()
            if channel:
                raise RuntimeError(
                    f"Não foi possível abrir o Google Chrome (channel={channel}). "
                    "Instale o Google Chrome ou defina PLAYWRIGHT_BROWSER_CHANNEL=msedge."
                ) from exc
            raise

    launch_kwargs: dict[str, Any] = {
        "headless": headless,
        "args": list(STEALTH_ARGS),
        "ignore_default_args": list(STEALTH_IGNORE_DEFAULT_ARGS),
    }
    channel = get_browser_channel()
    if channel:
        launch_kwargs["channel"] = channel

    browser = playwright.chromium.launch(**launch_kwargs)
    context_kwargs: dict[str, Any] = {
        "locale": "pt-BR",
        "viewport": {"width": 1366, "height": 768},
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
