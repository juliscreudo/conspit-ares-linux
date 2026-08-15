#!/usr/bin/env bash
# Verifica se esta maquina esta pronta para usar os devices Conspit.
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
PID_MCU2=0300
PID_PEDAIS=0005
PID_VOLANTE=0007

falhas=0
avisos=0

ok()    { printf '  [ ok ]  %s\n' "$1"; }
falha() { printf '  [FALHA] %s\n' "$1"; [[ -n "${2:-}" ]] && printf '          -> %s\n' "$2"; falhas=$((falhas+1)); }
aviso() { printf '  [aviso] %s\n' "$1"; [[ -n "${2:-}" ]] && printf '          -> %s\n' "$2"; avisos=$((avisos+1)); }
secao() { printf '\n%s\n' "$1"; }

# nome amigavel de um PID Conspit
nome_pid() {
  case "$1" in
    "$PID_BASE")    echo "base Ares" ;;
    "$PID_MCU2")    echo "2o MCU da base (dash)" ;;
    "$PID_PEDAIS")  echo "pedais CPP.LITE" ;;
    "$PID_VOLANTE") echo "volante H.AO" ;;
    *)              echo "device Conspit" ;;
  esac
}

echo "Conspit -- verificacao de ambiente"
echo "distro: $(. /etc/os-release 2>/dev/null && echo "$PRETTY_NAME" || echo desconhecida)"
echo "kernel: $(uname -r)"

# ---------------------------------------------------------------- hardware
secao "1. Hardware"

# Todos os devices Conspit no barramento, nao so a base: o mesmo app atende
# base, pedais e volantes, e cada um tem seu proprio canal.
pids_presentes=()
base_sysfs=""
for d in /sys/bus/usb/devices/*; do
  [[ -r "$d/idVendor" && -r "$d/idProduct" ]] || continue
  [[ "$(cat "$d/idVendor")" == "$VID" ]] || continue
  pid=$(cat "$d/idProduct")
  pids_presentes+=("$pid")
  ok "$VID:$pid  $(cat "$d/product" 2>/dev/null)  [$(nome_pid "$pid")]"
  [[ "$pid" == "$PID_BASE" ]] && base_sysfs="$d"
done

com_hw=0
if [[ ${#pids_presentes[@]} -gt 0 ]]; then
  com_hw=1
else
  aviso "nenhum device Conspit no USB" \
        "os testes de hardware serao pulados. Para conferi-los, ligue os
             dispositivos e rode de novo. Confira tambem: lsusb | grep -i 3514"
fi

# --------------------------------------------------------------- serial CDC
secao "2. Porta serial (configuracao da base)"

if [[ -z "$base_sysfs" ]]; then
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
secao "3. Canais HID"

# ⚠️ Isto ficou CRITICO desde 2026-08-15: com o winebus no backend hidraw, e'
# por aqui que o ConspitLink fala com TODOS os devices -- nao so com os canais
# vendor. Um hidraw sem ACL agora derruba o device inteiro no app.
if [[ $com_hw -eq 0 ]]; then
  echo "  (pulado -- nenhum device ligado)"
else
achou_hidraw=0
for h in /sys/class/hidraw/hidraw*; do
  [[ -r "$h/device/uevent" ]] || continue
  hid_id=$(grep '^HID_ID=' "$h/device/uevent" 2>/dev/null | cut -d= -f2)
  # HID_ID=0003:00003514:00000301 -- comparar como numero (zeros a esquerda
  # de largura variavel)
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

regra_oficial=/etc/udev/rules.d/70-conspit.rules
if [[ -f "$regra_oficial" ]]; then
  ok "regra instalada (70-conspit.rules)"
  if ! diff -q "$repo/udev/70-conspit.rules" "$regra_oficial" >/dev/null 2>&1; then
    aviso "a regra instalada difere da do repo" \
          "sudo cp $repo/udev/70-conspit.rules /etc/udev/rules.d/
             sudo udevadm control --reload-rules && sudo udevadm trigger"
  fi
else
  falha "regra udev NAO instalada" \
        "sudo cp $repo/udev/70-conspit.rules /etc/udev/rules.d/
             sudo udevadm control --reload-rules && sudo udevadm trigger"
fi

# O shim de uhid foi aposentado em 2026-08-15 (o backend hidraw do winebus
# tornou-o desnecessario). A regra que ele exigia dava a QUALQUER processo da
# sessao o poder de criar dispositivos de entrada virtuais -- num Wayland
# isso contorna o isolamento de entrada do compositor. Nao ha motivo para
# mante-la.
if [[ -f /etc/udev/rules.d/70-uhid-shim.rules ]]; then
  aviso "70-uhid-shim.rules ainda instalada, mas nao e' mais necessaria" \
        "ela concede acesso a /dev/uhid (criar teclado/mouse virtual) e so
             existia para o shim, que foi removido do projeto. Remova:
             sudo rm /etc/udev/rules.d/70-uhid-shim.rules
             sudo udevadm control --reload-rules"
fi

# Outras regras Conspit na maquina. Reportadas UMA A UMA, nunca em bloco: o
# glob *conspit* tambem pega regras de OUTROS dispositivos da marca (pedais,
# volantes), que nao sao deste projeto e nao devem ser apagadas as cegas.
for r in /etc/udev/rules.d/*conspit*.rules; do
  [[ -e "$r" ]] || continue
  [[ "$r" == "$regra_oficial" ]] && continue
  prefixo=$(basename "$r" | grep -oE '^[0-9]+')
  if [[ -n "$prefixo" && "$prefixo" -ge 73 ]]; then
    aviso "regra legada $(basename "$r") -- prefixo $prefixo, o TAG=uaccess dela NUNCA dispara" \
          "o systemd efetiva a tag em 73-seat-late.rules. Veja o conteudo antes de mexer:
             cat $r
           Se for de um device Conspit, a 70-conspit.rules ja cobre o acesso e esta pode sair:
             sudo rm $r
           Se ela fizer algo mais (ex.: ENV{ID_INPUT_JOYSTICK}=\"1\"), migre para a
           secao 3 da 70-conspit.rules em vez de descartar."
  else
    aviso "outra regra Conspit instalada: $(basename "$r")" \
          "confira se nao conflita com a 70-conspit.rules: cat $r"
  fi
done

# a regra chama este binario por caminho absoluto
if [[ -x /usr/bin/evdev-joystick ]]; then
  ok "/usr/bin/evdev-joystick presente"
else
  caminho=$(command -v evdev-joystick 2>/dev/null)
  if [[ -n "$caminho" ]]; then
    falha "evdev-joystick esta em $caminho, mas a regra chama /usr/bin/evdev-joystick" \
          "ajuste o caminho em $repo/udev/70-conspit.rules e reinstale"
  else
    falha "evdev-joystick ausente (pacote com jstest/fftest/evdev-joystick)" \
          "Fedora: sudo dnf install linuxconsoletools
             Arch:   sudo pacman -S linuxconsole
             (para achar o nome exato: 'pacman -F evdev-joystick' ou 'dnf provides */evdev-joystick')"
  fi
