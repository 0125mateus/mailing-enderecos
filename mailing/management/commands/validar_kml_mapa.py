from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from mailing.services.nio_layers import (
    NioLayerIndex,
    extract_network_link_href,
    summarize_layer_index,
)


class Command(BaseCommand):
    help = "Valida o KML configurado e lista camadas como PR-1 (CACE), NIO PR etc."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            default="",
            help="Caminho do KML (padrão: GOOGLE_MAPS_KML_PATH do .env)",
        )
        parser.add_argument(
            "--buscar",
            default="",
            help="Filtrar camadas pelo texto (ex.: PR-1 ou CACE)",
        )

    def handle(self, *args, **options):
        configured = options["path"] or getattr(settings, "GOOGLE_MAPS_KML_PATH", "") or ""
        if not configured:
            raise CommandError(
                "Informe --path ou configure GOOGLE_MAPS_KML_PATH no .env."
            )

        kml_path = Path(configured).expanduser().resolve()
        if not kml_path.is_file():
            raise CommandError(f"Arquivo não encontrado: {kml_path}")

        kml_bytes = kml_path.read_bytes()
        index = NioLayerIndex.from_kml_bytes(kml_bytes)
        summary = summarize_layer_index(index)

        if not index.polygons:
            href = extract_network_link_href(kml_bytes)
            self.stdout.write(self.style.WARNING("Nenhum polígono encontrado neste arquivo."))
            if href:
                self.stdout.write("")
                self.stdout.write(
                    "Este KML é só um link (NetworkLink). Baixe o arquivo completo com:"
                )
                self.stdout.write(
                    f'  python manage.py baixar_kml_mapa --source "{kml_path}"'
                )
            raise CommandError("KML inválido para detecção de manchas.")

        prefix = getattr(settings, "GOOGLE_MAPS_NIO_LAYER_PREFIX", "NIO")
        nio_polygons = [
            polygon
            for polygon in index.polygons
            if NioLayerIndex._matches_prefix(polygon, prefix)
        ]

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"KML válido: {kml_path}"))
        self.stdout.write(f"Polígonos totais: {summary['polygon_count']}")
        self.stdout.write(
            f"Polígonos com prefixo '{prefix}' (pastas/camadas NIO): {len(nio_polygons)}"
        )
        self.stdout.write(f"Camadas distintas: {summary['layer_count']}")
        self.stdout.write("")

        self.stdout.write("Pastas do mapa:")
        for folder in summary["folders"]:
            marker = "*" if prefix.upper() in folder.upper() else " "
            self.stdout.write(f"  [{marker}] {folder}")

        self.stdout.write("")
        search = options["buscar"].strip().lower()
        self.stdout.write("Camadas (placemarks):")
        shown = 0
        for name, count in summary["layers"]:
            if search and search not in name.lower():
                continue
            self.stdout.write(f"  - {name} ({count} poligono(s))")
            shown += 1
            if shown >= 30 and not search:
                remaining = summary["layer_count"] - 30
                if remaining > 0:
                    self.stdout.write(f"  ... e mais {remaining} camada(s)")
                break

        if search and shown == 0:
            self.stdout.write(self.style.WARNING(f"Nenhuma camada contendo '{options['buscar']}'."))

        pr1 = [name for name, _count in summary["layers"] if "PR-1" in name.upper() or "CACE" in name.upper()]
        if pr1:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Camadas PR-1 / CACE encontradas:"))
            for name in pr1[:20]:
                self.stdout.write(f"  - {name}")
