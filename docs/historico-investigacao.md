# Histórico da investigação — Conspit Ares no Linux

Registro cronológico de **como** cada coisa foi descoberta, incluindo os caminhos errados e
por que estavam errados. O [CLAUDE.md](../CLAUDE.md) na raiz contém só o estado atual e as
diretivas; este arquivo é a memória longa do projeto.

**Leia isto antes de reinvestigar qualquer coisa** — várias hipóteses aqui já foram testadas,
e algumas conclusões que pareciam "medidas" eram artefato de erro de método (as duas maiores:
a chave errada do winebus e a detecção de jogo "por processo").

---

## Fase 0 — Pesquisa antes de ligar o hardware (2026-08-12)

### O que se sabia do OpenFFBoard

Linux é cenário suportado upstream: https://github.com/Ultrawipf/OpenFFBoard/wiki/Linux-FFB-setup

- Usa o `hid-generic` embutido — não precisa de `hid-pidff` manual nem módulo especial.
- FFB funciona nos jogos. Limitação conhecida: "Desktop Spring" não funciona, e o indicador
  do configurador mostra "FFB 0hz" permanentemente (cosmético).
- O wiki já mandava corrigir os defaults ruins do `hid-generic` com udev (deadzone/fuzz),
  para o VID/PID stock `1209:ffb0`.
- O configurador oficial (https://github.com/Ultrawipf/OpenFFBoard-configurator, Python 3 +
  PyQt6) é multiplataforma e roda no Linux.

### As três hipóteses sobre o quanto a Conspit alterou

| hipótese | como confirmar | consequência |
|---|---|---|
| firmware stock, VID/PID `1209:ffb0` | `lsusb` | configurador oficial funciona direto |
| **firmware stock, VID/PID próprio** ✅ | `lsusb` + responde aos comandos padrão | conecta, mas sem auto-detecção |
| firmware forkado, comandos próprios | comandos padrão falham | ConspitLink necessário |

**Confirmada a segunda.** A aposta inicial ("há fork") estava errada — a classe `odrv` do
ODrive **já existe upstream** (`odrive_ui.py` no configurador oficial), então usar ODrive em
vez de TMC4671 não exigiu fork nenhum. A única divergência foi o VID/PID (`3514:0301`), que
só afeta auto-detecção.

### A estratégia proposta (e que funcionou)

1. Identificar o dispositivo (`lsusb`, interfaces, CDC?).
2. Tentar o configurador oficial nativo.
3. Falar o protocolo direto pela CDC serial (pyserial).
4. Só então considerar ConspitLink sob Wine — reaproveitando o aprendizado do projeto irmão
   (`~/apps/diy-ffb-pedal-linux/`, seção 11: registro PnP, WMI, mapeamento COM).

---

## Fase 1 — Primeira sessão com a base ligada (2026-08-12)

1. **VID/PID:** `3514:0301` (`CONSPIT ARES`). A Conspit registrou VID próprio.
2. **CDC serial: sim.** Composite device (IAD): if00/if01 CDC-ACM, if02 HID.
3. **Joystick com FFB: sim.** 40 slots de efeito, todos os condicionais. O kernel carregou
   `hid-pidff` sozinho via `hid-generic`. A regra udev é necessária e o problema é pior que
   o do wiki (ver as pegadinhas no CLAUDE.md).
4. **Configurador oficial: abre, conecta e opera** (ver abaixo).
5. **Protocolo: responde.** `sys.0.id?` não existe (não é comando do OpenFFBoard), mas
   `sys.0.help`, `sys.0.swver?`, `axis.0.power?` etc. respondem no formato documentado.

### Identidade do firmware

| campo | valor |
|---|---|
| `sys.0.swver?` | `1.15.0` |
| `sys.0.hwtype?` | `F407VG` (a placa de referência do OpenFFBoard) |
| `main.0` | `FFB Wheel (1 Axis)` |
| `axis.0.drvtype?` | `5` (ODrive) |