fi

# ---------------------------------------------------------- eixos corrigidos
secao "5. Eixos (fuzz / deadzone)"

# Conta quantos eixos de um device ainda tem fuzz/flat ruins. O evdev_info.py
# marca cada um com "fuzz/flat ruins".
eixos_ruins() {
  python3 "$repo/tools/evdev_info.py" "$1" 2>/dev/null | grep -cE 'fuzz/flat ruins'
}

if [[ $com_hw -eq 0 ]]; then
  echo "  (pulado -- nenhum device ligado)"
elif ! command -v python3 >/dev/null; then
  aviso "python3 ausente, nao da para verificar fuzz/flat"
else

# --- base
if [[ -n "$base_sysfs" ]]; then
  ev=$(ls /dev/input/by-id/usb-CONSPIT_CONSPIT_ARES_*-event-joystick 2>/dev/null | head -1)
  if [[ -z "$ev" ]]; then
    aviso "device de joystick da base nao encontrado" "confira: ls -l /dev/input/by-id/"
  else
    n=$(eixos_ruins "$ev")
    if [[ "$n" == "0" ]]; then
      ok "base: fuzz/flat zerados"
    else
      falha "base: $n eixo(s) ainda com fuzz/flat ruins" \
            "sudo udevadm control --reload-rules && sudo udevadm trigger
             e reconecte a base"
    fi
  fi
fi

# --- pedais CPP.LITE
# NAO usar /dev/input/by-id/ aqui: nos pedais ele aponta para o canal vendor
# (1 eixo de 0-255), nao para os tres eixos reais. Ver secao 3 da regra udev.
if printf '%s\n' "${pids_presentes[@]}" | grep -qx "$PID_PEDAIS"; then
  ped=/dev/input/conspit-cpp-lite
  if [[ ! -e "$ped" ]]; then
    falha "pedais presentes, mas $ped nao existe" \
          "a secao 3 da regra nao esta aplicada:
             sudo cp $repo/udev/70-conspit.rules /etc/udev/rules.d/
             sudo udevadm control --reload-rules && sudo udevadm trigger"
  else
    n=$(eixos_ruins "$ped")
    if [[ "$n" == "0" ]]; then
      ok "pedais CPP.LITE: fuzz/flat zerados"
    else
      falha "pedais CPP.LITE: $n eixo(s) ainda com fuzz/flat ruins" \
            "sudo udevadm control --reload-rules && sudo udevadm trigger
             e reconecte os pedais"
    fi
  fi
fi

