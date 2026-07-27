import io
import re
from typing import Any

import pandas as pd

ADDRESS_COLUMNS = {
    "endereco": ("ENDERECO", "ENDEREÇO", "ENDereco", "RUA", "LOGRADOURO"),
    "numero": ("NUMERO", "NÚMERO", "NRO", "NUM"),
    "bairro": ("BAIRRO",),
    "cep": ("CEP.1", "CEP", "CEP1"),
    "cidade": ("CIDADE", "MUNICIPIO", "MUNICÍPIO"),
    "uf": ("UF", "ESTADO"),
}


def _normalize_column_name(name: str) -> str:
    return re.sub(r"\s+", " ", str(name).strip().upper())


def _build_column_map(columns: list[str]) -> dict[str, str | None]:
    normalized = {_normalize_column_name(col): col for col in columns}
    mapping: dict[str, str | None] = {}

    for field, candidates in ADDRESS_COLUMNS.items():
        mapping[field] = None
        for candidate in candidates:
            key = _normalize_column_name(candidate)
            if key in normalized:
                mapping[field] = normalized[key]
                break

    return mapping


def _clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", ".", "cep"}:
        return ""
    return text


def _format_cep(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        digits = str(int(value))
    else:
        digits = re.sub(r"\D", "", str(value))

    if not digits:
        return ""

    digits = digits.zfill(8)[:8]
    return f"{digits[:5]}-{digits[5:]}"


def _format_numero(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if float(value).is_integer():
            return str(int(value))
        return str(value)

    return str(value).strip()


def _format_address(row: pd.Series, column_map: dict[str, str | None]) -> str | None:
    endereco = _clean_text(row.get(column_map["endereco"])) if column_map["endereco"] else ""
    numero = _format_numero(row.get(column_map["numero"])) if column_map["numero"] else ""
    bairro = _clean_text(row.get(column_map["bairro"])) if column_map["bairro"] else ""
    cep = _format_cep(row.get(column_map["cep"])) if column_map["cep"] else ""
    cidade = _clean_text(row.get(column_map["cidade"])) if column_map["cidade"] else ""
    uf = _clean_text(row.get(column_map["uf"])) if column_map["uf"] else ""

    parts: list[str] = []

    if endereco:
        street = endereco
        if numero:
            street = f"{street}, {numero}"
        parts.append(street)
    elif bairro:
        parts.append(bairro)

    if bairro and endereco:
        parts.append(bairro)

    if cep:
        parts.append(f"CEP {cep}")

    if cidade:
        city_part = cidade
        if uf:
            city_part = f"{city_part} - {uf}"
        parts.append(city_part)
    elif uf:
        parts.append(uf)

    if not parts:
        return None

    return " - ".join(parts)


def _read_dataframe(file_bytes: bytes, filename: str) -> pd.DataFrame:
    lower_name = filename.lower()

    if lower_name.endswith(".csv"):
        for encoding in ("utf-8", "latin-1", "cp1252"):
            try:
                return pd.read_csv(io.BytesIO(file_bytes), encoding=encoding)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(io.BytesIO(file_bytes), encoding="latin-1")

    if lower_name.endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(file_bytes))

    raise ValueError("Formato não suportado. Envie um arquivo .xlsx, .xls ou .csv.")


def extract_addresses(file_bytes: bytes, filename: str) -> dict[str, Any]:
    dataframe = _read_dataframe(file_bytes, filename)
    column_map = _build_column_map(list(dataframe.columns))

    if not any(column_map.values()):
        raise ValueError(
            "Não encontrei colunas de endereço na planilha. "
            "Esperado algo como ENDERECO, NUMERO, BAIRRO, CEP, CIDADE e UF."
        )

    addresses: list[dict[str, Any]] = []

    for index, row in dataframe.iterrows():
        formatted = _format_address(row, column_map)
        if not formatted:
            continue

        addresses.append(
            {
                "linha": int(index) + 2,
                "endereco": formatted,
            }
        )

    return {
        "arquivo": filename,
        "total_linhas_planilha": int(len(dataframe)),
        "total_enderecos": len(addresses),
        "enderecos": addresses,
        "colunas_detectadas": {
            key: column_map[key] for key in column_map if column_map[key]
        },
    }
