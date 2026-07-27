import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .playwright_browser import get_or_create_page, open_maps_context

SEARCH_INPUT_XPATH = '//*[@id="searchPanel"]/div/div/div[1]/div[2]/div[1]/div/div[1]/input'


def search_addresses_on_map(
    addresses: list[str],
    *,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if not addresses:
        raise ValueError("Nenhum endereço informado para pesquisa.")

    map_url = settings.GOOGLE_MAPS_URL
    headless = settings.PLAYWRIGHT_HEADLESS
    delay_ms = settings.PLAYWRIGHT_SEARCH_DELAY_MS

    processed: list[dict[str, Any]] = []
    cancelled = False

    with sync_playwright() as playwright:
        try:
            context = open_maps_context(playwright, headless=headless)
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc

        page = get_or_create_page(context)

        try:
            page.goto(map_url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_selector(
                f"xpath={SEARCH_INPUT_XPATH}",
                state="visible",
                timeout=90000,
            )
        except PlaywrightTimeoutError as exc:
            context.close()
            raise ValueError(
                "Não foi possível abrir o Google My Maps ou localizar o campo de busca. "
                "Execute 'python manage.py salvar_sessao_google' para autenticar no Google Chrome."
            ) from exc

        search_input = page.locator(f"xpath={SEARCH_INPUT_XPATH}")
        total = len(addresses)

        for index, address in enumerate(addresses, start=1):
            if should_cancel and should_cancel():
                cancelled = True
                break

            if on_progress:
                on_progress(index, total, address)

            try:
                search_input.click(timeout=15000)
                search_input.fill("", timeout=15000)
                search_input.fill(address, timeout=15000)
                search_input.press("Enter")
                page.wait_for_timeout(delay_ms)
                processed.append({"indice": index, "endereco": address, "status": "ok"})
            except PlaywrightTimeoutError as exc:
                processed.append(
                    {
                        "indice": index,
                        "endereco": address,
                        "status": "erro",
                        "mensagem": "Tempo esgotado ao preencher o campo de busca.",
                    }
                )
                context.close()
                raise ValueError(
                    f"Falha ao pesquisar o endereço {index}/{total}: {address}"
                ) from exc

        context.close()

    return {
        "total": len(addresses),
        "processados": len(processed),
        "cancelado": cancelled,
        "resultados": processed,
    }
