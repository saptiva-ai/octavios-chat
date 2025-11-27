import os
import pandas as pd
from sqlalchemy import create_engine
from src.bankadvisor.io_loader import load_all, get_data_paths
from src.bankadvisor.transforms import prepare_cnbv, prepare_castigos, enrich_with_castigos
from src.bankadvisor.metrics import monthly_kpis
from src.core.config import get_settings

settings = get_settings()

def run_etl():
    print("🚀 Iniciando ETL de BankAdvisor...")
    
    # 1. Configurar rutas
    # Asumimos que los datos están en apps/api/data/raw (copiados anteriormente)
    data_root = "/app/data/raw"
    if not os.path.exists(data_root):
        # Fallback si se ejecuta desde root del proyecto (local dev)
        data_root = os.path.join(os.path.dirname(__file__), "../../../data/raw")
    
    print(f"📂 Leyendo datos desde: {os.path.abspath(data_root)}")
    paths = get_data_paths(data_root)

    # 2. Cargar fuentes raw
    print("📥 Cargando archivos Excel (esto puede tardar un poco)...")
    dfs = load_all(paths)
    
    # 3. Transformaciones Base
    print("🔄 Ejecutando transformaciones...")
    cnbv_clean = prepare_cnbv(dfs["cnbv"])
    castigos_agg = prepare_castigos(dfs["castigos"])
    
    # Unir Castigos con Cartera
    full_data = enrich_with_castigos(cnbv_clean, castigos_agg)
    
    # Cruzar con Catálogo de Instituciones para tener nombres limpios
    instituciones = dfs["instituciones"]
    full_data = full_data.merge(
        instituciones[["institucion_code", "banco"]], 
        left_on="institucion", 
        right_on="institucion_code", 
        how="left"
    )
    
    # Agregar otras métricas (ICAP, TDA, Tasas) si existen en el source
    # (Simplificado para este ETL inicial, asumiendo cruces directos por fecha/inst)
    # ... lógica de cruce omitida para brevedad, enfocándonos en lo principal
    
    # 4. Generar KPIs Mensuales (Agrupados por Banco y Sistema)
    # Calculamos para INVEX
    print("📊 Calculando KPIs para INVEX...")
    kpi_invex = monthly_kpis(full_data, banco="INVEX")
    kpi_invex["banco_norm"] = "INVEX"
    kpi_invex = kpi_invex.reset_index() # periodo pasa a columna
    kpi_invex = kpi_invex.rename(columns={"periodo": "fecha"})  # CRITICAL FIX

    # Calculamos para Sistema (Todos)
    print("📊 Calculando KPIs del Sistema...")
    kpi_sistema = monthly_kpis(full_data, banco=None) # Sin filtro = Sistema completo
    kpi_sistema["banco_norm"] = "SISTEMA"
    kpi_sistema = kpi_sistema.reset_index()
    kpi_sistema = kpi_sistema.rename(columns={"periodo": "fecha"})  # CRITICAL FIX

    # Unir todo
    final_kpis = pd.concat([kpi_invex, kpi_sistema], ignore_index=True)

    # Limpieza final de columnas para coincidir con el Modelo SQL
    # Convertir PeriodIndex a datetime para compatibilidad con PostgreSQL
    if "fecha" in final_kpis.columns:
        final_kpis["fecha"] = final_kpis["fecha"].apply(lambda x: x.to_timestamp() if hasattr(x, "to_timestamp") else x)

    final_kpis["institucion"] = final_kpis["banco_norm"] # Para simplificar consultas por nombre
    
    # Seleccionar solo columnas que existen en el modelo
    target_columns = [
        "fecha", "institucion", "banco_norm",
        "cartera_total", "cartera_comercial_total", "cartera_consumo_total", 
        "cartera_vivienda_total", "entidades_gubernamentales_total",
        "entidades_financieras_total", "empresarial_total",
        "cartera_vencida", "imor", "icor", "reservas_etapa_todas"
    ]
    
    # Filtrar columnas existentes
    cols_to_save = [c for c in target_columns if c in final_kpis.columns]
    final_df = final_kpis[cols_to_save].copy()

    # 5. Cargar a Postgres
    print("💾 Guardando en PostgreSQL...")
    
    # Construir URL de conexión Sincrona (psycopg2) para Pandas
    # Usamos las variables de entorno del container
    user = os.getenv("POSTGRES_USER", "octavios")
    password = os.getenv("POSTGRES_PASSWORD", "secure_postgres_password")
    db = os.getenv("POSTGRES_DB", "bankadvisor")
    host = os.getenv("POSTGRES_HOST", "postgres") # Nombre del servicio en docker network
    port = os.getenv("POSTGRES_PORT", "5432")
    
    # IMPORTANTE: Si corremos esto DESDE el host (fuera de docker), el host es localhost
    # y el puerto mapeado es 5432.
    # Detectar si estamos en docker o local
    if not os.path.exists("/.dockerenv"):
        host = "localhost"
    
    db_url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    
    engine = create_engine(db_url)
    
    # Guardar (reemplazar tabla completa para idempodencia en dev)
    final_df.to_sql("monthly_kpis", engine, if_exists="replace", index=False)
    
    print(f"✅ Carga completada! {len(final_df)} registros insertados.")

if __name__ == "__main__":
    run_etl()
