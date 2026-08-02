import os

import re

import time

from collections.abc import Callable

from pathlib import Path

from typing import Any



from django.conf import settings

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from playwright.sync_api import sync_playwright



from .nio_layers import NioLayerIndex, get_search_coordinates, load_layer_index_from_page, load_local_layer_index

from .playwright_browser import get_or_create_page, get_storage_state_path, maps_browser_session



SEARCH_INPUT_XPATH = '//*[@id="searchPanel"]/div/div/div[1]/div[2]/div[1]/div/div[1]/input'

SEARCH_BUTTON_XPATH = '//*[@id="legendPanel"]/div/div/div[1]/div[4]/div'

LEGEND_CLICK_XPATH = '//*[@id="legendPanel"]/div/div/div[1]/div[4]/div/span/span/span'



SEARCH_BUTTON_SELECTORS = (

    SEARCH_BUTTON_XPATH,

    '#legendPanel [aria-label="Search"]',

    '#legendPanel [aria-label="Pesquisar"]',

    '#legendPanel div[role="button"][aria-label="Search"]',

)



SEARCH_SELECTORS = (

    SEARCH_INPUT_XPATH,

    "#searchPanel input[type='text']",

    "#searchPanel input",

    'input[placeholder*="Pesquisar" i]',

    'input[aria-label*="Pesquisar" i]',

    'input[aria-label*="Search" i]',

    'input[aria-label*="My Maps" i]',

)





def _selector_locator(page, selector: str):

    if selector.startswith("/") or selector.startswith("("):

        return page.locator(f"xpath={selector}")

    return page.locator(selector)





