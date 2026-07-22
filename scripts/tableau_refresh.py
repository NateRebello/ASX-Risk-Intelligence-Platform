"""
Trigger a Tableau Server/Online extract refresh via the REST API after the
nightly ETL completes (Milestone 7).

Requires a Personal Access Token (PAT) configured on Tableau Server/Online.
Set TABLEAU_SERVER_URL, TABLEAU_SITE_ID, TABLEAU_TOKEN_NAME,
TABLEAU_TOKEN_SECRET, and TABLEAU_DATASOURCE_ID as environment variables
(or Lambda env vars / Secrets Manager in production).

Usage:
    python scripts/tableau_refresh.py
"""

from __future__ import annotations

import logging
import os
import sys

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

API_VERSION = "3.22"


def sign_in(server_url: str, site_id: str, token_name: str, token_secret: str) -> tuple[str, str]:
    resp = requests.post(
        f"{server_url}/api/{API_VERSION}/auth/signin",
        json={
            "credentials": {
                "personalAccessTokenName": token_name,
                "personalAccessTokenSecret": token_secret,
                "site": {"contentUrl": site_id},
            }
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()["credentials"]
    return data["token"], data["site"]["id"]


def refresh_datasource(server_url: str, api_site_id: str, token: str, datasource_id: str) -> dict:
    resp = requests.post(
        f"{server_url}/api/{API_VERSION}/sites/{api_site_id}/datasources/{datasource_id}/refresh",
        headers={"X-Tableau-Auth": token},
        json={},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> int:
    server_url = os.environ.get("TABLEAU_SERVER_URL")
    site_id = os.environ.get("TABLEAU_SITE_ID", "")
    token_name = os.environ.get("TABLEAU_TOKEN_NAME")
    token_secret = os.environ.get("TABLEAU_TOKEN_SECRET")
    datasource_id = os.environ.get("TABLEAU_DATASOURCE_ID")

    missing = [
        name
        for name, val in [
            ("TABLEAU_SERVER_URL", server_url),
            ("TABLEAU_TOKEN_NAME", token_name),
            ("TABLEAU_TOKEN_SECRET", token_secret),
            ("TABLEAU_DATASOURCE_ID", datasource_id),
        ]
        if not val
    ]
    if missing:
        logger.error("Missing required env vars: %s", ", ".join(missing))
        return 1

    token, api_site_id = sign_in(server_url, site_id, token_name, token_secret)
    result = refresh_datasource(server_url, api_site_id, token, datasource_id)
    logger.info("Refresh triggered: %s", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
