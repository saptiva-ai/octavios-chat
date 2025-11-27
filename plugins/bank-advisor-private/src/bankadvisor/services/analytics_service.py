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