Classes ativas (`sys.0.lsactive?`):

```
Can port:can:0:3073:1      Can port:can:0:3073:2      FFB Wheel (1 Axis):main:0:1:3
System Commands:sys:0:16:4 CAN Analog:cananalog:0:66:5 Effects:fx:0:2562:6
Axis:axis:0:2561:7         ODrive (M0):odrv:0:133:8
```

Os class IDs batem com os documentados. O descritor HID de 1252 bytes traz a PID usage page
completa **e** a página vendor-defined com report ID `0xA1` — exatamente a interface de
comandos por HID do wiki.

Na época, `main.0.btntypes?` = `32` (bit 5) indicava uma fonte de botões ativa que
`main.0.lsbtn?` não enumerava — possivelmente o rim via CAN. Não é o H.AO (que entra como
device USB próprio).

### O configurador OpenFFBoard oficial — validado, depois removido do repo

Foi montado e **funcionou**: conectou na base, detectou-a e operou. As ferramentas foram
removidas do repo por decisão do usuário quando o ConspitLink passou a cobrir a configuração
sob Wine. Não estão em nenhum commit (o commit foi reescrito para remover o serial da base),
mas nada se perdeu — o upstream é público e os três ajustes necessários foram:

1. Registrar `3514:0301` em `SerialChooser.OFFICIAL_VID_PID` (`serial_ui.py`) — sem isso a
   base aparece como "Unsupported device"; conectar manualmente sempre funcionou.
2. Tornar `helper.classlistToIds` tolerante: este firmware responde `main.0.lsbtn?` com `OK`
   em vez de lista, e o parser upstream estoura `ValueError`. Bug do upstream.
3. Absorver uma corrida em `SerialComms.processMatchedReply` (`KeyError` no dispatch).
   Também bug do upstream. Os itens 2 e 3 valem como PR upstream.

**Valor que sobra:** é a prova de que a base é OpenFFBoard de verdade, e o plano B se o
ConspitLink quebrar.

### Primeiras horas do ConspitLink sob Wine

Instalador NSIS de 300 MB, EV-signed pela entidade legal da Conspit
(恩速（上海）电子科技有限公司). Confirmado na GUI em 2026-08-12:

- ✅ Telemetria ao vivo (`Force State`, torque, temperaturas de fase e MOS).
- ✅ Escrita em tempo real: Max Force refletindo na base na hora; Power On/Off.
- ✅ Presets, seleção de jogo, High Torque Mode.
- ❌ Ângulo do volante travado em `+0.00°` → virou a investigação abaixo.

**Medido, não suposto:** antes do nó PnP da serial, os file descriptors do processo não
continham device nenhum (só GPU) — o app lia o nome "CONSPIT ARES" da própria config, não do
hardware. Depois do nó, o `ttyACM` da base aparece aberto pelo processo.

---

## O ângulo travado em +0.00° — a conclusão errada que durou três dias

> ⚠️ **A conclusão desta investigação estava errada, e vale entender por quê.** A cadeia é
> boa e as medições são válidas — mas ela *pressupunha* que o device HID que o app via era o
> device real. Não era: o Wine entregava um device sintetizado pelo SDL, **sem a collection
> vendor**. A linha do `DisableInput` foi escrita na chave errada e nunca surtiu efeito, o
> que fechou prematuramente justamente a hipótese certa. Lição: **antes de concluir "é bug
> do app", confirme o que o app enxerga** — `tools/hidenum.c` responde isso em segundos.

Cadeia de eliminação original, toda com medição:

