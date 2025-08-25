# app.py — ZARI Smart Home Assistant (UI with no engine/IP details)

import os, io, json, socket, tempfile
from typing import Optional, Dict, Any

import streamlit as st
import numpy as np
import soundfile as sf
from pydub import AudioSegment
from streamlit_mic_recorder import mic_recorder

# Internal intent parser (kept generic)
from command_parser import parse_command

# Internal speech-to-text engine (kept generic in UI)
from faster_whisper import WhisperModel as STTEngine  # alias to avoid surfacing specific names in UI


# -----------------------------
# Minimal config (secrets/env)
# -----------------------------
def _get_secret_bool(name: str, default: bool) -> bool:
    try:
        raw = st.secrets.get(name)
    except Exception:
        raw = None
    if raw is None:
        raw = os.getenv(name, str(default))
    return str(raw).lower() in ("1", "true", "yes", "y", "on")

SIMULATOR_MODE = _get_secret_bool("SIMULATOR_MODE", True)
BRIDGE_HOST = st.secrets.get("BRIDGE_HOST", os.getenv("BRIDGE_HOST", "127.0.0.1"))
BRIDGE_PORT = int(st.secrets.get("BRIDGE_PORT", os.getenv("BRIDGE_PORT", "8765")))

# -----------------------------
# Branding
# -----------------------------
st.set_page_config(page_title="Smart Home Assistant", page_icon="🎙️")
st.title("🎙️ Smart Home Assistant")
st.caption("Powered by ZARI")

# Optional: keep a simple simulator state
if "sim_gpio" not in st.session_state:
    st.session_state.sim_gpio = {
        "light:living room": False,
        "light:kitchen": False,
        "fan:kitchen": False,
        "garage:door": "closed",
        "thermostat:home": 72,
    }

# -----------------------------
# Sidebar (minimal, no engine details)
# -----------------------------
st.sidebar.header("Settings")
lang_choice = st.sidebar.selectbox("Language", ["auto", "en", "es"], index=0)
st.sidebar.write("Mode:", "SIMULATOR" if SIMULATOR_MODE else "HARDWARE")

# Cache the internal STT engine without surfacing details
@st.cache_resource(show_spinner=False)
def _load_stt():
    # Sensible defaults for CPU; hidden from UI
    return STTEngine("tiny", compute_type="int8")

stt = _load_stt()


# -----------------------------
# Helpers
# -----------------------------
def _to_wav_16k_mono_bytes(blob: bytes) -> bytes:
    seg = AudioSegment.from_file(io.BytesIO(blob))
    seg = seg.set_channels(1).set_frame_rate(16000)
    samples = np.array(seg.get_array_of_samples()).astype(np.int16)
    out = io.BytesIO()
    sf.write(out, samples, 16000, subtype="PCM_16", format="WAV")
    return out.getvalue()

def _transcribe(wav_path: str, lang_hint: Optional[str]) -> str:
    segments, info = stt.transcribe(
        wav_path,
        language=None if (lang_hint in (None, "", "auto")) else lang_hint
    )
    return "".join([s.text for s in segments]).strip()

def _summarize_intent(intent: Dict[str, Any]) -> str:
    d = intent.get("device") or "device"
    a = intent.get("action") or "action"
    loc = intent.get("location") or "home"
    val = intent.get("value")
    if d == "thermostat" and isinstance(val, (int, float)):
        return f"{d.capitalize()} → {int(val)}° at {loc}"
    if d == "garage" and a in ("open", "close"):
        return f"{d.capitalize()} → {a.upper()} at {loc}"
    if d in ("light", "fan") and a in ("on", "off"):
        return f"{d.capitalize()} ({loc}) → {a.upper()}"
    return f"{d.capitalize()} → {a} ({loc})"

# -----------------------------
# 1) Capture Audio (no engine/UI details)
# -----------------------------
st.subheader("1) Capture Audio")

tab_mic, tab_upload = st.tabs(["🎤 Microphone", "📁 Upload Audio"])
audio_bytes: Optional[bytes] = None

with tab_mic:
    st.write("Press **Start**, speak, then **Stop**.")
    rec = mic_recorder(
        start_prompt="Start",
        stop_prompt="Stop",
        just_once=True,
        use_container_width=True,
        format="wav",
        key="zari_mic",
    )
    if rec and isinstance(rec, dict) and rec.get("bytes"):
        audio_bytes = rec["bytes"]
        st.audio(audio_bytes, format="audio/wav")

with tab_upload:
    up = st.file_uploader("Upload a short voice clip", type=["wav", "mp3", "m4a"])
    if up is not None:
        audio_bytes = up.read()
        st.success(f"Loaded {up.name}")

# -----------------------------
# 2) Execute
# -----------------------------
st.subheader("2) Run")
run = st.button("Transcribe & Execute", type="primary", disabled=(audio_bytes is None))

if run:
    if audio_bytes is None:
        st.warning("Record or upload audio first.")
        st.stop()

    with st.spinner("Working…"):
        try:
            wav_norm = _to_wav_16k_mono_bytes(audio_bytes)
        except Exception as e:
            st.error(f"Audio error: {e}")
            st.stop()

        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpf:
            tmpf.write(wav_norm)
            wav_path = tmpf.name

        transcript = _transcribe(wav_path, lang_choice)
        intent = parse_command(transcript)

    st.write("**Heard**")
    st.code(transcript or "(empty)")

    st.write("**Action**")
    st.success(_summarize_intent(intent))

    # Apply action
    if SIMULATOR_MODE:
        dev = intent.get("device")
        act = intent.get("action")
        loc = (intent.get("location") or "home")
        val = intent.get("value")

        if dev in ("light", "fan") and act in ("on", "off"):
            st.session_state.sim_gpio[f"{dev}:{loc}"] = (act == "on")
        elif dev == "thermostat" and isinstance(val, (int, float)):
            st.session_state.sim_gpio["thermostat:home"] = int(val)
        elif dev == "garage" and act in ("open", "close"):
            st.session_state.sim_gpio["garage:door"] = "open" if act == "open" else "closed"

        st.write("**Home status**")
        st.json(st.session_state.sim_gpio)
    else:
        try:
            payload = json.dumps(intent).encode("utf-8")
            with socket.create_connection((BRIDGE_HOST, BRIDGE_PORT), timeout=3) as s:
                s.sendall(payload + b"\n")
            st.success("Sent to local controller.")
        except Exception as e:
            st.error(f"Controller unreachable: {e}")

st.divider()
st.caption("© ZARI")
