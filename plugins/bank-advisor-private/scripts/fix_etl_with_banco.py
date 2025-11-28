#!/usr/bin/env python
"""
Fixed ETL script that preserves banco_nombre and fecha as explicit columns.
Creates one row per banco per month instead of aggregating all banks together.
"""
from pathlib import Path
import os
import pandas as pd
from sqlalchemy import create_engine

# Set working directory to project root
os.chdir('/home/jazielflo/Proyects/octavios-chat-bajaware_invex/plugins/bank-advisor-private')

# Add src to path
import sys
sys.path.insert(0, 'src')

from dotenv import load_dotenv
load_dotenv()

from bankadvisor.io_loader import load_all, get_data_paths
from bankadvisor.transforms import prepare_cnbv, prepare_castigos, enrich_with_castigos
from bankadvisor.metrics import monthly_kpis
from core.config import get_settings

def main():
    settings = get_settings()

    print("📂 Loading data files...")
    data_root = Path('data/raw')
    paths = get_data_paths(data_root)
    dfs = load_all(paths)

    # Prepare data
    print("🔄 Running transforms...")
    cnbv_clean = prepare_cnbv(dfs['cnbv'])
    castigos_clean = prepare_castigos(dfs['castigos'])
    merged = enrich_with_castigos(cnbv_clean, castigos_clean)

    # Filter to only INVEX (040059) and SISTEMA (000021)
    target_institutions = ['040059', '000021']
    filtered = merged[merged['institucion'].isin(target_institutions)].copy()

    print(f'✅ Filtered to {len(filtered)} records for INVEX and SISTEMA')
    print(f'   Date range: {filtered["fecha"].min()} to {filtered["fecha"].max()}')
    print(f'   Unique institutions: {filtered["institucion"].unique()}')

    # Calculate KPIs for the filtered data (don't pass banco parameter)
    print(f'📊 Calculating KPIs for all filtered institutions...')
    kpis = monthly_kpis(filtered, banco=None, include_rollups=True)

    # Reset index to get fecha as a column
    kpis_df = kpis.reset_index()
    kpis_df.rename(columns={'index': 'fecha'}, inplace=True)

    # The monthly_kpis aggregates all institutions together,
    # so we need to do the calculation differently - per institution per month
    # Let's group by institucion and fecha ourselves
    print(f'📊 Grouping by institution and month...')

    # Group by institution and period
    filtered['periodo'] = pd.PeriodIndex(filtered['fecha'], freq='M')

    # Basic aggregations per banco-month
    grouped = filtered.groupby(['institucion', 'periodo']).agg({
        'cartera_total': 'sum',
        'cartera_comercial_total': 'sum',
        'cartera_consumo_total': 'sum',
        'cartera_vivienda_total': 'sum',
        'reservas_etapa_todas': 'sum',
        'cartera_vencida': 'sum',
        'castigos_acumulados_comercial': 'sum',
        'comercial_etapa_3': 'sum'
    }).reset_index()

    # Calculate ratios
    grouped['imor'] = (grouped['comercial_etapa_3'] + grouped['castigos_acumulados_comercial']) / grouped['cartera_comercial_total']
    grouped['icor'] = grouped['reservas_etapa_todas'].abs() / grouped['cartera_vencida'].replace(0, pd.NA)

    # Map institution codes to names
    grouped['banco_nombre'] = grouped['institucion'].map({
        '040059': 'INVEX',
        '000021': 'SISTEMA'
    })

    # Convert period to timestamp
    grouped['fecha'] = grouped['periodo'].dt.to_timestamp()

    # Select and order columns
    combined = grouped[['banco_nombre', 'fecha', 'imor', 'icor', 'cartera_total',
                        'cartera_comercial_total', 'cartera_consumo_total',
                        'cartera_vivienda_total', 'reservas_etapa_todas', 'cartera_vencida']]

    print(f'   ✅ INVEX: {len(combined[combined["banco_nombre"]=="INVEX"])} monthly records')
    print(f'   ✅ SISTEMA: {len(combined[combined["banco_nombre"]=="SISTEMA"])} monthly records')

    print(f'\n📊 Total records: {len(combined)}')
    print(f'   Banks: {combined["banco_nombre"].unique()}')
    print(f'   Date range: {combined["fecha"].min()} to {combined["fecha"].max()}')
    print(f'\n📋 Sample data:')
    print(combined[['banco_nombre', 'fecha', 'imor', 'icor', 'cartera_total']].head(6))

    # Write to database
    print(f'\n💾 Writing to database...')
    engine = create_engine(settings.database_url_sync)
    combined.to_sql('monthly_kpis', engine, if_exists='replace', index=False)
    print(f'✅ Wrote {len(combined)} records to monthly_kpis table')

    # Verify
    with engine.connect() as conn:
        from sqlalchemy import text
        result = conn.execute(text('SELECT banco_nombre, COUNT(*) as count FROM monthly_kpis GROUP BY banco_nombre'))
        for row in result:
            print(f'   {row[0]}: {row[1]} records')

if __name__ == '__main__':
    main()
