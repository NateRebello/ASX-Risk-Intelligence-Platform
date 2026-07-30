"""Runtime-configurable ASX universe resolution.

See docs/adr/0001-market-universe-and-tableau.md for the full design
rationale. Resolution precedence, highest first:

  1. An explicit CSV path (`tickers_file` argument or `ASX_TICKERS_FILE`
     env var) — unchanged legacy override behavior, always wins.
  2. AWS SSM Parameter Store (`MARKET_UNIVERSE_SSM_PARAM`) names the active
     filename; its contents are read from a versioned S3 config prefix
     (`MARKET_UNIVERSE_S3_PREFIX` inside `S3_BUCKET`). Both lookups are
     best-effort: any failure (no AWS credentials, object not yet
     published, network error) falls through to the next source rather
     than raising.
  3. `settings.yaml`'s `market_universe` key, read from the local
     `config/universes/<file>` CSV baked into the image/repo.
  4. `config.settings.DEFAULT_UNIVERSE` — a small hardcoded list so the
     pipeline never has zero tickers.

Switching the deployed pipeline between ASX 50 and ASX 200 is then a single
`aws ssm put-parameter --overwrite` call with no code change and no
redeploy (subject to the CloudFormation-ownership caveat documented in the
ADR).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
import yaml

from config import settings

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"ticker", "name", "sector", "industry"}
REPO_ROOT = Path(__file__).resolve().parents[2]
UNIVERSE_DIR = REPO_ROOT / "config" / "universes"
SETTINGS_YAML = REPO_ROOT / "settings.yaml"
DEFAULT_UNIVERSE_FILE = "asx50.csv"


class UniverseValidationError(ValueError):
    """Raised when a universe source is malformed."""


def _validate(df: pd.DataFrame, source: str) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise UniverseValidationError(f"Universe source {source} is missing columns: {sorted(missing)}")
    if df.empty:
        raise UniverseValidationError(f"Universe source {source} contained no rows")

    tickers = df["ticker"].astype(str).str.strip().str.upper()
    duplicates = sorted(tickers[tickers.duplicated()].unique())
    if duplicates:
        raise UniverseValidationError(f"Universe source {source} has duplicate tickers: {duplicates}")

    df = df.copy()
    df["ticker"] = tickers
    return df[list(REQUIRED_COLUMNS)]


def local_default_filename() -> str:
    """The `market_universe:` value from settings.yaml, or asx50.csv."""
    if SETTINGS_YAML.exists():
        try:
            data = yaml.safe_load(SETTINGS_YAML.read_text(encoding="utf-8")) or {}
            value = data.get("market_universe")
            if value:
                return str(value)
        except Exception as exc:  # noqa: BLE001 — malformed YAML must not crash the pipeline
            logger.warning("Failed to parse %s (%s); using %s", SETTINGS_YAML, exc, DEFAULT_UNIVERSE_FILE)
    return DEFAULT_UNIVERSE_FILE


def load_from_local_file(filename: str) -> pd.DataFrame:
    """Read one of the committed CSVs under config/universes/ by filename."""
    path = UNIVERSE_DIR / filename
    return _validate(pd.read_csv(path), str(path))


def load_from_path(path: str) -> list[dict[str, str]]:
    """Read an arbitrary explicit CSV path (the `--tickers-file` override)."""
    df = _validate(pd.read_csv(path), path)
    return df.to_dict("records")


def active_filename_from_ssm() -> str | None:
    """Best-effort SSM lookup of the active universe filename."""
    if not settings.MARKET_UNIVERSE_SSM_PARAM:
        return None
    try:
        import boto3

        client = boto3.client("ssm", region_name=settings.AWS_REGION)
        response = client.get_parameter(Name=settings.MARKET_UNIVERSE_SSM_PARAM)
        return response["Parameter"]["Value"]
    except Exception as exc:  # noqa: BLE001 — SSM may be unavailable locally/CI
        logger.info("SSM active-universe lookup unavailable (%s); falling back to settings.yaml", exc)
        return None


def load_from_s3(filename: str) -> pd.DataFrame | None:
    """Best-effort read of a universe CSV from the versioned S3 config prefix."""
    if not settings.S3_BUCKET:
        return None
    try:
        import boto3

        client = boto3.client("s3", region_name=settings.AWS_REGION)
        key = f"{settings.MARKET_UNIVERSE_S3_PREFIX}{filename}"
        obj = client.get_object(Bucket=settings.S3_BUCKET, Key=key)
        text = obj["Body"].read().decode("utf-8")
    except Exception as exc:  # noqa: BLE001 — S3 may be unavailable/not yet published
        logger.info("S3 universe object unavailable (%s); falling back to local file", exc)
        return None

    import io

    return _validate(pd.read_csv(io.StringIO(text)), f"s3://{settings.S3_BUCKET}/{key}")


def resolve_active_filename() -> str:
    """The filename that would be used right now, without loading its rows."""
    return active_filename_from_ssm() or local_default_filename()


def load_universe(tickers_file: str = "") -> list[dict[str, str]]:
    """Resolve the active ASX universe using the documented precedence."""
    tickers_file = tickers_file or settings.ASX_TICKERS_FILE
    if tickers_file:
        return load_from_path(tickers_file)

    filename = resolve_active_filename()

    from_s3 = load_from_s3(filename)
    if from_s3 is not None:
        return from_s3.to_dict("records")

    try:
        return load_from_local_file(filename).to_dict("records")
    except Exception as exc:  # noqa: BLE001 — must never leave the pipeline with zero tickers
        logger.warning(
            "Local universe file %s unavailable (%s); using config.settings.DEFAULT_UNIVERSE", filename, exc
        )
        return settings.DEFAULT_UNIVERSE
