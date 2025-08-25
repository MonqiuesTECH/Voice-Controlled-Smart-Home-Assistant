import re
from typing import Dict, Any, Optional

# Simple, deterministic parser for smart‑home intents.
# Returns a normalized dict: { intent, action, device, location, value }

LOCATIONS = [
    "living room", "kitchen", "bedroom", "garage", "office", "hallway", "bathroom"
]
LOCATION_ALIASES = {
    "livingroom": "living room",
    "living-room": "living room",
}

DEVICE_SYNONYMS = {
    "lights": "light",
    "light": "light",
    "lamp": "light",
    "fan": "fan",
    "thermostat": "thermostat",
    "ac": "thermostat",
    "air": "thermostat",
    "garage": "garage",
    "garage door": "garage",
    "door": "garage",
}

ACTION_SYNONYMS = {
    "on": "on",
    "off": "off",
    "open": "open",
    "close": "close",
    "up": "open",
    "down": "close",
    "start": "on",
    "stop": "off",
    "turn on": "on",
    "turn off": "off",
    "switch on": "on",
    "switch off": "off",
    "set": "set",
}

def normalize_location(text: str) -> Optional[str]:
    t = text.strip().lower()
    if t in LOCATION_ALIASES:
        t = LOCATION_ALIASES[t]
    return t if t in LOCATIONS else None

def extract_number(text: str) -> Optional[float]:
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
        return {"intent": "none", "action": None, "device": None, "location": None, "value": None, "raw": transcript}

    # Normalize common multi-word actions
    t = t.replace("turn on", "on").replace("turn off", "off").replace("switch on", "on").replace("switch off", "off")

    # Heuristics:
    # Devices
    device = None
    for k, v in DEVICE_SYNONYMS.items():
        if re.search(rf"\b{k}\b", t):
            device = v
            break

    # Actions
    action = None
    if re.search(r"\bon\b", t):
        action = "on"
    elif re.search(r"\boff\b", t):
        action = "off"
    elif re.search(r"\bopen\b", t):
        action = "open"
    elif re.search(r"\bclose\b", t):
        action = "close"
    elif re.search(r"\bset\b", t):
        action = "set"

    # Location (simple heuristic: look for known rooms)
    location = None
    for loc in LOCATIONS:
        if re.search(rf"\b{re.escape(loc)}\b", t):
            location = loc
            break
    # Handle single-word variants like "livingroom"
    if location is None:
        for alias, normalized in LOCATION_ALIASES.items():
            if re.search(rf"\b{re.escape(alias)}\b", t):
                location = normalized
                break

    # Value (typically for thermostat)
    value = None
    if device == "thermostat" or (action == "set" and device):
        val = extract_number(t)
        if val is not None:
            value = int(val)

    # Defaults
    if device is None:
        # Guess: lights are the most common
        if action in ("on", "off"):
            device = "light"
        elif action in ("open", "close"):
            device = "garage"

    if device == "light" and location is None:
        location = "living room"

    if device == "thermostat" and action is None:
        action = "set"

    return {
        "intent": "device_control" if device else "unknown",
        "action": action,
        "device": device,
        "location": location,
        "value": value,
        "raw": transcript,
    }
