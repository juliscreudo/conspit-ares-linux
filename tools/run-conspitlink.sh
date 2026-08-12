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

cd "$app"
exec wine ./ConspitLink2.0.exe "$@"
