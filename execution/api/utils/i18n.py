"""
i18n utilities for API response localisation.

Provides:
  - translate_severity()   — severity label in the requested language
  - translate_alert_type() — alert type label
  - get_alert_text()       — pull title/body/sms from multilingual alert row
"""
from typing import Literal

Lang = Literal["en", "ha", "yo", "ig", "pg"]

# Severity labels — verified translations matching frontend locales
SEVERITY_LABELS: dict[str, dict[str, str]] = {
    "RED": {
        "en": "CRITICAL",
        "ha": "TSANANI",
        "yo": "ÌPELE PUPA — EWUEWU",
        "ig": "ỌCHỊCHỌ — IHE IZE NDỤ DARA OJI",
        "pg": "RED — DANGER DON REACH",
    },
    "ORANGE": {
        "en": "HIGH RISK",
        "ha": "HAƊARI SOSAI",
        "yo": "EWU GÍGA",
        "ig": "IHE IZE NDỤ DỊ ÒJÒ",
        "pg": "HIGH RISK",
    },
    "YELLOW": {
        "en": "MODERATE",
        "ha": "MATSAKAICI",
        "yo": "ÌWỌ̀NBA",
        "ig": "ETUTO",
        "pg": "MODERATE — DEY ALERT",
    },
    "GREEN": {
        "en": "LOW RISK",
        "ha": "ƘARAMIN HAƊARI",
        "yo": "EWU KÉKERÉ",
        "ig": "IHE IZE NDỤ DỊ NTAKỊRỊ",
        "pg": "LOW RISK",
    },
    "HIGHLY_PROBABLE": {
        "en": "Highly Probable",
        "ha": "Mai Yiwuwa Sosai",
        "yo": "Ṣeéṣe Gidigidi",
        "ig": "Nwere Ike Nke Ukwuu",
        "pg": "Very Likely",
    },
    "PROBABLE": {
        "en": "Probable",
        "ha": "Mai Yiwuwa",
        "yo": "Ṣeéṣe",
        "ig": "Nwere Ike",
        "pg": "Likely",
    },
    "LOW_RISK": {
        "en": "Low Risk",
        "ha": "Ƙaramin Haɗari",
        "yo": "Ewu Kékeré",
        "ig": "Ihe Ize Ndụ Dị Ntakịrị",
        "pg": "Low Chance",
    },
    "NONE": {
        "en": "No Risk",
        "ha": "Babu Haɗari",
        "yo": "Kò Sí Ewu",
        "ig": "Enweghị Ihe Ize Ndụ",
        "pg": "No Risk",
    },
}

ALERT_TYPE_LABELS: dict[str, dict[str, str]] = {
    "FLOOD_RIVERINE": {
        "en": "Riverine Flood",
        "ha": "Ambaliyar Kogi",
        "yo": "Ikun Omi Odò",
        "ig": "Mmiri Ịda Osimiri",
        "pg": "River Flood",
    },
    "FLOOD_FLASH": {
        "en": "Flash Flood",
        "ha": "Ambaliyar Kwatsam",
        "yo": "Ikun Omi Lójijì",
        "ig": "Mmiri Ịda Ngwa Ngwa",
        "pg": "Flash Flood",
    },
    "HEATWAVE_RISK": {
        "en": "Heat Warning",
        "ha": "Gargadin Zafi",
        "yo": "Ìkìlọ̀ Ìgbóná",
        "ig": "Ọdịmara Okpomọkụ",
        "pg": "Heat Warning",
    },
    "DAM_RELEASE": {
        "en": "Dam Release Alert",
        "ha": "Gargadin Buɗe Dam",
        "yo": "Ìkìlọ̀ Ìṣílẹ̀ Dam",
        "ig": "Ọdịmara Mmepụta Dam",
        "pg": "Dam Release Alert",
    },
    "EVACUATION": {
        "en": "Evacuation Order",
        "ha": "Umurnin Ficewa",
        "yo": "Àṣẹ Kúrò",
        "ig": "Iwu Ịpụ",
        "pg": "Evacuation Order",
    },
}


def translate_severity(severity: str, lang: Lang) -> str:
    """Return severity label in the requested language. Falls back to English."""
    labels = SEVERITY_LABELS.get(severity, SEVERITY_LABELS.get("NONE", {}))
    return labels.get(lang, labels.get("en", severity))


def translate_alert_type(alert_type: str, lang: Lang) -> str:
    """Return alert type label in the requested language. Falls back to English."""
    labels = ALERT_TYPE_LABELS.get(alert_type, {})
    return labels.get(lang, labels.get("en", alert_type))


def get_alert_text(row: dict, field: str, lang: Lang) -> str:
    """
    Pull the correct language column from a DB row.
    field: "title" | "body" | "sms"
    Falls back to English if the localised column is NULL/empty.
    """
    col = f"{field}_{lang}"
    value = row.get(col) or ""
    if not value:
        value = row.get(f"{field}_en") or ""
    return value
