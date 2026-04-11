"""
Multilingual Alert Payload Builder
5 languages: English (en), Hausa (ha), Yoruba (yo), Igbo (ig), Nigerian Pidgin (pg)

UTF-8 encoding for diacritics: ẹ, ọ, í, ń (Yoruba/Igbo)
SMS: 160-char limit, GSM 7-bit where possible (diacritics require Unicode — 70 char/segment)
"""
from dataclasses import dataclass
from typing import Optional

# ============================================================
# TERMINOLOGY STANDARDISATION
# Per spec: verified translations for core climate terms
# ============================================================

TERMS = {
    "temperature": {
        "en": "Temperature",
        "ha": "Zafi",
        "yo": "Otutu",
        "ig": "Okpomọkụ",
        "pg": "Temperachọ",
    },
    "flood_warning": {
        "en": "Flood Warning",
        "ha": "Gargajiya",
        "yo": "Ikilọ Ikun Omi",
        "ig": "Ịdá adá",
        "pg": "Flood Alert",
    },
    "evacuate": {
        "en": "Evacuate Now",
        "ha": "Tashi yanzu",
        "yo": "Kúrò níbẹ̀ báyìí",
        "ig": "Pụọ ugbu a",
        "pg": "Run comot now",
    },
    "shelter": {
        "en": "Emergency Shelter",
        "ha": "Matsuguni na gaggawa",
        "yo": "Ibi aabo pajawiri",
        "ig": "Ebe nchekwa ihe ize ndụ",
        "pg": "Emergency shelter",
    },
    "severity_red": {
        "en": "CRITICAL — Imminent Danger",
        "ha": "TSANANI — Haɗari nan take",
        "yo": "IPELE PUPA — Ewu ti sunmọ",
        "ig": "ỌCHỊCHỌ — Ihe ize ndụ dị nso",
        "pg": "RED — Danger don reach",
    },
    "severity_orange": {
        "en": "HIGH RISK — Prepare to Evacuate",
        "ha": "HAƊARI — Shirya ficewa",
        "yo": "EWU GIGA — Mura silẹ lati kúrò",
        "ig": "IHE IZE NDỤ — Dị njikere ịpụ",
        "pg": "HIGH RISK — Ready to comot",
    },
    "severity_yellow": {
        "en": "MODERATE — Stay Vigilant",
        "ha": "MATSAKAICI — Kasance a faɗake",
        "yo": "DEDE — Jẹ ki o ṣọra",
        "ig": "ETUTO — Nọ na-elekọta",
        "pg": "MODERATE — Dey alert",
    },
    "source_label_govt": {
        "en": "Source: NEMA/NIHSA (Official)",
        "ha": "Source: NEMA/NIHSA (Hukuma)",
        "yo": "Orisun: NEMA/NIHSA (Ijọba)",
        "ig": "Isi mmalite: NEMA/NIHSA (Gọọmenti)",
        "pg": "Source: NEMA/NIHSA (Govment)",
    },
}


# ============================================================
# SMS TEMPLATES (160 chars, WAT timestamp)
# ============================================================

