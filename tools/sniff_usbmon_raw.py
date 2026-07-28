#!/usr/bin/env python3
"""
Yamaha YDS Real-Time USB Raw Packet Sniffer for Linux (usbmon).
Captures raw USB URB transfer packets with exact 48-byte Linux kernel usbmon alignment.
Handles VirtualBox USB passthrough re-enumeration seamlessly.

Requires 'usbmon' kernel module:
  sudo modprobe usbmon
  sudo chmod 666 /dev/usbmon*
"""

import sys
import os
import time
import struct
import select
import argparse

def sniff_usbmon(target_bus: int = 0, target_dev: int = 0):
    dev_path = f"/dev/usbmon{target_bus}"
    if not os.path.exists(dev_path):
        os.system("sudo modprobe usbmon 2>/dev/null")
        os.system("sudo chmod 666 /dev/usbmon* 2>/dev/null")

    if not os.path.exists(dev_path):
        print(f"[-] Error: {dev_path} not found. Please run:")
        print("    sudo modprobe usbmon && sudo chmod 666 /dev/usbmon*")
        sys.exit(1)

    bus_label = f"Bus {target_bus}" if target_bus > 0 else "ALL BUSES"
    dev_label = f"Device {target_dev}" if target_dev > 0 else "ALL DEVICES (VirtualBox Passthrough)"

    print("=" * 70)
    print(f" YAMAHA YDS REAL-TIME USB RAW SNIFFER ({bus_label}, {dev_label})")
    print("=" * 70)
    print(f"[+] Reading non-blocking raw USB URB stream from: {dev_path}")
    print("=" * 70 + "\n")

    log_file = "yds_usb_raw_sniff.log"
    fd = os.open(dev_path, os.O_RDONLY | os.O_NONBLOCK)

    with open(log_file, "a") as f_log:
        header = f"\n=== RAW USB SNIFF SESSION STARTED AT {time.strftime('%Y-%m-%d %H:%M:%S')} ({bus_label}, {dev_label}) ===\n"
        print(header, end="", flush=True)
        f_log.write(header)
        f_log.flush()

        buf = bytearray()
        try:
            while True:
                r, _, _ = select.select([fd], [], [], 0.1)
                if fd in r:
                    try:
                        chunk = os.read(fd, 4096)
                        if chunk:
                            buf.extend(chunk)
                    except Exception:
                        pass

                while len(buf) >= 48:
                    # Unpack 48-byte Linux kernel usbmon_packet header
                    urb_id, urb_type, xfer_type, epnum, devnum, busnum, flag_setup, flag_data, ts_sec, ts_usec, status, length, len_cap, setup = struct.unpack('=QBBBBHBBqiiII8s', buf[:48])

                    # Validate header integrity (alignment check)
                    if len_cap < 0 or len_cap > 4096 or devnum > 127:
                        buf.pop(0)
                        continue

                    total_len = 48 + len_cap
                    if len(buf) < total_len:
                        break

                    payload = bytes(buf[48:total_len])
                    buf = buf[:0] if len(buf) == total_len else buf[total_len:]

                    # Optional filters
                    if target_bus > 0 and busnum != target_bus:
                        continue
                    if target_dev > 0 and devnum != target_dev:
                        continue

                    ts = time.strftime('%H:%M:%S.%3f')[:-3]
                    direction = "VM/Host -> USB Cable" if (epnum & 0x80 == 0) else "ECU/Cable -> VM/Host"
                    type_str = chr(urb_type) # 'S'=Submit, 'C'=Callback, 'E'=Error

                    # Format line with setup header for EP 0x00 control transfers
                    if epnum == 0x00 and chr(urb_type) == 'S':
                        req_type, req, val, idx, req_len = struct.unpack('<BBHHH', setup)
                        line = f"[{ts}] [{direction}] Bus {busnum:2d} Dev {devnum:2d} EP 0x00 (S) SETUP [ReqType:0x{req_type:02X} Req:0x{req:02X} Val:0x{val:04X} Idx:0x{idx:04X} Len:{req_len}] Data ({len(payload)}b): {payload.hex().upper()}\n"
                    else:
                        line = f"[{ts}] [{direction}] Bus {busnum:2d} Dev {devnum:2d} EP 0x{epnum:02X} ({type_str}) ({len(payload):2d}b): {payload.hex().upper()}\n"

                    print(line, end="", flush=True)
                    f_log.write(line)
                    f_log.flush()

        except KeyboardInterrupt:
            print("\n[+] Raw USB Sniffer stopped by user.")
        except Exception as e:
            print(f"\n[-] Error reading raw USB stream: {e}")
        finally:
            os.close(fd)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Linux Real-Time Raw USB Sniffer")
    parser.add_argument("--bus", type=int, default=0, help="USB Bus number (0 for all buses)")
    parser.add_argument("--dev", type=int, default=0, help="USB Device address (0 for all devices)")
    args = parser.parse_args()

    sniff_usbmon(args.bus, args.dev)
