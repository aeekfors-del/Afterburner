#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script — prints LibreHardwareMonitor sensor data to console.

Requirements:
  - LibreHardwareMonitor running with HTTP Server enabled
  - Default: http://localhost:8085
  - Enable in LHM: Settings → HTTP Server → Enable HTTP server

Run: python test_lh.py
Press Ctrl+C to stop.
"""

import logging
import signal
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("Afterburner.test")


def print_separator(char="=", length=80):
    print(char * length)


def print_section(title: str):
    print()
    print_separator("-")
    print(f"  {title}")
    print_separator("-")


def main():
    from lh_monitor import LibreHardwareMonitor

    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))

    print_separator()
    print("  LibreHardwareMonitor Sensor Test")
    print_separator()

    # Try default URL
    print("\n[1/2] Connecting to LibreHardwareMonitor...")
    lh = LibreHardwareMonitor()

    if not lh.available:
        print("\n  ERROR: LibreHardwareMonitor failed to initialize!")
        print("  Make sure LHM is installed in ./LHM/")
        print("  And LibreHardwareMonitorLib.dll is present.")
        return

    print(f"\n  [OK] LibreHardwareMonitor initialized successfully")

    # Raw sensor list
    print_section("ALL SENSORS")
    raw_list = lh.get_raw_list()
    if raw_list:
        print(f"  {'Name':<30} | {'Value':>8} | {'Unit':<10} | {'Type':<12}")
        print(f"  {'-'*30} | {'-'*8} | {'-'*10} | {'-'*12}")
        for s in raw_list:
            print(f"  {s['name']:<30} | {s['value']:>8.2f} | {s['unit']:<10} | {s['type']:<12}")
        print(f"\n  Total: {len(raw_list)} sensors")
    else:
        print("  No sensors found")

    # Category listing
    print_section("FANS (RPM)")
    fans = lh.get_fan_speeds()
    if fans:
        for name, rpm in fans:
            print(f"  {name}: {rpm} RPM")
    else:
        print("  No fan sensors detected")

    print_section("VOLTAGES (V)")
    voltages = lh.get_voltages()
    if voltages:
        for name, v in voltages:
            print(f"  {name}: {v:.3f} V")
    else:
        print("  No voltage sensors detected")

    print_section("TEMPERATURES (°C)")
    temps = lh.get_temperatures()
    if temps:
        for name, t in temps:
            print(f"  {name}: {t:.1f} °C")
    else:
        print("  No temperature sensors detected")

    # Live monitoring
    print()
    print_separator()
    print("  LIVE MONITORING (Ctrl+C to stop)")
    print_separator()

    try:
        prev_fans = prev_voltages = prev_temps = None
        frame = 0
        while True:
            frame += 1
            fans = lh.get_fan_speeds()
            voltages = lh.get_voltages()
            temps = lh.get_temperatures()

            changed = (fans != prev_fans or voltages != prev_voltages or temps != prev_temps or frame % 50 == 0)
            prev_fans = fans
            prev_voltages = voltages
            prev_temps = temps

            if changed:
                print(f"\n  [{time.strftime('%H:%M:%S')}] Frame #{frame}")
                if fans:
                    print(f"  Fans:   {', '.join(f'{n}: {r} RPM' for n, r in fans)}")
                if voltages:
                    print(f"  Volt:   {', '.join(f'{n}: {v:.3f}V' for n, v in voltages)}")
                if temps:
                    print(f"  Temp:   {', '.join(f'{n}: {t:.1f}°C' for n, t in temps)}")

            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\n  Stopped")

    lh.close()
    print()
    print_separator()
    print("  Test complete")
    print_separator()


if __name__ == "__main__":
    main()
