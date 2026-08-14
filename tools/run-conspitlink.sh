#!/usr/bin/env bash
# Abre o ConspitLink 2.0 no prefixo Wine isolado deste projeto.
#
#   tools/run-conspitlink.sh          abre o app
#   tools/run-conspitlink.sh --limpo  derruba o Wine antes de abrir
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

if [[ "${1:-}" == "--limpo" ]]; then
  echo "derrubando o Wine deste prefixo..."
  pkill -x "ConspitLink2.0." 2>/dev/null || true
  sleep 1
  wineserver -k 2>/dev/null || true
  sleep 2
fi

# Shim dos pedais CPP.LITE: sem ele o app nao enxerga a pedaleira sob Wine
# (o Wine expoe so a 1a top-level collection do descritor -- ver a secao
# "Pedais CPP.LITE" no CLAUDE.md). Sobe junto e cai junto; se os pedais nao
# estiverem ligados, nao faz nada.
shim_pid=""
if lsusb 2>/dev/null | grep -qi '3514:0005'; then
  if pgrep -f 'cpp_hid_sh[i]m' >/dev/null; then
    echo "shim dos pedais: ja estava rodando"
  elif [[ -w /dev/uhid ]]; then
    python3 -u "$repo/tools/cpp_hid_shim.py" >"$WINEPREFIX/cpp_hid_shim.log" 2>&1 &
    shim_pid=$!
    sleep 2
    if kill -0 "$shim_pid" 2>/dev/null; then
      echo "shim dos pedais: no ar (pid $shim_pid)"
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
