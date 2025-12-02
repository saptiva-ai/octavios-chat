"""
Corporate Rates Processor using Polars for high-performance processing.

Processes 1.3M+ records from Corporate Loan data to extract monthly
average interest rates (MN/ME) by institution.
"""
import polars as pl
import pandas as pd
from pathlib import Path
from typing import Optional
import structlog

logger = structlog.get_logger(__name__)


def process_corporate_rates(csv_path: Path, encoding: str = "latin-1") -> pd.DataFrame:
    """
    Process Corporate Loan CSV to extract monthly average rates by institution.

    Uses Polars for high-performance processing of 1.3M+ records.

    Args:
        csv_path: Path to CorporateLoan_CNBVDB.csv
        encoding: File encoding (default: latin-1)

    Returns:
        DataFrame with columns: [fecha, institucion, tasa_mn, tasa_me]
    """
    if not csv_path.exists():
        logger.warning(f"Corporate Loan file not found: {csv_path}")
        return pd.DataFrame(columns=["fecha", "institucion", "tasa_mn", "tasa_me"])

    logger.info(f"Processing Corporate Loan data with Polars from {csv_path}")

    # Read CSV with Polars (much faster than pandas for large files)
    try:
        df = pl.read_csv(
            csv_path,
            encoding=encoding,
            ignore_errors=True,  # Handle malformed rows
            low_memory=False,
        )

        logger.info(f"Loaded {len(df):,} records from Corporate Loan CSV")

        # Normalize column names
        df = df.rename({col: col.strip().lower().replace(" ", "_") for col in df.columns})

        # Parse monitoring_term to date (format: M/D/YY)
        df = df.with_columns([
            pl.col("monitoring_term").str.strptime(pl.Date, "%m/%d/%y", strict=False).alias("fecha")
        ])

        # Normalize institution code to match format used in other tables (6-digit zero-padded)
        df = df.with_columns([
            pl.col("institution_code").cast(pl.Utf8).str.zfill(6).alias("institucion")
        ])

        # Convert average_rate and currency to proper types
        df = df.with_columns([
            pl.col("average_rate").cast(pl.Float64, strict=False).alias("average_rate"),
            pl.col("currency").cast(pl.Utf8).alias("currency")
        ])

        # Filter out invalid data
        df = df.filter(
            (pl.col("fecha").is_not_null()) &
            (pl.col("institucion").is_not_null()) &
            (pl.col("average_rate").is_not_null()) &
            (pl.col("average_rate") > 0) &
            (pl.col("average_rate") < 100) &  # Filter outliers (> 100% seems unrealistic)
            (pl.col("currency").is_not_null())
        )

        logger.info(f"After filtering: {len(df):,} valid records")

        # Extract year-month for grouping
        df = df.with_columns([
            pl.col("fecha").dt.truncate("1mo").alias("periodo")
        ])

        # Separate MN (Moneda Nacional) and ME (Moneda Extranjera) data
        df_mn = df.filter(pl.col("currency").str.to_lowercase().str.contains("nacional"))
        df_me = df.filter(pl.col("currency").str.to_lowercase().str.contains("extranjera"))

        logger.info(f"Split by currency: {len(df_mn):,} MN records, {len(df_me):,} ME records")

        # Group MN by institution and month
        df_mn_agg = df_mn.group_by(["periodo", "institucion"]).agg([
            pl.col("average_rate").mean().alias("tasa_mn"),
            pl.col("average_rate").count().alias("n_registros_mn")
        ])

        # Group ME by institution and month
        df_me_agg = df_me.group_by(["periodo", "institucion"]).agg([
            pl.col("average_rate").mean().alias("tasa_me"),
            pl.col("average_rate").count().alias("n_registros_me")
        ])

        # Merge MN and ME data (outer join to keep all combinations)
        df_agg = df_mn_agg.join(
            df_me_agg,
            on=["periodo", "institucion"],
            how="outer"
        )

        # Fill nulls and calculate total records
        df_agg = df_agg.with_columns([
            pl.col("n_registros_mn").fill_null(0),
            pl.col("n_registros_me").fill_null(0),
        ])

        df_agg = df_agg.with_columns([
            (pl.col("n_registros_mn") + pl.col("n_registros_me")).alias("n_registros")
        ])

        # Filter out groups with very few records (< 5 total) as they may be unreliable
        df_agg = df_agg.filter(pl.col("n_registros") >= 5)

        logger.info(f"After aggregation: {len(df_agg):,} institution-month combinations")
        logger.info(f"  - With MN data: {df_agg.filter(pl.col('tasa_mn').is_not_null()).height}")
        logger.info(f"  - With ME data: {df_agg.filter(pl.col('tasa_me').is_not_null()).height}")

        # Rename periodo to fecha
        df_agg = df_agg.rename({"periodo": "fecha"})

        # Select final columns
        df_final = df_agg.select(["fecha", "institucion", "tasa_mn", "tasa_me", "n_registros"])

        logger.info(f"Aggregated to {len(df_final):,} institution-month combinations")

        # Convert to pandas for compatibility with existing pipeline
        result = df_final.to_pandas()

        # Convert fecha to datetime for consistency
        result["fecha"] = pd.to_datetime(result["fecha"])

        return result

    except Exception as e:
        logger.error(f"Error processing Corporate Loan data: {e}", exc_info=True)
        return pd.DataFrame(columns=["fecha", "institucion", "tasa_mn", "tasa_me"])


def merge_corporate_rates(full_data: pd.DataFrame, corp_rates: pd.DataFrame) -> pd.DataFrame:
    """
    Merge corporate rates into full_data.

    Args:
        full_data: Main DataFrame with all data
        corp_rates: DataFrame with corporate rates [fecha, institucion, tasa_mn, tasa_me]

    Returns:
        Merged DataFrame
    """
    if corp_rates.empty:
        logger.warning("No corporate rates data to merge")
        return full_data

    # Normalize dates to first day of month
    corp_rates = corp_rates.copy()
    corp_rates["fecha_normalized"] = pd.to_datetime(corp_rates["fecha"]).dt.to_period('M').dt.to_timestamp()
    full_data["fecha_normalized"] = pd.to_datetime(full_data["fecha"]).dt.to_period('M').dt.to_timestamp()

    # Merge on fecha and institucion
    merged = full_data.merge(
        corp_rates[["fecha_normalized", "institucion", "tasa_mn", "tasa_me"]],
        left_on=["fecha_normalized", "institucion"],
        right_on=["fecha_normalized", "institucion"],
        how="left"
    )

    # Drop temporary column
    merged = merged.drop(columns=["fecha_normalized"])

    logger.info(f"Merged corporate rates:")
    logger.info(f"  - tasa_mn: {merged['tasa_mn'].notna().sum()} records")
    logger.info(f"  - tasa_me: {merged['tasa_me'].notna().sum()} records")

    return merged
