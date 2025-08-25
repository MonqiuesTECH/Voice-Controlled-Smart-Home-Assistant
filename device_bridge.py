"""
TCP -> Serial bridge for local Arduino control.

Usage:
  python device_bridge.py --serial-port /dev/ttyACM0 --baud 115200 --host 127.0.0.1 --port 8765
  (Windows example: --serial-port COM3)
"""
import argparse
import json
import socket
import threading
import sys
import time

import serial  # pyserial


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--serial-port", required=True, help="e.g., /dev/ttyACM0 or COM3")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    return p.parse_args()


def to_arduino_line(cmd: dict) -> str:
    device = cmd.get("device")
    action = cmd.get("action")
    location = (cmd.get("location") or "home").replace(" ", "_")
    value = cmd.get("value")

    if device in ("light", "fan"):
        state = "ON" if action == "on" else "OFF"
        return f"{device.upper()}:{location}:{state}\n"
    if device == "thermostat" and isinstance(value, int):
        return f"THERMOSTAT:{location}:{value}\n"
    if device == "garage":
        state = "OPEN" if action == "open" else "CLOSE"
        return f"GARAGE:{location}:{state}\n"

    return f"UNKNOWN:{device}:{action}:{location}:{value}\n"


def client_thread(conn, ser):
    with conn:
        data = conn.recv(4096)
        if not data:
            return
        # Support newline-delimited JSON
        for line in data.splitlines():
            try:
                obj = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            msg = to_arduino_line(obj)
            ser.write(msg.encode("utf-8"))
            ser.flush()
            # Small delay to avoid flooding
            time.sleep(0.05)


def main():
    args = parse_args()
    print(f"[bridge] Opening serial {args.serial_port} @ {args.baud}")
    with serial.Serial(args.serial_port, args.baud, timeout=1) as ser:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind((args.host, args.port))
        srv.listen(5)
        print(f"[bridge] Listening on {args.host}:{args.port}")
        try:
            while True:
                conn, addr = srv.accept()
                print(f"[bridge] Client from {addr}")
                threading.Thread(target=client_thread, args=(conn, ser), daemon=True).start()
        except KeyboardInterrupt:
            print("\n[bridge] Exiting.")
        finally:
            srv.close()


if __name__ == "__main__":
    main()
