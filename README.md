# Conspit on Linux — Ares Platinum 20Nm base, CPP.LITE pedals, H.AO wheel

[🇧🇷 Português](README.pt-BR.md) · **🇬🇧 English**

Tools and a step-by-step guide for using **Conspit** sim-racing gear on Linux, including
**ConspitLink 2.0 running under Wine** with real-time configuration and telemetry for every
device.

### What this project is — and what it is not

This is **the solution I used** to get my Conspit devices working on Linux, organized so
that someone else can reproduce it.

**Nothing was ported.** There is no rewritten driver, no reimplemented software, no Linux
build of ConspitLink. The app is the **official, unmodified Conspit binary** running under
Wine. What this repository contains is the result of **analysis, configuration and
tuning**:

- finding out how each device presents itself to the kernel, and what Linux gets wrong by
  default;
- a `udev` rule that fixes that;
- the registry tweaks that make Wine hand the hardware to the app the way it expects;
- diagnostic tools (almost all read-only) so you can verify every stage;
- documentation of what was measured — **including the wrong turns**.

Nothing here redistributes third-party software. ConspitLink belongs to **Conspit** and you
download it from their official site; the base firmware is
**[OpenFFBoard](https://github.com/Ultrawipf/OpenFFBoard)** (Ultrawipf); the telemetry
bridge is **[Winecarte](https://github.com/srounce/winecarte)** (srounce). Much of the
credit for what works belongs to those projects — this repo just puts the pieces together.

Personal project, no warranty, no support.

Validated with the hardware connected on **Fedora 44** (2026-08-12, Wine 11.14) and
**CachyOS** (2026-08-14 and 2026-08-15, kernel 7.1, Wine 11.15). Distro-specific commands
are marked where they differ. If something diverges on yours, `tools/check-setup.sh` will
point at what.

Licensed under **[GPL-3.0](LICENSE)**: use it, study it, modify it, fork it. Whoever
distributes a modified version must keep the source open under the same license — nobody
closes this into a proprietary product.

## What works

| | status |
|---|---|
| Native FFB in games (via `hid-generic` + `hid-pidff`) | ✅ 40 effect slots, all conditional effects |
| Axis deadzone / jitter (base, pedals, wheel) | ✅ fixed by udev rule |
| CPP.LITE pedals natively, no Wine (read, monitor, calibrate) | ✅ `tools/cpp_pedal.py` |
| Command protocol straight over serial | ✅ documented and tested |
| **ConspitLink 2.0 under Wine** | ✅ config and telemetry in real time |
| ↳ Ares base: torque, range, filters, presets, live angle | ✅ |
| ↳ CPP.LITE pedals: curves, calibration, haptics (`Customize`) | ✅ |
| ↳ H.AO wheel: buttons, brightness, dashboard, paddles, Launch Control | ✅ |
| **Game telemetry → haptics and dash** | ✅ via [Winecarte](https://github.com/srounce/winecarte) — validated with Le Mans Ultimate |
| ↳ iRacing | ❌ Winecarte does not export iRacing's memory map |

> **Have a different Conspit peripheral?** (Ares Apex, CPP.EVO/Apex, 290GP, PW1, shifter,
> handbrake.) Most of this project matches by **vendor**, not by model — the H.AO wheel
> worked 100% on the day it was first plugged in, with no device-specific code. See
> [docs/adicionar-dispositivo.md](docs/adicionar-dispositivo.md) (Portuguese) for the
> diagnostic walkthrough and the support matrix.

The base is **OpenFFBoard 1.15.0** on `F407VG` hardware with an **ODrive** motor
controller, custom VID/PID `3514:0301`. Technical directives live in
[CLAUDE.md](CLAUDE.md) and the full investigation history in
[docs/historico-investigacao.md](docs/historico-investigacao.md) (both in Portuguese — they
double as LLM context, see below); the protocol ConspitLink speaks is documented in
[docs/protocolo-conspitlink.md](docs/protocolo-conspitlink.md) (base) and
[docs/protocolo-cpp-lite.md](docs/protocolo-cpp-lite.md) (pedals).

---

## The path, in 4 steps

| step | what it solves | required? |
|---|---|---|
| **1 — udev rule** | axis deadzone and jitter; HID access | **required**, even without Wine |
| **2 — Verify the hardware** | confirms the base responds before going on | recommended |
| **3 — ConspitLink under Wine** | configure base, pedals and wheel with the official GUI | optional |
| **4 — Game telemetry** | `Customize` haptics and the wheel dash | optional, needs step 3 |

If all you want is **FFB in games with correct axes**, step 1 is enough and you can stop
there. Steps 3 and 4 exist to get configuration and telemetry like on Windows.

At any point, `tools/check-setup.sh` tells you where you are and what is missing.

---

## Prerequisites

```bash
git clone https://github.com/juliscreudo/conspit-ares-linux.git ~/apps/conspit-ares-linux
cd ~/apps/conspit-ares-linux
```

### Packages

Nothing here is distro-specific; only package names change.

| what | used for | Fedora | Arch / CachyOS |
|---|---|---|---|
| `evdev-joystick` | zeroing fuzz/deadzone (step 1) | `linuxconsoletools` | `linuxconsole` |
| pyserial | diagnostic tools (step 2) | `python3-pyserial` | `python-pyserial` |
| Wine | running ConspitLink (step 3) | `wine` | `wine` — needs the **multilib** repo |
| mingw-w64 *(optional)* | building the `hidenum.exe` diagnostic | `mingw64-gcc` | `mingw-w64-gcc` |

```bash
# Fedora
sudo dnf install -y linuxconsoletools python3-pyserial python3 git wine

# Arch / CachyOS
sudo pacman -S --needed linuxconsole python-pyserial python git wine
```

If a name doesn't match on your distro, find it by file instead of guessing:

```bash
pacman -F evdev-joystick          # Arch (needs 'pacman -Fy' once)
dnf provides '*/evdev-joystick'   # Fedora
```

> ⚠️ On Arch, do **not** `pip install pyserial`: PEP 668 blocks global installs and the
> distro package is the right way.

### Winecarte (game telemetry)

**Only needed for step 4.** Skip this if you won't use in-game haptics or the wheel dash.

**[Winecarte](https://github.com/srounce/winecarte)** (by
[srounce](https://github.com/srounce)) is what carries telemetry across the boundary
between the game's prefix and ConspitLink's. **It is not part of this project** and is
installed separately:

| repository | what it is |
|---|---|
| **[srounce/winecarte](https://github.com/srounce/winecarte)** | the bridge itself (`winecarte-run`, `winehub`, `wine2linux.exe`) |
| **[srounce/linux-simracing-utils](https://github.com/srounce/linux-simracing-utils)** | installer by the same author; the **easiest way** to get Winecarte, also ships SimHub and CrewChief |

The recommended path is the installer:

```bash
git clone https://github.com/srounce/linux-simracing-utils
cd linux-simracing-utils
bash install.sh          # accept the defaults; Winecarte is one of the components
```

> It asks what to install. **The component required here is Winecarte**; SimHub and
> CrewChief are independent of this project and you may skip them.

> ⚠️ Pick the folder carefully before installing: the path gets baked into the launchers.
> If you move it later, re-run `install.sh` from the new location.

`tools/run-conspitlink.sh` **finds Winecarte on its own** if it's on `PATH` or in
`~/apps/linux-simracing-utils/bin/`. Without it the app opens normally — just without game
telemetry.

### Serial port access

The group owning `/dev/ttyACM*` **changes between distros** — `dialout` on Fedora, `uucp`
on Arch. Don't guess; detect:

```bash
# with the base powered on
group=$(stat -c '%G' /dev/ttyACM*)
echo "device group: $group"
id -nG | tr ' ' '\n' | grep -qx "$group" || sudo usermod -aG "$group" "$USER"
```

After `usermod` you **must log out and back in** — new groups don't apply to the current
session.

### Verification

This script checks everything this README asks for and says what's missing, with the fix
next to each failure:

```bash
tools/check-setup.sh
```

Run it before starting, and again at the end. It works with the hardware unplugged (it just
skips the tests that need it).

---

## Step 1 — udev rule (required)

Fixes the axes **and** grants the HID access ConspitLink needs.

```bash
sudo cp udev/70-conspit.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

It is **a single file for every Conspit device** (VID `3514`): the access section matches
by vendor, so the base, the 2nd MCU, pedals and wheels are all covered without one rule per
device — that's what made the H.AO wheel work the day it was plugged in, without touching
the file. If you had older rules (`70-conspit-ares.rules`, `99-conspit*.rules`, or the
`70-uhid-shim.rules` from earlier versions of this repo), remove them. `tools/check-setup.sh`
lists what's left, one by one.

> ⚠️ The **`70-`** prefix is mandatory, for **two** reasons:
>
> 1. systemd applies `TAG="uaccess"` in `73-seat-late.rules`. Numbered `99-`, the rule adds
>    the tag too late and `/dev/hidraw*` stays root-only — **silently, with no error**.
> 2. Joystick ACLs are granted by `70-uaccess.rules:61`
>    (`ENV{ID_INPUT_JOYSTICK}=="?*", TAG+="uaccess"`). Since `70-conspit` sorts before
>    `70-uaccess` (`c` < `u`), assigning `ID_INPUT_JOYSTICK="1"` here is still seen by it.

Verify (with the hardware on) — `fuzz` and `flat` must be zero:

```bash
python3 tools/evdev_info.py /dev/input/by-id/usb-CONSPIT_CONSPIT_ARES_*-if02-event-joystick
python3 tools/evdev_info.py /dev/input/conspit-cpp-lite                    # pedals
python3 tools/evdev_info.py /dev/input/by-id/usb-Conspit_CONSPIT_H.AO_*-event-joystick
```

What the rule fixes, measured before it:

| device | before | what that means |
|---|---|---|
| base, `ABS_X` | `fuzz 255`, `flat 4095` | steering jitter filter + **~12.5% deadzone** around center |
| pedals, 3 axes | `fuzz 15`, `flat 255` (0–4095) | **~6% dead travel** at the start of each pedal |
| wheel, 7 axes | `fuzz 15/255`, `flat 255/4095` | same, on the **Hall paddles** (clutch, bite point) |

> ⚠️ For the pedals, do **not** use `/dev/input/by-id/`. The CPP.LITE exposes two HID
> collections on the same USB interface, and `by-id` ends up pointing at the vendor channel
> (a single 0–255 axis) instead of the pedals. The `/dev/input/conspit-cpp-lite` symlink,
> created by the rule, is the stable path to the three real axes. (The H.AO doesn't suffer
> from this: since it has buttons, `input_id` classifies the right collection on its own.)

## Step 2 — Verify the hardware (recommended)

With the base **connected over USB**. Everything here is read-only — nothing is written to
the hardware.

```bash
python3 tools/probe_serial.py            # speaks the OpenFFBoard protocol (read-only)
python3 tools/hid_watch.py 15            # position on both channels (turn the wheel)
python3 tools/cpp_pedal.py ler           # config stored in the pedals (read-only)
```

`probe_serial.py` should answer `sys.0.swver? -> 1.15.0` and list the active classes
(`main`, `sys`, `axis`, `fx`, `odrv`, `can`, `cananalog`). It finds the port by itself via
`/dev/serial/by-id/`; to force another, pass the device as an argument.

---

## Step 3 — ConspitLink 2.0 under Wine (optional)

Download **ConspitLink2.0.exe** from Conspit's official site and put it at the repo root.
It is proprietary (~300 MB), it's in `.gitignore`, and it is **not redistributed here** —
you must get it from Conspit.

```bash
cd ~/apps/conspit-ares-linux        # your clone
export WINEPREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/conspit-ares-linux/prefix"
mkdir -p "$WINEPREFIX"

wineboot -u                       # creates the isolated prefix
wine ConspitLink2.0.exe /S        # silent install
```

Prepare the prefix — **without this the app cannot see the devices**:

```bash
python3 tools/conspit_wine_setup.py
```

The script should end with `tudo certo.` ("all good"). Open the app:

```bash
tools/run-conspitlink.sh
```

### Menu shortcut (optional)

To launch by clicking instead of from a terminal:

```bash
tools/instalar-atalho.sh              # install
tools/instalar-atalho.sh --remover    # uninstall
```

It reuses the icon Wine already extracted from the `.exe` and points at
`run-conspitlink.sh` — so the shortcut goes through the same pre-flight checks and starts
the telemetry bridge.

> Wine creates a shortcut of **its own** when the app installs, under
> `~/.local/share/applications/wine/Programs/`. It works, but it runs the `.lnk` directly:
> it skips the checks and doesn't start the bridge. Ours lives outside that folder
> precisely so `winemenubuilder` never overwrites it. The script tells you how to hide
> Wine's, if you want.

> ⚠️ **Re-run `conspit_wine_setup.py` whenever you plug in a new Conspit device.** It
> builds the device list from what's on the bus. (In practice a new device already works
> without it, thanks to the safety net described below — but the list is what documents the
> intent, and `check-setup.sh` checks for it.)

### What `conspit_wine_setup.py` does, and why

Two independent things:

**1. Registers the serial port in Wine's PnP tree.** Wine exposes serial ports as generic
devices, **without USB VID/PID**. Qt's `QSerialPortInfo` (which ConspitLink uses)
enumerates via SetupAPI's `Ports` class and takes the VID/PID from the device instance
ID — so without a PnP node the base never shows up. The script creates that node and maps
`COM33` in the two mandatory places (`dosdevices/com33` and
`HKLM\Software\Wine\Ports\COM33`), always via `/dev/serial/by-id/...`.

**2. Switches `winebus` to the hidraw backend.** This is the step that makes the pedals,
the wheel and the base's full telemetry work. By default Wine hands out HID devices
**synthesized by SDL**, with a single collection: the 64-byte vendor channels (pedals,
wheels) and the base's command collection simply don't exist for the app. On the hidraw
backend, Wine passes the real descriptor and `hidclass` splits the collections into
`&Col01`/`&Col02`, exactly like Windows.

> ⚠️ The key is `HKLM\System\CurrentControlSet\Services\`**`winebus`**, **not** the
> `...\winebus\Parameters` subkey. `winebus.sys` documents the key in its own source
> (`/* @@ Wine registry key: HKLM\System\CurrentControlSet\Services\WineBus */`) and never
> reads the subkey. Writing to the wrong place is ignored **silently** — it cost this
> project three days. If you're debugging Wine's HID backend, the channel is
> `WINEDEBUG=+hid` (`+plugplay` does **not** show these decisions).

---

## Step 4 — Game telemetry (optional)

Needed for the pedals' **`Customize` haptics** and the wheel's **dash / rev lights**, both
fed by ConspitLink itself. None of this is needed to configure the base, the pedals or the
wheel.

The problem: games write telemetry into named shared memory, and the wineserver object
namespace is **per prefix**. The game runs in Proton's prefix, ConspitLink in its own, and
neither sees the other's memory — the app stays at `Not Started` forever.

**[Winecarte](https://github.com/srounce/winecarte)** solves it with a bridge in two
halves — installed in [Prerequisites](#winecarte-game-telemetry).

1. **On the game**, in Steam under *Properties → Launch Options*:

   ```
   winecarte-run %command%
   ```

   This exports the game's shared memory to `/dev/shm`.

2. **On ConspitLink**, nothing to do: `tools/run-conspitlink.sh` starts the other half by
   itself (`winehub`, pointed at this prefix) and prints `ponte de telemetria: no ar`
   ("telemetry bridge: up"). To disable it, `--sem-ponte`.

Join a session in the game: `Select Game` should flip from `Not Started` to **`Started`**.

> Detection **is** the attach to shared memory — there is no separate mechanism. If
> `Started` showed up, telemetry is flowing; if it didn't, the bridge is what failed.

### Games covered

Validated with **Le Mans Ultimate**. The memory-map names also match for **Assetto Corsa**,
**AC EVO**, **rFactor 2** and **AMS2 / Project Cars 2**.

> ❌ **iRacing does not work through this route** — Winecarte doesn't export its map
> (`Local\IRSDKMemMapFileName`).

> **UDP** telemetry games (the F1 series, DiRT Rally 2.0, EA WRC, Forza) need no bridge at
> all: UDP is kernel networking and crosses the Wine/Proton boundary on its own. Point the
> game's telemetry at `127.0.0.1`. **Untested here** — none of those games on this rig.

---

## Known issues

### "Error: The base port is occupied"

Happens when you **unplug the USB with the app open**: the port handle is orphaned in the
wineserver. Usually harmless (the app keeps working), but to clean up:

```bash
tools/run-conspitlink.sh --limpo      # "--clean": restarts this prefix's wineserver
```

Avoid it by closing the app before disconnecting the base.

### The `/dev/ttyACM*`, `hidraw*` and `event*` numbers change

On every kernel re-enumeration (replug, suspend/resume) the numbers shuffle — including
**between the base and the base's second MCU**. Never hard-code `ttyACM2`/`hidraw2`/
`event21` anywhere. Always resolve via `/dev/serial/by-id/`, `/dev/input/by-id/` or by
VID/PID in `/sys/class/hidraw/*/device/uevent`. Every tool in this repo does that.

### The app doesn't list a device that is plugged in

Almost always one of these two:

1. **`/dev/hidraw*` without ACLs** — the hidraw backend depends on it. Section 3 of
   `tools/check-setup.sh` says which ones lack access; the fix is the udev rule from
   step 1.
2. **`winebus` not on the hidraw backend** — section 7 of `check-setup.sh`; the fix is
   `python3 tools/conspit_wine_setup.py`.

To see exactly what the app sees, build the enumerator and run it inside the prefix:

```bash
make -C tools     # needs mingw-w64
WINEPREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/conspit-ares-linux/prefix" wine tools/hidenum.exe
```

Every Conspit device should show its two collections (`usage 0x04` for the joystick,
`usage 0x3A` for the 64-byte vendor channel). ⚠️ Enumeration has a race: right after a
`wineserver -k`, run it **twice** a few seconds apart.

### Calibrating the pedals

**Min/max** calibration lives in the pedal unit, not on the PC, and it is **not readable
back** by any command — diagnose via the axis: pedal released should read near `0`, at full
travel near `4095`.

```bash
python3 tools/cpp_pedal.py monitorar                  # raw reading of all three
python3 tools/cpp_pedal.py calibrar acelerador min    # with the pedal RELEASED
python3 tools/cpp_pedal.py calibrar acelerador max    # with the pedal FULLY PRESSED
```

(Subcommands are in Portuguese: `monitorar` = monitor, `calibrar acelerador min/max` =
calibrate throttle min/max.) The same can be done from the ConspitLink GUI, which also
exposes the *curve* (a separate setting from min/max — see
[docs/protocolo-cpp-lite.md](docs/protocolo-cpp-lite.md)).

---

## Tools

| file | what it does |
|---|---|
| `tools/check-setup.sh` | checks the whole environment and says what to fix |
| `tools/probe_serial.py` | **read-only** probe of the CDC serial (only `?` and `!`, never `=`) |
| `tools/evdev_info.py` | axes with fuzz/flat and FFB capabilities, without firing effects |
| `tools/parse_hid_rdesc.py` | decodes a report descriptor, highlights the PID usage page |
| `tools/hid_watch.py` | wheel position on evdev and hidraw at the same time |
| `tools/cpp_pedal.py` | reads, monitors and calibrates the pedals **natively** (⚠️ `calibrar` writes) |
| `tools/conspit_wine_setup.py` | serial PnP node + winebus hidraw backend + SteamBridge |
| `tools/hidenum.c` | enumerates HID from inside the Wine prefix (diagnostic) |
| `tools/dinput_axes.c` | measures DirectInput axis mapping inside the prefix (diagnostic) |
| `tools/Makefile` | builds the two `.exe` diagnostics (`make -C tools`) |
| `tools/conspit-prefixo.sh` | resolves the prefix path (sourced by the others) |
| `tools/instalar-atalho.sh` | installs the app's menu shortcut (reuses Wine's icon) |
| `tools/run-conspitlink.sh` | opens ConspitLink in the isolated prefix |
| `udev/70-conspit.rules` | zeroes fuzz/deadzone and grants hidraw access |

> ⚠️ **This is a 20 Nm base.** The diagnostic tools are deliberately read-only. Do not send
> `=`, `sys.0.save`, `sys.0.format` or ODrive calibration commands unless the wheel is free
> and your hands are clear. The two exceptions that write are marked above.
