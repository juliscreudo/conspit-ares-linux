#!/usr/bin/env bash
# Abre o ConspitLink 2.0 no prefixo Wine isolado deste projeto.
#
#   tools/run-conspitlink.sh             abre o app
#   tools/run-conspitlink.sh --limpo     derruba o Wine antes de abrir
#   tools/run-conspitlink.sh --sem-ponte nao sobe a ponte de telemetria
#
# O `--limpo` existe porque tirar o USB com o app aberto deixa o handle da
# porta orfao no wineserver; na proxima abertura o app reclama "The base port
# is occupied". Derrubar o wineserver limpa isso.
#
# NAO ha mais shim de HID aqui. Ate 2026-08-15 este script subia o
# tools/cpp_hid_shim.py para expor a 2a collection dos pedais e um joystick
# virtual para corrigir a ordem dos eixos. Nada disso e' necessario desde que
# o winebus foi posto no backend hidraw (chave `Services\winebus`, escrita
# pelo tools/conspit_wine_setup.py): o Wine entrega o descritor real e o
# hidclass separa as collections em &Col01/&Col02, como no Windows.
# Ver "O backend do winebus" no CLAUDE.md.
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

args=()
limpo=0
ponte=1
for a in "$@"; do
  case "$a" in
    # nao repassar ao app: sao flags deste script
    --limpo)     limpo=1 ;;
    --sem-ponte) ponte=0 ;;
    *) args+=("$a") ;;
  esac
done
set -- "${args[@]+"${args[@]}"}"

if [[ "$limpo" == "1" ]]; then
  echo "derrubando o Wine deste prefixo..."
  # o comm do Linux corta em 15 chars: "ConspitLink2.0.exe" vira
  # "ConspitLink2.0." -- por isso o ponto no fim, e -x para casar exato.
  pkill -x "ConspitLink2.0." 2>/dev/null || true
  sleep 1
  wineserver -k 2>/dev/null || true
  sleep 2
fi

# O backend hidraw e' o que faz o app enxergar os canais vendor (pedais,
# volantes) e a collection de comandos da base. Sem ele o app abre, mas so
# ve o basico -- falha confusa, entao e' melhor avisar aqui.
if ! grep -q '"Enable SDL"=dword:00000000' "$WINEPREFIX/system.reg" 2>/dev/null; then
  echo "AVISO: o winebus deste prefixo nao esta no backend hidraw." >&2
  echo "  os canais vendor (pedais, volantes) nao vao aparecer no app." >&2
  echo "  corrija com: python3 $repo/tools/conspit_wine_setup.py" >&2
fi

# Um device Conspit ligado depois do setup nao esta na lista EnableHidraw.
# O `Enable SDL=0` cobre o caso, mas a lista e' o que documenta a intencao --
# e conferir e' barato.
if command -v lsusb >/dev/null; then
  while read -r pid; do
    grep -qi "3514:$pid" "$WINEPREFIX/system.reg" 2>/dev/null || {
      echo "nota: device 3514:$pid nao esta no EnableHidraw deste prefixo." >&2
      echo "  (deve funcionar assim mesmo; para registrar: " \
           "python3 $repo/tools/conspit_wine_setup.py)" >&2
    }
  done < <(lsusb 2>/dev/null | sed -n 's/.*ID 3514:\([0-9a-f]\{4\}\).*/\1/p' | sort -u)
fi

# --------------------------------------------------------------------------
# Ponte de telemetria (Winecarte)
# --------------------------------------------------------------------------
# Os jogos escrevem telemetria em memoria compartilhada nomeada, e o namespace
# de objetos do wineserver e' POR PREFIXO: o jogo no Proton esta num prefixo,
# o ConspitLink noutro, e um nao ve a memoria do outro. Sem ponte, o app fica
# em "Not Started" para todo jogo desse regime.
#
# O Winecarte (https://github.com/srounce/winecarte) resolve em duas metades:
#
#   winecarte-run %command%  nas opcoes de lancamento do jogo no Steam
#                            -> EXPORTA a shm do jogo para /dev/shm
#   winehub  (aqui)          -> IMPORTA /dev/shm para dentro deste prefixo
#
# Sem a metade de cima nada chega -- esta aqui so' cobre a nossa ponta. Os
# nomes conferidos batem exatamente com os que o ConspitLink abre (AC:
# acpmf_physics/graphics/static, LMU: LMU_Data, rF2: $rFactor2SMMP_*$,
# AC EVO: acevo_pmf_*, AMS2: $pcars2$). iRacing NAO e' coberto pelo Winecarte.
#
# Opcional de proposito: sem o Winecarte instalado o app abre igual, so' sem
# telemetria de jogo. A configuracao da base, pedais e volante nao depende
# disto em nada.
ponte_pid=""
if [[ "$ponte" == "1" ]]; then
  winehub=$(command -v winehub 2>/dev/null \
            || ls "$HOME/apps/linux-simracing-utils/bin/winehub" 2>/dev/null \
            || true)
  w2l=$(command -v wine2linux.exe 2>/dev/null \
        || ls "$HOME/apps/linux-simracing-utils/bin/wine2linux.exe" 2>/dev/null \
        || true)
  if [[ -x "$winehub" && -f "$w2l" ]]; then
    WINECARTE_WINE2LINUX_EXE="$w2l" "$winehub" >"$WINEPREFIX/winehub.log" 2>&1 &
    ponte_pid=$!
    sleep 1
    if kill -0 "$ponte_pid" 2>/dev/null; then
      echo "ponte de telemetria: no ar (pid $ponte_pid)"
      echo "  lembre do outro lado: 'winecarte-run %command%' nas opcoes do jogo no Steam"
    else
      echo "ponte de telemetria FALHOU -- veja $WINEPREFIX/winehub.log" >&2
      ponte_pid=""
    fi
  else
    echo "nota: Winecarte nao encontrado; sem telemetria de jogo no app." >&2
    echo "  (a configuracao dos devices funciona normalmente sem ele)" >&2
    echo "  https://github.com/srounce/winecarte" >&2
  fi
fi

# Derruba a ponte junto com o app, inclusive se o app morrer sozinho.
# Mata pelo PID que guardamos, nunca por `pkill -f winehub`: o -f casa com
# QUALQUER linha de comando que mencione o nome -- inclusive a de outro
# consumidor legitimo (o do SimHub, que roda contra outro prefixo) e a do
# proprio shell. Ver "Cuidado ao matar processos" no CLAUDE.md.
if [[ -n "$ponte_pid" ]]; then
  trap 'kill "$ponte_pid" 2>/dev/null || true' EXIT INT TERM
fi

cd "$app"
wine ./ConspitLink2.0.exe "$@"