| hipótese | teste | resultado |
|---|---|---|
| base em falha / sem energia | `odrv.0.vbus?`, `errors?`, `estop?` pela serial | 47,5 V, zero erro, encoder vivo |
| posição não chega ao kernel | `tools/hid_watch.py` girando o volante | 10111 eventos evdev, faixa cheia ±32767 |
| posição não está no HID | idem, lado hidraw | **report ID 1, bytes 18–19**, 695/s |
| falta calibrar o centro | botão `Center Calibration` na GUI | não mudou nada |
| Wine cria device HID duplicado | `DisableInput=1` no winebus | **não ajudou** — `event*` continua aberto *(inválido: chave errada)* |
| Wine não entrega o eixo | `wine control joy.cpl`, aba DInput | eixo X acompanha o volante |
| app não lê o eixo | `WINEDEBUG=+dinput` | 1534 `GetDeviceState` em 20 s |
| ângulo vem pela serial | lista completa de comandos do app | nenhum comando de posição existe |

**Conclusão da época (errada):** defeito dentro da lógica do ConspitLink
(`AresApexManger::Base_Angle`). **Conclusão real:** o app lia o `DIJOYSTATE2` de um device
sintético, e o canal por onde o firmware manda a posição (collection vendor `0xA1`) não
existia no prefixo. As duas linhas de trace que teriam entregado o caso de imediato:

```
WINEDEBUG=+hid   ->  ignoring hidraw device 3514:0301 with usages 0001:0004
                     creating non-hidraw device 3514:0301 with usages 0001:0004
```

Se algum dia só o número interessar: `axis.0.pos?` / `axis.0.curpos?` pela serial, ou os
bytes 18–19 do report ID 1.

---

## Fase 2 — A saga do udev e dos pedais (2026-08-14)

### Regra única para todos os devices Conspit

`udev/70-conspit.rules` substituiu `70-conspit-ares.rules` + `99-conspit.rules` +
`99-conspit-cpp.rules` — as duas `99-` estavam **parcialmente quebradas pelo prefixo**.

Medições que fundamentaram (via `udevadm test` + `getfacl`):

- Em `99-`, o `TAG+="uaccess"` é **inerte** — a tag aparece em `CURRENT_TAGS` mas o ACL
  nunca é aplicado (o `event*` dos pedais ficou sem ACL).
- O `ENV{ID_INPUT_JOYSTICK}="1"` em `99-` funciona **parcialmente**: fica no banco do udev e
  é lido por quem consulta depois (SDL), mas chega tarde para `60-persistent-input`
  (symlink) e `70-uaccess` (ACL). Apagar a regra legada sem replicar a atribuição
  **regride** a enumeração dos pedais nos jogos.

### Pedais CPP.LITE — o que foi medido

`3514:0005`. Descritor HID de 88 bytes com duas collections na mesma interface USB; o kernel
cria **dois** input devices:

| collection | conteúdo | vira | `capabilities/abs` |
|---|---|---|---|
| `Usage(Joystick)`, report ID 1 | 3 eixos de 12 bits (Rx, Y, Z) | os três pedais | `e` |
| `Usage(Counted Buffer)`, report ID 2 | 63 bytes vendor | um `ABS_MISC` inútil | `10000000000` |

Fatos medidos que viraram as diretivas do CLAUDE.md: o `by-id` aponta para o canal vendor
(a última collection processada vence o nome do symlink); o `input_id` não classifica os
pedais (sem botões); `ATTRS{}` múltiplos precisam casar no mesmo device da cadeia (custou
uma rodada: a seção 3 da regra instalava, `udevadm verify` passava, e ela simplesmente não
fazia nada); e o `check-setup.sh` chegou a mandar `sudo rm` numa regra dos pedais por casar
`*conspit*` em bloco.

### O shim de uhid (2026-08-14) — construído e aposentado em 24 h

Para expor a 2ª collection dos pedais ao app (que o Wine então escondia), foi construído o
`tools/cpp_hid_shim.py`: 492 linhas de MITM via `/dev/uhid`, com joystick virtual para
corrigir a ordem dos eixos, keepalive, semeadura de posição e regra própria de acesso
(`70-uhid-shim.rules`, uma concessão de segurança real no Wayland).

