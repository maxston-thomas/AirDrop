"""
AirLink - Network Discovery and QR Code Generation
Handles local IPv4 detection, network interface listing, and QR code generation for pairing.
Works entirely offline without any external servers or internet connection.
"""

import io
import re
import socket
import subprocess
from typing import List, Dict, Optional
import qrcode
from qrcode.image.svg import SvgPathImage
import base64


def is_private_ipv4(ip: str) -> bool:
    """Check if an IPv4 address belongs to standard private/LAN subnets."""
    if not ip or ip.startswith("127.") or ip.startswith("169.254."):
        return False
    parts = ip.split(".")
    if len(parts) != 4:
        return False
    try:
        first = int(parts[0])
        second = int(parts[1])
        # 10.0.0.0 - 10.255.255.255
        if first == 10:
            return True
        # 172.16.0.0 - 172.31.255.255
        if first == 172 and 16 <= second <= 31:
            return True
        # 192.168.0.0 - 192.168.255.255 (Standard Wi-Fi / Hotspot)
        if first == 192 and second == 168:
            return True
    except ValueError:
        return False
    return False


def get_all_network_interfaces() -> List[Dict[str, str]]:
    """
    Discover all active IPv4 network interfaces on the host.
    Parses Windows ipconfig or socket address info without requiring external packages.
    """
    interfaces: List[Dict[str, str]] = []
    seen_ips = set()

    # Method 1: On Windows, parse 'ipconfig' to get adapter names and corresponding IPv4 addresses
    try:
        proc = subprocess.run(
            ["ipconfig"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False
        )
        if proc.returncode == 0:
            current_adapter = "Local Network"
            for line in proc.stdout.splitlines():
                line = line.strip()
                if "adapter" in line.lower() and line.endswith(":"):
                    current_adapter = line[:-1]
                elif "ipv4 address" in line.lower() or "ip address" in line.lower():
                    # Format: IPv4 Address. . . . . . . . . . . : 192.168.1.50
                    match = re.search(r":\s*([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})", line)
                    if match:
                        ip = match.group(1)
                        if ip not in seen_ips and not ip.startswith("127."):
                            seen_ips.add(ip)
                            interfaces.append({
                                "name": current_adapter,
                                "ip": ip,
                                "is_private": is_private_ipv4(ip)
                            })
    except Exception:
        pass

    # Method 2: Standard socket address info lookup
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, family=socket.AF_INET):
            ip = info[4][0]
            if ip not in seen_ips and not ip.startswith("127."):
                seen_ips.add(ip)
                interfaces.append({
                    "name": f"Interface ({hostname})",
                    "ip": ip,
                    "is_private": is_private_ipv4(ip)
                })
    except Exception:
        pass

    # Method 3: Socket probe fallback
    if not interfaces:
        fallback_ip = get_local_ip()
        if fallback_ip not in seen_ips:
            interfaces.append({
                "name": "Default Interface",
                "ip": fallback_ip,
                "is_private": is_private_ipv4(fallback_ip)
            })

    return interfaces


def get_local_ip() -> str:
    """
    Determines the best local IPv4 address for hosting the offline server.
    Ensures zero internet dependency and handles isolated Wi-Fi or Hotspots.
    """
    # 1. Try socket connection to dummy address in private range (no packet sent)
    for probe_ip in ["192.168.1.254", "10.255.255.254", "172.16.255.254", "8.8.8.8"]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.2)
            s.connect((probe_ip, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("127."):
                return ip
        except Exception:
            continue

    # 2. Try gethostbyname
    try:
        hostname = socket.gethostname()
        ip = socket.gethostbyname(hostname)
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass

    # 3. Fallback to loopback
    return "127.0.0.1"


def get_access_url(port: int = 8000, ip: Optional[str] = None) -> str:
    """Constructs the HTTP access URL for the mobile device."""
    target_ip = ip or get_local_ip()
    return f"http://{target_ip}:{port}"


def generate_qr_code_svg(content: str) -> str:
    """
    Generates a clean vector SVG string of the QR code.
    Ideal for sharp, scalable rendering on modern displays.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
        image_factory=SvgPathImage
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(attrib={"class": "airlink-qr-code", "role": "img", "aria-label": "Pairing QR Code"})
    stream = io.BytesIO()
    img.save(stream)
    raw = stream.getvalue().decode("utf-8")
    if raw.startswith("<?xml"):
        raw = raw.split("?>", 1)[-1].strip()
    return raw


def generate_qr_code_base64_png(content: str) -> str:
    """
    Generates a base64 encoded PNG data URI for maximum compatibility with all image elements.
    """
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"
