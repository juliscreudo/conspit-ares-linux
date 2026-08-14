#!/usr/bin/env bash
# Verifica se esta maquina esta pronta para usar a Conspit Ares.
#
# Roda em qualquer distro: nada aqui assume gerenciador de pacotes. Cada
# falha vem com a correcao ao lado.
#
#   tools/check-setup.sh
#
# Sai com 0 se tudo essencial passou, 1 caso contrario.

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VID=3514
PID_BASE=0301

falhas=0
avisos=0

ok()    { printf '  [ ok ]  %s\n' "$1"; }
falha() { printf '  [FALHA] %s\n' "$1"; [[ -n "${2:-}" ]] && printf '          -> %s\n' "$2"; falhas=$((falhas+1)); }
aviso() { printf '  [aviso] %s\n' "$1"; [[ -n "${2:-}" ]] && printf '          -> %s\n' "$2"; avisos=$((avisos+1)); }
secao() { printf '\n%s\n' "$1"; }

echo "Conspit Ares -- verificacao de ambiente"
echo "distro: $(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || echo desconhecida)"
echo "kernel: $(uname -r)"

# ---------------------------------------------------------------- hardware
secao "1. Hardware"

base_sysfs=""
for d in /sys/bus/usb/devices/*; do
  [[ -r "$d/idVendor" && -r "$d/idProduct" ]] || continue
  if [[ "$(cat "$d/idVendor")" == "$VID" && "$(cat "$d/idProduct")" == "$PID_BASE" ]]; then
    base_sysfs="$d"; break
  fi
done

com_hw=0
if [[ -n "$base_sysfs" ]]; then
  ok "base detectada ($VID:$PID_BASE, $(cat "$base_sysfs/product" 2>/dev/null))"
  com_hw=1
else
  aviso "base nao detectada no USB" \
        "os testes de hardware serao pulados. Para conferi-los, ligue a base
             e rode de novo. Confira tambem: lsusb | grep -i conspit"
fi

# --------------------------------------------------------------- serial CDC
secao "2. Porta serial (configuracao da base)"

if [[ $com_hw -eq 0 ]]; then
  echo "  (pulado -- base desligada)"
else
serial_link=$(ls /dev/serial/by-id/usb-CONSPIT_CONSPIT_ARES_*-if00 2>/dev/null | head -1)
if [[ -n "$serial_link" ]]; then
  serial_dev=$(readlink -f "$serial_link")
  ok "interface CDC presente ($serial_dev)"

  grupo_dev=$(stat -c '%G' "$serial_dev" 2>/dev/null)
  if [[ -r "$serial_dev" && -w "$serial_dev" ]]; then
    ok "acesso de leitura/escrita a serial (grupo do device: $grupo_dev)"
  else
    falha "sem acesso a $serial_dev (grupo do device: $grupo_dev)" \
          "sudo usermod -aG $grupo_dev \$USER   e depois FAZER LOGOUT/LOGIN"
  fi
else
  falha "interface CDC ausente" "confira: ls -l /dev/serial/by-id/"
fi
fi

# -------------------------------------------------------------------- hidraw
secao "3. Canais HID (telemetria do ConspitLink)"

if [[ $com_hw -eq 0 ]]; then
  echo "  (pulado -- base desligada)"
else
achou_hidraw=0
for h in /sys/class/hidraw/hidraw*; do
  [[ -r "$h/device/uevent" ]] || continue
  hid_id=$(grep '^HID_ID=' "$h/device/uevent" 2>/dev/null | cut -d= -f2)
  # HID_ID=0003:00003514:00000301 -- comparar como numero
  ovid=$(echo "$hid_id" | cut -d: -f2)
  [[ -z "$ovid" ]] && continue
  if [[ $((16#$ovid)) -eq $((16#$VID)) ]]; then
    achou_hidraw=1
    dev="/dev/$(basename "$h")"
    nome=$(grep '^HID_NAME=' "$h/device/uevent" 2>/dev/null | cut -d= -f2)
    if [[ -r "$dev" && -w "$dev" ]]; then
      ok "$dev acessivel ($nome)"
    else
      falha "$dev SEM acesso ($nome)" \
            "instale a regra udev -- ver secao 4"
    fi
  fi
done
[[ $achou_hidraw -eq 1 ]] || falha "nenhum hidraw Conspit encontrado"
fi

# ---------------------------------------------------------------- regra udev
secao "4. Regra udev"

regra=$(ls /etc/udev/rules.d/*conspit*.rules 2>/dev/null | head -1)
if [[ -n "$regra" ]]; then
  prefixo=$(basename "$regra" | grep -oE '^[0-9]+')
  if [[ -n "$prefixo" && "$prefixo" -lt 73 ]]; then
    ok "regra instalada com prefixo correto ($(basename "$regra"))"
  else
    falha "regra instalada como $(basename "$regra") -- prefixo >= 73" \
          "o systemd aplica o TAG=uaccess em 73-seat-late.rules; renomeie para 70-:
             sudo rm $regra
             sudo cp $repo/udev/70-conspit-ares.rules /etc/udev/rules.d/
             sudo udevadm control --reload-rules && sudo udevadm trigger"
  fi
else
  falha "regra udev NAO instalada" \
        "sudo cp $repo/udev/70-conspit-ares.rules /etc/udev/rules.d/
             sudo udevadm control --reload-rules && sudo udevadm trigger"
fi

# a regra chama este binario por caminho absoluto
if [[ -x /usr/bin/evdev-joystick ]]; then
  ok "/usr/bin/evdev-joystick presente"
else
  caminho=$(command -v evdev-joystick 2>/dev/null)
  if [[ -n "$caminho" ]]; then
    falha "evdev-joystick esta em $caminho, mas a regra chama /usr/bin/evdev-joystick" \
          "ajuste o caminho em $repo/udev/70-conspit-ares.rules e reinstale"
  else
    falha "evdev-joystick ausente (pacote com jstest/fftest/evdev-joystick)" \
          "Fedora: sudo dnf install linuxconsoletools
             Arch:   sudo pacman -S linuxconsole
             (para achar o nome exato: 'pacman -F evdev-joystick' ou 'dnf provides */evdev-joystick')"
  fi
