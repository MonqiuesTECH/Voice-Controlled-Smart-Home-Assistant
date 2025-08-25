README.md
Voice‑Controlled Smart Home Assistant (Streamlit, No OpenAI)

A lightweight voice assistant you can deploy on Streamlit’s free tier. It transcribes speech with faster‑whisper, parses commands with a deterministic command parser, and sends device actions to either:

a local Arduino via a tiny Python socket bridge (when running locally), or

a built‑in simulator (when deployed to Streamlit Cloud).

Features

STT pipeline: Whisper (via faster-whisper, CPU‑friendly)

Command parser: Deterministic regex + small intent grammar (no external LLM required)

GPIO signal generator: Arduino sketch included; controlled via a local socket bridge

Cloud‑friendly: Works on Streamlit Cloud in SIMULATOR_MODE (no hardware needed)

Optional LLM: Hook in a non‑OpenAI provider later by setting one env var (kept off by default)

Architecture
[Browser Mic] ──> Streamlit app (Whisper STT) ──> Command Parser ──> Action
                                                           │
                                                           ├─> (SIMULATOR) Show GPIO state in UI
                                                           └─> (LOCAL) TCP socket -> Python Bridge -> Serial -> Arduino

Two Ways to Run
1) Cloud Demo (Streamlit Cloud – no hardware)

Uses SIMULATOR_MODE (default on Cloud).

Speak or upload an audio clip → see parsed command + simulated GPIO state.

2) Full Local Control (with Arduino)

Run the Device Bridge on your machine.

Connect Arduino via USB.

The Streamlit app sends actions over TCP → bridge forwards to Arduino over serial.

Setup
A) Python environment
python -m venv .venv && source .venv/bin/activate  # (Windows: .venv\Scripts\activate)
pip install -r requirements.txt

B) Streamlit secrets / env

Create .streamlit/secrets.toml (optional but recommended):

# .streamlit/secrets.toml
SIMULATOR_MODE = true         # true on Cloud; set false for local hardware
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 8765

# Optional: If you later add a non‑OpenAI LLM endpoint, set:
USE_EXTERNAL_LLM = false
EXTERNAL_LLM_BASE_URL = ""    # e.g., HuggingFace Inference Endpoint (optional)
EXTERNAL_LLM_API_KEY = ""     # token for that provider (optional)

C) Arduino wiring (example)

LED (with resistor) on pin 13 (built‑in LED also works).

(Optional) Garage door servo on pin 9.

(Optional) Fan relay on pin 7.

Upload the provided sketch (arduino_smart_home/arduino_smart_home.ino) via Arduino IDE.

D) Run the Device Bridge (for local hardware)
python device_bridge.py --serial-port /dev/ttyACM0 --baud 115200 --host 127.0.0.1 --port 8765
# Windows example: --serial-port COM3

E) Start the app
streamlit run app.py


On Streamlit Cloud, push the repo and deploy. It will default to SIMULATOR_MODE=true and work without hardware.

Using the App

Click Start Recording (or upload an audio file).

Click Transcribe & Execute.

See:

Transcript (from Whisper)

Parsed Command (intent, device, location, value)

Result (simulated or sent to Arduino)

Example commands

“Turn on the living room lights”

“Turn off kitchen fan”

“Set thermostat to 72”

“Open the garage”

“Close the garage”

Files

app.py – Streamlit UI + STT + socket/sim integration

command_parser.py – Deterministic intent/entity parser

device_bridge.py – TCP server that forwards JSON actions to Arduino over serial

arduino_smart_home/arduino_smart_home.ino – Arduino sketch (GPIO/servo control)

requirements.txt – Python deps

.streamlit/secrets.toml – config (optional/local)

Notes & Limits

Whisper on CPU: choose tiny or base for speed on free tiers.

Mic capture: handled via streamlit-webrtc. If your browser/mic blocks it, upload a WAV/MP3 file instead.

No OpenAI: The assistant runs fully without OpenAI. An optional non‑OpenAI LLM hook is included (disabled by default).

Security: If you expose the bridge over the network, protect it (firewall, private network, or auth proxy).

Troubleshooting

No audio from mic: Use the Upload audio path; check browser permissions.

Whisper too slow: Switch model size to tiny in the UI sidebar.

Bridge not found: Ensure SIMULATOR_MODE=false, bridge running, host/port correct, Arduino connected to the right serial port.

Arduino not reacting: Open Serial Monitor at the same baud to see logs; confirm pins match your wiring.
