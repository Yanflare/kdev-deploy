---
title: USB Drive Corruption Diagnosis and Recovery
tags: usb, firmware, recovery, diskpart, powershell
complexity: complex
summary: Diagnose and recover corrupted USB drives using PowerShell to distinguish filesystem vs. controller-level brick states.
---

## When to use
- USB drive shows 0 bytes, "No Media," or `VID=FFFF` after a failed flash/imaging operation
- Drive enumerates but all I/O returns NOT_READY or similar errors
- User reports repeated corruption after BIOS flash tool (Q-Flash, Rufus, dd) wrote raw data to a USB device

## Approach
The core task is **triage before action**: determine whether the failure is filesystem-level (recoverable via format/diskpart) or controller-level (requires vendor flash tool or physical recovery). These require completely different remediation paths.

Escalating evidence levels:
1. Filesystem corrupt → diskpart can see size, sectors are readable
2. Partition table destroyed → diskpart sees size, sector 0 readable, clean+format works
3. Controller brick → `VID=FFFF`, 0 bytes, sector 0 returns NOT_READY; no software format is possible

Do not attempt formatting or writing until you've confirmed the controller is presenting valid LBA media.

## Tool strategy
All via `powershell` in sequence:

1. **Enumerate device** — `Get-PnpDevice`, `Get-Disk`, WMI `Win32_DiskDrive` to get VID/PID, reported size, device name
2. **Check media state** — `diskpart` (`list disk`, `select disk N`, `detail disk`) to confirm Online vs. No Media
3. **Probe sector 0** — raw read of LBA 0 using `[System.IO.File]::OpenRead("\\\\.\\PhysicalDriveN")` to confirm I/O is accepted
4. **Attempt recovery** — only if steps 1–3 show healthy controller: `diskpart clean`, `create partition primary`, `format fs=fat32 quick`
5. **Report state** — present a comparison table of current vs. last-known-good state; identify VID/PID anomalies explicitly

## Pitfalls
- `VID=FFFF` is a definitive controller brick signal — do not attempt diskpart operations, they will silently fail or mislead
- Drive name changing (e.g., Philips → "NAND USB2DISK") indicates the controller has switched to a recovery/failsafe firmware persona — treat as a different device
- Disk number can shift between USB plug cycles; always re-enumerate before operating
- Do not confuse "disk visible in Device Manager" with "disk ready for I/O" — enumeration and media readiness are independent states