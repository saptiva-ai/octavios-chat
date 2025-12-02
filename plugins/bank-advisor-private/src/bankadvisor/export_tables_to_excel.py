"""
Export all Bank Advisor tables to Excel with DDL and column comments.

Each table gets its own sheet with:
- Data from the table
- SQL DDL (CREATE TABLE statement)
- Column comments explaining each field
"""
import pandas as pd
from sqlalchemy import create_engine, text, inspect
from datetime import datetime
import os


def get_table_ddl(engine, table_name: str, schema: str = 'public') -> str:
    """Get CREATE TABLE DDL for a table."""
    with engine.connect() as conn:
        # Get columns with their types
        result = conn.execute(text(f"""
            SELECT
                column_name,
                data_type,
                character_maximum_length,
                is_nullable,
                column_default
            FROM information_schema.columns
            WHERE table_schema = '{schema}'
              AND table_name = '{table_name}'
            ORDER BY ordinal_position;
        """))

        columns = []
        for row in result:
            col_name = row[0]
            data_type = row[1]
            max_length = row[2]
            is_nullable = row[3]
            default = row[4]

            # Build column definition
            if max_length and data_type in ('character varying', 'character'):
                col_def = f"{col_name} {data_type.upper()}({max_length})"
            else:
                col_def = f"{col_name} {data_type.upper()}"

            if default:
                col_def += f" DEFAULT {default}"

            if is_nullable == 'NO':
                col_def += " NOT NULL"

            columns.append(f"    {col_def}")

        ddl = f"CREATE TABLE {table_name} (\n"
        ddl += ",\n".join(columns)
        ddl += "\n);"

        return ddl


# Predefined column descriptions for Bank Advisor tables
COLUMN_DESCRIPTIONS = {
    'monthly_kpis': {
        'fecha': 'Fecha del período (primer día del mes)',
        'institucion': 'Nombre de la institución bancaria',
        'banco_norm': 'Nombre normalizado del banco (INVEX, SISTEMA, etc.)',
        'cartera_total': 'Cartera de crédito total (todas las categorías)',
        'cartera_comercial_total': 'Cartera comercial total (empresarial + entidades)',
        'cartera_consumo_total': 'Cartera de créditos al consumo',
        'cartera_vivienda_total': 'Cartera de créditos hipotecarios',
        'entidades_gubernamentales_total': 'Cartera con entidades gubernamentales',
        'entidades_financieras_total': 'Cartera con entidades financieras',
        'empresarial_total': 'Cartera empresarial privada',
        'cartera_vencida': 'Cartera vencida (más de 90 días de atraso)',
        'imor': 'Índice de Morosidad (cartera vencida / cartera total)',
        'icor': 'Índice de Cobertura (reservas / cartera vencida)',
        'reservas_etapa_todas': 'Reservas totales para créditos (todas las etapas)',
        'reservas_variacion_mm': 'Variación mes a mes de reservas totales (%)',
        'pe_total': 'Pérdida Esperada Total - ratio reservas/cartera total',
        'pe_empresarial': 'Pérdida Esperada Empresarial - ratio reservas/cartera empresarial',
        'pe_consumo': 'Pérdida Esperada Consumo - ratio reservas/cartera consumo',
        'pe_vivienda': 'Pérdida Esperada Vivienda - ratio reservas/cartera vivienda',
        'ct_etapa_1': 'Cartera Etapa 1 como ratio de cartera total (performing)',
        'ct_etapa_2': 'Cartera Etapa 2 como ratio de cartera total (watchlist)',
        'ct_etapa_3': 'Cartera Etapa 3 como ratio de cartera total (non-performing)',
        'quebrantos_cc': 'Quebrantos de cartera comercial (write-offs)',
        'quebrantos_vs_cartera_cc': 'Ratio quebrantos vs cartera comercial total',
        'icap_total': 'Índice de Capitalización Total',
        'tda_cartera_total': 'Tasa de Deterioro Anualizada de Cartera Total',
        'tasa_sistema': 'Tasa de Interés Efectiva del Sistema Bancario (%)',
        'tasa_invex_consumo': 'Tasa de Interés Efectiva INVEX Consumo (%)',
        'tasa_mn': 'Tasa de Interés Promedio Crédito Corporativo en Moneda Nacional (Pesos)',
        'tasa_me': 'Tasa de Interés Promedio Crédito Corporativo en Moneda Extranjera (Dólares)',
    },
    'etl_runs': {
        'id': 'ID único del proceso ETL',
        'started_at': 'Fecha y hora de inicio del ETL',
        'completed_at': 'Fecha y hora de finalización del ETL',
        'duration_seconds': 'Duración del proceso en segundos',
        'status': 'Estado del proceso (success, failed, running)',
        'error_message': 'Mensaje de error si el proceso falló',
        'rows_processed_base': 'Número de filas procesadas en ETL base',
        'rows_processed_icap': 'Número de filas procesadas de ICAP',
        'rows_processed_tda': 'Número de filas procesadas de TDA',
        'rows_processed_tasas': 'Número de filas procesadas de Tasas',
        'etl_version': 'Versión del ETL ejecutado',
        'triggered_by': 'Origen del trigger (manual, scheduled, api)',
    }
}


