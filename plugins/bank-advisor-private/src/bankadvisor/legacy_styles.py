"""
Módulo de layouts para convergencia PDF A → PDF B.

Implementa diseño dashboard denso con múltiples elementos por página,
siguiendo especificación de InformacionTablero.pdf.

Estructura:
- Dashboard 3 meses con tablas + gráficos de barras horizontales
- Gráficos de líneas temporales con tabla resumen
- Gráficos de barras apiladas 100% (Etapas IFRS 9)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import yaml
from pathlib import Path


# =============================================================================
# CONSTANTES Y CONFIGURACIÓN
# =============================================================================

SCALE_MM = 1_000_000  # Escala global para montos

# Cargar design tokens
def _load_design_tokens() -> dict:
    """Carga design tokens desde YAML."""
    tokens_path = Path(__file__).parent.parent / "config" / "design_tokens.yaml"
    with tokens_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)

DESIGN_TOKENS = _load_design_tokens()

# Colores según PDF B (S1-06 corregidos)
COLOR_INVEX = DESIGN_TOKENS["colores"]["invex"]["primario"]  # #E45756
COLOR_SISTEMA = DESIGN_TOKENS["colores"]["sistema"]["primario"]  # #AAB0B3
COLOR_ETAPA_1 = DESIGN_TOKENS["colores"]["riesgo"]["bajo"]  # #2E8B57 verde
COLOR_ETAPA_2 = DESIGN_TOKENS["colores"]["riesgo"]["moderado"]  # #FFD700 amarillo
COLOR_ETAPA_3 = DESIGN_TOKENS["colores"]["riesgo"]["alto"]  # #DC143C rojo


# =============================================================================
# FUNCIÓN 1: DASHBOARD 3 MESES (Páginas 1, 3, 5, 8-9, 11)
# =============================================================================

def create_dashboard_month_comparison(
    kpis_sistema: pd.DataFrame,
    kpis_invex: pd.DataFrame,
    section_config: dict,
    months: List[str],
    settings: dict
) -> plt.Figure:
    """
    Genera página dashboard con 3 meses en formato:
    [Tabla Mes1] [Gráfico Barras Mes1]
    [Tabla Mes2] [Gráfico Barras Mes2]
    [Tabla Mes3] [Gráfico Barras Mes3]

    Args:
        kpis_sistema: DataFrame con KPIs de todos los bancos del sistema
        kpis_invex: DataFrame con KPIs de INVEX
        section_config: Configuración de la sección (field, title, type, etc.)
        months: Lista de 3 meses a mostrar (ej: ["Oct/2024", "Nov/2024", "Dic/2024"])
        settings: Configuración global del reporte

    Returns:
        Figura de matplotlib con layout 3x2
    """
    # Crear figura con GridSpec
    fig = plt.figure(figsize=(8.5, 11))  # Carta vertical
    gs = gridspec.GridSpec(
        3, 2,
        figure=fig,
        height_ratios=[1, 1, 1],  # 3 meses iguales
        width_ratios=[1.2, 1],    # Tabla más ancha que gráfico
        hspace=0.12,
        wspace=0.25,
        left=0.08,
        right=0.96,
        top=0.94,
        bottom=0.05
    )

    # Título principal
    title = section_config.get("title", "")
    fig.suptitle(f"{title} Cuadro", fontsize=14, fontweight="bold", y=0.97)

    # Extraer campo de datos
    field = section_config.get("field")
    metric_type = section_config.get("type", "currency")

    # Renderizar cada mes
    for idx, month_label in enumerate(months):
        # Convertir label a periodo (ej: "Oct/2024" → "2024-10-01")
        month_period = _parse_month_label(month_label)

        # Obtener datos del mes
        month_data = _get_month_comparison_data(
            kpis_sistema, kpis_invex, field, month_period
        )

        if month_data is None:
            continue

        # Crear tabla (columna izquierda)
        ax_table = fig.add_subplot(gs[idx, 0])
        _render_comparison_table(
            ax_table, month_data, month_label, metric_type, section_config
        )

        # Crear gráfico de barras (columna derecha)
        ax_chart = fig.add_subplot(gs[idx, 1])
        _render_horizontal_bar_chart(
            ax_chart, month_data, month_label, metric_type, section_config
        )

    return fig


def _parse_month_label(month_label: str) -> pd.Timestamp:
    """
    Convierte label de mes a pd.Timestamp.

    Ejemplos:
        "Oct/2024" → Timestamp('2024-10-01')
        "04/2025" → Timestamp('2025-04-01')
    """
    import re

    # Formato "MM/YYYY"
    if re.match(r"^\d{2}/\d{4}$", month_label):
        month, year = month_label.split("/")
        return pd.Timestamp(f"{year}-{month}-01")

    # Formato "Mon/YYYY" (ej: "Oct/2024")
    month_map = {
        "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04",
        "May": "05", "Jun": "06", "Jul": "07", "Aug": "08",
        "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12"
    }
    for mon_name, mon_num in month_map.items():
        if month_label.startswith(mon_name):
            year = month_label.split("/")[1]
            return pd.Timestamp(f"{year}-{mon_num}-01")

    raise ValueError(f"No se pudo parsear month_label: {month_label}")


def _get_month_comparison_data(
    kpis_sistema: pd.DataFrame,
    kpis_invex: pd.DataFrame,
    field: str,
    month_period: pd.Timestamp
) -> Optional[pd.DataFrame]:
    """
    Obtiene datos de comparación para un mes específico.

    Returns:
        DataFrame con columnas: ['banco', 'valor_actual', 'valor_anterior', 'variacion_pct']
        Index: bancos ordenados por valor_actual descendente
    """
    # Filtrar datos del mes actual
    sistema_month = kpis_sistema[kpis_sistema.index == month_period]
    invex_month = kpis_invex[kpis_invex.index == month_period]

    if sistema_month.empty or invex_month.empty:
        return None

    # Obtener mes anterior (comparación año anterior mismo mes)
    month_anterior = month_period - pd.DateOffset(months=12)
    sistema_anterior = kpis_sistema[kpis_sistema.index == month_anterior]
    invex_anterior = kpis_invex[kpis_invex.index == month_anterior]

    # Extraer valores del campo específico
    try:
        if field not in sistema_month.columns:
            print(f"⚠️  Campo '{field}' no encontrado en kpis_sistema")
            return None

        # Extraer datos
        valor_sistema_actual = sistema_month[field].iloc[0] if not sistema_month.empty else 0
        valor_invex_actual = invex_month[field].iloc[0] if not invex_month.empty and field in invex_month.columns else 0
        valor_sistema_anterior = sistema_anterior[field].iloc[0] if not sistema_anterior.empty else valor_sistema_actual
        valor_invex_anterior = invex_anterior[field].iloc[0] if not invex_anterior.empty and field in invex_anterior.columns else valor_invex_actual

        # Crear lista de bancos con datos
        bancos_data = []

        # INVEX
        variacion_invex = ((valor_invex_actual - valor_invex_anterior) / valor_invex_anterior * 100) if valor_invex_anterior != 0 else 0
        bancos_data.append({
            "banco": "INVEX",
            "valor_actual": valor_invex_actual,
            "valor_anterior": valor_invex_anterior,
            "variacion_pct": variacion_invex
        })

        # Sistema Promedio (representando al resto de bancos)
        variacion_sistema = ((valor_sistema_actual - valor_sistema_anterior) / valor_sistema_anterior * 100) if valor_sistema_anterior != 0 else 0
        bancos_data.append({
            "banco": "Sistema Promedio",
            "valor_actual": valor_sistema_actual,
            "valor_anterior": valor_sistema_anterior,
            "variacion_pct": variacion_sistema
        })

        # Crear DataFrame
        df = pd.DataFrame(bancos_data)

        # Ordenar por valor actual descendente
        df = df.sort_values("valor_actual", ascending=False).reset_index(drop=True)

        return df

    except Exception as e:
        print(f"❌ Error en _get_month_comparison_data: {e}")
        import traceback
        traceback.print_exc()
        return None


def _render_comparison_table(
    ax: plt.Axes,
    data: pd.DataFrame,
    month_label: str,
    metric_type: str,
    section_config: dict
) -> None:
    """
    Renderiza tabla de comparación en el eje dado.

    Columnas:
    - Bancos
    - 2024 [Mes] (año anterior)
    - 2025 [Mes] (año actual)
    - % Variación
    """
    ax.axis("off")

    # Formatear valores según tipo
    if metric_type == "currency":
        fmt_func = lambda x: f"${x/1000:,.0f}"  # Miles de MM MXN
        col_labels = ["Bancos", f"2024\n{month_label}", f"2025\n{month_label}", "% Variación"]
    else:  # ratio/percentage
        fmt_func = lambda x: f"{x:.2f}%"
        col_labels = ["Bancos", f"2024\n{month_label}", f"2025\n{month_label}", "% Variación"]

    # Preparar datos de tabla
    table_data = []
    for _, row in data.iterrows():
        banco = row["banco"]
        val_ant = fmt_func(row["valor_anterior"]) if metric_type == "currency" else f"{row['valor_anterior']:.2f}"
        val_act = fmt_func(row["valor_actual"]) if metric_type == "currency" else f"{row['valor_actual']:.2f}"
        var_pct = f"{row['variacion_pct']:.2f}%"
        table_data.append([banco, val_ant, val_act, var_pct])

    # Crear tabla
    table = ax.table(
        cellText=table_data,
        colLabels=col_labels,
        cellLoc="right",
        loc="center",
        colWidths=[0.4, 0.2, 0.2, 0.2]
    )

    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.8)

    # Estilizar header
    for col_idx in range(len(col_labels)):
        cell = table[(0, col_idx)]
        cell.set_facecolor("#ECF0F1")
        cell.set_text_props(weight="bold", fontsize=10)

    # Destacar INVEX en rojo
    for row_idx, (_, row) in enumerate(data.iterrows(), start=1):
        if row["banco"] == "INVEX":
            for col_idx in range(len(col_labels)):
                cell = table[(row_idx, col_idx)]
                cell.set_text_props(color=COLOR_INVEX, weight="bold")

    # Título de la tabla
    ax.text(
        0.5, 0.98,
        section_config.get("title", "Métrica"),
        ha="center", va="top",
        fontsize=11, fontweight="bold",
        transform=ax.transAxes
    )
    ax.text(
        0.5, 0.93,
        "(Cifras en millones de pesos)",
        ha="center", va="top",
        fontsize=8, color="#7F8C8D",
        transform=ax.transAxes
    )


def _render_horizontal_bar_chart(
    ax: plt.Axes,
    data: pd.DataFrame,
    month_label: str,
    metric_type: str,
    section_config: dict
) -> None:
    """
    Renderiza gráfico de barras horizontales mostrando % diferencia.

    INVEX destacado en rojo, resto en gris.
    """
    # Ordenar por variación (para coincidir con tabla)
    data_sorted = data.sort_values("variacion_pct", ascending=True)

    # Colores: INVEX rojo, resto gris
    colors = [COLOR_INVEX if banco == "INVEX" else COLOR_SISTEMA
              for banco in data_sorted["banco"]]

    # Crear barras horizontales
    y_pos = np.arange(len(data_sorted))
    ax.barh(y_pos, data_sorted["variacion_pct"], color=colors, alpha=0.85)

    # Configurar ejes
    ax.set_yticks(y_pos)
    ax.set_yticklabels(data_sorted["banco"], fontsize=9)
    ax.set_xlabel("% Diferencia en " + section_config.get("title", "Métrica"), fontsize=10)
    ax.set_title(
        f"{section_config.get('title', 'Métrica')}\n(Variación respecto al periodo\nseleccionado)",
        fontsize=10,
        pad=10
    )

    # Grid sutil
    ax.grid(axis="x", linestyle="--", alpha=0.3, linewidth=0.5)
    ax.set_axisbelow(True)

    # Formato de eje X (porcentajes)
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"{x:.0f}%"))

    # Etiquetas de valor al final de cada barra
    for idx, (i, row) in enumerate(data_sorted.iterrows()):
        value = row["variacion_pct"]
        ax.text(
            value + (2 if value > 0 else -2),
            idx,
            f"{value:.2f}%",
            va="center",
            ha="left" if value > 0 else "right",
            fontsize=8,
            fontweight="bold" if row["banco"] == "INVEX" else "normal",
            color=COLOR_INVEX if row["banco"] == "INVEX" else "#2C3E50"
        )

    # Línea vertical en 0
    ax.axvline(0, color="#2C3E50", linewidth=1, linestyle="-", alpha=0.6)

    # Remover spines superiores y derechos
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


# =============================================================================
# FUNCIÓN 2: GRÁFICO DE BARRAS HORIZONTALES STANDALONE (Páginas 8, 10, 12, 14)
# =============================================================================

def create_horizontal_bar_chart(
    ax: plt.Axes,
    data: pd.Series,
    title: str,
    subtitle: Optional[str] = None,
    invex_highlight: bool = True,
    show_average_line: bool = True,
    value_format: str = "percent",
    xlabel: Optional[str] = None
) -> None:
    """
    Genera gráfico de barras horizontales standalone con:
    - INVEX destacado en rojo
    - Resto en gris
    - Línea vertical de promedio (opcional)
    - Etiquetas de valor al final de cada barra

    Args:
        ax: Eje de matplotlib donde renderizar
        data: Serie con Index=bancos, Values=valores
        title: Título del gráfico
        subtitle: Subtítulo opcional
        invex_highlight: Si True, destaca INVEX en rojo
        show_average_line: Si True, muestra línea de promedio
        value_format: "percent", "currency", "ratio"
        xlabel: Etiqueta del eje X (opcional)

    Usado en:
        - Página 8: Reservas Totales (promedio)
        - Página 10: IMOR Cuadro
        - Página 12: ICOR Cuadro
        - Página 14: ICAP Cuadro
    """
    # Ordenar datos
    data_sorted = data.sort_values(ascending=True)

    # Colores
    colors = []
    for banco in data_sorted.index:
        if invex_highlight and "INVEX" in banco.upper():
            colors.append(COLOR_INVEX)
        else:
            colors.append(COLOR_SISTEMA)

    # Crear barras
    y_pos = np.arange(len(data_sorted))
    ax.barh(y_pos, data_sorted.values, color=colors, alpha=0.85, height=0.7)

    # Configurar ejes
    ax.set_yticks(y_pos)
    ax.set_yticklabels(data_sorted.index, fontsize=9)

    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10)

    # Título
    title_full = title
    if subtitle:
        title_full += f"\n{subtitle}"
    ax.set_title(title_full, fontsize=11, fontweight="bold", pad=12)

    # Grid
    ax.grid(axis="x", linestyle="--", alpha=0.3, linewidth=0.5)
    ax.set_axisbelow(True)

    # Formato de valores
    if value_format == "percent":
        formatter = mticker.FuncFormatter(lambda x, p: f"{x:.2f}%")
    elif value_format == "currency":
        formatter = mticker.FuncFormatter(lambda x, p: f"${x:,.0f}")
    else:  # ratio
        formatter = mticker.FuncFormatter(lambda x, p: f"{x:.2f}")

    ax.xaxis.set_major_formatter(formatter)

    # Etiquetas de valor
    for idx, (banco, value) in enumerate(data_sorted.items()):
        is_invex = invex_highlight and "INVEX" in banco.upper()

        if value_format == "percent":
            label_text = f"{value:.2f}%"
        elif value_format == "currency":
            label_text = f"${value:,.0f}"
        else:
            label_text = f"{value:.2f}"

        ax.text(
            value + (data_sorted.max() * 0.02),
            idx,
            label_text,
            va="center",
            ha="left",
            fontsize=8,
            fontweight="bold" if is_invex else "normal",
            color=COLOR_INVEX if is_invex else "#2C3E50"
        )

    # Línea de promedio
    if show_average_line:
        avg = data_sorted.mean()
        ax.axvline(avg, color="#E67E22", linewidth=2, linestyle="--", alpha=0.7)

        # Etiqueta de promedio
        label_avg = f"Promedio = {avg:.2f}%" if value_format == "percent" else f"Promedio = {avg:.2f}"
        ax.text(
            avg,
            len(data_sorted) * 1.02,
            label_avg,
            ha="center",
            fontsize=9,
            color="#E67E22",
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor="#E67E22", linewidth=1.5)
        )

    # Remover spines
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


# =============================================================================
# FUNCIÓN 3: GRÁFICO DE BARRAS APILADAS 100% (Página 13 - Etapas Deterioro)
# =============================================================================

def create_stacked_bar_100(
    ax: plt.Axes,
    data: pd.DataFrame,
    title: str = "Cartera total por etapas",
    subtitle: Optional[str] = None
) -> None:
    """
    Genera gráfico de barras apiladas al 100% para Etapas IFRS 9.

    Args:
        ax: Eje de matplotlib donde renderizar
        data: DataFrame con columnas ['Etapa 1', 'Etapa 2', 'Etapa 3']
              Index: bancos
              Valores: Porcentajes (deben sumar ~100%)
        title: Título del gráfico
        subtitle: Subtítulo opcional

    Colores:
        - Verde (#2E8B57): Etapa 1
        - Amarillo (#FFD700): Etapa 2
        - Rojo (#DC143C): Etapa 3

    Usado en:
        - Página 13: Etapas Deterioro
    """
    # Validar que data suma ~100%
    row_sums = data.sum(axis=1)
    if not np.allclose(row_sums, 100, atol=1.0):
        print(f"⚠️  Advertencia: Etapas no suman 100%: {row_sums.tolist()}")

    # Colores por etapa
    colors = [COLOR_ETAPA_1, COLOR_ETAPA_2, COLOR_ETAPA_3]

    # Ordenar bancos (INVEX al final para destacar)
    data_sorted = data.copy()
    if "INVEX" in data.index:
        invex_row = data_sorted.loc["INVEX"]
        data_sorted = data_sorted.drop("INVEX")
        data_sorted = pd.concat([data_sorted, invex_row.to_frame().T])

    # Crear barras apiladas
    x_pos = np.arange(len(data_sorted))
    bottom = np.zeros(len(data_sorted))

    for idx, (col, color) in enumerate(zip(data_sorted.columns, colors)):
        values = data_sorted[col].values
        bars = ax.bar(x_pos, values, bottom=bottom, color=color,
                      alpha=0.9, label=col, edgecolor="white", linewidth=1.5)

        # Etiquetas de porcentaje en cada segmento
        for bar_idx, (bar, value) in enumerate(zip(bars, values)):
            if value > 3:  # Solo mostrar si segmento > 3%
                height = bar.get_height()
                y_pos = bar.get_y() + height / 2
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    y_pos,
                    f"{value:.2f}%",
                    ha="center",
                    va="center",
                    fontsize=8,
                    fontweight="bold",
                    color="white" if idx == 2 else "#2C3E50"  # Blanco en rojo
                )

        bottom += values

    # Configurar ejes
    ax.set_xticks(x_pos)
    ax.set_xticklabels(data_sorted.index, rotation=45, ha="right", fontsize=9)
    ax.set_ylabel("Prom. CT Etapa", fontsize=10)

    # Título
    title_full = title
    if subtitle:
        title_full += f"\n{subtitle}"
    ax.set_title(title_full, fontsize=11, fontweight="bold", pad=12)

    # Formato de eje Y
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"{x:.0f}"))
    ax.set_ylim(0, 1.0)  # 0-100% normalizado a 0-1

    # Leyenda
    ax.legend(
        loc="upper right",
        fontsize=9,
        framealpha=0.9,
        edgecolor="#BDC3C7"
    )

    # Grid horizontal sutil
    ax.grid(axis="y", linestyle="--", alpha=0.3, linewidth=0.5)
    ax.set_axisbelow(True)

    # Destacar INVEX con borde más grueso
    if "INVEX" in data_sorted.index:
        invex_idx = list(data_sorted.index).index("INVEX")
        # Agregar rectángulo de borde
        rect = plt.Rectangle(
            (invex_idx - 0.4, 0),
            0.8,
            100,
            fill=False,
            edgecolor=COLOR_INVEX,
            linewidth=3,
            linestyle="--"
        )
        ax.add_patch(rect)

    # Remover spines superiores
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


# =============================================================================
# FUNCIÓN 4: GRÁFICO DE LÍNEAS TEMPORAL CON TABLA (Página 2, 4, 6, etc.)
# =============================================================================

def create_timeline_chart_with_summary(
    kpis_sistema: pd.DataFrame,
    kpis_invex: pd.DataFrame,
    section_config: dict,
    months_summary: List[str],
    settings: dict
) -> plt.Figure:
    """
    Genera página con:
    - Tabla resumen arriba (últimos 3 meses)
    - Gráfico de líneas temporal abajo (rango amplio)

    Args:
        kpis_sistema: DataFrame con KPIs del sistema
        kpis_invex: DataFrame con KPIs de INVEX
        section_config: Configuración de la sección
        months_summary: Lista de meses para tabla resumen
        settings: Configuración global

    Returns:
        Figura de matplotlib con layout 2x1
    """
    # Crear figura con GridSpec
    fig = plt.figure(figsize=(8.5, 11))
    gs = gridspec.GridSpec(
        2, 1,
        figure=fig,
        height_ratios=[0.25, 0.75],  # Tabla pequeña, gráfico grande
        hspace=0.15,
        left=0.08,
        right=0.96,
        top=0.94,
        bottom=0.05
    )

    # Título principal
    title = section_config.get("title", "")
    fig.suptitle(f"{title} Gráfica", fontsize=14, fontweight="bold", y=0.97)

    # Parte superior: Tabla resumen
    ax_table = fig.add_subplot(gs[0, 0])
    _render_summary_table(
        ax_table, kpis_sistema, kpis_invex, section_config, months_summary
    )

    # Parte inferior: Gráfico de líneas temporal
    ax_chart = fig.add_subplot(gs[1, 0])
    _render_temporal_line_chart(
        ax_chart, kpis_sistema, kpis_invex, section_config
    )

    return fig


def _render_summary_table(
    ax: plt.Axes,
    kpis_sistema: pd.DataFrame,
    kpis_invex: pd.DataFrame,
    section_config: dict,
    months_summary: List[str]
) -> None:
    """
    Renderiza tabla resumen con últimos 3 meses.

    Formato:
    | Banco        | Oct 2024 | Nov 2024 | Dic 2024 |
    | INVEX        |   X.XX   |   X.XX   |   X.XX   |
    | Prom. Sistema|   X.XX   |   X.XX   |   X.XX   |
    """
    ax.axis("off")

    field = section_config.get("field")
    metric_type = section_config.get("type", "currency")
    unit = section_config.get("unit", "")
    decimals = section_config.get("decimals", 2)

    if field not in kpis_invex.columns or field not in kpis_sistema.columns:
        ax.text(0.5, 0.5, f"Datos no disponibles: {field}",
                ha="center", va="center", fontsize=10, color="red")
        return

    # Extraer últimos 3 meses disponibles
    last_3_months_invex = kpis_invex[field].tail(3)
    last_3_months_sistema = kpis_sistema[field].tail(3)

    # Formatear valores según tipo de métrica
    def format_value(val, metric_type, decimals):
        if pd.isna(val):
            return "N/A"
        if metric_type == "currency":
            # Convertir a MM MXN si es necesario
            return f"{val:,.{decimals}f}"
        elif metric_type == "ratio":
            # Mostrar como porcentaje
            return f"{val * 100:.{decimals}f}%"
        else:
            return f"{val:,.{decimals}f}"

    # Construir datos de tabla
    table_data = []

    # Encabezados
    headers = ["Banco"] + months_summary
    table_data.append(headers)

    # Fila INVEX
    invex_row = ["INVEX"]
    for val in last_3_months_invex.values:
        invex_row.append(format_value(val, metric_type, decimals))
    table_data.append(invex_row)

    # Fila Sistema Promedio
    sistema_row = ["Prom. Sistema"]
    for val in last_3_months_sistema.values:
        sistema_row.append(format_value(val, metric_type, decimals))
    table_data.append(sistema_row)

    # Crear tabla con matplotlib
    table = ax.table(
        cellText=table_data,
        cellLoc="center",
        loc="center",
        bbox=[0, 0, 1, 1]
    )

    # Estilo de tabla
    table.auto_set_font_size(False)
    table.set_fontsize(9)

    # Estilos por celda
    for i, row in enumerate(table_data):
        for j, _ in enumerate(row):
            cell = table[(i, j)]

            # Encabezado
            if i == 0:
                cell.set_facecolor("#34495E")
                cell.set_text_props(weight="bold", color="white")
                cell.set_height(0.15)
            # Fila INVEX
            elif i == 1:
                if j == 0:
                    cell.set_facecolor("#FADBD8")  # Rojo claro
                    cell.set_text_props(weight="bold", color="#E45756")
                else:
                    cell.set_facecolor("#FEF5E7")
                    cell.set_text_props(color="#2C3E50")
                cell.set_height(0.12)
            # Fila Sistema
            else:
                if j == 0:
                    cell.set_facecolor("#E8EAED")  # Gris claro
                    cell.set_text_props(weight="bold", color="#5F6A6A")
                else:
                    cell.set_facecolor("#F8F9F9")
                    cell.set_text_props(color="#2C3E50")
                cell.set_height(0.12)

            cell.set_edgecolor("#BDC3C7")
            cell.set_linewidth(1.5)

    # Título pequeño encima de la tabla
    ax.text(0.5, 1.05, f"Resumen {unit}",
            ha="center", va="bottom", fontsize=10, fontweight="bold",
            transform=ax.transAxes)


def _render_temporal_line_chart(
    ax: plt.Axes,
    kpis_sistema: pd.DataFrame,
    kpis_invex: pd.DataFrame,
    section_config: dict
) -> None:
    """
    Renderiza gráfico de líneas temporal con doble eje Y.

    Serie 1 (INVEX): Rojo sólido, eje izquierdo
    Serie 2 (Sistema): Gris sólido, eje derecho
    """
    field = section_config.get("field")
    metric_type = section_config.get("type", "currency")

    # Extraer series
    invex_series = kpis_invex[field] if field in kpis_invex.columns else None
    sistema_series = kpis_sistema[field] if field in kpis_sistema.columns else None

    if invex_series is None or sistema_series is None:
        ax.text(0.5, 0.5, f"Datos no disponibles para campo: {field}",
                ha="center", va="center", fontsize=12, color="red")
        return

    # Filtrar fechas comunes
    common_dates = invex_series.index.intersection(sistema_series.index)
    invex_filtered = invex_series.loc[common_dates]
    sistema_filtered = sistema_series.loc[common_dates]

    # Eje izquierdo: INVEX (rojo)
    line1 = ax.plot(
        invex_filtered.index,
        invex_filtered.values,
        color=COLOR_INVEX,
        linestyle="-",  # Sólida
        linewidth=2.0,
        label=f"Invex {section_config.get('title', '')}",
        alpha=1.0,
        zorder=3
    )
    ax.set_ylabel(
        f"Invex {section_config.get('title', '')}",
        fontsize=11,
        color=COLOR_INVEX
    )
    ax.tick_params(axis="y", labelcolor=COLOR_INVEX)

    # Formato eje Y izquierdo
    if metric_type == "currency":
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x/1000:,.0f}"))
    else:  # ratio
        ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"{x:.2f}%"))

    # Eje derecho: Sistema (gris)
    ax2 = ax.twinx()
    line2 = ax2.plot(
        sistema_filtered.index,
        sistema_filtered.values,
        color=COLOR_SISTEMA,
        linestyle="-",  # Sólida (S1-06 corregido)
        linewidth=2.0,
        label=f"Prom. {section_config.get('title', '')}",
        alpha=0.85,
        zorder=2
    )
    ax2.set_ylabel(
        f"Prom. {section_config.get('title', '')}",
        fontsize=11,
        color=COLOR_SISTEMA
    )
    ax2.tick_params(axis="y", labelcolor=COLOR_SISTEMA)

    # Formato eje Y derecho
    if metric_type == "currency":
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"${x/1000:,.0f}"))
    else:
        ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, p: f"{x:.2f}%"))

    # Título del gráfico (S0-05: título contextual, NO "Evolución Cartera Total")
    ax.set_title(
        f"Evolución {section_config.get('title', '')}",  # Contextual
        fontsize=12,
        fontweight="bold",
        pad=15
    )

    # Grid sutil
    ax.grid(axis="y", linestyle="--", alpha=0.3, linewidth=0.5, color="#E0E0E0")
    ax.set_axisbelow(True)

    # Leyenda combinada
    lines = line1 + line2
    labels = [line.get_label() for line in lines]
    ax.legend(lines, labels, loc="upper left", fontsize=10, framealpha=0.9)

    # Formato eje X (fechas)
    ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%m/%Y"))
    fig = ax.get_figure()
    fig.autofmt_xdate(rotation=45, ha="right")

    # Remover spines superiores
    ax.spines["top"].set_visible(False)
    ax2.spines["top"].set_visible(False)


# =============================================================================
# FUNCIONES AUXILIARES
# =============================================================================

def format_value(value: float, format_type: str) -> str:
    """
    Formatea valor según tipo.

    Args:
        value: Valor numérico
        format_type: "currency", "percent", "ratio"

    Returns:
        String formateado
    """
    if format_type == "currency":
        return f"${value/1000:,.0f}"  # Miles de MM MXN
    elif format_type == "percent":
        return f"{value:.2f}%"
    else:  # ratio
        return f"{value:.2f}"
