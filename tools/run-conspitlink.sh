#!/usr/bin/env bash
# Abre o ConspitLink 2.0 no prefixo Wine isolado deste projeto.
#
#   tools/run-conspitlink.sh             abre o app
#   tools/run-conspitlink.sh --limpo     derruba o Wine antes de abrir
#   tools/run-conspitlink.sh --sem-eixos nao cria o joystick virtual dos
#                                        pedais (some da lista dos jogos;
#                                        as barras do app voltam trocadas)
#   tools/run-conspitlink.sh --capturar  registra o trafego do canal vendor
#                                        dos pedais em texto, nos dois
#                                        sentidos (shim em -v)
#
# O `--limpo` existe porque tirar o USB com o app aberto deixa o handle da
# porta orfao no wineserver; na proxima abertura o app reclama "The base port
# is occupied". Derrubar o wineserver limpa isso.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export WINEPREFIX="$repo/.wine-conspitlink"
export WINEDEBUG="${WINEDEBUG:--all}"

app="$WINEPREFIX/drive_c/Program Files (x86)/Conspit Link 2.0"

[[ -d "$WINEPREFIX" ]] || {
  echo "prefixo nao existe: $WINEPREFIX" >&2
  echo "siga o README (secao 'ConspitLink 2.0 sob Wine')." >&2
  exit 1
}
[[ -d "$app" ]] || {
  echo "ConspitLink nao instalado no prefixo." >&2
  echo "  wine \$repo/ConspitLink2.0.exe /S" >&2
  exit 1
}

sem_eixos=0
capturar=0
shim_args=()
args=()
for a in "$@"; do
  case "$a" in
    --sem-eixos) sem_eixos=1; shim_args+=(--sem-eixos) ;;
    --capturar)  capturar=1;  shim_args+=(-v) ;;
    *) args+=("$a") ;;
  esac
done
set -- "${args[@]+"${args[@]}"}"

# PIDs do shim, lidos do /proc em vez de `pgrep -f`.
#
# `pgrep -f`/`pkill -f` casam com QUALQUER linha de comando que mencione o
# nome -- inclusive a do proprio shell que roda o comando. Isso ja matou
# este script (ver "Cuidado ao matar processos" no CLAUDE.md). Exigir que
# argv[0] seja o python elimina a classe inteira do problema: um editor com
# o arquivo aberto, um grep ou este script nunca casam.
pids_do_shim() {
  local p argv0
  for p in /proc/[0-9]*; do
    [[ -r "$p/cmdline" ]] || continue
    argv0=$(tr '\0' '\n' <"$p/cmdline" 2>/dev/null | head -1)
    [[ "${argv0##*/}" == python* ]] || continue
    tr '\0' '\n' <"$p/cmdline" 2>/dev/null \
      | grep -q 'cpp_hid_shim\.py$' || continue
    echo "${p##*/}"
  done
}

# O shim NAO e' processo do Wine: `wineserver -k` nao o alcanca. Sem isto,
# um shim antigo sobrevive ao --limpo, o shim_ativo() logo abaixo conclui
# "ja esta rodando" e o shim novo (com as flags que voce pediu) nunca sobe
# -- em silencio. Foi exatamente o que aconteceu com o --capturar.
derrubar_shim() {
  local pids p
  pids=$(pids_do_shim)
  [[ -n "$pids" ]] || return 0
  echo "derrubando shim anterior (pid $(echo $pids))..."
  for p in $pids; do kill "$p" 2>/dev/null || true; done
  # o shim trata SIGTERM e destroi os devices virtuais na saida
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    [[ -z "$(pids_do_shim)" ]] && return 0
    sleep 0.3
  done
  for p in $(pids_do_shim); do kill -9 "$p" 2>/dev/null || true; done
  sleep 0.5
}

if [[ "${1:-}" == "--limpo" ]]; then
  echo "derrubando o Wine deste prefixo..."
  pkill -x "ConspitLink2.0." 2>/dev/null || true
  sleep 1
  wineserver -k 2>/dev/null || true
  sleep 2
  derrubar_shim
