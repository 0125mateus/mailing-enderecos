import json

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.automation_jobs import cancel_job, create_job, get_job
from .services.spreadsheet import extract_addresses

MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = (".xlsx", ".xls", ".csv")


@ensure_csrf_cookie
def home(request):
    from django.conf import settings

    return render(
        request,
        "index.html",
        {"maps_automation_enabled": settings.PLAYWRIGHT_ENABLED},
    )


@require_http_methods(["POST"])
def upload_planilha(request):
    uploaded_file = request.FILES.get("arquivo")

    if not uploaded_file:
        return JsonResponse({"erro": "Nenhum arquivo foi enviado."}, status=400)

    filename = uploaded_file.name.lower()
    if not filename.endswith(ALLOWED_EXTENSIONS):
        return JsonResponse(
            {
                "erro": "Formato inválido. Envie uma planilha .xlsx, .xls ou .csv.",
            },
            status=400,
        )

    if uploaded_file.size > MAX_FILE_SIZE:
        return JsonResponse(
            {"erro": "Arquivo muito grande. O limite é 20 MB."},
            status=400,
        )

    try:
        file_bytes = uploaded_file.read()
        result = extract_addresses(file_bytes, uploaded_file.name)
        return JsonResponse(result)
    except ValueError as exc:
        return JsonResponse({"erro": str(exc)}, status=400)
    except Exception:
        return JsonResponse(
            {
                "erro": "Não foi possível ler a planilha. Verifique se o arquivo não está corrompido.",
            },
            status=500,
        )


def _parse_json_body(request) -> dict:
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("JSON inválido no corpo da requisição.") from exc


@require_http_methods(["POST"])
def iniciar_maps_automation(request):
    from django.conf import settings

    if not settings.PLAYWRIGHT_ENABLED:
        return JsonResponse(
            {
                "erro": "Automação do Google My Maps disponível apenas no ambiente local.",
            },
            status=503,
        )

    try:
        payload = _parse_json_body(request)
    except ValueError as exc:
        return JsonResponse({"erro": str(exc)}, status=400)

    enderecos_raw = payload.get("enderecos", [])
    if not isinstance(enderecos_raw, list):
        return JsonResponse(
            {"erro": "O campo 'enderecos' deve ser uma lista de textos."},
            status=400,
        )

    enderecos = []
    for item in enderecos_raw:
        if isinstance(item, dict):
            text = str(item.get("endereco", "")).strip()
        else:
            text = str(item).strip()
        if text:
            enderecos.append(text)

    if not enderecos:
        return JsonResponse(
            {"erro": "Nenhum endereço válido foi enviado para pesquisa."},
            status=400,
        )

    job = create_job(enderecos)
    return JsonResponse(job.to_dict(), status=202)


@require_http_methods(["GET"])
def status_maps_automation(request, job_id):
    job = get_job(job_id)
    if not job:
        return JsonResponse({"erro": "Automação não encontrada."}, status=404)
    return JsonResponse(job.to_dict())


@require_http_methods(["POST"])
def cancelar_maps_automation(request, job_id):
    job = cancel_job(job_id)
    if not job:
        return JsonResponse({"erro": "Automação não encontrada."}, status=404)
    return JsonResponse(job.to_dict())