def get_column_comments(engine, table_name: str, schema: str = 'public') -> pd.DataFrame:
    """Get column comments for a table."""
    with engine.connect() as conn:
        result = conn.execute(text(f"""
            SELECT
                c.column_name,
                c.data_type,
                c.is_nullable,
                pgd.description as column_comment
            FROM information_schema.columns c
            LEFT JOIN pg_catalog.pg_statio_all_tables st
                ON c.table_schema = st.schemaname
                AND c.table_name = st.relname
            LEFT JOIN pg_catalog.pg_description pgd
                ON pgd.objoid = st.relid
                AND pgd.objsubid = c.ordinal_position
            WHERE c.table_schema = '{schema}'
              AND c.table_name = '{table_name}'
            ORDER BY c.ordinal_position;
        """))

        comments = []
        predefined = COLUMN_DESCRIPTIONS.get(table_name, {})

        for row in result:
            col_name = row[0]
            # Use predefined description if available, otherwise use DB comment
            description = row[3] or predefined.get(col_name, '(sin descripción)')

            comments.append({
                'Columna': col_name,
                'Tipo': row[1],
                'Nullable': row[2],
                'Descripción': description
            })

        return pd.DataFrame(comments)


def export_all_tables_to_excel(output_path: str):
    """Export all tables from bankadvisor database to Excel."""

    # Connect to database using environment variables
    pg_user = os.getenv("POSTGRES_USER", "octavios")
    pg_password = os.getenv("POSTGRES_PASSWORD", "secure_postgres_password")
    pg_host = os.getenv("POSTGRES_HOST", "postgres")
    pg_port = os.getenv("POSTGRES_PORT", "5432")
    pg_db = os.getenv("POSTGRES_DB", "bankadvisor")

    db_url = f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_db}"

    # Check if running outside docker
    if not os.path.exists("/.dockerenv"):
        db_url = db_url.replace(f"@{pg_host}:", "@localhost:")

    engine = create_engine(db_url)
    inspector = inspect(engine)

    # Get all tables
    tables = inspector.get_table_names(schema='public')

    print(f"📊 Exportando {len(tables)} tablas a Excel...")
    print(f"   Tablas encontradas: {', '.join(tables)}")

    # Create Excel writer
    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:

        # Create metadata sheet with DDL and comments for all tables
        metadata_rows = []
        metadata_rows.append(['DOCUMENTACIÓN DE BASE DE DATOS BANK ADVISOR'])
        metadata_rows.append([f'Generado: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'])
        metadata_rows.append([''])
        metadata_rows.append(['=' * 80])
        metadata_rows.append([''])

        for table_name in tables:
            print(f"   Procesando tabla: {table_name}")

            # Get table data
            try:
                df_data = pd.read_sql_table(table_name, engine)

                # Write data to its own sheet (truncate name if too long)
                sheet_name = table_name[:31] if len(table_name) > 31 else table_name
                df_data.to_excel(writer, sheet_name=sheet_name, index=False)

                print(f"      ✓ Datos exportados: {len(df_data)} filas")

            except Exception as e:
                print(f"      ⚠ Error exportando datos: {e}")
                df_data = pd.DataFrame()

            # Add to metadata sheet
            metadata_rows.append([f'TABLA: {table_name}'])
            metadata_rows.append([''])

            # Add row count
            metadata_rows.append([f'Total de registros: {len(df_data)}'])
            metadata_rows.append([''])

            # Get DDL
            try:
                ddl = get_table_ddl(engine, table_name)
                metadata_rows.append(['SQL DDL:'])
                for line in ddl.split('\n'):
                    metadata_rows.append([line])
                metadata_rows.append([''])
            except Exception as e:
                metadata_rows.append([f'Error obteniendo DDL: {e}'])
                metadata_rows.append([''])

            # Get column comments
            try:
                df_comments = get_column_comments(engine, table_name)
                metadata_rows.append(['COMENTARIOS DE COLUMNAS:'])
                metadata_rows.append([''])

                # Add header
                metadata_rows.append(['Columna', 'Tipo', 'Nullable', 'Descripción'])

                # Add rows
                for _, row in df_comments.iterrows():
                    metadata_rows.append([
                        row['Columna'],
                        row['Tipo'],
                        row['Nullable'],
                        row['Descripción']
                    ])

                metadata_rows.append([''])
                print(f"      ✓ Comentarios exportados: {len(df_comments)} columnas")

            except Exception as e:
                metadata_rows.append([f'Error obteniendo comentarios: {e}'])
                metadata_rows.append([''])
                print(f"      ⚠ Error exportando comentarios: {e}")

            metadata_rows.append(['=' * 80])
            metadata_rows.append([''])
            metadata_rows.append([''])

        # Write metadata sheet
        df_metadata = pd.DataFrame(metadata_rows)
        df_metadata.to_excel(writer, sheet_name='_DOCUMENTACION', index=False, header=False)

        print(f"\n✅ Exportación completada: {output_path}")
        print(f"   Total de pestañas: {len(tables) + 1}")


def main():
    """Entry point for export."""
    # Use /tmp for writable location inside container
    output_path = "/tmp/bank_advisor_export.xlsx"

    # Check if running outside docker
    if not os.path.exists("/.dockerenv"):
        output_path = "./bank_advisor_export.xlsx"

    export_all_tables_to_excel(output_path)
    print(f"\n📁 Archivo generado: {output_path}")

    # Copy to shared volume if exists
    shared_path = "/app/data/raw/bank_advisor_export.xlsx"
    if os.path.exists("/app/data/raw"):
        import shutil
        try:
            shutil.copy(output_path, shared_path)
            print(f"📁 Copiado a: {shared_path}")
        except Exception as e:
            print(f"⚠️ No se pudo copiar a volumen compartido: {e}")


if __name__ == "__main__":
    main()
