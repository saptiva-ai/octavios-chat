"""
AnalyticsService - Servicio de consultas de métricas bancarias

Cambios de Seguridad (24 Nov 2025):
- Whitelist explícita de columnas válidas (SAFE_METRIC_COLUMNS)
- Validación guard clause (_get_safe_column)
- Manejo de errores con HTTPException
- Logging estructurado de seguridad
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from fastapi import HTTPException
from bankadvisor.models.kpi import MonthlyKPI
from typing import Dict, Any, List, Optional
import difflib
import structlog

logger = structlog.get_logger(__name__)


class AnalyticsService:

    # =========================================================================
    # SECURITY: WHITELIST DE COLUMNAS VÁLIDAS
    # =========================================================================
    # Mapeo explícito de nombres de métricas a objetos Column de SQLAlchemy.
    # Previene inyección de atributos vía getattr().
    # Cualquier métrica no listada aquí será rechazada con error 400.

    SAFE_METRIC_COLUMNS = {
        # Carteras
        "cartera_total": MonthlyKPI.cartera_total,
        "cartera_comercial_total": MonthlyKPI.cartera_comercial_total,
        "cartera_comercial_sin_gob": "CALCULATED",  # Special: calculated field
        "cartera_consumo_total": MonthlyKPI.cartera_consumo_total,
        "cartera_vivienda_total": MonthlyKPI.cartera_vivienda_total,
        "entidades_gubernamentales_total": MonthlyKPI.entidades_gubernamentales_total,
        "entidades_financieras_total": MonthlyKPI.entidades_financieras_total,
        "empresarial_total": MonthlyKPI.empresarial_total,

        # Calidad de Cartera
        "cartera_vencida": MonthlyKPI.cartera_vencida,
        "imor": MonthlyKPI.imor,
        "icor": MonthlyKPI.icor,

        # Reservas
        "reservas_etapa_todas": MonthlyKPI.reservas_etapa_todas,

        # Tasas (nullable)
        "tasa_mn": MonthlyKPI.tasa_mn,
        "tasa_me": MonthlyKPI.tasa_me,
        "icap_total": MonthlyKPI.icap_total,
        "tda_cartera_total": MonthlyKPI.tda_cartera_total,
    }

    # =========================================================================
    # NLP TOPIC MAP (sin cambios)
    # =========================================================================
    # Mapa de "Frases de Usuario" -> "Columna Real en monthly_kpis"

    TOPIC_MAP = {
        "cartera total": "cartera_total",
        "cartera": "cartera_total",
        "total": "cartera_total",

        "cartera comercial": "cartera_comercial_total",
        "comercial": "cartera_comercial_total",

        "cartera comercial sin gobierno": "cartera_comercial_sin_gob",
        "comercial sin gob": "cartera_comercial_sin_gob",
        "cartera comercial privada": "cartera_comercial_sin_gob",

        "cartera gobierno": "entidades_gubernamentales_total",
        "gobierno": "entidades_gubernamentales_total",

        "cartera consumo": "cartera_consumo_total",
        "consumo": "cartera_consumo_total",

        "cartera vivienda": "cartera_vivienda_total",
        "vivienda": "cartera_vivienda_total",

        "empresarial": "empresarial_total",
        "entidades financieras": "entidades_financieras_total",

        "imor": "imor",
        "morosidad": "imor",

        "icor": "icor",
        "cobertura": "icor",

        "reservas": "reservas_etapa_todas",
        "cartera vencida": "cartera_vencida",
        "vencida": "cartera_vencida",

        # Capitalización y Tasas (agregadas Phase 4)
        "icap": "icap_total",
        "icap_total": "icap_total",  # Direct mapping for legacy flow
        "capitalización": "icap_total",
        "capitalizacion": "icap_total",
        "capital": "icap_total",

        "tda": "tda_cartera_total",
        "tda_cartera_total": "tda_cartera_total",  # Direct mapping for legacy flow
        "deterioro": "tda_cartera_total",
        "tasa deterioro": "tda_cartera_total",

        "tasa_mn": "tasa_mn",
        "tasa mn": "tasa_mn",
        "tasa pesos": "tasa_mn",

        "tasa_me": "tasa_me",
        "tasa me": "tasa_me",
        "tasa dolares": "tasa_me"
    }

    @staticmethod
    def resolve_metric_id(user_query: str) -> Optional[str]:
        """
        Resuelve una query de usuario a un nombre de columna válido.

        Estrategia:
        1. Match exacto en TOPIC_MAP
        2. Match parcial (substring)
        3. Fuzzy matching (cutoff 0.6)

        Args:
            user_query: Query del usuario (ej: "cartera comercial")

        Returns:
            Nombre de columna o None si no hay match
        """
        query_lower = user_query.lower()

        # 1. Match exacto
        if query_lower in AnalyticsService.TOPIC_MAP:
            return AnalyticsService.TOPIC_MAP[query_lower]

        # 2. Match parcial - SECURITY: La query debe contener TODAS las palabras del keyword
        # Evita que "cartera_fake_column" haga match con "cartera"
        for key, value in AnalyticsService.TOPIC_MAP.items():
            # Match si el keyword está completamente dentro de la query
            # y tienen longitud similar (±30%)
            if key in query_lower:
                # Security check: Prevenir matches espurios por substring corto
                # Ejemplo: "cartera" NO debe matchear "cartera_sql_injection_here"
                if len(key) >= len(query_lower) * 0.7:
                    return value

        # 3. Fuzzy matching - SECURITY: Cutoff más estricto (0.8 en vez de 0.6)
        matches = difflib.get_close_matches(
            query_lower,
            AnalyticsService.TOPIC_MAP.keys(),
            n=1,
            cutoff=0.8  # Más estricto: requiere 80% de similitud
        )
        if matches:
            return AnalyticsService.TOPIC_MAP[matches[0]]

        return None

    @staticmethod
    def _get_safe_column(metric_name: str):
        """
        SECURITY GUARD: Valida que la métrica esté en la whitelist.

        Pattern: Guard Clause / Whitelist Validation

        Previene:
        - Inyección de atributos vía getattr()
        - Acceso a metadatos internos de SQLAlchemy (__class__, metadata, etc.)
        - DoS por atributos inexistentes

        Args:
            metric_name: Nombre de columna (ej: "cartera_total")

        Returns:
            Column object de SQLAlchemy

        Raises:
            ValueError: Si la métrica no está en la whitelist

        Example:
            >>> _get_safe_column("cartera_total")  # OK
            >>> _get_safe_column("__class__")  # ValueError
        """
        if metric_name not in AnalyticsService.SAFE_METRIC_COLUMNS:
            # Security logging - alerta de intento de acceso no autorizado
            logger.warning(
                "security.metric_validation_failed",
                metric=metric_name,
                valid_metrics_sample=list(AnalyticsService.SAFE_METRIC_COLUMNS.keys())[:5],
                total_valid_metrics=len(AnalyticsService.SAFE_METRIC_COLUMNS)
            )

            # Error amigable al usuario con sugerencias
            valid_sample = list(AnalyticsService.SAFE_METRIC_COLUMNS.keys())[:5]
            raise ValueError(
                f"Métrica '{metric_name}' no está autorizada. "
                f"Métricas válidas incluyen: {', '.join(valid_sample)}, etc. "
                f"Total de métricas disponibles: {len(AnalyticsService.SAFE_METRIC_COLUMNS)}"
            )

        return AnalyticsService.SAFE_METRIC_COLUMNS[metric_name]

    @staticmethod
    async def get_dashboard_data(
        session: AsyncSession,
        metric_or_query: str,
        mode: str = "dashboard"
    ) -> Dict[str, Any]:
        """
        Obtiene datos de dashboard con validación de seguridad.

        Security Improvements (24 Nov 2025):
        - Whitelist validation antes de acceder a columnas
        - Try/except con manejo granular de errores (400/503/500)
        - Logging estructurado para auditoría
        - Mensajes de error user-friendly

        Args:
            session: Sesión async de SQLAlchemy
            metric_or_query: Nombre de métrica o query de usuario
            mode: Modo de visualización (dashboard/timeline)

        Returns:
            Dict con datos formateados para Plotly

        Raises:
            HTTPException(400): Métrica no válida
            HTTPException(503): Error de base de datos
            HTTPException(500): Error inesperado

        Example:
            >>> data = await get_dashboard_data(session, "cartera comercial")
            >>> data["title"]
            "Cartera Comercial Total"
        """
        try:
            # 1. Resolver ID con NLP
            metric_column = AnalyticsService.resolve_metric_id(metric_or_query)

            # SECURITY: Si el NLP no puede resolver, rechazar directamente
            # No permitir fallback a metric_or_query sin validación NLP
            if metric_column is None:
                logger.warning(
                    "security.nlp_resolution_failed",
                    query=metric_or_query,
                    reason="No match in TOPIC_MAP"
                )
                raise ValueError(
                    f"No se pudo identificar la métrica '{metric_or_query}'. "
                    f"Por favor, usa términos como: 'cartera comercial', 'IMOR', 'ICOR', etc."
                )

            final_column_name = metric_column

            # 2. SECURITY: Validación de whitelist (reemplaza getattr vulnerable)
            safe_column = AnalyticsService._get_safe_column(final_column_name)

            logger.info(
                "analytics.query_started",
                metric=final_column_name,
                original_query=metric_or_query,
                mode=mode
            )

            # 3. Obtener fecha de corte (Data As Of)
            date_query = select(func.max(MonthlyKPI.fecha))
            date_result = await session.execute(date_query)
            max_date = date_result.scalar()
            data_as_of = max_date.strftime("%d/%m/%Y") if max_date else "N/A"

            # 4. Consulta SQL con columna validada
            query = (
                select(MonthlyKPI.fecha, MonthlyKPI.banco_norm, safe_column)
                .order_by(MonthlyKPI.fecha.asc())
            )

            result = await session.execute(query)
            rows = result.fetchall()

            logger.info(
                "analytics.query_completed",
                metric=final_column_name,
                rows_returned=len(rows),
                data_as_of=data_as_of
            )

            # 5. Procesar resultados
            data_by_month = {}

            for row in rows:
                date_str = row.fecha.strftime("%Y-%m") if row.fecha else "N/A"
                banco = row.banco_norm
                val = row[2]

                if date_str not in data_by_month:
                    data_by_month[date_str] = []

                # Handle NULL values: skip records with NULL metric values
                # This prevents "unsupported format string passed to NoneType" errors
                if val is None:
                    continue

                # Normalizar ratios a porcentaje
                if final_column_name in ["imor", "icor"]:
                    val = val * 100 if val else 0

                data_by_month[date_str].append({
                    "category": banco,
                    "value": val
                })

            chart_data = [
                {"month_label": k, "data": v}
                for k, v in data_by_month.items()
            ]

            return {
                "title": final_column_name.replace("_", " ").title(),
                "layout_type": "dashboard_month_comparison",
                "period": "Historico",
                "data_as_of": data_as_of,
                "chart_props": {
                    "colors": ["rose", "slate"],
                    "valueFormatter": (
                        "(number) => `${number.toFixed(2)}%`"
                        if final_column_name in ["imor", "icor"]
                        else "(number) => `$${Intl.NumberFormat('us', {notation: 'compact'}).format(number)}`"
                    )
                },
                "data": {
                    "months": chart_data
                }
            }

        except ValueError as ve:
            # Error de validación de negocio (400 Bad Request)
            # Incluye: métrica no válida, parámetros incorrectos
            logger.info(
                "analytics.validation_error",
                metric=metric_or_query,
                error=str(ve),
                error_type="ValueError"
            )
            raise HTTPException(
                status_code=400,
                detail=str(ve)
            )

        except SQLAlchemyError as db_err:
            # Error de base de datos (503 Service Unavailable)
            # Incluye: conexión perdida, timeout, constraint violations
            logger.error(
                "analytics.database_error",
                metric=metric_or_query,
                error=str(db_err),
                error_type=type(db_err).__name__
            )
            raise HTTPException(
                status_code=503,
                detail=(
                    "El servicio de datos bancarios no está disponible temporalmente. "
                    "Por favor, intente nuevamente en unos momentos."
                )
            )

        except Exception as e:
            # Catch-all para errores inesperados (500 Internal Server Error)
            # Esto NO debería ocurrir en operación normal
            logger.error(
                "analytics.unexpected_error",
                metric=metric_or_query,
                error=str(e),
                error_type=type(e).__name__
            )
            raise HTTPException(
                status_code=500,
                detail=(
                    "Error interno procesando el análisis. "
                    "El equipo técnico ha sido notificado."
                )
            )

    # =========================================================================
    # HU3: NLP QUERY FILTERING AND FORMATTING
    # =========================================================================

    @staticmethod
    async def get_filtered_data(
        session: AsyncSession,
        metric_id: str,
        banks: List[str] = None,
        date_start=None,
        date_end=None,
        intent: str = "evolution"
    ) -> Dict[str, Any]:
        """
        Get metric data with filters for HU3 NLP pipeline.
        Production-grade: parameterized queries, proper error handling.

        Args:
            session: AsyncSession for database queries
            metric_id: Metric identifier (e.g., 'imor', 'cartera_total')
            banks: List of bank names to filter (or None for all)
            date_start: Start date for filtering
            date_end: End date for filtering
            intent: Query intent for response formatting

        Returns:
            Dict with data, visualization config, and metadata
        """
        from bankadvisor.config_service import get_config
        config = get_config()

        column_name = config.get_metric_column(metric_id)

        if not column_name:
            return {
                "type": "error",
                "message": f"Métrica desconocida: {metric_id}",
                "available_metrics": [m["label"] for m in config.get_all_metric_options()[:5]]
            }

        # Validate column exists in whitelist
        if column_name not in AnalyticsService.SAFE_METRIC_COLUMNS:
            logger.warning(
                "analytics.filtered_data.invalid_column",
                metric_id=metric_id,
                column_name=column_name
            )
            return {
                "type": "error",
                "message": f"Métrica '{metric_id}' no está autorizada"
            }

        metric_column = AnalyticsService.SAFE_METRIC_COLUMNS[column_name]

        try:
            # Build query - handle calculated fields
            if column_name == "cartera_comercial_sin_gob":
                # Special case: Cartera Comercial - Entidades Gubernamentales
                calculated_value = (
                    MonthlyKPI.cartera_comercial_total -
                    func.coalesce(MonthlyKPI.entidades_gubernamentales_total, 0)
                ).label('value')
                query = select(
                    MonthlyKPI.fecha,
                    MonthlyKPI.banco_norm,
                    calculated_value
                )
            else:
                # Standard column query
                query = select(
                    MonthlyKPI.fecha,
                    MonthlyKPI.banco_norm,
                    metric_column.label('value')
                )

            # Apply filters
            if banks and len(banks) > 0:
                query = query.where(MonthlyKPI.banco_norm.in_(banks))

            if date_start:
                query = query.where(MonthlyKPI.fecha >= date_start)

            if date_end:
                query = query.where(MonthlyKPI.fecha <= date_end)

            # Order by date
            query = query.order_by(MonthlyKPI.fecha.asc())

            # Execute
            result = await session.execute(query)
            rows = result.fetchall()

            if not rows:
                return {
                    "type": "empty",
                    "message": f"No hay datos para {config.get_metric_display_name(metric_id)}",
                    "filters": {
                        "banks": banks,
                        "date_start": str(date_start) if date_start else None,
                        "date_end": str(date_end) if date_end else None
                    }
                }

            # Format based on intent
            metric_type = config.get_metric_type(metric_id)

            if intent == "evolution":
                return AnalyticsService._format_evolution(rows, metric_id, config, metric_type)
            elif intent == "comparison":
                return AnalyticsService._format_comparison(rows, metric_id, config, metric_type)
            elif intent == "ranking":
                return AnalyticsService._format_ranking(rows, metric_id, config, metric_type)
            else:  # point_value or unknown
                # SMART DEFAULT: If we have multiple data points, show as evolution
                # This ensures visualizations are always generated
                if len(rows) > 3:
                    logger.debug(
                        "analytics.auto_evolution",
                        metric=metric_id,
                        original_intent=intent,
                        rows=len(rows),
                        reason="Multiple data points available - showing as evolution"
                    )
                    return AnalyticsService._format_evolution(rows, metric_id, config, metric_type)
                else:
                    return AnalyticsService._format_point_value(rows, metric_id, config, metric_type)

        except SQLAlchemyError as e:
            logger.error(
                "analytics.filtered_data.db_error",
                metric_id=metric_id,
                error=str(e)
            )
            return {
                "type": "error",
                "message": "Error de base de datos. Por favor intente nuevamente."
            }

    @staticmethod
    def _format_evolution(rows, metric_id: str, config, metric_type: str) -> Dict[str, Any]:
        """Format data for evolution/trend view with Plotly config."""
        import pandas as pd

        df = pd.DataFrame(rows, columns=['fecha', 'banco', 'value'])

        # Convert ratio metrics to percentage, currency to millions
        is_ratio = metric_type == "ratio"

        # DEBUG: Log original values
        import structlog
        logger = structlog.get_logger(__name__)
        logger.info("analytics_service._format_evolution.values_before_conversion",
                   metric_id=metric_id,
                   metric_type=metric_type,
                   is_ratio=is_ratio,
                   sample_values=df['value'].head(10).tolist() if len(df) > 0 else [],
                   all_unique_values=sorted(df['value'].unique().tolist()) if len(df) > 0 else [])

        if is_ratio:
            df['value'] = df['value'] * 100
        else:
            # IMPORTANT: Database values are ALREADY in millions (MDP)
            # DO NOT divide by 1,000,000 as it would make them too small
            # df['value'] = df['value'] / 1_000_000
            pass  # Values are already in correct scale

        # DEBUG: Log converted values
        logger.info("analytics_service._format_evolution.values_after_conversion",
                   metric_id=metric_id,
                   is_ratio=is_ratio,
                   sample_values=df['value'].head(10).tolist() if len(df) > 0 else [])

        # Build hovertemplate with units
        hover_template = (
            "<b>%{fullData.name}</b><br>" +
            "Fecha: %{x}<br>" +
            ("Valor: %{y:.2f}%<extra></extra>" if is_ratio else "Valor: %{y:,.2f} MDP<extra></extra>")
        )

        # Group by bank for multi-line chart
        traces = []
        for banco in df['banco'].unique():
            bank_data = df[df['banco'] == banco].sort_values('fecha')
            traces.append({
                "x": bank_data['fecha'].astype(str).tolist(),
                "y": bank_data['value'].tolist(),
                "type": "scatter",
                "mode": "lines+markers",
                "name": banco,
                "hovertemplate": hover_template
            })

        display_name = config.get_metric_display_name(metric_id)

        return {
            "type": "data",
            "visualization": "line_chart",
            "metric_name": display_name,
            "metric_type": metric_type,  # Include type for context
            "plotly_config": {
                "data": traces,
                "layout": {
                    "title": f"Evolución de {display_name}",
                    "xaxis": {"title": "Fecha"},
                    "yaxis": {
                        "title": "%" if is_ratio else "MDP (Millones de Pesos)"
                    }
                }
            },
            "summary": f"Mostrando evolución de {display_name}"
        }

    @staticmethod
    def _format_comparison(rows, metric_id: str, config, metric_type: str) -> Dict[str, Any]:
        """Format data for bank comparison with Plotly config."""
        import pandas as pd

        df = pd.DataFrame(rows, columns=['fecha', 'banco', 'value'])

        # Convert ratio metrics to percentage, currency to millions
        is_ratio = metric_type == "ratio"
        if is_ratio:
            df['value'] = df['value'] * 100
        # else: Database values are ALREADY in millions (MDP), no conversion needed

        # Get latest value per bank
        latest = df.sort_values('fecha').groupby('banco').last().reset_index()

        display_name = config.get_metric_display_name(metric_id)

        # Build hovertemplate with units
        hover_template = (
            "<b>%{x}</b><br>" +
            ("Valor: %{y:.2f}%<extra></extra>" if is_ratio else "Valor: %{y:,.2f} MDP<extra></extra>")
        )

        return {
            "type": "data",
            "visualization": "bar_chart",
            "metric_name": display_name,
            "metric_type": metric_type,
            "plotly_config": {
                "data": [{
                    "x": latest['banco'].tolist(),
                    "y": latest['value'].tolist(),
                    "type": "bar",
                    "marker": {"color": "#4F46E5"},
                    "hovertemplate": hover_template,
                    "text": [f"{v:.2f}%" if is_ratio else f"{v:,.0f} MDP" for v in latest['value'].tolist()],
                    "textposition": "auto"
                }],
                "layout": {
                    "title": f"Comparación de {display_name}",
                    "xaxis": {"title": "Banco"},
                    "yaxis": {
                        "title": "%" if is_ratio else "MDP (Millones de Pesos)"
                    }
                }
            },
            "summary": f"Comparando {display_name} entre bancos"
        }

    @staticmethod
    def _format_ranking(rows, metric_id: str, config, metric_type: str) -> Dict[str, Any]:
        """Format data for ranking view."""
        import pandas as pd

        df = pd.DataFrame(rows, columns=['fecha', 'banco', 'value'])

        # Convert ratio metrics to percentage, currency to millions
        is_ratio = metric_type == "ratio"
        if is_ratio:
            df['value'] = df['value'] * 100
        # else: Database values are ALREADY in millions (MDP), no conversion needed

        # Get latest value per bank, sorted
        latest = df.sort_values('fecha').groupby('banco').last().reset_index()
        latest = latest.sort_values('value', ascending=False)

        display_name = config.get_metric_display_name(metric_id)

        # Build hovertemplate with units
        hover_template = (
            "<b>%{y}</b><br>" +
            ("Valor: %{x:.2f}%<extra></extra>" if is_ratio else "Valor: %{x:,.2f} MDP<extra></extra>")
        )

        return {
            "type": "data",
            "visualization": "ranking",
            "metric_name": display_name,
            "metric_type": metric_type,
            "ranking": [
                {
                    "position": i + 1,
                    "banco": row['banco'],
                    "value": round(row['value'], 2),
                    "unit": "%" if is_ratio else "MDP"
                }
                for i, (_, row) in enumerate(latest.iterrows())
            ],
            "plotly_config": {
                "data": [{
                    "x": latest['value'].tolist(),
                    "y": latest['banco'].tolist(),
                    "type": "bar",
                    "orientation": "h",
                    "marker": {"color": "#10B981"},
                    "hovertemplate": hover_template,
                    "text": [f"{v:.2f}%" if is_ratio else f"{v:,.0f} MDP" for v in latest['value'].tolist()],
                    "textposition": "auto"
                }],
                "layout": {
                    "title": f"Ranking de {display_name}",
                    "xaxis": {
                        "title": "%" if is_ratio else "MDP (Millones de Pesos)",
                        "tickformat": ".0f",
                        "ticksuffix": "%" if is_ratio else " MDP"
                    },
                    "yaxis": {"title": "Banco", "autorange": "reversed"}
                }
            },
            "summary": f"Ranking de {display_name}"
        }

    @staticmethod
    def _format_point_value(rows, metric_id: str, config, metric_type: str) -> Dict[str, Any]:
        """Format data for single point value."""
        import pandas as pd

        df = pd.DataFrame(rows, columns=['fecha', 'banco', 'value'])

        # Convert ratio metrics to percentage, currency to millions
        is_ratio = metric_type == "ratio"
        if is_ratio:
            df['value'] = df['value'] * 100
        # else: Database values are ALREADY in millions (MDP), no conversion needed

        # Get latest values
        latest = df.sort_values('fecha').groupby('banco').last().reset_index()

        display_name = config.get_metric_display_name(metric_id)

        return {
            "type": "data",
            "visualization": "value",
            "metric_name": display_name,
            "metric_type": metric_type,
            "values": [
                {
                    "banco": row['banco'],
                    "value": round(row['value'], 2),
                    "fecha": str(row['fecha']),
                    "unit": "%" if is_ratio else "MDP"
                }
                for _, row in latest.iterrows()
            ],
            "summary": f"Valor actual de {display_name}"
        }