SMS_TEMPLATES = {
    "FLOOD_RIVERINE": {
        "en": "⚠ FLOOD ALERT [{severity}] {lga}, {state}. {probability}% flood risk next {days}d. Evacuate low areas. Shelter: {shelter_short}. NEMA:{nema_id} {timestamp}",
        "ha": "⚠ GARGAJIYA [{severity}] {lga}, {state}. Haɗarin ambaliya {probability}%. Ka tashi. Matsuguni: {shelter_short}. NEMA:{nema_id} {timestamp}",
        "yo": "⚠ IKILỌ IKUN [{severity}] {lga}, {state}. Ewu iṣan omi {probability}%. Kúrò. Ibi aabo: {shelter_short}. NEMA:{nema_id} {timestamp}",
        "ig": "⚠ ỊDÁ ADÁ [{severity}] {lga}, {state}. Ike mmiri {probability}%. Pụọ. Ebe nchekwa: {shelter_short}. NEMA:{nema_id} {timestamp}",
        "pg": "⚠ FLOOD ALERT [{severity}] {lga}, {state}. {probability}% flood chance. Run comot. Shelter: {shelter_short}. NEMA:{nema_id} {timestamp}",
    },
    "HEATWAVE": {
        "en": "⚠ HEAT ALERT {temp}°C in {lga}, {state}. Stay indoors 11am-4pm. Drink water. Children/elderly at risk. NiMet:{nimet_id} {timestamp}",
        "ha": "⚠ ZAFI {temp}°C a {lga}. Zauna ciki 11-4pm. Sha ruwa. Yara/tsofaffi a haɗari. NiMet:{nimet_id} {timestamp}",
        "yo": "⚠ OTUTU {temp}°C ni {lga}. Wa inu ile 11am-4pm. Mu omi. Awọn ọmọde/agbalagba wa ninu ewu. NiMet:{nimet_id} {timestamp}",
        "ig": "⚠ OKPOMỌKỤ {temp}°C na {lga}. Nọdị n'ime ụlọ 11am-4pm. Ṅụọ mmiri. Ndị okenye/ụmụaka na-egwu. NiMet:{nimet_id} {timestamp}",
        "pg": "⚠ HOT WEATHER {temp}°C for {lga}. Stay inside 11am-4pm. Drink water. Children/old people dey risk. NiMet:{nimet_id} {timestamp}",
    },
    "EVACUATION": {
        "en": "🚨 EVACUATE NOW {lga}, {state}. Official order from NEMA. Go to: {shelter_short}. Avoid: {avoid_roads}. Call 08000-NEMA. ID:{nema_id}",
        "ha": "🚨 TASHI YANZU {lga}. Umarnin NEMA. Je zuwa: {shelter_short}. Guji: {avoid_roads}. Kira 08000-NEMA. ID:{nema_id}",
        "yo": "🚨 KÚRÒ BÁYÌÍ {lga}. Aṣẹ NEMA. Lọ si: {shelter_short}. Yago fun: {avoid_roads}. Pe 08000-NEMA. ID:{nema_id}",
        "ig": "🚨 PỤỌ UGBU A {lga}. Iwu NEMA. Gaa: {shelter_short}. Zere: {avoid_roads}. Kpọọ 08000-NEMA. ID:{nema_id}",
        "pg": "🚨 RUN COMOT NOW {lga}. NEMA order. Go to: {shelter_short}. No pass: {avoid_roads}. Call 08000-NEMA. ID:{nema_id}",
    },
}


def build_multilingual_payload(event, severity: str) -> dict:
    """
    Build complete alert dict with title/body/SMS in all 5 languages.
    Called by alert_classifier.py before persistence.
    """
    data = event.data
    lga_name  = data.get("lga_name", "Unknown LGA")
    state_name = data.get("state_name", "")
    timestamp = _wat_timestamp()

    sev_term = {
        "RED":    "severity_red",
        "ORANGE": "severity_orange",
        "YELLOW": "severity_yellow",
        "GREEN":  "severity_green",
    }.get(severity, "severity_yellow")

    payload = {
        "alert_type": event.event_type,
        "severity": severity,
        "lga_id": event.lga_id,
        "source_primary": event.source,
        "valid_from": timestamp,
        "nema_alert_id": data.get("nema_alert_id"),
        "nihsa_alert_id": data.get("nihsa_alert_id"),
    }

    # Build multilingual title/body/SMS for each language
    for lang in ("en", "ha", "yo", "ig", "pg"):
        sev_label = TERMS.get(sev_term, {}).get(lang, severity)
        flood_term = TERMS["flood_warning"].get(lang, "Flood Warning")
        source_label = TERMS["source_label_govt"].get(lang, "Source: NEMA/NIHSA")

        payload[f"title_{lang}"] = f"{flood_term}: {sev_label} — {lga_name}"
        payload[f"body_{lang}"]  = _build_body(event, severity, lang, lga_name, state_name, source_label)
        payload[f"sms_{lang}"]   = _build_sms(event, severity, lang, lga_name, state_name, timestamp)

    return payload