# --- volante H.AO
# Aqui o by-id serve: como o volante tem botoes, o input_id classifica a
# collection de joystick sozinho e o symlink -event-joystick sai correto.
if printf '%s\n' "${pids_presentes[@]}" | grep -qx "$PID_VOLANTE"; then
  vol=$(ls /dev/input/by-id/usb-Conspit_CONSPIT_H.AO_*-event-joystick 2>/dev/null | head -1)
  if [[ -z "$vol" ]]; then
    aviso "volante H.AO presente, mas sem symlink -event-joystick" \
          "confira: ls -l /dev/input/by-id/"
  else
    n=$(eixos_ruins "$vol")
    if [[ "$n" == "0" ]]; then
      ok "volante H.AO: fuzz/flat zerados"
    else
      falha "volante H.AO: $n eixo(s) ainda com fuzz/flat ruins (paddles Hall)" \
            "a secao 4 da regra nao esta aplicada:
             sudo cp $repo/udev/70-conspit.rules /etc/udev/rules.d/
             sudo udevadm control --reload-rules && sudo udevadm trigger"
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

# shellcheck source=conspit-prefixo.sh
. "$repo/tools/conspit-prefixo.sh"
pfx="$WINEPREFIX"
if [[ ! -d "$pfx" ]]; then
  aviso "prefixo Wine nao criado" "siga o Passo 3 do README"
else
  ok "prefixo existe ($pfx)"
  if [[ -d "$pfx/drive_c/Program Files (x86)/Conspit Link 2.0" ]]; then
    ok "ConspitLink instalado"
  else
    falha "ConspitLink nao instalado no prefixo" \
          "WINEPREFIX=$pfx wine $repo/ConspitLink2.0.exe /S"
  fi

  reg="$pfx/system.reg"

  if grep -q "VID_${VID}&PID_${PID_BASE}" "$reg" 2>/dev/null; then
    ok "no PnP da serial registrado (o app acha a base)"
  else
    falha "no PnP AUSENTE -- o ConspitLink nao vai encontrar a base" \
          "python3 $repo/tools/conspit_wine_setup.py"
  fi

  # Backend do winebus. Sem isto o Wine entrega devices HID sintetizados pelo
  # SDL, com UMA collection so: os canais vendor (pedais, volantes) e a
  # collection de comandos da base simplesmente nao existem para o app.
  if grep -q '"Enable SDL"=dword:00000000' "$reg" 2>/dev/null; then
    ok "winebus no backend hidraw (Enable SDL=0)"
  else
    falha "winebus NAO esta no backend hidraw" \
          "o app abre, mas nao ve pedais nem volantes, e a telemetria da base
             fica incompleta. Corrija com:
             python3 $repo/tools/conspit_wine_setup.py"
  fi

  # ⚠️ A pegadinha que custou o projeto inteiro: ate 2026-08-15 este setup
  # escrevia em Services\winebus\PARAMETERS, subchave que o driver nunca le
  # (o winebus.sys documenta a chave como Services\WineBus). Tudo era
  # ignorado em silencio. Se a subchave ainda existir, ela confunde quem for
  # diagnosticar.
  if grep -q 'Services\\\\winebus\\\\Parameters' "$reg" 2>/dev/null; then
    aviso "sobrou a subchave winebus\\Parameters (inerte -- o driver nao a le)" \
          "python3 $repo/tools/conspit_wine_setup.py   (ela e' removida)"
  fi

  # Cada device presente deve estar no EnableHidraw. Nao e' obrigatorio
  # (o Enable SDL=0 ja cobre), mas e' o que documenta a intencao.
  if [[ $com_hw -eq 1 ]]; then
    faltando=()
    for pid in "${pids_presentes[@]}"; do
      grep -qi "${VID}:${pid}" "$reg" 2>/dev/null || faltando+=("$VID:$pid")
    done
    if [[ ${#faltando[@]} -eq 0 ]]; then
      ok "EnableHidraw cobre os ${#pids_presentes[@]} device(s) presentes"
    else
      aviso "EnableHidraw nao lista: ${faltando[*]}" \
            "deve funcionar assim mesmo (Enable SDL=0 cobre), mas para
             registrar: python3 $repo/tools/conspit_wine_setup.py"
    fi
  fi

  # O shim antigo escondia o device real do DirectInput neste prefixo. Se a
  # chave sobrou, o app deixa de ver os eixos dos pedais.
  if grep -q '"CONSPIT CPP.LITE"="disabled"' "$pfx/user.reg" 2>/dev/null; then
    falha "sobrou a entrada que esconde os pedais do DirectInput" \
          "era do shim, que foi removido. Remova:
             WINEPREFIX=$pfx wine reg delete 'HKCU\\Software\\Wine\\DirectInput\\Joysticks' /v 'CONSPIT CPP.LITE' /f"
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
