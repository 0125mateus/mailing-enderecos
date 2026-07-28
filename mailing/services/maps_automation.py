from collections.abc import Callable
from typing import Any

from django.conf import settings
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .playwright_browser import get_or_create_page, get_storage_state_path, maps_browser_session

SEARCH_INPUT_XPATH = '//*[@id="searchPanel"]/div/div/div[1]/div[2]/div[1]/div/div[1]/input'
LEGEND_CLICK_XPATH = '//*[@id="legendPanel"]/div/div/div[1]/div[4]/div/span/span/span'


def _click_legend_panel(page) -> None:
    legend_xpath = getattr(settings, "GOOGLE_MAPS_LEGEND_XPATH", LEGEND_CLICK_XPATH)
    timeout_ms = getattr(settings, "PLAYWRIGHT_LEGEND_TIMEOUT_MS", 60000)

    legend_item = page.locator(f"xpath={legend_xpath}")
    legend_item.wait_for(state="visible", timeout=timeout_ms)
    legend_item.click(timeout=15000)
    page.wait_for_timeout(500)


def search_addresses_on_map(
    addresses: list[str],
    *,
    on_progress: Callable[[int, int, str], None] | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if not addresses:
        raise ValueError("Nenhum endereço informado para pesquisa.")

    if not get_storage_state_path() and settings.PLAYWRIGHT_REQUIRE_AUTH:
        raise ValueError(
            "Sessão do Google não configurada. "
            "Execute 'python manage.py salvar_sessao_google' localmente e configure "
            "PLAYWRIGHT_STORAGE_STATE_JSON no Render com o conteúdo do google-auth.json."
        )

    map_url = settings.GOOGLE_MAPS_URL
    headless = settings.PLAYWRIGHT_HEADLESS
    delay_ms = settings.PLAYWRIGHT_SEARCH_DELAY_MS

    processed: list[dict[str, Any]] = []
    cancelled = False

    with sync_playwright() as playwright:
        try:
            with maps_browser_session(playwright, headless=headless) as context:
                page = get_or_create_page(context)

                try:
                    page.goto(map_url, wait_until="domcontentloaded", timeout=90000)
                    page.wait_for_selector(
                        f"xpath={SEARCH_INPUT_XPATH}",
                        state="visible",
                        timeout=90000,
                    )
                except PlaywrightTimeoutError as exc:
                    raise ValueError(
                        "Não foi possível abrir o Google My Maps ou localizar o campo de busca. "
                        "Verifique a sessão Google (google-auth.json) e se o mapa está acessível."
                    ) from exc

                try:
                    _click_legend_panel(page)
                except PlaywrightTimeoutError as exc:
                    raise ValueError(
                        "Não foi possível clicar no item da legenda do mapa. "
                        "Verifique se o painel legendPanel carregou corretamente."
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
                        raise ValueError(
                            f"Falha ao pesquisar o endereço {index}/{total}: {address}"
                        ) from exc
        except RuntimeError as exc:
            raise ValueError(str(exc)) from exc

    return {
        "total": len(addresses),
        "processados": len(processed),
        "cancelado": cancelled,
        "resultados": processed,
    }
