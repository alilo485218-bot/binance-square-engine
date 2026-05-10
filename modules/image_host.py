"""Image Host — يرفع الصورة إلى استضافة عامة ويرجع image_url صالح للنشر.

السبب: Binance Square OpenAPI نصي فقط؛ بدون استضافة عامة لن تظهر الصورة لأحد.

تجرّب مزوّدات بترتيب الأفضلية:
1. ImgBB إذا كان IMGBB_API_KEY متوفر (موصى — رابط مباشر، CDN سريع، 32 MB max).
2. 0x0.st كاحتياط مجاني (لا يحتاج مفتاح، لكن قد يحجب الزائرين).
3. لو كل شيء فشل: يرجع None ويعتمد المتصل على رابط محلي + رفع يدوي.

Usage:
    from modules.image_host import upload_to_public

    url = upload_to_public("/path/to/hook.png")
    if url:
        publisher.publish_text(body, image_url=url)
    else:
        # fallback: حمّل الصورة يدويًا
        ...
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)


def upload_to_public(image_path: str, prefer: Optional[str] = None) -> Optional[str]:
    """يحاول رفع الصورة لاستضافة عامة ويرجع URL أو None.

    prefer: None | "imgbb" | "0x0" — لإجبار مزوّد محدد للاختبار.
    """
    if not os.path.exists(image_path):
        logger.warning("image not found: %s", image_path)
        return None

    providers = []
    if prefer == "imgbb" or (prefer is None and config.IMGBB_API_KEY):
        providers.append(_upload_imgbb)
    if prefer == "0x0" or prefer is None:
        providers.append(_upload_0x0)

    for fn in providers:
        try:
            url = fn(image_path)
            if url:
                logger.info("uploaded via %s: %s", fn.__name__, url)
                return url
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s failed: %s", fn.__name__, exc)
            continue
    return None


def _upload_imgbb(image_path: str) -> Optional[str]:
    """ImgBB — أبسط وأسرع. يحتاج IMGBB_API_KEY."""
    if not config.IMGBB_API_KEY:
        return None
    with open(image_path, "rb") as fh:
        b64 = base64.b64encode(fh.read()).decode("ascii")
    resp = requests.post(
        "https://api.imgbb.com/1/upload",
        data={"key": config.IMGBB_API_KEY, "image": b64},
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("success"):
        return payload.get("data", {}).get("url")
    return None


def _upload_0x0(image_path: str) -> Optional[str]:
    """0x0.st — مجاني بدون مفتاح. الرابط يبقى ~30 يوم."""
    with open(image_path, "rb") as fh:
        resp = requests.post(
            "https://0x0.st",
            files={"file": fh},
            headers={"User-Agent": "binance-square-engine/1.0"},
            timeout=30,
        )
    resp.raise_for_status()
    url = resp.text.strip()
    if url.startswith("http"):
        return url
    return None
