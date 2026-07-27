from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .services.spreadsheet import extract_addresses

MAX_FILE_SIZE = 20 * 1024 * 1024
ALLOWED_EXTENSIONS = (".xlsx", ".xls", ".csv")


def home(request):
    return render(request, "index.html")


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
