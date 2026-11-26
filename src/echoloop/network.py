"""Phone access over the local network (LAN mode).

Off by default: the server then listens on 127.0.0.1 only. Turned on in Settings, it listens on every network
interface so a phone on the same Wi-Fi can open the pages, but only with the access key: the phone opens the
link (or scans the QR code) once, the key is stored in a cookie, and every request without it is refused.
API keys, backups, the speech settings and stopping the server stay available on this computer only.

Plain HTTP on the LAN means browsers don't allow the microphone there, so speaking practice stays on the computer.
"""
from __future__ import annotations

import hmac
import ipaddress
import json
import os
import secrets
import socket
import tempfile
from http.cookies import SimpleCookie

from .config import DATA_DIR, HOST

NETWORK_PATH = DATA_DIR / "network.json"
COOKIE = "echoloop_key"
LEGACY_COOKIE = "ielts_key"


def load() -> dict:
    try:
        data = json.loads(NETWORK_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"lan": bool(data.get("lan")), "token": str(data.get("token") or "")}


def _write(data: dict) -> None:
    NETWORK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".network-", dir=NETWORK_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(name, NETWORK_PATH)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def save(lan: bool, new_key: bool = False) -> dict:
    data = load()
    data["lan"] = bool(lan)
    if new_key or not data["token"]:
        data["token"] = secrets.token_urlsafe(18)
    _write(data)
    return data


# the setting as the server started with it: switching LAN mode needs a restart
STARTED = load()


def bind_host() -> str:
    return "0.0.0.0" if STARTED["lan"] else HOST


# Not a home / office network: VPN and proxy tunnels (Clash, Surge "fake IP" 198.18/15), carrier-grade NAT and
# overlay networks (100.64/10, e.g. Tailscale), link-local addresses.
NOT_LAN = [ipaddress.ip_network(n) for n in ("198.18.0.0/15", "100.64.0.0/10", "169.254.0.0/16", "127.0.0.0/8")]


def _usable(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return addr.version == 4 and addr.is_private and not any(addr in n for n in NOT_LAN)


def _interface_addresses() -> list[str]:
    import re
    import subprocess
    import sys

    found = []
    try:
        found += [info[4][0] for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)]
    except OSError:
        pass
    commands = [["ipconfig"]] if sys.platform == "win32" else [["ifconfig"], ["ip", "-4", "-o", "addr"]]
    for command in commands:
        try:
            out = subprocess.run(command, capture_output=True, text=True, timeout=3, errors="replace").stdout
        except (OSError, subprocess.SubprocessError):
            continue
        found += re.findall(r"(?:inet |IPv4[^:]*:\s*)(\d+\.\d+\.\d+\.\d+)", out)
    return found


def lan_ips() -> list[str]:
    """This computer's addresses on the local network, the likeliest first (Wi-Fi / Ethernet, not a VPN)."""
    candidates = []
    try:  # the address of the default route: right unless a VPN or proxy tunnel took it
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            candidates.append(s.getsockname()[0])
    except OSError:
        pass
    candidates += _interface_addresses()
    seen, out = set(), []
    for ip in candidates:
        if ip not in seen and _usable(ip):
            seen.add(ip)
            out.append(ip)
    rank = lambda ip: (0 if ip.startswith("192.168.") else 1 if ip.startswith("10.") else 2)  # noqa: E731
    return sorted(out, key=rank)


def lan_ip() -> str | None:
    ips = lan_ips()
    return ips[0] if ips else None


def phone_url(port: int) -> str | None:
    ip, token = lan_ip(), load()["token"]
    return f"http://{ip}:{port}/?key={token}" if ip and token else None


def qr_svg(text: str) -> bytes:
    import io

    import segno

    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="svg", scale=5, border=2, dark="#111", light="#fff")
    return buf.getvalue()


def private_host(host_header: str) -> bool:
    """A LAN request names the computer by its private IP address (never a domain: no DNS rebinding)."""
    host = host_header.rsplit(":", 1)[0].strip("[]")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private and not ip.is_loopback


def key_ok(value: str | None) -> bool:
    token = load()["token"]  # a new key takes effect at once
    return bool(value and token) and hmac.compare_digest(value, token)


def cookie_key(cookie_header: str | None) -> str | None:
    if not cookie_header:
        return None
    try:
        jar = SimpleCookie(cookie_header)
    except Exception:  # noqa: BLE001 - a malformed cookie header
        return None
    if COOKIE in jar:
        return jar[COOKIE].value
    return jar[LEGACY_COOKIE].value if LEGACY_COOKIE in jar else None


def set_cookie(token: str) -> str:
    return f"{COOKIE}={token}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict"


def status(port: int) -> dict:
    data = load()
    ips = lan_ips()
    return {"lan": data["lan"], "running": STARTED["lan"], "needsRestart": data["lan"] != STARTED["lan"],
            "ip": ips[0] if ips else None, "others": [f"http://{ip}:{port}/" for ip in ips[1:]],
            "url": phone_url(port) if data["lan"] else None}
