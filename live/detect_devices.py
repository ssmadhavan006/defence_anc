"""
live/detect_devices.py — Detects audio hardware and suggests config overrides.

Usage:
    python live/detect_devices.py
"""

import os
import sys

# Ensure repo root is on sys.path
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

try:
    import sounddevice as sd
except ImportError:
    print("[detect_devices] sounddevice is not installed. Run: pip install sounddevice", file=sys.stderr)
    sys.exit(1)


def detect_and_suggest():
    print("=== Audio Device Detection ===")
    devices = sd.query_devices()
    print(f"Total devices found: {len(devices)}")
    print("-" * 60)
    
    suggested_in = None
    suggested_out = None
    
    # Loopback or USB targets
    usb_keywords = ["usb", "loopback", "aloop", "audio adapter", "focusrite", "behringer"]
    
    for idx, dev in enumerate(devices):
        name = dev["name"].lower()
        max_in = dev["max_input_channels"]
        max_out = dev["max_output_channels"]
        
        is_usb_or_loopback = any(kw in name for kw in usb_keywords)
        
        marker = " [USB/Loopback Target]" if is_usb_or_loopback else ""
        print(f"Index {idx}: {dev['name']}")
        print(f"  Max Inputs: {max_in}, Max Outputs: {max_out}, SR: {dev['default_samplerate']} Hz{marker}")
        
        # Auto-suggestion logic
        if is_usb_or_loopback:
            if max_in > 0 and suggested_in is None:
                suggested_in = idx
            if max_out > 0 and suggested_out is None:
                suggested_out = idx
                
    # Fallback to defaults if no USB/Loopback
    if suggested_in is None:
        try:
            suggested_in = sd.default.device[0]
        except Exception:
            pass
    if suggested_out is None:
        try:
            suggested_out = sd.default.device[1]
        except Exception:
            pass
            
    print("-" * 60)
    print("=== Suggested YAML Config Settings ===")
    print("Update config/audio_config.yaml with these values:")
    print()
    print("audio:")
    if suggested_in is not None:
        print(f"  input_device: {suggested_in}  # {devices[suggested_in]['name']}")
    else:
        print("  input_device: null")
        
    if suggested_out is not None:
        print(f"  output_device: {suggested_out}  # {devices[suggested_out]['name']}")
    else:
        print("  output_device: null")
        
    print()


if __name__ == "__main__":
    detect_and_suggest()
