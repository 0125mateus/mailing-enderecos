import json

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_http_methods

from .services.spreadsheet import export_results_spreadsheet, extract_addresses

MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = (".xlsx", ".xls", ".csv")


@ensure_csrf_cookie
def home(request):
    from django.conf import settings

    auth_ready = not settings.PLAYWRIGHT_REQUIRE_AUTH
    if settings.PLAYWRIGHT_ENABLED:
        try:
            from .services.playwright_browser import get_storage_state_path

            auth_ready = bool(get_storage_state_path()) or not settings.PLAYWRIGHT_REQUIRE_AUTH
        except ModuleNotFoundError:
            auth_ready = False

    return render(
        request,
        "index.html",
        {
            "maps_automation_enabled": settings.PLAYWRIGHT_ENABLED,
            "google_maps_url": settings.GOOGLE_MAPS_URL,
            "playwright_auth_ready": auth_ready,
        },
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
                "erro": (
                    "Automação Playwright disponível apenas no ambiente local. "
                    "No Render, o botão abre o mapa em nova aba."
                ),
            },
            status=503,
        )

    from .services.automation_jobs import create_job

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
    resultados_anteriores = payload.get("resultados_anteriores", [])
    if not isinstance(resultados_anteriores, list):
        return JsonResponse(
            {"erro": "O campo 'resultados_anteriores' deve ser uma lista."},
            status=400,
        )

    for item in enderecos_raw:
        if isinstance(item, dict):
            text = str(item.get("endereco", "")).strip()
            if not text:
                continue
            linha = item.get("linha")
            enderecos.append(
                {
                    "linha": linha,
                    "endereco": text,
                }
            )
        else:
            text = str(item).strip()
            if text:
                enderecos.append({"linha": len(enderecos) + 1, "endereco": text})

    if not enderecos:
        return JsonResponse(
            {"erro": "Nenhum endereço válido foi enviado para pesquisa."},
            status=400,
        )

    try:
        job = create_job(enderecos, resultados_anteriores=resultados_anteriores)
    except ValueError as exc:
        return JsonResponse({"erro": str(exc)}, status=409)

    return JsonResponse(job.to_dict(), status=202)


@require_http_methods(["GET"])
def status_maps_automation(request, job_id):
    from .services.automation_jobs import get_job

    job = get_job(job_id)
    if not job:
        return JsonResponse({"erro": "Automação não encontrada."}, status=404)
    return JsonResponse(job.to_dict())


@require_http_methods(["GET"])
def exportar_maps_resultado(request, job_id):
    from .services.automation_jobs import get_job

    job = get_job(job_id)
    if not job or not job.result:
        return JsonResponse({"erro": "Resultado da automação não encontrado."}, status=404)

    resultados = job.result.get("resultados") or []
    if not resultados:
        return JsonResponse({"erro": "Nenhum resultado disponível para exportação."}, status=404)

    try:
        parcial = job.status in {"cancelled", "failed"}
        file_bytes = export_results_spreadsheet(resultados, parcial=parcial)
    except Exception:
        return JsonResponse(
            {"erro": "Não foi possível gerar a planilha de resultados."},
            status=500,
        )

    filename = f"resultado-nio-{job_id[:8]}.xlsx"
    response = HttpResponse(
        file_bytes,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


@require_http_methods(["POST"])
def cancelar_maps_automation(request, job_id):
    from .services.automation_jobs import cancel_job

    job = cancel_job(job_id)
    if not job:
        return JsonResponse({"erro": "Automação não encontrada."}, status=404)
    return JsonResponse(job.to_dict())


@require_http_methods(["POST"])
def continuar_maps_automation(request, job_id):
    from .services.automation_jobs import resume_job

    job = resume_job(job_id)
    if not job:
        return JsonResponse({"erro": "Automação não encontrada."}, status=404)
    return JsonResponse(job.to_dict())
