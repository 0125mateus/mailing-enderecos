from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from playwright.sync_api import sync_playwright

from mailing.services.maps_automation import SEARCH_INPUT_XPATH
from mailing.services.playwright_browser import (
    connect_over_cdp,
    get_or_create_page,
    get_user_data_dir,
    open_maps_context,
)

DEFAULT_OUTPUT = Path(settings.BASE_DIR) / "playwright" / "google-auth.json"

SEARCH_SELECTORS = (
    f"xpath={SEARCH_INPUT_XPATH}",
    'input[aria-label*="Search" i]',
    'input[aria-label*="Pesquis" i]',
    'input[aria-label*="Buscar" i]',
    "#searchboxinput",
)

CHROME_CDP_HINT = (
    'Abra o Chrome manualmente e conecte com:\n'
    '  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
    '--remote-debugging-port=9222 '
    '--user-data-dir="%USERPROFILE%\\chrome-nio-profile"\n'
    'Depois execute:\n'
    "  python manage.py salvar_sessao_google --cdp http://127.0.0.1:9222"
)


class Command(BaseCommand):
    help = (
        "Abre o Google Chrome com perfil persistente para login no My Maps "
        "e salva a sessão para uso do Playwright."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=str(DEFAULT_OUTPUT),
            help=f"Caminho do arquivo de sessão (padrão: {DEFAULT_OUTPUT})",
        )
        parser.add_argument(
            "--auto",
            action="store_true",
            help="Salva automaticamente ao detectar o campo de busca (sem pressionar Enter).",
        )
        parser.add_argument(
            "--cdp",
            default="",
            help="URL do Chrome já aberto (ex.: http://127.0.0.1:9222). Evita bloqueio do Google.",
        )

    def handle(self, *args, **options):
        output_path = Path(options["output"]).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        map_url = settings.GOOGLE_MAPS_URL
        auto_mode = options["auto"]
        cdp_url = options["cdp"].strip()
        profile_dir = get_user_data_dir()

        self.stdout.write("")
        self.stdout.write(self.style.NOTICE("=== Sessão Google para Playwright ==="))
        self.stdout.write("")
        if cdp_url:
            self.stdout.write("Modo CDP: usando Chrome que você abriu manualmente.")
        else:
            self.stdout.write("O Google Chrome será aberto (não o Chromium do Playwright).")
            self.stdout.write(f"Perfil persistente: {profile_dir}")
        self.stdout.write("")
        self.stdout.write("1. Faça login na conta Google, se solicitado.")
        self.stdout.write("2. Aguarde o mapa carregar por completo.")
        if auto_mode:
            self.stdout.write(
                "3. A sessão será salva automaticamente quando o campo de busca aparecer."
            )
        else:
            self.stdout.write(
                "3. Volte a ESTE terminal e pressione ENTER para salvar a sessão."
            )
        self.stdout.write("")
        self.stdout.write(f"URL: {map_url}")
        self.stdout.write(f"Arquivo de saída: {output_path}")
        self.stdout.write("")

        try:
            with sync_playwright() as playwright:
                if cdp_url:
                    context = connect_over_cdp(playwright, cdp_url)
                else:
                    try:
                        context = open_maps_context(
                            playwright,
                            headless=False,
                            prefer_persistent=True,
                        )
                    except RuntimeError as exc:
                        raise CommandError(str(exc)) from exc

                page = get_or_create_page(context)
                page.goto(map_url, wait_until="domcontentloaded", timeout=90000)

                if auto_mode:
                    self.stdout.write(
                        self.style.WARNING(
                            "Aguardando login e carregamento do mapa (campo de busca)..."
                        )
                    )
                    if not self._wait_for_search_input(page, timeout_ms=600_000):
                        context.close()
                        raise CommandError(
                            "Campo de busca não encontrado.\n\n"
                            "Se o Google bloqueou o login, use o modo CDP:\n"
                            f"{CHROME_CDP_HINT}"
                        )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            "Chrome aberto. Faça login e, quando o mapa estiver pronto, "
                            "pressione ENTER aqui no terminal."
                        )
                    )
                    self.stdout.flush()
                    try:
                        input()
                    except EOFError:
                        context.close()
                        raise CommandError(
                            "Entrada cancelada. Execute no terminal do Cursor:\n"
                            "  python manage.py salvar_sessao_google\n\n"
                            "Se o Google bloquear o login, use:\n"
                            f"{CHROME_CDP_HINT}"
                        ) from None

                context.storage_state(path=str(output_path))
                context.close()
        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(
                "Erro ao abrir o navegador.\n"
                "Instale o Google Chrome ou use o modo CDP:\n"
                f"{CHROME_CDP_HINT}\n\n"
                f"Detalhe: {exc}"
            ) from exc

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Sessão salva em: {output_path}"))
        self.stdout.write(self.style.SUCCESS(f"Perfil Chrome em: {profile_dir}"))
        self.stdout.write("")
        self.stdout.write("No .env (opcional — o perfil persistente já mantém o login):")
        self.stdout.write("")
        self.stdout.write(f"  PLAYWRIGHT_STORAGE_STATE={output_path}")
        self.stdout.write("  PLAYWRIGHT_HEADLESS=False")
        self.stdout.write("")
        self.stdout.write(
            "Para automação, prefira PLAYWRIGHT_HEADLESS=False na primeira execução."
        )
        self.stdout.write("")

    def _wait_for_search_input(self, page, timeout_ms: int) -> bool:
        elapsed = 0
        step_ms = 2000

        while elapsed < timeout_ms:
            for selector in SEARCH_SELECTORS:
                locator = page.locator(selector).first
                try:
                    if locator.is_visible(timeout=500):
                        return True
                except Exception:
                    continue
            page.wait_for_timeout(step_ms)
            elapsed += step_ms

        return False
