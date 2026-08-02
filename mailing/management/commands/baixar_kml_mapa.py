from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from playwright.sync_api import sync_playwright

from mailing.services.nio_layers import (
    NioLayerIndex,
    extract_map_mid,
    extract_network_link_href,
    fetch_kml_with_page,
    summarize_layer_index,
)
from mailing.services.playwright_browser import get_or_create_page, open_maps_context


DEFAULT_OUTPUT = Path(settings.BASE_DIR) / "playwright" / "mapa-nio-07-2026.kml"


class Command(BaseCommand):
    help = (
        "Baixa o KML completo do Google My Maps (com polígonos) usando sessão do Chrome. "
        "O arquivo 'Download KML' do site costuma vir só como link; este comando resolve isso."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=str(DEFAULT_OUTPUT),
            help=f"Caminho de saída do KML (padrão: {DEFAULT_OUTPUT})",
        )
        parser.add_argument(
            "--source",
            default="",
            help="KML local com NetworkLink (opcional). Ex.: Downloads/MAPA NOVO 07-2026.kml",
        )

    def handle(self, *args, **options):
        output_path = Path(options["output"]).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        map_url = settings.GOOGLE_MAPS_URL
        map_mid = extract_map_mid(map_url)
        if not map_mid:
            raise CommandError("Não foi possível extrair o mid do mapa em GOOGLE_MAPS_URL.")

        candidate_urls: list[str] = [
            f"https://www.google.com/maps/d/u/0/kml?mid={map_mid}&forcekml=1",
            f"https://www.google.com/maps/d/kml?mid={map_mid}&forcekml=1",
        ]

        source_path = Path(options["source"]).expanduser() if options["source"] else None
        if source_path and source_path.is_file():
            href = extract_network_link_href(source_path.read_bytes())
            if href:
                candidate_urls.insert(0, href)

        self.stdout.write("")
        self.stdout.write(self.style.NOTICE("=== Download KML do My Maps ==="))
        self.stdout.write("")
        self.stdout.write("Abrindo Chrome. Faça login no Google se necessário.")
        self.stdout.write("")

        downloaded: bytes | None = None
        with sync_playwright() as playwright:
            with open_maps_context(playwright, headless=False) as context:
                page = get_or_create_page(context)
                page.goto(map_url, wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(3000)

                for kml_url in candidate_urls:
                    self.stdout.write(f"Tentando: {kml_url}")
                    body = fetch_kml_with_page(page, kml_url)
                    if not body:
                        continue
                    index = NioLayerIndex.from_kml_bytes(body)
                    if index.polygons:
                        downloaded = body
                        break
                    href = extract_network_link_href(body)
                    if href and href not in candidate_urls:
                        self.stdout.write(f"Seguindo NetworkLink: {href}")
                        body = fetch_kml_with_page(page, href)
                        if body:
                            index = NioLayerIndex.from_kml_bytes(body)
                            if index.polygons:
                                downloaded = body
                                break

        if not downloaded:
            raise CommandError(
                "Não foi possível baixar o KML com polígonos. "
                "Confirme login no Google e acesso ao mapa, depois tente novamente."
            )

        output_path.write_bytes(downloaded)
        index = NioLayerIndex.from_kml_bytes(downloaded)
        summary = summarize_layer_index(index)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"KML salvo em: {output_path}"))
        self.stdout.write(f"Polígonos: {summary['polygon_count']}")
        self.stdout.write(f"Camadas (placemarks): {summary['layer_count']}")
        self.stdout.write(f"Pastas: {summary['folder_count']}")
        self.stdout.write("")
        self.stdout.write("Pastas NIO encontradas:")
        for folder in summary["folders"]:
            if "NIO" in folder.upper():
                self.stdout.write(f"  - {folder}")
        self.stdout.write("")
        self.stdout.write("Exemplos de camadas:")
        for name, count in summary["layers"][:15]:
            safe_name = name.encode("ascii", errors="replace").decode("ascii")
            self.stdout.write(f"  - {safe_name} ({count} poligono(s))")
        if summary["layer_count"] > 15:
            self.stdout.write(f"  ... e mais {summary['layer_count'] - 15} camada(s)")
        self.stdout.write("")
        self.stdout.write(
            "Configure no .env:\n"
            f"GOOGLE_MAPS_KML_PATH={output_path}"
        )
