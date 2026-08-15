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