def _wait_for_search_input(page, timeout_ms: int = 90000):

    step = max(timeout_ms // max(len(SEARCH_SELECTORS), 1), 8000)

    last_error: PlaywrightTimeoutError | None = None



    for selector in SEARCH_SELECTORS:

        try:

            locator = _selector_locator(page, selector).first

            locator.wait_for(state="visible", timeout=step)

            return locator

        except PlaywrightTimeoutError as exc:

            last_error = exc



    if last_error:

        raise last_error

    raise PlaywrightTimeoutError("Campo de busca não encontrado.")





def _get_search_input(page, timeout_ms: int = 15000):

    configured_xpath = getattr(settings, "GOOGLE_MAPS_SEARCH_INPUT_XPATH", "") or SEARCH_INPUT_XPATH

    locator = page.locator(f"xpath={configured_xpath}").first

    locator.wait_for(state="visible", timeout=timeout_ms)

    return locator





def _grant_clipboard_if_needed(page) -> None:

    context = page.context

    if getattr(context, "_mailing_clipboard_granted", False):

        return



    try:

        context.grant_permissions(["clipboard-read", "clipboard-write"])

        context._mailing_clipboard_granted = True

    except Exception:

        pass





def _set_search_input_value(page, search_input, address: str) -> None:

    search_input.click(timeout=15000)

    search_input.press("Control+a")

    search_input.press("Backspace")



    pasted = False

    if len(address) >= 40:

        try:

            _grant_clipboard_if_needed(page)

            page.evaluate(

                "async (text) => { await navigator.clipboard.writeText(text); }",

                address,

            )

            search_input.press("Control+v")

            pasted = True

        except Exception:

            pasted = False



    if not pasted:

        try:

            search_input.press_sequentially(address, delay=0)

        except Exception:

            search_input.fill(address, timeout=15000)



    page.wait_for_timeout(200)





def _press_enter_on_search(page, search_input) -> None:

    search_input.click(timeout=5000)

    search_input.focus()

    page.wait_for_timeout(200)



    for action in (

        lambda: search_input.press("Enter", timeout=5000),

        lambda: page.keyboard.press("Enter"),

    ):

        try:

            action()

            page.wait_for_timeout(150)

            return

        except Exception:

            continue



    search_input.evaluate(

        """(element) => {

            element.focus();

            const options = {

                key: "Enter",

                code: "Enter",

                keyCode: 13,

                which: 13,

                bubbles: true,

                cancelable: true,

            };

            element.dispatchEvent(new KeyboardEvent("keydown", options));

            element.dispatchEvent(new KeyboardEvent("keypress", options));

            element.dispatchEvent(new KeyboardEvent("keyup", options));

        }"""

    )





def _search_tokens(address: str) -> dict[str, str]:
    city = ""
    city_match = re.search(r",\s*([^,]+?)\s*-\s*([A-Z]{2})\b", address, flags=re.IGNORECASE)
    if city_match:
        city = city_match.group(1).strip().lower()
    elif re.search(r"-\s*([^-]+?)\s*-\s*([A-Z]{2})\b", address, flags=re.IGNORECASE):
        parts = re.search(r"-\s*([^-]+?)\s*-\s*([A-Z]{2})\b", address, flags=re.IGNORECASE)
        if parts:
            city = parts.group(1).strip().lower()

    cep_match = re.search(r"(\d{5})-?(\d{3})", address)
    cep = f"{cep_match.group(1)}{cep_match.group(2)}" if cep_match else ""

    return {"city": city, "cep": cep}





def _score_suggestion_text(text: str, tokens: dict[str, str], original: str) -> int:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    if not normalized:
        return -1

    score = len(normalized)
    if tokens["city"] and tokens["city"] in normalized:
        score += 120
    if tokens["cep"] and tokens["cep"] in normalized.replace("-", ""):
        score += 120
    if "brasil" in normalized or "brazil" in normalized:
        score += 30

    if len(normalized) < max(20, len(original) * 0.35):
        score -= 80

    return score





def _select_best_search_suggestion(page, address: str) -> bool:
    tokens = _search_tokens(address)
    selectors = (
        "#searchPanel [role='option']",
        "#searchPanel [role='listbox'] [role='option']",
        ".pac-item",
        "#searchPanel div[data-value]",
    )

    candidates: list[tuple[Any, str, int]] = []
    for selector in selectors:
        locator = page.locator(selector)
        count = min(locator.count(), 12)
        for index in range(count):
            item = locator.nth(index)
            try:
                if not item.is_visible():
                    continue
                text = re.sub(r"\s+", " ", item.inner_text(timeout=500).strip())
            except Exception:
                continue
            score = _score_suggestion_text(text, tokens, address)
            if score >= 0:
                candidates.append((item, text, score))
        if candidates:
            break

    if not candidates:
        return False

    best_item, best_text, best_score = max(candidates, key=lambda entry: entry[2])
    if tokens["city"] and tokens["city"] not in best_text.lower() and best_score < 80:
        return False

    try:
        best_item.click(timeout=5000)
        page.wait_for_timeout(400)
        return True
    except Exception:
        return False





def _paste_address_in_search(page, address: str, delay_ms: int) -> None:

    if not _is_search_panel_open(page):

        _click_search_button(page)

        _get_search_input(page, timeout_ms=30000)



    search_input = _get_search_input(page)

    _set_search_input_value(page, search_input, address)

    page.wait_for_timeout(900)

    if not _select_best_search_suggestion(page, address):

        _press_enter_on_search(page, search_input)

    page.wait_for_timeout(delay_ms)





def _click_locator(locator) -> None:

    locator.scroll_into_view_if_needed(timeout=10000)

    try:

        locator.click(timeout=10000)

        return

    except Exception:

        pass



    try:

        locator.click(force=True, timeout=10000)

        return

    except Exception:

        pass



    try:

        locator.evaluate(

            """(element) => {

                element.dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));

                element.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));

                element.click();

            }"""

        )

        return

    except Exception:

        pass



    box = locator.bounding_box()

    if box:

        page = locator.page

        page.mouse.click(

            box["x"] + box["width"] / 2,

            box["y"] + box["height"] / 2,

        )





def _is_search_panel_open(page) -> bool:

    try:

        panel = page.locator("#searchPanel")

        if panel.count() == 0 or not panel.first.is_visible():

            return False



        search_input = page.locator("#searchPanel input")

        if search_input.count() == 0:

            return False



        input_el = search_input.first

        return input_el.is_visible() and input_el.is_enabled()

    except Exception:

        return False





def _wait_for_map_ui(page, timeout_ms: int = 90000) -> None:

    page.locator("#legendPanel").wait_for(state="visible", timeout=timeout_ms)

    page.wait_for_timeout(1500)





def _click_search_button(page) -> None:

    timeout_ms = getattr(settings, "PLAYWRIGHT_SEARCH_BUTTON_TIMEOUT_MS", 60000)

    _wait_for_map_ui(page, timeout_ms=timeout_ms)



    configured_xpath = getattr(settings, "GOOGLE_MAPS_SEARCH_BUTTON_XPATH", "") or SEARCH_BUTTON_XPATH

    candidates = (

        page.locator(f"xpath={configured_xpath}").first,

        page.locator("#legendPanel").get_by_role("button", name="Search").first,

        page.locator("#legendPanel").get_by_role("button", name="Pesquisar").first,

        _selector_locator(page, '#legendPanel [aria-label="Search"]').first,

        _selector_locator(page, '#legendPanel [aria-label="Pesquisar"]').first,

    )



    last_error: PlaywrightTimeoutError | None = None

    per_candidate_timeout = max(timeout_ms // max(len(candidates), 1), 10000)



    for locator in candidates:

        try:

            locator.wait_for(state="visible", timeout=per_candidate_timeout)

            _click_locator(locator)

            page.wait_for_timeout(800)

            return

        except PlaywrightTimeoutError as exc:

            last_error = exc



    if last_error:

        raise last_error

    raise PlaywrightTimeoutError("Botão de busca (lupa) não encontrado.")





def _ensure_search_panel_open(page, timeout_ms: int = 90000):

    if not _is_search_panel_open(page):

        _click_search_button(page)



    deadline = time.monotonic() + (timeout_ms / 1000)

    while time.monotonic() < deadline:

        if _is_search_panel_open(page):

            remaining_ms = max(int((deadline - time.monotonic()) * 1000), 5000)

            return _wait_for_search_input(page, timeout_ms=remaining_ms)

        page.wait_for_timeout(500)



    raise PlaywrightTimeoutError("Painel de busca não abriu após clicar na lupa.")





def _try_find_search_input(page, timeout_ms: int = 3000):

    try:

        return _wait_for_search_input(page, timeout_ms=timeout_ms)

    except PlaywrightTimeoutError:

        return None





def _is_google_login_page(page) -> bool:

    url = page.url

    return "accounts.google.com" in url or "ServiceLogin" in url





def _is_my_maps_page(page) -> bool:

    return "google.com/maps/d" in page.url





def _wait_for_manual_google_login(

    page,

    map_url: str,

    *,

    on_status: Callable[[str], None] | None,

    should_cancel: Callable[[], bool] | None,

) -> None:

    if _is_search_panel_open(page):

        return



    if _is_my_maps_page(page):

        try:

            _ensure_search_panel_open(page, timeout_ms=10000)

            return

        except PlaywrightTimeoutError:

            pass



    if on_status:

        on_status(

            "Faça login com sua Conta Google na janela do Chrome. "

            "A automação continua assim que o My Maps abrir."

        )



    timeout_ms = getattr(settings, "PLAYWRIGHT_LOGIN_TIMEOUT_MS", 300000)

    deadline = time.monotonic() + (timeout_ms / 1000)



    while time.monotonic() < deadline:

        if should_cancel and should_cancel():

            raise ValueError("Automação cancelada pelo usuário.")



        if _is_search_panel_open(page):

            return



        if _is_my_maps_page(page):

            try:

                _ensure_search_panel_open(page, timeout_ms=15000)

                return

            except PlaywrightTimeoutError:

                page.goto(map_url, wait_until="domcontentloaded", timeout=60000)

        elif not _is_google_login_page(page):

            page.goto(map_url, wait_until="domcontentloaded", timeout=60000)

        else:

            page.bring_to_front()



        page.wait_for_timeout(1500)



    raise ValueError(

        "Tempo esgotado aguardando login no Google. "

        "Conclua o login na janela do Chrome e clique no botão novamente."

    )





def _wait_before_address_loop(
    *,
    on_status: Callable[[str], None] | None,
    on_pause: Callable[[], None] | None,
    should_cancel: Callable[[], bool] | None,
    should_resume: Callable[[], bool] | None,
) -> None:
    if on_pause:
        on_pause()
    if on_status:
        on_status(
            "Mapa pronto. Edite o mapa e clique em Continuar pesquisa na página."
        )
    while True:
        if should_cancel and should_cancel():
            raise ValueError("Automação cancelada pelo usuário.")
        if should_resume and should_resume():
            return
        time.sleep(1)





def _maybe_save_storage_state(context) -> None:

    if not getattr(settings, "PLAYWRIGHT_SAVE_SESSION_AFTER_LOGIN", False):

        return



    target = getattr(settings, "PLAYWRIGHT_STORAGE_STATE", "")

    if not target:

        return



    path = Path(target)

    path.parent.mkdir(parents=True, exist_ok=True)

    context.storage_state(path=str(path))





def _click_legend_panel(page) -> None:

    legend_xpath = getattr(settings, "GOOGLE_MAPS_LEGEND_XPATH", LEGEND_CLICK_XPATH)

    timeout_ms = getattr(settings, "PLAYWRIGHT_LEGEND_TIMEOUT_MS", 60000)



    legend_item = page.locator(f"xpath={legend_xpath}")

    legend_item.wait_for(state="visible", timeout=timeout_ms)

    legend_item.click(timeout=15000)

    page.wait_for_timeout(500)





def _normalize_address_items(addresses: list[Any]) -> list[dict[str, Any]]:

    items: list[dict[str, Any]] = []

    for index, address in enumerate(addresses, start=1):

        if isinstance(address, dict):

            endereco = str(address.get("endereco", "")).strip()

            linha = address.get("linha", index)

        else:

            endereco = str(address).strip()

            linha = index

        if endereco:

            items.append({"linha": linha, "endereco": endereco})

    return items





def _processed_address_keys(processed: list[dict[str, Any]]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for item in processed:
        if item.get("linha") is not None:
            keys.add(("linha", str(item["linha"])))
        endereco = str(item.get("endereco", "")).strip()
        if endereco:
            keys.add(("endereco", endereco))
    return keys





def _filter_pending_address_items(
    address_items: list[dict[str, Any]],
    processed: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    keys = _processed_address_keys(processed)
    pending: list[dict[str, Any]] = []
    for item in address_items:
        linha = item.get("linha")
        endereco = str(item.get("endereco", "")).strip()
        if ("linha", str(linha)) in keys or ("endereco", endereco) in keys:
            continue
        pending.append(item)
    return pending





def search_addresses_on_map(

    addresses: list[Any],

    *,

    on_progress: Callable[[int, int, str], None] | None = None,

    on_status: Callable[[str], None] | None = None,

    on_partial_result: Callable[[dict[str, Any]], None] | None = None,

    should_cancel: Callable[[], bool] | None = None,

    should_resume: Callable[[], bool] | None = None,

    on_pause: Callable[[], None] | None = None,

    resultados_anteriores: list[dict[str, Any]] | None = None,

) -> dict[str, Any]:

    if (

        not get_storage_state_path()

        and settings.PLAYWRIGHT_REQUIRE_AUTH

        and not settings.PLAYWRIGHT_WAIT_FOR_MANUAL_LOGIN

    ):

        raise ValueError(

            "Sessão do Google não configurada. "

            "Execute 'python manage.py salvar_sessao_google' localmente e configure "

            "PLAYWRIGHT_STORAGE_STATE_JSON no Render com o conteúdo do google-auth.json."

        )



    map_url = settings.GOOGLE_MAPS_URL

    headless = settings.PLAYWRIGHT_HEADLESS

    delay_ms = settings.PLAYWRIGHT_SEARCH_DELAY_MS

    wait_for_login = settings.PLAYWRIGHT_WAIT_FOR_MANUAL_LOGIN and not headless



    processed: list[dict[str, Any]] = list(resultados_anteriores or [])

    cancelled = False

    address_items = _normalize_address_items(addresses)

    if not address_items and not processed:

        raise ValueError("Nenhum endereço informado para pesquisa.")

    pending_items = _filter_pending_address_items(address_items, processed)

    if not pending_items:

        return {

            "total": len(address_items),

            "processados": len(processed),

            "cancelado": False,

            "resultados": processed,

        }



    def status(message: str) -> None:

        if on_status:

            on_status(message)



    def publish_partial_result() -> None:

        if not on_partial_result:

            return

        on_partial_result(

            {

                "total": len(address_items),

                "processados": len(processed),

                "cancelado": cancelled,

                "resultados": processed,

            }

        )



    status("Carregando camadas NIO do KML...")
    layer_index: NioLayerIndex | None = None
    try:
        layer_index = load_local_layer_index()
    except Exception:
        layer_index = None
    if layer_index and layer_index.polygons:
        status(
            f"Camadas NIO prontas ({len(layer_index.layer_names)} camada(s), "
            f"{len(layer_index.polygons)} polígono(s))."
        )
    else:
        status("Camadas NIO locais indisponíveis. Tentando carregar pelo navegador...")



    with sync_playwright() as playwright:

        try:

            status("Abrindo navegador...")

            with maps_browser_session(playwright, headless=headless) as context:

                page = get_or_create_page(context)

                if not headless:

                    page.bring_to_front()



                try:

                    status("Carregando Google My Maps...")

                    page.goto(map_url, wait_until="domcontentloaded", timeout=90000)

                    _wait_for_map_ui(page, timeout_ms=90000)



                    if wait_for_login and (

                        _is_google_login_page(page) or not _is_search_panel_open(page)

                    ):

                        _wait_for_manual_google_login(

                            page,

                            map_url,

                            on_status=on_status,

                            should_cancel=should_cancel,

                        )

                        _maybe_save_storage_state(context)

                    elif not wait_for_login and _is_google_login_page(page):

                        raise ValueError(

                            "Sessão Google expirada ou ausente. "

                            "Faça login localmente ou configure google-auth.json."

                        )



                    status("Aguardando painel do mapa...")

                    _wait_for_map_ui(page, timeout_ms=90000)



                    status("Clicando no botão de busca (lupa)...")

                    search_input = _ensure_search_panel_open(page, timeout_ms=90000)

                except PlaywrightTimeoutError as exc:

                    raise ValueError(

                        "Não foi possível abrir o Google My Maps ou localizar o campo de busca. "

                        "Verifique se o mapa está acessível após o login."

                    ) from exc



                status("Carregando camadas NIO do mapa...")

                if not layer_index or not layer_index.polygons:
                    try:
                        layer_index = load_layer_index_from_page(page, map_url)
                    except Exception:
                        layer_index = None

                if layer_index and layer_index.polygons:

                    status(

                        f"Camadas NIO carregadas ({len(layer_index.layer_names)} camada(s), "

                        f"{len(layer_index.polygons)} polígono(s)). Iniciando endereços..."

                    )

                else:

                    status(

                        "Camadas NIO indisponíveis. Continuando pesquisa dos endereços..."

                    )



                try:

                    legend_xpath = getattr(settings, "GOOGLE_MAPS_LEGEND_XPATH", "")

                    if legend_xpath:

                        status("Clicando na legenda do mapa...")

                        _click_legend_panel(page)

                except PlaywrightTimeoutError as exc:

                    raise ValueError(

                        "Não foi possível clicar no item da legenda do mapa. "

                        "Verifique se o painel legendPanel carregou corretamente."

                    ) from exc



                if getattr(settings, "PLAYWRIGHT_WAIT_BEFORE_ADDRESS_LOOP", False):

                    _wait_before_address_loop(

                        on_status=status,

                        on_pause=on_pause,

                        should_cancel=should_cancel,

                        should_resume=should_resume,

                    )



                total = len(address_items)

                if processed:
                    status(
                        f"Retomando: {len(processed)} endereço(s) já processado(s), "
                        f"{len(pending_items)} restante(s)."
                    )
                    publish_partial_result()



                for index, item in enumerate(pending_items, start=1):

                    address = item["endereco"]

                    linha = item.get("linha")

                    current_position = len(processed) + index



                    if should_cancel and should_cancel():

                        cancelled = True

                        break



                    if on_progress:

                        on_progress(current_position, total, address)



                    status(f"Pesquisando endereço {current_position} de {total}: {address}")



                    try:

                        _paste_address_in_search(page, address, delay_ms)

                        coords = get_search_coordinates(

                            page,

                            timeout_ms=getattr(

                                settings, "PLAYWRIGHT_COORDINATES_TIMEOUT_MS", 2500

                            ),

                        )

                        camada_nio = None
                        distancia_km = None
                        viabilidade = "Sem coordenadas"
                        destacado = False

                        if coords and layer_index:
                            analysis = layer_index.analyze_point(coords[0], coords[1])
                            camada_nio = analysis.camada_nio
                            distancia_km = analysis.distancia_km
                            viabilidade = analysis.viabilidade
                            destacado = analysis.destacado
                        elif coords:
                            viabilidade = "Camadas indisponíveis"
                            camada_nio = "—"
                        else:
                            camada_nio = "—"



                        result_item = {

                            "indice": current_position,

                            "linha": linha,

                            "endereco": address,

                            "status": "ok",

                            "camada_nio": camada_nio or "—",

                            "distancia_km": distancia_km,

                            "viabilidade": viabilidade,

                            "destacado": destacado,

                        }

                        if coords:

                            result_item["lat"] = coords[0]

                            result_item["lng"] = coords[1]



                        processed.append(result_item)

                        publish_partial_result()

                        status(

                            f"Endereço {current_position}/{total}: {viabilidade}"

                            + (
                                f" ({distancia_km} km)"
                                if distancia_km is not None and distancia_km > 0
                                else ""
                            )

                        )

                    except PlaywrightTimeoutError:

                        processed.append(

                            {

                                "indice": current_position,

                                "linha": linha,

                                "endereco": address,

                                "status": "erro",

                                "camada_nio": "",

                                "mensagem": "Tempo esgotado ao preencher o campo de busca.",

                            }

                        )

                        publish_partial_result()

                        status(

                            f"Erro no endereço {current_position}/{total}. Continuando com o próximo..."

                        )

                        continue

                    except Exception as exc:

                        processed.append(

                            {

                                "indice": current_position,

                                "linha": linha,

                                "endereco": address,

                                "status": "erro",

                                "camada_nio": "",

                                "mensagem": str(exc)[:200],

                            }

                        )

                        publish_partial_result()

                        status(

                            f"Erro no endereço {current_position}/{total}. Continuando com o próximo..."

                        )

                        continue

        except RuntimeError as exc:

            raise ValueError(str(exc)) from exc

        except PlaywrightTimeoutError as exc:

            if "Target page, context or browser has been closed" in str(exc):

                raise ValueError(

                    "O navegador foi fechado antes de concluir a automação. "

                    "Não feche a janela do Chrome durante a execução."

                ) from exc

            raise



    return {

        "total": len(address_items),

        "processados": len(processed),

        "cancelado": cancelled,

        "resultados": processed,

    }


