from django.core.management.base import BaseCommand

from mailing.services.automation_jobs import run_maps_job


class Command(BaseCommand):
    help = "Executa a automação do Google My Maps em processo separado."

    def add_arguments(self, parser):
        parser.add_argument("job_id", help="ID do job de automação")

    def handle(self, *args, **options):
        run_maps_job(options["job_id"])