def _build_body(event, severity, lang, lga, state, source_label) -> str:
    data = event.data
    prob = data.get("probability_pct", 0)
    temp = data.get("temp_max_c")

    if event.event_type == "HEATWAVE_RISK" and temp:
        base = {
            "en": f"Maximum temperature of {temp}°C expected. Health risk to children, elderly, and outdoor workers. Stay indoors 11am–4pm. Drink water regularly.",
            "ha": f"Zafin yanayi har {temp}°C ana tsammanin. Yaranku da tsofaffi su zauna gida 11-4pm. Su sha ruwa.",
            "yo": f"Iwọn otutu ti {temp}°C ni a retí. Awọn ọmọdé àti àgbàdo máa wà inú ilé 11am-4pm. Mu omi.",
            "ig": f"A na-atọ anya okpomọkụ nke {temp}°C. Ụmụ nwa na ndị okenye nọdị n'ime ụlọ. Ṅụọ mmiri.",
            "pg": f"Temperature go reach {temp}°C. Children and old people stay inside 11am-4pm. Drink water plenty.",
        }
        return f"{base.get(lang, base['en'])}\n\n{source_label}"

    base = {
        "en": f"{prob}% probability of flooding in the next 5 days. LGAs along Niger/Benue confluence at highest risk. Secure valuables, know your nearest shelter.",
        "ha": f"Haɗarin ambaliya {prob}% a cikin kwanaki 5. Shirya matsuguni. Tabbatar da amincinku.",
        "yo": f"Iṣeeṣe iṣan omi {prob}% ni ọjọ 5 to nbọ. Mura ibi aabo rẹ. Dáàbò bo ohun-ini rẹ.",
        "ig": f"Ike mmiri {prob}% n'ụbọchị 5 na-abịa. Chee ebe nchekwa gị n'uche. Echekwa ihe ọ bụla dị ọnụahịa.",
        "pg": f"{prob}% chance of flood next 5 days. Know where shelter dey. Protect your things.",
    }
    return f"{base.get(lang, base['en'])}\n\n{source_label}"


def _build_sms(event, severity, lang, lga, state, timestamp) -> str:
    """Build SMS ≤160 chars. Unicode diacritics = 70 chars/segment for Yo/Ig."""
    template_key = {
        "HEATWAVE_RISK": "HEATWAVE",
        "FLOOD_RIVERINE": "FLOOD_RIVERINE",
        "EVACUATION": "EVACUATION",
    }.get(event.event_type, "FLOOD_RIVERINE")

    template = SMS_TEMPLATES.get(template_key, SMS_TEMPLATES["FLOOD_RIVERINE"]).get(lang, "")
    data = event.data

    sms = template.format(
        severity=severity,
        lga=lga[:20],
        state=state[:10],
        probability=int(data.get("probability_pct", 0)),
        days=5,
        shelter_short=_short_shelter(data.get("shelter_coords")),
        nema_id=data.get("nema_alert_id", "N/A"),
        nimet_id=data.get("nimet_alert_id", "N/A"),
        temp=data.get("temp_max_c", "--"),
        avoid_roads=data.get("avoid_roads", "flooded routes"),
        timestamp=timestamp[:11],
    )
    return sms[:160]   # hard truncate to SMS limit


def _short_shelter(shelters) -> str:
    if not shelters:
        return "Call 08000-NEMA"
    s = shelters[0] if isinstance(shelters, list) else shelters
    return s.get("name", "Local shelter")[:30]


def _wat_timestamp() -> str:
    from datetime import datetime, timezone, timedelta
    WAT = timezone(timedelta(hours=1))
    return datetime.now(WAT).strftime("%d/%m/%Y %H:%M WAT")
