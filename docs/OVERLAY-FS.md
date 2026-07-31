# Read-Only OverlayFS Protection & Read-Write Storage Guide for ASUS Tinker Board (TinkerOS / Debian Buster)

## Overview

This document provides a comprehensive summary of the architecture, implementation steps, and management scripts for configuring an **OverlayFS-based Read-Only Root Filesystem** on an ASUS Tinker Board running TinkerOS (Debian Buster / Linaro-ALIP desktop).

This setup makes the system resilient against power cuts and corruption of the MicroSD/eMMC card, while supporting a dedicated read-write data partition for persistent storage (e.g., SQLite databases, log files, telemetry) and providing clickable desktop scripts to toggle read-only mode on and off.

---

## Technical Context & Architectural Decisions

### 1. Why Standard Read-Only Mounts Fail on GUI Systems
Simply mounting the root filesystem `/` as read-only (`ro`) in `/etc/fstab` causes desktop managers (LightDM, X11, LXDE) to enter a continuous boot crash loop. Desktop applications rely heavily on writing runtime sockets, session states, and lock files to `/tmp`, `/var/run`, `/var/lib/lightdm`, and home directories.

### 2. Why Canonical `overlayroot` / Initramfs Was Bypassed
Stock TinkerOS U-Boot reads the kernel (`zImage`) directly from raw sectors on Partition 6 (`/dev/mmcblk0p6`) and does not pass control through a standard Debian initramfs (`uInitrd`). As a result, software like `overlayroot` that hooks into the initramfs phase is completely skipped during boot.

### 3. The `switch_root` Init Wrapper Solution
To bypass U-Boot limitations without flashing custom bootloaders, we replace the kernel's default `/sbin/init` call in `/boot/cmdline.txt` with a custom script: `/sbin/init_overlay.sh`.

During boot:
1. The kernel launches `/sbin/init_overlay.sh` as PID 1.
2. The script mounts a `tmpfs` (RAM disk) at `/mnt`.
3. It creates an `overlay` filesystem combining the physical read-only root card (lower) and the volatile RAM layer (upper).
4. Virtual filesystems (`/proc`, `/sys`, `/dev`) are moved to the overlay root.
5. Control is transferred to `systemd` (`switch_root /mnt/newroot /lib/systemd/systemd`).

All system writes occur entirely in RAM and vanish on reboot, preserving the physical flash memory.

---

## Storage & Partition Architecture

```text
/dev/mmcblk0 (MicroSD / eMMC 32 GB GPT)
├── p1 - p6 : Rockchip boot infrastructure (ARM Trusted Firmware, SPL, U-Boot, Device Tree) [DO NOT REMOVE]
├── p7      : /boot partition (Kernel, DTB, cmdline.txt)
├── p8      : / (Root Filesystem - Mounted READ-ONLY via OverlayFS)
└── p9      : /data (Data Partition - Mounted READ-WRITE, Ext4, Label: data)
```

### Mount Configuration (`/etc/fstab`)
```text
# Root filesystem entry
/dev/mmcblk0p8    /          ext4    defaults,noatime    0    1

# Persistent RW Data Partition
LABEL=data        /data      ext4    defaults,noatime    0    2
```

Persistent files (such as SQLite databases at `/data/yamaha-data-logger/db`) must be written directly under `/data`.

---

## Core System Configuration

### 1. Custom Init Overlay Script (`/sbin/init_overlay.sh`)

Create `/sbin/init_overlay.sh`:

```bash
#!/bin/sh
# Mount essential virtual filesystems
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs dev /dev

# Mount RAM disk for the writable layer
mount -t tmpfs -o mode=0755 tmpfs /mnt
mkdir -p /mnt/upper /mnt/work /mnt/newroot

# Mount OverlayFS combining read-only flash (lower) and RAM (upper)
mount -t overlay overlay -o lowerdir=/,upperdir=/mnt/upper,workdir=/mnt/work /mnt/newroot

# Move virtual filesystems into the new overlay root
mount --move /proc /mnt/newroot/proc
mount --move /sys /mnt/newroot/sys
mount --move /dev /mnt/newroot/dev
mount --move /mnt /mnt/newroot/mnt

# Pass PID 1 control directly to systemd inside the overlay
exec switch_root /mnt/newroot /lib/systemd/systemd
```

Set execution permissions:
```bash
sudo chmod +x /sbin/init_overlay.sh
```

---

## Management Scripts & Desktop Launchers

Two bash scripts allow switching between Read-Only mode (Overlay active) and Read-Write mode (Overlay disabled for updates/maintenance).

### 1. Enable Overlay Script (`/usr/local/bin/enable_overlay.sh`)