Funcionou — detecção, haptics, curvas e captura de protocolo passaram a operar — e foi
**inteiramente aposentado no dia seguinte** pela descoberta do backend hidraw (abaixo).
O código está preservado nos commits `ec0ad06`..`1e29b84`.

A captura com o shim (`--capturar`) foi o que mapeou o protocolo `$` dos pedais
([protocolo-cpp-lite.md](protocolo-cpp-lite.md)) — esse produto sobreviveu ao shim.

---

## Fase 3 — O backend do winebus: a descoberta que reorganizou o projeto (2026-08-15)

**Uma linha de registro na chave certa substituiu 492 linhas de shim, uma concessão de
segurança e três "pendências do app".**

### A causa raiz

O `winebus.sys` lê as opções em `Services\winebus` (comentário `@@ Wine registry key` no
próprio código). Este projeto escrevia em `Services\winebus\Parameters` — subchave que o
driver **nunca consulta**. Todas as opções eram ignoradas em silêncio, e o backend continuava
no SDL.

Isso invalidou quatro conclusões registradas como "medidas":

| o que se afirmava | o que era de verdade |
|---|---|
| "`Enable SDL=0` configurado" | nunca leu; o SDL estava ativo e fabricava os joysticks |
| "`DisableInput=1` não ajudou, `event*` continua aberto" | nunca leu; o `event*` aberto era do próprio SDL |
| "`EnableHidraw=3514:0005` não muda o backend" | nunca leu; o formato estava **certo** o tempo todo |
| "o setup configurou o hidraw para a telemetria" | a telemetria do `0300` já vinha por hidraw **por default** (usage vendor) — era no-op |

Foi por olhar o canal de debug errado (`+plugplay`, e os fds do `winedevice`) que a medição
de 14/08 concluiu errado — as decisões de backend saem em `WINEDEBUG=+hid`.

### O antes e depois, medido com `hidenum` dentro do prefixo

```
ANTES (backend SDL)                              DEPOIS (backend hidraw)
3514:0005 usage 0x04 in 7                        3514:0005 &Col01 usage 0x04 in 19
                                                 3514:0005 &Col02 usage 0x3A in 64 out 64
3514:0007 usage 0x04 in 26                       3514:0007 &Col01 usage 0x04 in 52
                                                 3514:0007 &Col02 usage 0x3A in 64 out 64
3514:0300 usage 0x01 in 64                       3514:0300        usage 0x01 in 64 out 64
3514:0301 usage 0x04 in 28                       3514:0301 &mi_02 usage 0x04 in 64 out 25
```

O hidclass do Wine separa as top-level collections em PDOs `&Col01`/`&Col02`, como o
Windows. O problema que motivou o shim inteiro não existia nesta versão do Wine — só estava
desligado por política.

### O que a descoberta aposentou

| removido | por quê |
|---|---|
| `tools/cpp_hid_shim.py` (492 linhas) | o Wine já entrega as duas collections |
| `udev/70-uhid-shim.rules` | a concessão de `/dev/uhid` deixou de ser necessária |
| joystick virtual + `--sem-eixos` | o app lê os eixos reais, na ordem do descritor |
| `HKCU\...\DirectInput\Joysticks = disabled` | não há mais device duplicado a esconder |
| `--capturar` do runner | captura agora é por usbmon |

### Pendências que morreram juntas

- **Ângulo da base em `+0.00°`** — o app via o device do SDL, sem a collection vendor por
  onde o OpenFFBoard manda as notificações HID. Não era `AresApexManger::Base_Angle`.
- **Barra dos pedais saturando em ~16384** — era o app interpretando a escala sintética do
  SDL; com o descritor real de 12 bits o valor sai certo.
- **Rótulos dos pedais rotacionados** — o Wine não sintetiza mais o device a partir do
  evdev, então a ordenação por código de eixo deixou de existir; vale a ordem do descritor.