fi

# ---------------------------------------------------------- eixos corrigidos
secao "5. Eixos (fuzz / deadzone)"

if [[ $com_hw -eq 0 ]]; then
  echo "  (pulado -- base desligada)"
else
ev=$(ls /dev/input/by-id/usb-CONSPIT_CONSPIT_ARES_*-event-joystick 2>/dev/null | head -1)
if [[ -z "$ev" ]]; then
  aviso "device de joystick nao encontrado" "confira: ls -l /dev/input/by-id/"
elif ! command -v python3 >/dev/null; then
  aviso "python3 ausente, nao da para verificar fuzz/flat"
else
  linha=$(python3 "$repo/tools/evdev_info.py" "$ev" 2>/dev/null | grep -E '^\s+ABS_X')
  if [[ -z "$linha" ]]; then
    aviso "nao consegui ler os eixos de $ev"
  else
    fuzz=$(echo "$linha" | awk '{print $5}')
    flat=$(echo "$linha" | awk '{print $6}')
    if [[ "$fuzz" == "0" && "$flat" == "0" ]]; then
      ok "ABS_X com fuzz=0 flat=0"
    else
      falha "ABS_X com fuzz=$fuzz flat=$flat (deveria ser 0/0)" \
            "a regra udev nao esta sendo aplicada; rode:
             sudo udevadm control --reload-rules && sudo udevadm trigger
             e reconecte a base"
    fi
  fi
fi
fi

# ------------------------------------------------------------------ software
secao "6. Software"

if command -v python3 >/dev/null; then
  ok "python3 ($(python3 --version 2>&1 | cut -d' ' -f2))"
  if python3 -c "import serial" 2>/dev/null; then
    ok "pyserial"
  else
    falha "pyserial ausente" \
          "Fedora: sudo dnf install python3-pyserial
             Arch:   sudo pacman -S python-pyserial
             (evite 'pip install' no Arch: PEP 668 bloqueia instalacao global)"
  fi
else
  falha "python3 ausente" "necessario para as ferramentas de diagnostico"
fi

if command -v wine >/dev/null; then
  ok "wine ($(wine --version 2>/dev/null))"
else
  aviso "wine ausente (so necessario para o ConspitLink)" \
        "Fedora: sudo dnf install wine
             Arch:   sudo pacman -S wine   (requer o repo multilib habilitado)"
fi

# -------------------------------------------------------------- prefixo wine
secao "7. ConspitLink sob Wine (opcional)"

pfx="$repo/.wine-conspitlink"
if [[ ! -d "$pfx" ]]; then
  aviso "prefixo Wine nao criado" "siga o Passo 3 do README"
else
  ok "prefixo existe"
  if [[ -d "$pfx/drive_c/Program Files (x86)/Conspit Link 2.0" ]]; then
    ok "ConspitLink instalado"
  else
    falha "ConspitLink nao instalado no prefixo" \
          "WINEPREFIX=$pfx wine $repo/ConspitLink2.0.exe /S"
  fi

  no_pnp=$(grep -l "VID_${VID}&PID_${PID_BASE}" "$pfx/system.reg" 2>/dev/null)
  if [[ -n "$no_pnp" ]]; then
    ok "no PnP registrado (o app consegue enxergar a base)"
  else
    falha "no PnP AUSENTE -- o ConspitLink nao vai encontrar a base" \
          "python3 $repo/tools/conspit_wine_setup.py"
  fi
fi

# --------------------------------------------------------------------- resumo
echo
echo "-------------------------------------------------------------"
if [[ $falhas -eq 0 ]]; then
  echo "Tudo essencial OK ($avisos aviso(s))."
  exit 0
fi
echo "$falhas falha(s), $avisos aviso(s). Corrija o que esta marcado [FALHA]."
exit 1
