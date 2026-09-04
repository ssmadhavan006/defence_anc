"""
demo/webdash/generate_qr.py — Generate a QR code encoding the webdash LAN URL.

Usage:
    python demo/webdash/generate_qr.py --ip 192.168.1.42 --port 8080
    python demo/webdash/generate_qr.py --ip 192.168.1.42   # defaults to port 8080

Requires: pip install "qrcode[pil]"
Output: qr_dashboard.png in the repo root (or --out path).
"""

import argparse
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def generate(ip: str, port: int = 8080, out_path: str | None = None) -> str:
    try:
        import qrcode
    except ImportError:
        raise ImportError("qrcode not installed. Run: pip install 'qrcode[pil]'")

    url = f"http://{ip}:{port}"
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    if out_path is None:
        out_path = os.path.join(_REPO_ROOT, "qr_dashboard.png")
    img.save(out_path)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="Generate dashboard QR code")
    parser.add_argument("--ip", required=True, help="Pi LAN IP address")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--out", default=None, help="Output PNG path")
    args = parser.parse_args()

    try:
        path = generate(args.ip, args.port, args.out)
        print(f"QR code written to: {path}")
        print(f"URL encoded: http://{args.ip}:{args.port}")
    except ImportError as e:
        print(f"ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
