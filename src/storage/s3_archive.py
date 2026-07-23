"""Best-effort raw input archival for the platform data lake."""

from __future__ import annotations

import io
import logging

import boto3
import pandas as pd

from config import settings

logger = logging.getLogger(__name__)


def archive_dataframe(
    dataframe: pd.DataFrame,
    source: str,
    identifier: str,
    bucket: str | None = None,
    client=None,
) -> str | None:
    """Write a normalized raw extract to S3 and return its object key.

    Archival is deliberately non-fatal: a temporary data-lake outage must not
    stop the warehouse refresh, but it is logged for operations follow-up.
    """
    bucket = bucket or settings.S3_BUCKET
    if not bucket or dataframe.empty:
        return None

    run_date = pd.Timestamp.utcnow().strftime("%Y-%m-%d")
    key = f"raw/{source}/{run_date}/{identifier}.csv"
    buffer = io.StringIO()
    dataframe.to_csv(buffer, index=False)
    try:
        (client or boto3.client("s3", region_name=settings.AWS_REGION)).put_object(
            Bucket=bucket,
            Key=key,
            Body=buffer.getvalue().encode("utf-8"),
            ContentType="text/csv",
            ServerSideEncryption="AES256",
        )
    except Exception as exc:  # noqa: BLE001 - database ingestion remains available
        logger.warning("Raw archive failed for %s/%s: %s", source, identifier, exc)
        return None
    return key