### Epílogo: a diretiva do `Enable SDL=0` também estava errada (2026-08-15, noite)

Ao investigar por que o **SimHub** não enxergava o volante H.AO, apareceu um fato
incômodo: o prefixo dele **já tinha `Enable SDL=0` na chave certa** e mesmo assim os
devices saíam sintetizados.

O CLAUDE.md afirmava, com trecho de código junto, que `Enable SDL=0` sozinho bastava porque
"SDL desligado também desliga o evdev". O raciocínio estava **invertido**:

```c
if (!sdl_driver_init()) options.disable_input = TRUE;
```

`sdl_driver_init()` devolve `STATUS_SUCCESS` (=0) quando dá certo — então o `!` liga o
`disable_input` quando o SDL **funciona** (para não duplicar device). Com `Enable SDL=0` a
função devolve `STATUS_NOT_SUPPORTED` (≠0), o `disable_input` fica FALSE, e o backend evdev
continua sintetizando.

Experimento controlado no prefixo do ConspitLink, com `hidenum` a cada passo:

| configuração | resultado |
|---|---|
| `EnableHidraw` + `Enable SDL=0` (o que estava em uso) | devices reais (`0x04` + `0x3A`) |
| só `Enable SDL=0` | **sintetizados** (`usage 0x05`, `out 0`, sem canal vendor) |
| `Enable SDL=0` + `DisableInput=1` | devices reais, **sem precisar da lista** |

Ou seja: quem sempre fez o trabalho foi a **lista `EnableHidraw`**; a rede de segurança
existe, mas exige **os dois** valores. O `DisableInput` chegou a estar na lista de "não
reintroduzir" — herança da época em que era escrito na subchave `Parameters` e portanto
nunca havia sido testado de fato.

Correção aplicada em `conspit_wine_setup.py` (passa a escrever os três valores),
`check-setup.sh` (verifica os três, e avisa se a rede de segurança estiver pela metade),
`run-conspitlink.sh` (o pre-flight passa a olhar o `EnableHidraw`) e no CLAUDE.md.

**Padrão que se repete neste projeto:** a conclusão errada não veio de má medição, veio de
ler o código com o sinal trocado e nunca testar a hipótese isoladamente. As duas vezes que
isso aconteceu (a chave `Parameters`, e agora o `Enable SDL`), o desempate foi o mesmo:
mudar **uma** variável por vez e medir com o `hidenum`.

### SimHub e o H.AO — resolvido pela mesma correção

Com `EnableHidraw` gravado no prefixo do SimHub e o wineserver reiniciado, o volante passa a
expor as duas collections lá também:

```
3514:0007 usage 0x04 in 52 out 11    joystick
3514:0007 usage 0x3A in 64 out 64    canal vendor -- e' por aqui que os LEDs sao escritos
```

Antes: `usage 0x05, in 26, out 0` — sem canal vendor e sem nenhum output report, ou seja,
sem como escrever LED. A parte do SimHub (perfis, telemetria) é território do
linux-simracing-utils; o que faltava era o Wine entregar o device real.

### Validação na GUI (2026-08-15)

- Base: ângulo em tempo real (`-449.31°` na tela com o volante girado).
- Pedais: telemetria idêntica à do Windows; haptics `Customize` OK; acelerador calibrado
  pela GUI com gráfico fluido.
- Volante H.AO: tudo operante **no primeiro dia em que foi ligado**, sem uma linha de
  código específica. Os 6 paddles são Hall (por isso eixos) e calibram corretamente.
- `check-setup.sh`: 0 falhas, 0 avisos.

### O volante H.AO (`3514:0007`)

Apareceu no barramento em 2026-08-15. Mesma estrutura de duas collections dos pedais,
firmware `V1.78`. Não precisou de tratamento especial: **tem botões**, então o `input_id`
classifica sozinho e o `by-id` sai correto. Precisou só da correção de fuzz/flat (7 eixos
analógicos, todos ruins — hoje coberta pela linha genérica por vendor da regra).

