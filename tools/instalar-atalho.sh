#!/usr/bin/env bash
# Instala (ou remove) o atalho do ConspitLink no menu de aplicativos.
#
#   tools/instalar-atalho.sh              instala
#   tools/instalar-atalho.sh --remover    desinstala
#
# POR QUE UM ATALHO PROPRIO, SE O WINE JA CRIA UM
# O winemenubuilder gera sozinho um .desktop em
# ~/.local/share/applications/wine/Programs/Conspit Link 2.0/, mas ele executa
# o .lnk direto -- pulando o tools/run-conspitlink.sh e portanto:
#
#   - a verificacao de que o winebus esta no backend hidraw (sem ela o app
#     abre mas nao lista os canais vendor: falha confusa);
#   - o aviso de device Conspit fora da lista EnableHidraw;
#   - a ponte de telemetria (winehub), que o runner sobe e derruba junto.
#
# Alem disso o winemenubuilder SOBRESCREVE o proprio arquivo a cada
# reinstalacao do app. Por isso o nosso mora fora daquela pasta, com nome
# proprio (conspit-link.desktop): assim ele nunca e' tocado.
set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icones="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor"
alvo="$apps/conspit-link.desktop"
icone_nome="conspit-link"

atualizar_cache() {
  command -v update-desktop-database >/dev/null \
    && update-desktop-database "$apps" 2>/dev/null || true
  command -v gtk-update-icon-cache >/dev/null \
    && gtk-update-icon-cache -f -t "$icones" 2>/dev/null || true
}

if [[ "${1:-}" == "--remover" ]]; then
  rm -f "$alvo"
  find "$icones" -name "$icone_nome.png" -delete 2>/dev/null || true
  atualizar_cache
  echo "atalho removido."
  exit 0
fi

[[ -x "$repo/tools/run-conspitlink.sh" ]] || {
  echo "run-conspitlink.sh nao encontrado em $repo/tools/" >&2
  exit 1
}

# 1. Icone. O winemenubuilder ja extraiu um do .exe ao instalar; reaproveitar
#    evita depender do icoutils. O nome dele carrega um numero gerado
#    (ex.: 4796_ConspitLink2.0.0.png), entao procuramos por padrao.
echo "1. Icone..."
achou_icone=""
for tam in 128x128 64x64 48x48 32x32 256x256; do
  origem=$(find "$icones/$tam/apps" -iname "*ConspitLink*.png" 2>/dev/null | head -1)
  [[ -n "$origem" ]] || continue
  mkdir -p "$icones/$tam/apps"
  cp -f "$origem" "$icones/$tam/apps/$icone_nome.png"
  achou_icone="$tam"
done

if [[ -n "$achou_icone" ]]; then
  echo "   reaproveitado do Wine (maior: $achou_icone)"
  icone="$icone_nome"
else
  # Sem icone extraido: cai para um generico do tema, que sempre existe.
  echo "   nenhum icone do Wine encontrado; usando um generico"
  echo "   (reinstalar o app no prefixo faz o Wine extrair o oficial)"
  icone="input-gaming"
fi

# 2. O .desktop.
#    StartupWMClass casa a janela do Wine com este lancador -- sem ele a
#    barra de tarefas mostra um icone generico separado quando o app abre.
echo "2. Atalho..."
mkdir -p "$apps"
cat > "$alvo" <<DESKTOP
[Desktop Entry]
Type=Application
Name=ConspitLink 2.0
GenericName=Conspit wheelbase configuration
Comment=Configura base, pedais e volante Conspit (via Wine)
Exec=$repo/tools/run-conspitlink.sh
Path=$repo
Icon=$icone
Terminal=false
# Uma unica categoria principal (Settings). Com "Game;Settings;" o
# desktop-file-validate avisa que o app pode aparecer DUAS vezes no menu.
Categories=Settings;HardwareSettings;
Keywords=conspit;ares;wheelbase;simracing;ffb;racing;
StartupNotify=true
StartupWMClass=conspitlink2.0.exe
DESKTOP
chmod +x "$alvo"
echo "   $alvo"

# 3. O atalho que o Wine gerou aponta para o .lnk e pula os pre-flights.
#    Nao apagamos (e' do winemenubuilder, ele o recria), so' avisamos.
wine_desktop="$apps/wine/Programs/Conspit Link 2.0"
if [[ -d "$wine_desktop" ]]; then
  echo
  echo "nota: o Wine tem um atalho proprio em"
  echo "  $wine_desktop"
  echo "  ele funciona, mas pula as verificacoes e a ponte de telemetria."
  echo "  para escondê-lo do menu:"
  echo "    rm -rf \"$wine_desktop\""
fi

atualizar_cache
echo
echo "pronto -- procure por 'ConspitLink' no menu de aplicativos."
