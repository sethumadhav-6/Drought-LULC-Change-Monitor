"""
Google Earth Engine bootstrap.

Uses the geemap / opengeos ecosystem (https://github.com/opengeos,
https://github.com/giswqs) as the primary data-access layer for
Sentinel-2 and Landsat. Authenticates with a service account so the
API can run headless (e.g. on Render) rather than needing an
interactive `earthengine authenticate` each time.

If no credentials are configured, `is_available()` returns False and
callers should fall back to the Planetary Computer STAC client in
core/stac_pc.py.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache

from .config import get_settings

logger = logging.getLogger(__name__)

_EE_READY = False


def _try_init() -> bool:
    global _EE_READY
    settings = get_settings()
    try:
        import ee
    except ImportError:
        logger.warning("earthengine-api not installed; GEE backend disabled.")
        return False

    try:
        if settings.gee_service_account and (
            settings.gee_service_account_key_path or settings.gee_service_account_key_json
        ):
            if settings.gee_service_account_key_json:
                key_data = json.loads(settings.gee_service_account_key_json)
                credentials = ee.ServiceAccountCredentials(
                    settings.gee_service_account, key_data=json.dumps(key_data)
                )
            else:
                credentials = ee.ServiceAccountCredentials(
                    settings.gee_service_account, settings.gee_service_account_key_path
                )
            ee.Initialize(credentials, project=settings.gee_project)
        else:
            # Falls back to Application Default Credentials / cached
            # `earthengine authenticate` token, useful for local dev.
            ee.Initialize(project=settings.gee_project)
        _EE_READY = True
        logger.info("Google Earth Engine initialized.")
    except Exception as exc:  # noqa: BLE001
        logger.warning("GEE initialization failed, will use Planetary Computer fallback: %s", exc)
        _EE_READY = False
    return _EE_READY


@lru_cache
def is_available() -> bool:
    return _try_init()


def ee_module():
    """Return the initialized `ee` module, raising if unavailable."""
    if not is_available():
        raise RuntimeError(
            "Google Earth Engine is not available. Configure GEE_SERVICE_ACCOUNT + "
            "GEE_SERVICE_ACCOUNT_KEY_JSON (or run `earthengine authenticate` locally), "
            "or use the Planetary Computer data source instead."
        )
    import ee

    return ee


def kerala_boundary():
    """
    Kerala state boundary via FAO GAUL (level-1 admin boundaries).
    Swap for a Survey-of-India / GADM asset if higher precision is needed.
    """
    ee = ee_module()
    gaul = ee.FeatureCollection("FAO/GAUL/2015/level1")
    return gaul.filter(ee.Filter.eq("ADM1_NAME", "Kerala"))


def kerala_districts():
    """Kerala's 14 districts as a FeatureCollection (FAO GAUL level-2)."""
    ee = ee_module()
    gaul2 = ee.FeatureCollection("FAO/GAUL/2015/level2")
    return gaul2.filter(ee.Filter.eq("ADM1_NAME", "Kerala"))
