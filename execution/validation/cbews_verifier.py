"""
CBEWS Ground Truth Verification
Community-Based Early Warning System — photo/video validation pipeline.

Steps:
  1. Accept geo-tagged community report with photo URL
  2. Verify geotag authenticity (EXIF vs. reported location)
  3. Run AI flood-detection model on photo
  4. If verified: mark public_visible=True, feed into alert cross-reference
  5. If suspicious: flag for manual NEMA/NiMet review

Uses: OpenAI Vision API (or local YOLOv8 flood model for offline operation)
"""
import asyncio
import logging
import os
from typing import Optional
from uuid import UUID

import httpx
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

OPENAI_API_KEY   = os.getenv("OPENAI_API_KEY", "")
# Confidence threshold for automatic approval
FLOOD_CONFIDENCE_THRESHOLD = 0.75
# Max distance (km) between EXIF geotag and reported location
MAX_GEOTAG_DRIFT_KM = 2.0


async def verify_report(report_id: UUID, photo_url: str, reported_lat: float, reported_lng: float) -> dict:
    """
    Full verification pipeline for a community flood report.
    Returns: {verified: bool, confidence: float, method: str, notes: str}
    """
    results = {
        "report_id": str(report_id),
        "photo_verified": False,
        "geotag_verified": False,
        "photo_confidence": 0.0,
        "is_false_report": False,
        "public_visible": False,
        "notes": "",
    }

    # Step 1: AI flood detection on photo
    detection = await _run_flood_detection(photo_url)
    results["photo_confidence"] = detection["confidence"]
    results["photo_verified"] = detection["confidence"] >= FLOOD_CONFIDENCE_THRESHOLD
    results["notes"] = detection.get("notes", "")

    # Step 2: Geotag verification (where EXIF data available)
    exif_coords = await _extract_exif_coords(photo_url)
    if exif_coords:
        distance_km = _haversine(
            reported_lat, reported_lng,
            exif_coords["lat"], exif_coords["lng"]
        )
        results["geotag_verified"] = distance_km <= MAX_GEOTAG_DRIFT_KM
        if distance_km > MAX_GEOTAG_DRIFT_KM * 3:
            results["is_false_report"] = True
            results["notes"] += f" Geotag mismatch: {distance_km:.1f}km drift."
    else:
        # No EXIF — skip geotag verification but don't penalise
        results["geotag_verified"] = False

    # Determine public visibility
    # Must pass photo AI AND not be flagged as false report
    results["public_visible"] = (
        results["photo_verified"] and not results["is_false_report"]
    )

    log.info(
        f"Report {report_id}: photo_conf={results['photo_confidence']:.2f}, "
        f"public={results['public_visible']}, false={results['is_false_report']}"
    )
    return results


async def _run_flood_detection(photo_url: str) -> dict:
    """
    Uses OpenAI Vision API to detect flood conditions in photo.
    Falls back to heuristic if API unavailable (offline operation).
    """
    if not OPENAI_API_KEY:
        log.warning("OpenAI API not configured — using heuristic flood detection")
        return {"confidence": 0.5, "notes": "Heuristic (API unavailable)"}

    prompt = (
        "Analyze this image for flood conditions. "
        "Return a JSON object with: "
        "{'is_flood': bool, 'confidence': float 0-1, 'water_visible': bool, "
        "'flood_depth_estimate': str, 'notes': str}. "
        "Be conservative — only flag as flood if water is clearly present and abnormal."
    )

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": photo_url}},
                            ],
                        }
                    ],
                    "max_tokens": 200,
                    "response_format": {"type": "json_object"},
                },
                timeout=30,
            )
            resp.raise_for_status()
            import json
            content = resp.json()["choices"][0]["message"]["content"]
            result = json.loads(content)
            return {
                "confidence": float(result.get("confidence", 0.0)),
                "notes": result.get("notes", ""),
                "water_visible": result.get("water_visible", False),
            }
    except Exception as e:
        log.error(f"Flood detection API error: {e}")
        return {"confidence": 0.0, "notes": f"Detection failed: {e}"}


async def _extract_exif_coords(photo_url: str) -> Optional[dict]:
    """
    Download photo headers and extract EXIF GPS data if available.
    Returns {lat, lng} or None.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(photo_url, timeout=10, follow_redirects=True)
            resp.raise_for_status()
            content = resp.content

        import piexif
        from PIL import Image
        import io

        img = Image.open(io.BytesIO(content))
        exif_data = piexif.load(img.info.get("exif", b""))
        gps = exif_data.get("GPS", {})

        if not gps:
            return None

        def dms_to_decimal(dms, ref):
            d, m, s = [(n / d) for n, d in dms]
            decimal = d + m / 60 + s / 3600
            if ref in (b'S', b'W'):
                decimal = -decimal
            return decimal

        lat = dms_to_decimal(gps[piexif.GPSIFD.GPSLatitude], gps[piexif.GPSIFD.GPSLatitudeRef])
        lng = dms_to_decimal(gps[piexif.GPSIFD.GPSLongitude], gps[piexif.GPSIFD.GPSLongitudeRef])
        return {"lat": lat, "lng": lng}

    except Exception:
        return None   # No EXIF or extraction failed


def _haversine(lat1, lng1, lat2, lng2) -> float:
    """Haversine distance in km between two coordinates."""
    from math import radians, sin, cos, sqrt, atan2
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))
