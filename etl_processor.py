#!/usr/bin/env python3
"""
ETL para BE_BM_202509.xlsx -> carga_inicial_bancos.sql

Requiere: pandas (y openpyxl como backend de Excel).
Lee las hojas Pm2, Indicadores y CCT, limpia valores, hace unpivot a largo,
normaliza nombres de instituciones y genera statements SQL de insercion.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
EXCEL_PATH = BASE_DIR / "plugins" / "bank-advisor-private" / "data" / "raw" / "BE_BM_202509.xlsx"
OUTPUT_SQL = BASE_DIR / "carga_inicial_bancos.sql"


def clean_numeric(value):
    """Normaliza valores numericos y devuelve float o None."""
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if text in {"n.d.", "n.d", "n.a.", "n.a", "-", "", "nan"}:
        return None
    text = text.replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def normalize_bank_name(name: str | float | int | None) -> str:
    """Limpia pies de pagina o caracteres residuales en el nombre de institucion."""
    if name is None or pd.isna(name):
        return ""
    text = str(name).strip()
    text = text.replace("*/", "").replace("*", "").strip()
    text = re.sub(r"\s{2,}", " ", text)
    return text


def excel_serial_to_date(serial_val) -> str | None:
    """Convierte un serial de Excel a ISO date (YYYY-MM-DD)."""
    try:
        serial_float = float(serial_val)
    except (TypeError, ValueError):
        return None
    # Excel usa 1899-12-30 como origen (evita el bug de 1900)
    base = pd.to_datetime("1899-12-30")
    return (base + pd.to_timedelta(serial_float, unit="D")).date().isoformat()


def find_header_row(df: pd.DataFrame, marker: str) -> int:
    """Detecta la fila que contiene el marcador de cabecera."""
    marker_lower = marker.lower()
    for idx in range(min(len(df), 25)):
        row_vals = df.iloc[idx].astype(str).str.lower()
        if row_vals.str.contains(marker_lower, na=False).any():
            return idx
    raise ValueError(f"No se encontro la fila de cabecera que contenga '{marker}'.")


def parse_sheet(
    df: pd.DataFrame,
    bank_col: int,
    header_marker: str,
    metrics: List[Tuple[str, int, int, int]],
) -> pd.DataFrame:
    """
    Extrae filas en formato largo para una hoja.

    metrics: lista de tuplas (field_name, start_col, step, num_dates)
             start_col y step son indices de columna basados en header row.
    """
    header_idx = find_header_row(df, header_marker)
    date_row = df.iloc[header_idx + 1]
    data_rows = df.iloc[header_idx + 2 :]

    # Determinar fechas base usando el primer bloque de metricas
    first_metric = metrics[0]
    _, start_col_first, step_first, num_dates_first = first_metric
    dates = []
    for i in range(num_dates_first):
        col_idx = start_col_first + step_first * i
        dates.append(excel_serial_to_date(date_row.iloc[col_idx]))

    records: List[Dict[str, object]] = []
    for _, row in data_rows.iterrows():
        bank_raw = row.iloc[bank_col]
        bank = normalize_bank_name(bank_raw)
        if not bank:
            continue
        for date_idx, fecha in enumerate(dates):
            if not fecha:
                continue
            rec: Dict[str, object] = {"institucion": bank, "fecha_corte": fecha}
            for field, start_col, step, num_dates in metrics:
                if date_idx >= num_dates:
                    continue
                col_idx = start_col + step * date_idx
                rec[field] = clean_numeric(row.iloc[col_idx])
            records.append(rec)

    return pd.DataFrame.from_records(records)


def load_all_sheets(excel_path: Path) -> pd.DataFrame:
    """Orquesta la lectura de Pm2, Indicadores y CCT."""
    if not excel_path.exists():
        raise FileNotFoundError(f"No se encontro el archivo {excel_path}")

    print(f"Leyendo Excel: {excel_path}")
    pm2_raw = pd.read_excel(excel_path, sheet_name="Pm2", header=None, dtype=object, engine="openpyxl")
    ind_raw = pd.read_excel(excel_path, sheet_name="Indicadores", header=None, dtype=object, engine="openpyxl")
    cct_raw = pd.read_excel(excel_path, sheet_name="CCT", header=None, dtype=object, engine="openpyxl")

    pm2 = parse_sheet(
        pm2_raw,
        bank_col=1,
        header_marker="Activo total",
        metrics=[
            ("activo_total", 2, 2, 3),
            ("inversiones_financieras", 8, 2, 3),
            ("cartera_total", 14, 2, 3),
            ("captacion_total", 20, 2, 3),
            ("capital_contable", 26, 2, 3),
            ("resultado_neto", 32, 2, 3),
        ],
    )

    indicadores = parse_sheet(
        ind_raw,
        bank_col=1,
        header_marker="ROA",
        metrics=[
            ("roa_12m", 2, 1, 3),
            ("roe_12m", 5, 1, 3),
        ],
    )

    cct = parse_sheet(
        cct_raw,
        bank_col=1,
        header_marker="IMOR",
        metrics=[
            # cartera_total se ignora en merge si es redundante
            ("cartera_total_cct", 2, 1, 3),
            ("imor", 5, 1, 3),
            ("icor", 8, 1, 3),
            ("perdida_esperada", 11, 1, 3),
        ],
    )

    print("Combinando hojas...")
    master = pm2.merge(indicadores, on=["institucion", "fecha_corte"], how="outer")
    master = master.merge(cct, on=["institucion", "fecha_corte"], how="outer")

    if "cartera_total_cct" in master.columns:
        master = master.drop(columns=["cartera_total_cct"])

    # Elimina duplicados exactos
    master = master.drop_duplicates(subset=["institucion", "fecha_corte"])

    # Normalizacion final de nombres
    master["institucion"] = master["institucion"].apply(normalize_bank_name)

    return master


def generate_sql(df: pd.DataFrame) -> str:
    """Genera statements SQL para catalogo e inserts."""
    statements: List[str] = []

    statements.append("-- Catalogo de instituciones")
    bancos_unicos = sorted(b for b in df["institucion"].dropna().unique() if str(b).strip())
    for banco in bancos_unicos:
        nombre = str(banco).replace("'", "''")
        nombre_corto = nombre.split(" (")[0]
        es_sistema = "TRUE" if nombre.lower().startswith("sistema") else "FALSE"
        statements.append(
            f"INSERT INTO instituciones (nombre_oficial, nombre_corto, es_sistema)\n"
            f"VALUES ('{nombre}', '{nombre_corto}', {es_sistema})\n"
            f"ON CONFLICT (nombre_oficial) DO NOTHING;"
        )

    statements.append("\n-- Metricas financieras")
    for _, row in df.iterrows():
        banco = str(row["institucion"]).replace("'", "''")
        if not banco or banco.lower() == "nan":
            continue

        def fmt(val):
            return "NULL" if pd.isna(val) else str(val)

        statements.append(
            "INSERT INTO metricas_financieras (\n"
            "    institucion_id, fecha_corte,\n"
            "    activo_total, inversiones_financieras, cartera_total,\n"
            "    captacion_total, capital_contable, resultado_neto,\n"
            "    roa_12m, roe_12m, imor, icor, perdida_esperada\n"
            ")\n"
            "VALUES (\n"
            f"    (SELECT id FROM instituciones WHERE nombre_oficial = '{banco}' LIMIT 1),\n"
            f"    '{row['fecha_corte']}',\n"
            f"    {fmt(row.get('activo_total'))}, {fmt(row.get('inversiones_financieras'))}, {fmt(row.get('cartera_total'))},\n"
            f"    {fmt(row.get('captacion_total'))}, {fmt(row.get('capital_contable'))}, {fmt(row.get('resultado_neto'))},\n"
            f"    {fmt(row.get('roa_12m'))}, {fmt(row.get('roe_12m'))},\n"
            f"    {fmt(row.get('imor'))}, {fmt(row.get('icor'))}, {fmt(row.get('perdida_esperada'))}\n"
            ")\n"
            "ON CONFLICT (institucion_id, fecha_corte) DO UPDATE SET\n"
            "    activo_total = EXCLUDED.activo_total,\n"
            "    inversiones_financieras = EXCLUDED.inversiones_financieras,\n"
            "    cartera_total = EXCLUDED.cartera_total,\n"
            "    captacion_total = EXCLUDED.captacion_total,\n"
            "    capital_contable = EXCLUDED.capital_contable,\n"
            "    resultado_neto = EXCLUDED.resultado_neto,\n"
            "    roa_12m = EXCLUDED.roa_12m,\n"
            "    roe_12m = EXCLUDED.roe_12m,\n"
            "    imor = EXCLUDED.imor,\n"
            "    icor = EXCLUDED.icor,\n"
            "    perdida_esperada = EXCLUDED.perdida_esperada;"
        )

    return "\n\n".join(statements)


def main():
    df = load_all_sheets(EXCEL_PATH)
    print(f"Registros totales: {len(df)}")
    sql_script = generate_sql(df)
    OUTPUT_SQL.write_text(sql_script, encoding="utf-8")
    print(f"Archivo generado: {OUTPUT_SQL}")


if __name__ == "__main__":
    main()
