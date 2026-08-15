# Resolve o prefixo Wine deste projeto. Para ser incluido com `.`, nao executado.
#
#   . "$repo/tools/conspit-prefixo.sh"     # define WINEPREFIX
#
# Ordem: $CONSPIT_PREFIX  ->  $XDG_DATA_HOME/conspit-ares-linux/prefix
#                             (XDG_DATA_HOME default: ~/.local/share)
#
# POR QUE UM PREFIXO DEDICADO, E NAO O ~/.wine PADRAO
# O `Enable SDL=0` que o tools/conspit_wine_setup.py escreve vale para o
# PREFIXO INTEIRO -- e' ele que faz o winebus entregar o descritor HID real
# (canais vendor dos pedais, do volante e a collection de comandos da base).
# Num prefixo compartilhado, todo outro app Windows dali perderia a
# enumeracao de controle por SDL. Nesta maquina, por exemplo, o ~/.wine tem
# os drivers AX206 e VOCORE. O isolamento aqui e' o que torna o ajuste
# seguro, nao burocracia.
#
# POR QUE FORA DO REPO
# O prefixo passa de 870 MB. Dentro do repo, um `git clean -xfd` -- comando
# corriqueiro -- apagava tudo, incluindo a calibracao ja feita.

: "${XDG_DATA_HOME:=$HOME/.local/share}"
WINEPREFIX="${CONSPIT_PREFIX:-$XDG_DATA_HOME/conspit-ares-linux/prefix}"

# Ate 2026-08-15 o prefixo ficava em <repo>/.wine-conspitlink. Se alguem
# atualizar o repo com o prefixo antigo no lugar, avisa em vez de criar um
# segundo prefixo vazio e "perder" a configuracao em silencio.
if [[ -d "${repo:-}/.wine-conspitlink" && ! -d "$WINEPREFIX" ]]; then
  echo "AVISO: achei um prefixo no local ANTIGO (<repo>/.wine-conspitlink)." >&2
  echo "  o projeto agora usa: $WINEPREFIX" >&2
  echo "  mova-o para nao perder a configuracao ja feita:" >&2
  echo "    mkdir -p \"$(dirname "$WINEPREFIX")\"" >&2
  echo "    mv \"${repo}/.wine-conspitlink\" \"$WINEPREFIX\"" >&2
  echo "  (ou aponte para ele com CONSPIT_PREFIX=...)" >&2
fi
