import json
import re
import urllib.error
import urllib.request
from typing import Any

_viacep_cache: dict[str, dict[str, str] | None] = {}


def _cep_digits(cep: str) -> str:
    return re.sub(r"\D", "", cep or "")[:8]


def lookup_cep(cep: str) -> dict[str, str] | None:
    digits = _cep_digits(cep)
    if len(digits) != 8:
        return None

    if digits in _viacep_cache:
        return _viacep_cache[digits]

    try:
        with urllib.request.urlopen(
            f"https://viacep.com.br/ws/{digits}/json/",
            timeout=5,
        ) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        _viacep_cache[digits] = None
        return None

    if data.get("erro"):
        _viacep_cache[digits] = None
        return None

    result = {
        "logradouro": str(data.get("logradouro") or "").strip(),
        "bairro": str(data.get("bairro") or "").strip(),
        "cidade": str(data.get("localidade") or "").strip(),
        "uf": str(data.get("uf") or "").strip(),
    }
    _viacep_cache[digits] = result
    return result


def extract_cep_from_text(text: str) -> str:
    match = re.search(r"(\d{5})-?(\d{3})", text or "")
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}"


def _needs_enrichment(
    endereco: str,
    bairro: str,
    cidade: str,
    uf: str,
) -> bool:
    if not endereco:
        return True
    if not cidade or not uf:
        return True
    if not bairro and len(endereco) < 40:
        return True
    return False


def enrich_address_fields(
    *,
    endereco: str,
    bairro: str,
    cep: str,
    cidade: str,
    uf: str,
) -> tuple[dict[str, str], bool]:
    fields = {
        "endereco": endereco,
        "bairro": bairro,
        "cep": cep,
        "cidade": cidade,
        "uf": uf,
    }

    if not _needs_enrichment(endereco, bairro, cidade, uf):
        return fields, False

    lookup_cep_value = cep or extract_cep_from_text(endereco)
    viacep = lookup_cep(lookup_cep_value)
    if not viacep:
        return fields, False

    enriched = False

    if not fields["endereco"] and viacep["logradouro"]:
        fields["endereco"] = viacep["logradouro"]
        enriched = True

    if not fields["bairro"] and viacep["bairro"]:
        fields["bairro"] = viacep["bairro"]
        enriched = True

    if not fields["cidade"] and viacep["cidade"]:
        fields["cidade"] = viacep["cidade"]
        enriched = True

    if not fields["uf"] and viacep["uf"]:
        fields["uf"] = viacep["uf"]
        enriched = True

    if lookup_cep_value and not fields["cep"]:
        fields["cep"] = lookup_cep_value
        enriched = True

    return fields, enriched