elif [[ "$capturar" == "1" ]]; then
  # sem --limpo, um shim vivo continuaria mudo e a captura sairia vazia
  derrubar_shim
fi

# Shim dos pedais CPP.LITE: sem ele o app nao enxerga a pedaleira sob Wine
# (o Wine expoe so a 1a top-level collection do descritor -- ver a secao
# "Pedais CPP.LITE" no CLAUDE.md). Sobe junto e cai junto; se os pedais nao
# estiverem ligados, nao faz nada.
shim_pid=""

# "Ja tem shim rodando?" e' verificado pelo ESTADO (existe device HID
# virtual com o VID/PID dos pedais?), nao por pgrep. `pgrep -f` casa com
# qualquer linha de comando que MENCIONE o nome -- inclusive a do shell que
# esta rodando o proprio pgrep, um editor com o arquivo aberto, ou um grep.
# Ja deu falso positivo aqui.
shim_ativo() {
  local h
  for h in /sys/class/hidraw/hidraw*; do
    [[ -e "$h/device/modalias" ]] || continue
    case "$(readlink -f "$h/device")" in
      */devices/virtual/*) ;;
      *) continue ;;
    esac
    grep -qi 'v00003514p00000005' "$h/device/modalias" && return 0
  done
  return 1
}

if lsusb 2>/dev/null | grep -qi '3514:0005'; then
  if shim_ativo; then
    echo "shim dos pedais: ja estava rodando"
  elif [[ -w /dev/uhid ]]; then
    # O device virtual de EIXOS corrige os rotulos dos pedais na tela do app
    # (sem ele o Wine entrega os eixos na ordem do evdev e o app mostra
    # acelerador como embreagem). Em troca, ele aparece como uma pedaleira a
    # mais na lista de controles dos jogos -- inerte, mas visivel.
    #
    # --sem-eixos derruba so essa parte: deteccao, haptics, curvas e
    # telemetria continuam, porque tudo isso passa pelo canal vendor.
    if [[ "$sem_eixos" == "1" ]]; then
      # o app volta a ler o device real; entao ele nao pode ficar escondido
      wine reg delete 'HKCU\Software\Wine\DirectInput\Joysticks' \
           /v 'CONSPIT CPP.LITE' /f >/dev/null 2>&1 || true
    else
      # esconde o device real do DirectInput SO NESTE PREFIXO, para o app
      # pegar o virtual (que tem os eixos na ordem certa)
      wine reg add 'HKCU\Software\Wine\DirectInput\Joysticks' \
           /v 'CONSPIT CPP.LITE' /d disabled /f >/dev/null 2>&1 || true
    fi
    python3 -u "$repo/tools/cpp_hid_shim.py" --esperar \
            "${shim_args[@]+"${shim_args[@]}"}" \
            >"$WINEPREFIX/cpp_hid_shim.log" 2>&1 &
    shim_pid=$!
    sleep 2
    if kill -0 "$shim_pid" 2>/dev/null; then
      echo "shim dos pedais: no ar (pid $shim_pid)"
      if [[ "$capturar" == "1" ]]; then
        echo "capturando o canal vendor em: $WINEPREFIX/cpp_hid_shim.log"
        echo "  (mexa na GUI; cada comando aparece como 'app->pedal <texto>')"
      fi
    else
      echo "shim dos pedais FALHOU -- veja $WINEPREFIX/cpp_hid_shim.log" >&2
      shim_pid=""
    fi
  else
    echo "pedais CPP.LITE ligados, mas /dev/uhid nao esta acessivel." >&2
    echo "  sudo cp $repo/udev/70-uhid-shim.rules /etc/udev/rules.d/" >&2
    echo "  sudo udevadm control --reload-rules && sudo udevadm trigger" >&2
    echo "  (sem isso o app abre normalmente, so nao lista os pedais)" >&2
  fi
fi

# derruba o shim junto com o app, inclusive se o app morrer sozinho
if [[ -n "$shim_pid" ]]; then
  trap 'kill "$shim_pid" 2>/dev/null || true' EXIT INT TERM
fi

cd "$app"
wine ./ConspitLink2.0.exe "$@"
