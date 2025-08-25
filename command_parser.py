import re
from typing import Dict, Any, Optional

# Rooms / Locations
LOCATIONS_EN = [
    "living room","kitchen","bedroom","garage","office","hallway","bathroom"
]
LOCATIONS_ES = [
    "sala","cocina","dormitorio","garaje","oficina","pasillo","baño","bano"
]
LOCATION_ALIASES = {
    "livingroom": "living room",
    "living-room": "living room",
}

# Devices
DEVICE_SYNONYMS = {
    # English
    "lights":"light","light":"light","lamp":"light","fan":"fan",
    "thermostat":"thermostat","ac":"thermostat","air":"thermostat",
    "garage":"garage","garage door":"garage","door":"garage",
    # Spanish
    "luces":"light","luz":"light","ventilador":"fan",
    "termostato":"thermostat","aire":"thermostat","ac":"thermostat",
    "garaje":"garage","puerta del garaje":"garage","puerta":"garage",
}

# Actions
ACTION_SYNONYMS = {
    # English
    "on":"on","off":"off","open":"open","close":"close","set":"set",
    "up":"open","down":"close","start":"on","stop":"off",
    "turn on":"on","turn off":"off","switch on":"on","switch off":"off",
    # Spanish
    "encender":"on","prender":"on","apagar":"off",
    "abrir":"open","cerrar":"close","subir":"open","bajar":"close","ajustar":"set","poner":"set"
}

def _normalize_location(text: str) -> Optional[str]:
    t = text.strip().lower()
    if t in LOCATION_ALIASES: t = LOCATION_ALIASES[t]
    if t in LOCATIONS_EN: return t
    if t in LOCATIONS_ES:
        # map to English canonical names to keep keys stable
        mapping = {
            "sala":"living room","cocina":"kitchen","dormitorio":"bedroom","garaje":"garage",
            "oficina":"office","pasillo":"hallway","baño":"bathroom","bano":"bathroom"
        }
        return mapping[t]
    return None

def _extract_number(text: str) -> Optional[float]:
    m = re.search(r"(-?\d+(\.\d+)?)", text)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None

def parse_command(transcript: str) -> Dict[str, Any]:
    t = (transcript or "").strip().lower()
    if not t:
        return {"intent":"none","action":None,"device":None,"location":None,"value":None,"raw":transcript}

    # Normalize multi-word actions in both languages
    replacements = {
        "turn on":"on","turn off":"off","switch on":"on","switch off":"off",
        "encender":"on","prender":"on","apagar":"off","abrir":"open","cerrar":"close",
        "ajustar":"set","poner":"set"
    }
    for k,v in replacements.items():
        t = t.replace(k, v)

    # Device
    device = None
    for k, v in DEVICE_SYNONYMS.items():
        if re.search(rf"\b{re.escape(k)}\b", t):
            device = v; break

    # Action
    action = None
    for k,v in ACTION_SYNONYMS.items():
        if re.search(rf"\b{re.escape(k)}\b", t):
            action = v; break

    # Location
    location = None
    for loc in LOCATIONS_EN + LOCATIONS_ES + list(LOCATION_ALIASES.keys()):
        if re.search(rf"\b{re.escape(loc)}\b", t):
            location = _normalize_location(loc); break

    # Value (e.g., thermostat temp)
    value = None
    if device == "thermostat" or (action == "set" and device):
        num = _extract_number(t)
        if num is not None:
            value = int(num)

    # Defaults
    if device is None:
        if action in ("on","off"): device = "light"
        elif action in ("open","close"): device = "garage"
    if device == "light" and location is None: location = "living room"
    if device == "thermostat" and action is None: action = "set"

    return {"intent":"device_control" if device else "unknown",
            "action":action,"device":device,"location":location,"value":value,"raw":transcript}
