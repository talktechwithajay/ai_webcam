# 01 – Windows setup (Milestone 1)

All commands are PowerShell. Run from the repo root unless stated.

## 0. Inspect the host
```powershell
powershell -ExecutionPolicy Bypass -File scripts\check-environment.ps1
```

## 1. Python 3.12, Git, Node, VS Code, VirtualBox
Python 3.13 is installed on this laptop, but 3.12 is the project target (wider CV wheel support). Both can coexist via the `py` launcher.
```powershell
# Python 3.12 (+ Git/Node if missing). Add -IncludeVSCode if you want VS Code.
powershell -ExecutionPolicy Bypass -File scripts\install-prerequisites.ps1
# VirtualBox needs an elevated (Run as administrator) PowerShell:
powershell -ExecutionPolicy Bypass -File scripts\install-prerequisites.ps1 -IncludeVirtualBox
```
Open a **new** terminal afterwards, then:
```powershell
py -3.12 --version
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-tools.txt
```

## 2. Hyper-V / virtualization caveat (this laptop)
This laptop reports `HypervisorPresent = True` and *Virtualization-based security: Running*, so Windows' hypervisor is active. VirtualBox 7 can still run VMs on top of it (via the Windows Hypervisor Platform), but **Home Assistant OS may be noticeably slower or unstable**. Also confirm virtualization is enabled in BIOS/UEFI (the firmware flag reads `False` while the hypervisor is active, which is normal under Hyper-V, so it is not conclusive).

Decision for you after VirtualBox is installed: if HAOS boots and is responsive, continue. If not, the fallback is Hyper-V Manager with the HAOS `.vhdx` image (the official HA docs also provide a Hyper-V path). Do not disable VBS unless you accept the security trade-off.

## 3. Home Assistant OS in VirtualBox (official procedure)
Source: <https://www.home-assistant.io/installation/windows> (checked 2026-10-11).

1. Download the **VirtualBox (Intel chip)** `.vdi.zip` image (listed as `haos_ova-<version>.vdi.zip`) from the link on that page (Home Assistant OS GitHub releases). Extract it to a folder **outside** the repo.
2. VirtualBox → **New**: Name `Home Assistant`, ISO Image blank, OS **Linux**, distribution **Oracle Linux (64-bit)**.
3. Hardware: memory **≥ 2048 MB** (use 4096 MB; this laptop has 31 GB), CPUs **≥ 2** (use 2–4), tick **Use EFI** (required).
4. Settings → Storage: remove the empty disk under *Controller: SATA*, add a hard disk, pick the extracted `.vdi`.
5. Settings → Network: Attached to **Bridged Adapter**, Name = the adapter you use for internet (Wi‑Fi or Ethernet).
6. Start the VM; wait for boot, then browse to `http://homeassistant.local:8123` (try the VM's IP if mDNS fails).
7. Create the owner account in the onboarding wizard. Use a strong unique password; it is **never** used by this application.

Cameras stay on Windows; the VM does not need USB passthrough.

## 4. Keep Windows awake
```powershell
powershell -ExecutionPolicy Bypass -File scripts\prevent-sleep.ps1          # AC: never sleep, lid-close does nothing
powershell -ExecutionPolicy Bypass -File scripts\prevent-sleep.ps1 -Restore 30   # undo (30 min)
```
Keep the laptop plugged in. DC (battery) sleep is left unchanged on purpose.
Also auto-start the VM at login (Milestone 7 will add a scheduled task using `VBoxManage startvm "Home Assistant" --type headless`).

## 5. Cameras
```powershell
python tools\list_cameras.py --snapshots        # probe indices, save one JPEG each to data\camera_probe\ (git-ignored)
python tools\list_cameras.py --preview 1        # live window for index 1; press q to close
```
Unplug/replug one webcam and re-run to see which index changes: that is how you tell front-door from indoor. Indices are not stable across reboots or ports, so the app stores them in config and the diagnostic is re-runnable. Snapshots are personal data: delete `data\camera_probe\` when done.