```bash
#!/bin/bash
if [ "$EUID" -ne 0 ]; then
  echo "Error: This script must be run as root."
  exit 1
fi

CMDLINE="/boot/cmdline.txt"

# Strip existing init parameter to prevent duplicate entries
sed -i 's| init=/sbin/init_overlay.sh||g' "$CMDLINE"
sed -i 's|init=/sbin/init_overlay.sh||g' "$CMDLINE"

# Append init parameter to the end of the line
sed -i 's|[[:space:]]*$| init=/sbin/init_overlay.sh|' "$CMDLINE"

echo "=========================================="
echo " Overlay ENABLED (Read-Only Mode) "
echo " Rebooting system in 3 seconds..."
echo "=========================================="
sleep 3
reboot
```

### 2. Disable Overlay Script (`/usr/local/bin/disable_overlay.sh`)

```bash
#!/bin/bash
if [ "$EUID" -ne 0 ]; then
  echo "Error: This script must be run as root."
  exit 1
fi
BOOT_MOUNT=$(findmnt --noheadings -o TARGET /dev/mmcblk0p7)
CMDLINE=$BOOT_MOUNT"/cmdline.txt"

# Remove the init parameter
sed -i 's| init=/sbin/init_overlay.sh||g' "$CMDLINE"
sed -i 's|init=/sbin/init_overlay.sh||g' "$CMDLINE"
sed -i 's/[[:space:]]*$//' "$CMDLINE"

echo "=========================================="
echo " Overlay DISABLED (Read-Write Mode) "
echo " Rebooting system in 3 seconds..."
echo "=========================================="
sleep 3
reboot
```

Set permissions:
```bash
sudo chmod +x /usr/local/bin/enable_overlay.sh /usr/local/bin/disable_overlay.sh
```

---

### 3. LXDE Desktop Launchers (`~/Desktop`)

#### Enable Overlay Shortcut (`~/Desktop/Enable Overlay.desktop`)
```ini
[Desktop Entry]
Type=Application
Name=Enable Overlay (Read-Only)
Comment=Enable RAM overlay and reboot
Exec=lxterminal -e "sudo /usr/local/bin/enable_overlay.sh"
Icon=system-lock-screen
Terminal=false
Categories=System;
```

#### Disable Overlay Shortcut (`~/Desktop/Disable Overlay.desktop`)
```ini
[Desktop Entry]
Type=Application
Name=Disable Overlay (Read-Write)
Comment=Disable RAM overlay for updates and reboot
Exec=lxterminal -e "sudo /usr/local/bin/disable_overlay.sh"
Icon=system-run
Terminal=false
Categories=System;
```

Set launcher permissions:
```bash
chmod +x ~/Desktop/"Enable Overlay.desktop" ~/Desktop/"Disable Overlay.desktop"
```

---

## Operating Procedures & Verification

### How to Verify Active Overlay
Run:
```bash
mount | grep "on / "
```
**Active Overlay Output:**
`overlay on / type overlay (rw,relatime,lowerdir=/,upperdir=/mnt/upper,workdir=/mnt/work)`

### Maintenance / Package Installation Workflow
To install packages (e.g., `sqlite3`), update system tools, or edit system configurations permanently:

1. Double-click **Disable Overlay (Read-Write)** on the desktop (or run `sudo /usr/local/bin/disable_overlay.sh`).
2. The board will reboot into normal Read-Write mode.
3. Perform system maintenance:
   ```bash
   sudo timedatectl set-timezone Europe/Stockholm
   sudo apt update --allow-releaseinfo-change
   sudo apt install sqlite3
   ```
4. Double-click **Enable Overlay (Read-Only)** on the desktop (or run `sudo /usr/local/bin/enable_overlay.sh`).
5. The system reboots back into powercut-protected Read-Only mode.

---

## Key Maintenance Commands Summary

| Task | Command |
|---|---|
| Check Overlay Mount Status | `mount \| grep "on / "` |
| Check Timezone | `timedatectl` |
| Set Timezone | `sudo timedatectl set-timezone Europe/Stockholm` |
| Install SQLite3 (Debian Archive) | `wget [http://archive.debian.org/debian/pool/main/s/sqlite3/sqlite3_3.27.2-3+deb10u2_armhf.deb](http://archive.debian.org/debian/pool/main/s/sqlite3/sqlite3_3.27.2-3+deb10u2_armhf.deb) && sudo dpkg -i sqlite3_3.27.2-3+deb10u2_armhf.deb` |
| Enable Protection & Reboot | `sudo /usr/local/bin/enable_overlay.sh` |
| Disable Protection & Reboot | `sudo /usr/local/bin/disable_overlay.sh` |
