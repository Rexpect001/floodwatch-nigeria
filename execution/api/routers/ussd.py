"""
USSD Handler — *384*FLOOD# query system for basic phone users.

Africa's Talking USSD callback endpoint.
Session flow:
  CON → Main menu (1=Flood Risk, 2=Weather, 3=Evacuate, 4=Language)
    1 → Enter LGA number or 0 for current state summary
    2 → Current conditions + 24h forecast
    3 → Nearest shelter + route
    4 → Language select (EN/HA/YO/IG/PG)
  END → Final message (160-char optimised)

All responses <182 chars (USSD limit).
"""
from fastapi import APIRouter, Form
from fastapi.responses import PlainTextResponse

# db + i18n imported only if needed inside handlers (USSD responses are lightweight)

router = APIRouter()

LANG_CODES = {"1": "en", "2": "ha", "3": "yo", "4": "ig", "5": "pg"}


@router.post("/callback", response_class=PlainTextResponse)
async def ussd_callback(
    sessionId: str = Form(...),
    serviceCode: str = Form(...),
    phoneNumber: str = Form(...),
    text: str = Form(default=""),
):
    """
    Africa's Talking USSD callback.
    Prefix CON = continue session, END = terminal message.
    """
    parts = text.split("*") if text else []
    level = len(parts)

    if level == 0:
        return (
            "CON Welcome to FloodWatch NG\n"
            "1. Flood Risk\n"
            "2. Weather Alert\n"
            "3. Evacuation Help\n"
            "4. Change Language"
        )

    if parts[0] == "1":
        if level == 1:
            return "CON Enter LGA code (0=state summary):"
        lga_code = parts[1]
        summary = await _get_flood_summary_ussd(lga_code, phoneNumber)
        return f"END {summary}"

    elif parts[0] == "2":
        if level == 1:
            return "CON Enter LGA code:"
        weather = await _get_weather_ussd(parts[1])
        return f"END {weather}"

    elif parts[0] == "3":
        shelters = await _get_shelter_ussd(phoneNumber)
        return f"END {shelters}"

    elif parts[0] == "4":
        if level == 1:
            return (
                "CON Select language:\n"
                "1. English\n2. Hausa\n3. Yoruba\n4. Igbo\n5. Pidgin"
            )
        lang = LANG_CODES.get(parts[1], "en")
        await _save_lang_preference(phoneNumber, lang)
        return f"END Language set. Dial *384*FLOOD# again."

    return "END Invalid option. Dial *384*FLOOD# to restart."


async def _get_flood_summary_ussd(lga_code: str, phone: str) -> str:
    """Returns a 160-char flood risk summary for USSD display."""
    # In production: query flood_forecasts + active alerts tables
    return "NIHSA: Kogi LGA - HIGH FLOOD RISK next 5 days. Evacuate low-lying areas. Call 08000-NEMA for help. -FloodWatchNG"


async def _get_weather_ussd(lga_code: str) -> str:
    return "NiMet: Heavy rain expected 24-48h. Wind 55km/h. Temp 31C. Stay indoors. -FloodWatchNG"


async def _get_shelter_ussd(phone: str) -> str:
    return "Nearest shelter: Kogi State Secondary School, 8.48N 6.74E, cap 500. Route: avoid Lokoja Bridge. -NEMA"


async def _save_lang_preference(phone: str, lang: str):
    pass  # Persist to DB in production