A descoberta de que ele expõe **CDC serial própria** foi o que levou o
`conspit_wine_setup.py` a selecionar a porta da base **pelo PID** — até então acertava por
acidente da ordem alfabética (`ARES` < `H.AO`).

---

## Fase 4 — Telemetria de jogo (2026-08-15)

### A correção: a detecção NÃO é enumeração de processos

A análise inicial viu os imports `CreateToolhelp32Snapshot`/`OpenProcess` e concluiu que o
app detectava o jogo varrendo processos — e que detecção e telemetria seriam problemas
**separados**. Errado: os símbolos do `.pdb` mostram `GanmeOf<Jogo>::Get_GameStatus` (o typo
é deles) ao lado de `Get_InitSuccess` e `GameData::Slot_initShareMemory`. **A detecção é o
próprio attach à memória compartilhada** — as duas coisas se resolveram juntas.

Lição de método: um import presente não prova que é o mecanismo usado; o `.pdb` respondia
isso o tempo todo. E: o app é Qt — as strings estão em **UTF-16**, `strings` sem `-el` não
acha nenhum nome de mapa (quase levou à conclusão errada de que os nomes não batiam).

### O que também caiu

- "Testar um jogo UDP primeiro" não era testável: a biblioteca do usuário (AC, iRacing,
  LMU) é inteiramente de memória compartilhada.
- Rodar o ConspitLink **dentro** do prefixo do Proton (com os riscos do `pressure-vessel`)
  não foi necessário — o Winecarte replica a shm entre prefixos.

### Validação (Le Mans Ultimate)

`Select Game` foi de `Not Started` para `Started`; haptics `Customize` vibrando conforme o
efeito; dash / rev lights do volante recebendo dados. Duas pontes: `winecarte-run %command%`
no jogo (exporta para `/dev/shm`) e `winehub` contra o prefixo do ConspitLink (importa) —
esta metade o `run-conspitlink.sh` sobe sozinho.

O app também não achava os jogos **instalados**: lê `HKCU\SOFTWARE\Valve\Steam\SteamPath` e
o `libraryfolders.vdf`, que não existem num Linux com Steam nativo — e apontar direto não
basta, porque os caminhos dentro do vdf são Linux absolutos. Daí o `C:\SteamBridge` que o
setup monta (vdf reescrito para `Z:` + symlink do `steamapps`).

---

## Fase 5 — Reorganização do repo (2026-08-15, mesma noite)

- Prefixo Wine saiu do repo (876 MB; `git clean -xfd` apagava a configuração) para
  `~/.local/share/conspit-ares-linux/prefix`, com override `$CONSPIT_PREFIX`. O `~/.wine`
  compartilhado foi analisado e rejeitado: `Enable SDL=0` vale para o prefixo inteiro e
  quebraria outros apps (a máquina tem drivers AX206/VOCORE lá). De passagem, o resto de uma
  instalação antiga e quebrada do ConspitLink no `~/.wine` (180 KB, sem `.exe`) foi removido.
- Licença GPL-3.0 (traduzindo o desejo "usar e forkar, mas não vender" sem os custos de uma
  licença não-comercial, que não é open source pela OSI).
- Atalho `.desktop` próprio (`tools/instalar-atalho.sh`) apontando para o runner — o do
  `winemenubuilder` executa o `.lnk` direto e pula os pre-flights.
- A regra de fuzz/flat virou **uma linha por vendor** (era uma por PID); a linha genérica
  vem por último no arquivo porque os devices sem botão só viram "joystick" na seção 3.
- Mapeamento COM duplicado (com33 + com34 para a mesma base) investigado e documentado como
  esperado e inofensivo — só a COM33 tem nó PnP com VID/PID.
- README reestruturado para replicação por terceiros; `docs/adicionar-dispositivo.md`
  criado para os periféricos não testados.
