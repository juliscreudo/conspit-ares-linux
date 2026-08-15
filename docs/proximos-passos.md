# Pendências

Atualizado em **2026-08-15**, depois da rodada que executou o plano original (os seis pontos
de análise estão resolvidos ou descartados; o registro do que foi feito está no
[historico-investigacao.md](historico-investigacao.md), Fase 5, e no `git log`).

## Pendente

### 1. README em inglês

Decisão tomada: **sim, ao final dos ajustes**. O README em PT-BR foi reestruturado para
replicação (2026-08-15); falta a versão em inglês — a comunidade sim-racing/Linux é
majoritariamente internacional, e esta é provavelmente a mudança de maior alcance do
projeto. Manter CLAUDE.md e `docs/` em português.

### 2. `tools/Makefile`

Pequeno: um alvo para os dois `.c` (`hidenum.c`, `dinput_axes.c`), cujo comando de
compilação hoje só existe no cabeçalho de cada arquivo. (Da análise de reorganização do
`tools/` — o resto foi avaliado e **descartado de propósito**: 12 arquivos numa pasta plana
são navegáveis, e mover quebraria dezenas de referências na documentação.)

### 3. Push inicial + varredura de dados sensíveis

Os commits estão todos locais. Antes do primeiro push: varrer o **histórico inteiro** (não
só os diffs) por serial da base, e-mail, caminhos pessoais que não deveriam vazar.

### 4. SimHub enxergar o H.AO (LEDs por telemetria)

O SimHub (sob Wine, via linux-simracing-utils) tem perfil para o `Conspit H.AO HUB (LEDs
and buttons only)`, mas fica em `Searching device...` — não acha o volante.

**Diagnóstico já feito (2026-08-15, `hidenum` no prefixo do SimHub):** o canal vendor de
64 bytes do H.AO (usage `0x3A`, por onde os LEDs são escritos) **não existe naquele
prefixo** — os devices aparecem como gamepad sintetizado (usage `0x05`, `out 0` em todos).
É a mesma classe de problema que o ConspitLink tinha antes do backend hidraw.

Curioso: aquele prefixo já tem `Enable SDL=0` na chave certa, e ainda assim os devices
saem sintetizados. Hipóteses: o wineserver de lá está no ar desde antes da opção valer, ou
falta o `EnableHidraw`. Decidir exige **reiniciar o wineserver do SimHub** (mata a sessão)
e medir de novo com `hidenum` — 10 minutos, quando for conveniente.

**Divisão de escopo:** fazer o Wine entregar o canal HID real ao SimHub é know-how DESTE
projeto (mesma receita: `EnableHidraw` + restart; o ACL de hidraw a nossa regra udev já dá
para a máquina toda). Os perfis de LED e a telemetria dentro do SimHub são território do
SimHub/linux-simracing-utils — fora do escopo daqui.

## Aberto, sem prioridade definida

- **iRacing sem telemetria** — o Winecarte não exporta o mapa dele. Se alguém atacar:
  `Local\IRSDKMemMapFileName` + `Local\IRSDKDataValidEvent` + `IRSDK_BROADCASTMSG`.
  Contribuição natural para o upstream (https://github.com/srounce/winecarte).
- **ETS2/ATS** — o app abre `Local\SCSTelemetry`, o Winecarte exporta `Local\SHSCSTelemetry`
  (prefixo `SH`). Divergência anotada, não testada.
- **Jogos UDP** (F1, DiRT 2.0, EA WRC, Forza) — devem funcionar sem ponte (UDP para
  `127.0.0.1`); nenhum instalado nesta bancada. O usuário cogitou instalar um Forza para
  validar; não prioritário.
- **Canal vendor do H.AO** — protocolo não mapeado (rota: usbmon, ver CLAUDE.md "Captura de
  protocolo").
- **PRs upstream para o OpenFFBoard-configurator** — os dois bugs genéricos encontrados em
  2026-08-12 (parser do `lsbtn` e corrida no `processMatchedReply`; ver histórico, Fase 1).
