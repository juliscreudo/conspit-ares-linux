# Conspit Ares Platinum 20Nm no Linux — análise e ferramentas

Repo deste projeto: `~/apps/conspit-ares-linux/`.

**Projeto irmão, separado de propósito:** `~/apps/diy-ffb-pedal-linux/` (pedal ativo DIY FFB
do ChrGri). Hardware, fabricante, protocolo e upstream diferentes — por isso repos
distintos. Mas o aprendizado de **Wine + serial** de lá é diretamente reaproveitável aqui se
a rota do ConspitLink sob Wine for necessária; ver a seção 11 do CLAUDE.md daquele projeto
antes de reinvestigar qualquer coisa de Wine/WMI/porta COM.

## Objetivo
Usar a base Conspit Ares Platinum 20Nm plenamente no Linux — configuração e telemetria —
sem depender do Windows. O objetivo declarado pelo usuário foi "fazer o ConspitLink abrir e
conectar à base, como no Windows". **Mas o resultado preferível pode ser não precisar dele**
(ver "Estratégia" abaixo).

## Hardware / contexto
- Base: **Conspit Ares Platinum, 20 Nm**.
- Bancada completa (VID `3514`): base `0301` + 2º MCU `0300` (hub interno da base),
  pedais **CPP.LITE** `0005`, volante **H.AO** `0007`. Todos atendidos pelo mesmo app.
- Por baixo: firmware **OpenFFBoard** (https://github.com/Ultrawipf/OpenFFBoard,
  https://hackaday.io/project/163904-open-ffboard) + controladora de motor **ODrive**.
- Software oficial do fabricante: **ConspitLink** (proprietário, Windows), usado para
  configuração e telemetria. Firmware e o Link 2.0 são distribuídos pelo site da Conspit.
- ✅ **Confirmado no hardware em 2026-08-12** (primeira sessão com a base ligada). Ver
  "Resultados da primeira sessão" no fim deste arquivo. O que estava certo: é OpenFFBoard
  de verdade, com ODrive, falando o protocolo documentado. O que estava errado: **não há
  fork relevante** — é firmware 1.15.0 essencialmente stock, só com VID/PID próprio.

## O que já se sabe do OpenFFBoard (pesquisa, 2026-08-12)

### Linux é cenário suportado upstream
Existe página oficial de setup: https://github.com/Ultrawipf/OpenFFBoard/wiki/Linux-FFB-setup

- Usa o **`hid-generic`** embutido — não precisa de `hid-pidff` nem módulo especial.
- **FFB funciona nos jogos.** Limitação conhecida: "Desktop Spring" não funciona, e o
  indicador do configurador mostra "FFB 0hz" permanentemente (cosmético, sem efeito no jogo).
- O `hid-generic` aplica defaults ruins (deadzone e fuzz = 255); corrige-se com udev:

```
SUBSYSTEM=="input", ATTRS{idVendor}=="1209", ATTRS{idProduct}=="ffb0",
RUN+="/usr/bin/evdev-joystick --s '%E{DEVNAME}' --f 0 --d 0"
```
(pacote `joyutils`; salvar em `/etc/udev/rules.d/98-openffboard.rules`, depois
`udevadm control --reload-rules && udevadm trigger`)

- **VID/PID stock: `1209:ffb0`** (`1209` é o VID compartilhado do pid.codes).

### O configurador oficial é multiplataforma
https://github.com/Ultrawipf/OpenFFBoard-configurator — **Python 3 + PyQt6**, open source.
Dependências: PyQt6, PyQt6-Charts, pyusb, intelhex (libusb só para DFU). Roda no Linux.
Detecta dispositivos compatíveis pelo VID/PID (destaca em verde os que batem).

### O protocolo de comandos é texto e está documentado
https://github.com/Ultrawipf/OpenFFBoard/wiki/Commands

Sistema unificado de comandos exposto em **CDC serial, HID e UART**. Formato texto:

```
cls.(instance.)cmd?          consulta        → resposta  [cls.instance.cmd?|val]
cls.(instance.)cmd?adr       consulta em endereço
cls.(instance.)cmd=val       escreve         → resposta  [cls.instance.cmd=val|OK]
cls.(instance.)cmd!          info
```

Exemplos reais: `axis.0.power?`, `axis.0.power=1337`, `sys.0.save`, `tmc.0.calibrate`.
Valores aceitam hexadecimal com prefixo `x` (`x4d2`) ou base 10.

Endereçamento: **Class ID** (16 bits, ex.: `0x0` system, `0xA01` axis, `0x81` TMC4671),
**Instance** (8 bits, normalmente 0), **Command ID** (32 bits).

**Baudrate no CDC é irrelevante** — transmite na velocidade máxima, ignora a configuração.
(Contraste importante com o pedal DIY, onde o baud errado era *a* causa raiz. Aqui esse
problema não existe por construção.)

Há também interface de comandos por **HID**, com relatórios vendor-defined (report ID
`0xA1`), campos binários, mesma estrutura class/instance/command. Tipos de relatório:
write(0), request(1), info(2), writeAddr(3), requestAddr(4), ACK(10), notification(14),
error(15). Só funciona quando a interface HID está ativa e configurada — por padrão
principalmente para a classe FFB.

## Estratégia proposta (ordem de tentativa)

O cenário é **muito melhor** que o do pedal DIY: protocolo documentado, configurador oficial
open source e multiplataforma, e Linux já suportado upstream. Não há engenharia reversa de
struct binária a fazer.

1. **Identificar o dispositivo.** `lsusb`, interfaces expostas (HID? CDC?), se aparece
   `/dev/ttyACM*`, VID/PID reais. Isto decide tudo o que vem depois.
2. **Tentar o configurador oficial nativo.** Se a Conspit manteve o protocolo, pode
   simplesmente funcionar — e aí o ConspitLink vira desnecessário.
3. **Falar o protocolo direto**, se o configurador não abrir: mandar `sys.0.id?` etc. na
   CDC serial e ver o que responde. Trivial com pyserial, sem GUI nenhuma.
4. **Só então** considerar ConspitLink sob Wine — e aí o conhecimento do projeto do pedal se
   aplica (registro PnP, WMI, mapeamento COM).

### As três hipóteses sobre o quanto a Conspit alterou

| hipótese | como confirmar | consequência |
|---|---|---|
| firmware stock, VID/PID `1209:ffb0` | `lsusb` | configurador oficial deve funcionar direto |
| **firmware stock, VID/PID próprio** ✅ | `lsusb` + responde aos comandos padrão | conecta, mas sem auto-detecção; ajuste pequeno |
| firmware forkado, comandos próprios | comandos padrão falham ou faltam classes | ConspitLink pode ser necessário para features específicas |

**Confirmado: a segunda hipótese.** A aposta inicial ("há fork") estava errada — a classe
`odrv` do ODrive **já existe upstream** (`odrive_ui.py` no configurador oficial), então usar
ODrive em vez de TMC4671 não exigiu fork nenhum. A única divergência encontrada foi o
VID/PID (`3514:0301` em vez de `1209:ffb0`), que só afeta auto-detecção.

## Checklist da primeira sessão com o hardware

Rodar com a base **conectada por USB**:

```
lsusb                                  # VID:PID
ls -l /dev/serial/by-id/ /dev/ttyACM*  # existe interface CDC?
ls -l /dev/input/by-id/                # aparece como joystick?
ls -l /dev/hidraw*
udevadm info -q property -n /dev/...   # ID_VENDOR_ID, ID_MODEL_ID, ID_SERIAL
dmesg | tail -40                       # como o kernel enumerou
lsusb -v -d VID:PID                    # interfaces e endpoints (HID? CDC?)
```

## Resultados da primeira sessão (2026-08-12, base ligada)

1. **VID/PID:** `3514:0301` (`CONSPIT ARES`). **Não** bate com `1209:ffb0` — a Conspit
   registrou VID próprio. O serial de fábrica aparece em
   `/dev/serial/by-id/usb-CONSPIT_CONSPIT_ARES_<serial>-if00` — **não versionar**, é dado de
   garantia. Resolva sempre por glob nas ferramentas e nos exemplos.
2. **CDC serial: sim.** Composite device (IAD): if00/if01 CDC-ACM → `/dev/ttyACM2`,
   if02 HID. Basta o usuário estar no grupo dono do device — que **varia por distro**
   (`dialout` no Fedora, `uucp` no Arch); detectar com `stat -c '%G' /dev/ttyACM*`.
3. **Joystick com FFB: sim.** `/dev/input/js0` + evdev, com 40 slots de efeito
   simultâneos e todos os condicionais (spring, damper, inertia, friction, constant,
   ramp, periódicos). O kernel carregou `hid-pidff` sozinho via `hid-generic`.
   **A regra udev é necessária e o problema é pior que o do wiki** — ver
   `udev/70-conspit.rules`.
4. **Configurador oficial: abre, conecta e opera.** Ver "Rodando o configurador" abaixo.
5. **Protocolo: responde.** `sys.0.id?` não existe (não é comando do OpenFFBoard), mas
   `sys.0.help`, `sys.0.swver?`, `axis.0.power?` etc. respondem no formato documentado.

### Identidade do firmware

| campo | valor |
|---|---|
| `sys.0.swver?` | `1.15.0` |
| `sys.0.hwtype?` | `F407VG` (STM32F407VG — a placa de referência do OpenFFBoard) |
| `main.0` | `FFB Wheel (1 Axis)` |
| `axis.0.drvtype?` | `5` (ODrive) |
| `axis.0.power?` | `27098` |

Classes ativas (`sys.0.lsactive?`, formato `Nome:cls:inst:clsid:idx`):

```
Can port:can:0:3073:1      Can port:can:0:3073:2      FFB Wheel (1 Axis):main:0:1:3
System Commands:sys:0:16:4 CAN Analog:cananalog:0:66:5 Effects:fx:0:2562:6
Axis:axis:0:2561:7         ODrive (M0):odrv:0:133:8
```

Os class IDs batem com os documentados (`0xA01` axis, `0xA02` fx, `0x10` sys). O descritor
HID de 1252 bytes traz a PID usage page (`0x0F`) completa **e** a página vendor-defined com
report ID `0xA1` — exatamente a interface de comandos por HID descrita no wiki.

### Segundo dispositivo Conspit no barramento

`3514:0300` (`CONSPIT`), na porta vizinha do mesmo hub. HID puro,
descritor de 87 bytes, **sem PID/FFB e sem botões declarados**: só arrays vendor-defined de
63 bytes na Consumer page (report IDs 1–5). É um canal de comunicação, não um controle.
Descritor com `bNumConfigurations` = 64 (o kernel corta em 8), o que é um descritor
malformado. **Ainda não identificado** — precisa saber do usuário qual periférico é.
Detalhe relacionado: `main.0.btntypes?` = `32` (bit 5) indica uma fonte de botões ativa que
`main.0.lsbtn?` não enumera; pode ser o volante/rim via CAN. **Não é o H.AO** — este entra
como device USB próprio (`3514:0007`), não pela base.

### O configurador OpenFFBoard oficial — validado, mas REMOVIDO do repo

Em 2026-08-12 o configurador oficial (https://github.com/Ultrawipf/OpenFFBoard-configurator,
Python + PyQt6) foi montado e **funcionou**: conectou na base, detectou-a sozinha e operou.
As ferramentas foram removidas do repo por decisão do usuário quando o ConspitLink passou a
funcionar sob Wine e cobrir a configuração. **O caminho existe e é viável** — não precisa ser
redescoberto.

Não estão em nenhum commit (o commit que as trazia foi reescrito para remover o serial da
base). Mas nada se perdeu: o upstream é público e os três ajustes necessários estão descritos
abaixo com precisão suficiente para reaplicá-los em minutos.

O que foi preciso para ele funcionar, caso alguém retome:

1. Registrar `3514:0301` em `SerialChooser.OFFICIAL_VID_PID` (`serial_ui.py`). Sem isso a
   base aparece como "Unsupported device" e não é auto-conectada; conectar manualmente
   sempre funcionou — o VID/PID só controla destaque e auto-connect.
2. Tornar `helper.classlistToIds` tolerante. **Bug do upstream, não da Conspit:** este
   firmware responde `main.0.lsbtn?` com `OK` (nenhuma fonte de botão enumerável) em vez de
   uma lista, e o parser assume sempre `id:creatable:nome` → `ValueError` a cada resposta.
3. Absorver uma corrida em `SerialComms.processMatchedReply`: um callback remove a própria
   classe de `callbackDict` durante o dispatch, e a limpeza seguinte estoura `KeyError`.
   Também é bug do upstream.

Os itens 2 e 3 são genéricos e valem como PR pro upstream.

**Valor que sobra mesmo sem usá-lo:** é a prova de que a base é OpenFFBoard de verdade, e é
o plano B se o ConspitLink quebrar (atualização de firmware, de Wine ou do próprio app).

### Ferramentas deste repo

| arquivo | o que faz |
|---|---|
| `tools/check-setup.sh` | verifica o ambiente inteiro e imprime a correção de cada falha |
| `tools/probe_serial.py` | sonda **read-only** da CDC (só `?` e `!`, nunca `=`) |
| `tools/evdev_info.py` | eixos com fuzz/flat + capacidades de FFB, sem disparar efeito |
| `tools/parse_hid_rdesc.py` | decodifica report descriptor, destaca a PID usage page |
| `tools/hid_watch.py` | posição do volante em evdev e hidraw ao mesmo tempo |
| `tools/cpp_pedal.py` | lê e calibra os pedais CPP.LITE **nativamente**, sem Wine |
| `tools/conspit_wine_setup.py` | nó PnP da serial **e** backend hidraw do winebus |
| `tools/hidenum.c` | enumera HID **de dentro do prefixo**: o que um app Windows enxerga |
| `tools/dinput_axes.c` | mede o mapeamento de eixos do DirectInput dentro do prefixo |
| `tools/run-conspitlink.sh` | abre o ConspitLink no prefixo isolado |
| `udev/70-conspit.rules` | zera fuzz/deadzone e libera hidraw (precisa de `sudo`) |

⚠️ **Segurança:** é uma base de 20 Nm. As ferramentas acima são deliberadamente somente de
leitura. Não mandar `=`, `sys.0.save`, `sys.0.format`, `odrv.*` de calibração ou carregar
efeitos de FFB sem o volante livre e as mãos fora.

## ConspitLink 2.0 sob Wine (2026-08-12)

**As duas rotas não competem — cobrem coisas diferentes.** Configuração e FFB já estão
resolvidos nativamente pelo configurador OpenFFBoard. O que só o ConspitLink tem é a
**telemetria proprietária para o dash dos volantes Conspit** (300GT etc.), que nenhum
software open source substitui. Prioridade acordada com o usuário: **primeiro o app rodando
com a configuração da base** (torque, suavidade — os ajustes típicos de base DD), **dash
depois**.

### O que o app é

Instalador NSIS de 300 MB, EV-signed por 恩速（上海）电子科技有限公司 (entidade legal da
Conspit). Instala silenciosamente com `wine ConspitLink2.0.exe /S`. Prefixo isolado deste
projeto: **`~/.local/share/conspit-ares-linux/prefix`** (apagar a pasta desfaz tudo).
Ate 2026-08-15 ficava em `<repo>/.wine-conspitlink`; saiu de la porque passa de 870 MB e um
`git clean -xfd` apagava a configuracao junto. Resolvido por `tools/conspit-prefixo.sh`,
com override em `$CONSPIT_PREFIX`. ⚠️ **Nao usar o `~/.wine` compartilhado:** o
`Enable SDL=0` vale para o prefixo inteiro e quebraria a enumeracao de controle de todo
outro app Windows dele.

App **Qt 5.15.2, x86-64**, 479 MB instalado. Bibliotecas que dizem como ele fala com o
hardware: `Qt5SerialPort.dll` (a CDC), `hidapi.dll` (canal HID proprietário),
`libusb-1.0.dll` (DFU). Acompanha **`ConspitLink2.0.pdb` de 77 MB — símbolos de debug
completos**, alavanca enorme caso o protocolo do dash precise ser entendido.

### Telemetria: dois regimes, e isso importa

São 18 jogos em `JsonConfigure/GameSettingCenter.json`, divididos em:

- **UDP** — F1 22/23/24/25, DiRT Rally 2.0, EA WRC, WRC Generations, Forza Horizon 5,
  Forza Motorsport 8. O `F1.txt` manda apontar UDP para `127.0.0.1`. **Atravessa a fronteira
  Wine/Proton sem esforço** — é só rede no kernel Linux. Jogo no Proton + ConspitLink no
  Wine funciona.
- **Memória compartilhada** — AC, ACC, AC EVO, AC Rally, iRacing, AMS2, rFactor 2,
  Le Mans Ultimate, RaceRoom, ETS2, RBR. O namespace de objetos do wineserver é **por
  prefixo**: o jogo está no prefixo do Proton, o ConspitLink no dele, e um não vê a memória
  do outro. ✅ **Resolvido em 2026-08-15 pelo Winecarte** — ver a seção adiante. A hipótese
  antiga ("o ConspitLink precisa rodar dentro do prefixo do jogo") **não era necessária**.

Nada disso bloqueia a fase 1 (configuração da base), que não usa telemetria de jogo nenhuma.

### A telemetria de jogo, resolvida (2026-08-15)

✅ **Validado com Le Mans Ultimate**: `Select Game` saiu de `Not Started` para **`Started`**,
a telemetria alimentou o app, os **haptics no modo `Customize` passaram a vibrar conforme o
efeito**, e o **dash / rev lights do volante** receberam os dados.

#### Como o app sabe que o jogo está rodando

⚠️ **Não é enumeração de processos.** O binário importa `CreateToolhelp32Snapshot` e
`OpenProcess`, o que me levou a inferir isso — e **estava errado**. Os símbolos do `.pdb`
mostram uma família `GanmeOf<Jogo>` (o typo é deles) com **`GanmeOfACC::Get_GameStatus`** ao
lado de `Get_InitSuccess`, e um `GameData::Slot_initShareMemory`.

**A detecção é o próprio attach à memória compartilhada.** Por isso detecção e telemetria são
**o mesmo problema**, e se resolveram juntas: entregue a shm no prefixo e o `Started` vem de
brinde. Não perca tempo procurando um mecanismo separado de detecção.

#### A ponte: Winecarte

https://github.com/srounce/winecarte — instalado aqui via
`~/apps/linux-simracing-utils/` (do mesmo autor). Três componentes:

| componente | papel |
|---|---|
| `winecarte-run %command%` | nas opções de lançamento do jogo no Steam; injeta no prefixo do Proton e **exporta** a shm para `/dev/shm` |
| `winehub` | roda contra um **prefixo alvo** e **importa** `/dev/shm` para dentro dele |
| `wine2linux.exe` | o motor que os dois injetam; copia os named file mappings Win32 ↔ arquivos Linux |

O `winehub` aceita **qualquer** prefixo alvo (`--prefix`, ou `$WINEPREFIX`), e `/dev/shm`
permite vários consumidores — então o ConspitLink é só um segundo alvo, convivendo com o do
SimHub. `tools/run-conspitlink.sh` sobe essa metade sozinho; a metade de cima é manual, nas
opções do jogo no Steam.

#### Os nomes batem — era a pergunta que decidia tudo

Conferido com `strings -el` (o app é Qt, guarda em UTF-16 — `strings` sem `-el` não acha):

| jogo | ConspitLink abre | Winecarte exporta | |
|---|---|---|---|
| Assetto Corsa | `Local\acpmf_physics/graphics/static` | idem | ✅ |
| Le Mans Ultimate | `LMU_Data` | `LMU_Data` + `LMU_Data_Event` | ✅ **validado** |
| rFactor 2 | `$rFactor2SMMP_*$` | idem | ✅ |
| AC EVO | `Local\acevo_pmf_*` | idem | ✅ |
| AMS2 / PCars2 | `$pcars2$` | idem | ✅ |
| ETS2 / ATS | `Local\SCSTelemetry` | `Local\SHSCSTelemetry` | ⚠️ prefixo `SH` difere |
| **iRacing** | `Local\IRSDKMemMapFileName` | **não exporta** | ❌ |

⚠️ **iRacing não é coberto pelo Winecarte**, e é um dos jogos desta bancada. Se for atacar,
o mapa é `Local\IRSDKMemMapFileName` + `Local\IRSDKDataValidEvent` + `IRSDK_BROADCASTMSG`.

#### O app também não achava os jogos INSTALADOS — problema separado

Ele lê `HKCU\SOFTWARE\Valve\Steam\SteamPath` e daí abre `config/libraryfolders.vdf` e
`steamapps/common/` (há um `GameData::readVdf` no `.pdb`). Com **Steam nativo** essa chave não
existe no prefixo — o Steam do Linux nunca escreve no registro do Wine.

⚠️ Apontar `SteamPath` direto para o Steam via `Z:` **não basta**: os caminhos dentro do
`libraryfolders.vdf` são Linux absolutos (`/home/...`), que como caminho Windows cairiam na
raiz do drive atual. Por isso `conspit_wine_setup.py` monta `C:\SteamBridge` com o vdf
reescrito para `Z:` e um symlink para o `steamapps` real.

### O que foi preciso para o app enxergar a base

`tools/conspit_wine_setup.py`, adaptado do `pedal_wine_setup.py` (seção 11.3 do projeto do
pedal) de .NET/WMI para Qt/SetupAPI. O Wine expõe portas seriais sem VID/PID de USB, e o
`QSerialPortInfo` enumera pela classe `Ports` do SetupAPI, tirando o nome de
`Device Parameters\PortName` e o VID/PID do device instance ID — então sem um nó na árvore
PnP a base não aparece na lista dele.

O script registra
`HKLM\System\CurrentControlSet\Enum\USB\VID_3514&PID_0301\<serial>` com `Class=Ports`,
`Service=Serial`, `DeviceDesc="CONSPIT ARES (COM33)"` e `Device Parameters\PortName=COM33`,
mais o mapeamento COM33 nos dois lugares obrigatórios (`dosdevices/com33` **e**
`HKLM\Software\Wine\Ports\COM33`), sempre pelo caminho `/dev/serial/by-id/...`.

**Medido, não suposto:** antes do nó PnP, com o app rodando, os file descriptors dele não
continham device nenhum (só GPU) — ele lia o nome "CONSPIT ARES" da própria config, não do
hardware. Depois do nó, `/dev/ttyACM2` aparece aberto pelo processo.

⚠️ COM33 e não COM3: o `wineboot` preenche `com1`..`com32` varrendo `/dev/ttyS*` e
sobrescreve qualquer symlink nessa faixa.

### Estado atual e o que falta

**O ConspitLink 2.0 funciona sob Wine, com controle da base em tempo real.** Confirmado na
GUI pelo usuário em 2026-08-12:

- ✅ Telemetria ao vivo: `Force State: Enabled`, `Current Torque 0.04Nm`, `Phase U/V/W
  Temperature 11.53°C`, `MOS Temperature 22.43°C`.
- ✅ Escrita em tempo real: mudar Max Force (1 N·m ↔ 20 N·m) reflete na base na hora;
  Power On/Off alterna o `Force State`.
- ✅ Presets, seleção de jogo e `High Torque Mode` operando.
- ❌ ~~a leitura de ângulo do volante fica em `+0.00°`~~ — **resolvido em 2026-08-15** pelo
  backend hidraw do winebus; ver "O backend do winebus" adiante.

Dois canais são usados ao mesmo tempo, e ambos precisam estar liberados:

| canal | processo que abre | serve para |
|---|---|---|
| CDC serial (`/dev/ttyACM*`) | `ConspitLink2.0.exe` + `wineserver` | configuração |
| `/dev/hidraw*` + `/dev/input/event*` | `winedevice.exe` (winebus) | telemetria ao vivo |

Logs do app são strings chinesas que saem como `?` no console (conversão de codepage);
não é erro. `LANG=zh_CN.gb18030` pode recuperá-las se precisar diagnosticar.

⚠️ **Os números de `hidrawN` e `eventN` trocam entre a base e o segundo MCU a cada
reenumeração do kernel.** Aconteceu duas vezes em 2026-08-12 e me levou a uma conclusão
errada. Nunca fixar `hidraw2`/`event21` em lugar nenhum — resolver sempre pelo VID/PID via
`/sys/class/hidraw/*/device/uevent` (campo `HID_ID`, comparado como **número**, porque vem
com zeros à esquerda de largura variável) ou por `/dev/input/by-id/`. É o que
`tools/hid_watch.py` faz.

### O ângulo travado em +0.00° — RESOLVIDO em 2026-08-15 (registro histórico)

> ⚠️ **A conclusão desta seção estava errada, e vale entender por quê.** A cadeia abaixo é
> boa e as medições são válidas — mas ela *pressupunha* que o device HID que o app via era o
> device real. Não era: o Wine entregava um device sintetizado pelo SDL, **sem a collection
> vendor**. A linha do `DisableInput` foi escrita na chave errada e nunca surtiu efeito, o
> que fechou prematuramente justamente a hipótese certa. Corrigido o backend, o ângulo
> passou a funcionar. Lição: **antes de concluir "é bug do app", confirme o que o app
> enxerga** — `tools/hidenum.c` responde isso em segundos.

Cadeia de eliminação original, toda com medição:

| hipótese | teste | resultado |
|---|---|---|
| base em falha / sem energia | `odrv.0.vbus?`, `errors?`, `estop?` pela serial | 47,5 V, zero erro, encoder vivo |
| posição não chega ao kernel | `tools/hid_watch.py` girando o volante | 10111 eventos evdev, faixa cheia ±32767 |
| posição não está no HID | idem, lado hidraw | **report ID 1, bytes 18–19**, 695/s |
| falta calibrar o centro | botão `Center Calibration` na GUI | não mudou nada |
| Wine cria device HID duplicado | `DisableInput=1` no winebus | **não ajudou** — `event*` continua aberto |
| Wine não entrega o eixo | `wine control joy.cpl`, aba DInput | **eixo X acompanha o volante perfeitamente** |
| app não lê o eixo | `WINEDEBUG=+dinput` | **1534 `GetDeviceState`** em 20 s, `DIJOYSTATE2` |
| ângulo vem pela serial | lista completa de comandos do app | **nenhum comando de posição existe** |

**Conclusão da época (errada):** o defeito estaria dentro da lógica do ConspitLink
(`AresApexManger::Base_Angle`). **Conclusão real:** o app lia o `DIJOYSTATE2` de um device
sintético, e o canal por onde o firmware manda a posição não existia no prefixo.

O que faltava testar, e que ninguém tinha olhado: **o que o app enxerga**, com
`tools/hidenum.c`. As duas linhas do trace que teriam entregado o caso de imediato:

```
WINEDEBUG=+hid   ->  ignoring hidraw device 3514:0301 with usages 0001:0004
                     creating non-hidraw device 3514:0301 with usages 0001:0004
```

Se algum dia só o número interessar, ele está disponível nativamente: `axis.0.pos?` /
`axis.0.curpos?` pela serial, ou os bytes 18–19 do report ID 1. O protocolo completo que o
app usa está em `docs/protocolo-conspitlink.md`.

### Pegadinha do udev que custou uma rodada

O `TAG+="uaccess"` **só funciona se a regra for numerada antes de 73**. O systemd efetiva a
tag em `/usr/lib/udev/rules.d/73-seat-late.rules`:

```
TAG=="uaccess", ENV{MAJOR}!="", RUN{builtin}+="uaccess"
```

Como as regras rodam em ordem lexical, uma regra `99-` adiciona a tag depois dessa checagem
já ter passado: o builtin nunca dispara e o hidraw continua root-only — **em silêncio, sem
erro nenhum**. Confirmado empiricamente: com `99-`, a correção de deadzone funcionou
(`RUN+` roda no fim de qualquer jeito) mas o `uaccess` não. Por isso o arquivo é
`70-conspit.rules`.

**Segundo motivo do `70-`, descoberto em 2026-08-14.** Não é só o `73-`: quem concede ACL a
joystick é `/usr/lib/udev/rules.d/70-uaccess.rules:61`

```
SUBSYSTEM=="input", ENV{ID_INPUT_JOYSTICK}=="?*", TAG+="uaccess"
```

e quem classifica é o builtin `input_id`, chamado em `60-input-id.rules`. Isso explica a
medição de 12/08 (o `event*` da base tinha ACL **sem** nenhuma regra deste repo instalada:
ela é joystick). E significa que atribuir `ENV{ID_INPUT_JOYSTICK}="1"` só surte efeito se a
regra ordenar **antes de `70-uaccess`** — `70-conspit` ordena (`c` < `u`), `99-` não.

### Regra única para todos os devices Conspit (2026-08-14)

`udev/70-conspit.rules` substituiu a antiga `70-conspit-ares.rules`. As três linhas de
`TAG+="uaccess"` casam **só por `ATTRS{idVendor}=="3514"`**, sem `idProduct` — então base,
2º MCU e pedais CPP ficam cobertos por um arquivo só. Apenas o `RUN+` do `evdev-joystick`
é por PID, porque os valores de fuzz/flat têm de ser medidos device a device.

Motivo da unificação: esta máquina tinha `99-conspit.rules` e `99-conspit-cpp.rules`
(pedais CPP, PID `0005`) instaladas, e **as duas estavam parcialmente quebradas pelo
prefixo**. O escopo casa com o repo: o `.pdb` do ConspitLink tem classes `CppLite`/`CppPro`/
`CppEvo`, ou seja, é o mesmo app que atende os pedais.

Precisão importante (medido em 2026-08-14, `udevadm test` + `getfacl`): em `99-`, o
`TAG+="uaccess"` é **inerte** — a tag aparece em `CURRENT_TAGS` mas o ACL nunca é aplicado
(o `event*` dos pedais ficou sem ACL de usuário). Já o `ENV{ID_INPUT_JOYSTICK}="1"`
**funciona parcialmente**: a propriedade fica no banco do udev e é lida por quem consulta
depois (SDL), mas chega tarde para os dois consumidores em tempo de regra —
`60-persistent-input` (symlink `-joystick`) e `70-uaccess` (ACL). Ou seja: apagar a regra
legada sem replicar essa atribuição **regride** a enumeração dos pedais nos jogos.

### Pedais CPP.LITE — o que foi medido (2026-08-14)

`3514:0005`, `Conspit CONSPIT CPP.LITE`. Descritor HID de 88 bytes com **duas collections
na mesma interface USB**, e o kernel cria **dois** input devices:

| collection | conteúdo | vira | `capabilities/abs` |
|---|---|---|---|
| `Usage(Joystick)`, report ID 1 | 3 eixos de 12 bits (Rx, Y, Z) | os três pedais | `e` |
| `Usage(Counted Buffer)`, report ID 2 | 63 bytes vendor | um `ABS_MISC` inútil | `10000000000` |

⚠️ **`/dev/input/by-id/` do CPP.LITE aponta para o canal vendor, não para os pedais.** As
duas collections saem da mesma interface (`if00`), então o `60-persistent-input.rules` gera
o mesmo nome de symlink para as duas e a última processada vence. Medir eixos por aquele
caminho retorna **um** eixo de 0–255 e engana — foi o que aconteceu comigo antes de olhar o
descritor. A regra agora discrimina por `ATTRS{capabilities/abs}=="e"` e cria
`/dev/input/conspit-cpp-lite`, que é o caminho a usar em qualquer ferramenta.

Outros dois fatos medidos: o `input_id` **não** classifica os pedais como joystick sozinho
(eles não têm botão nenhum, só eixos) — daí a necessidade do `ENV{ID_INPUT_JOYSTICK}="1"`; e
os três eixos vêm com `fuzz 15, flat 255` em escala 0–4095, ou seja **~6% de curso morto no
início de cada pedal**, que a regra zera.

⚠️ **`ATTRS{}` múltiplos têm de casar no MESMO device da cadeia.** Do `man udev`:

> If multiple ATTRS matches are specified, all of them must match on the same device.

`idVendor`/`idProduct` moram no device USB; `capabilities/abs` mora no device de input.
São devices diferentes na mesma cadeia — então `ATTRS{idProduct}=="0005"` +
`ATTRS{capabilities/abs}=="e"` na mesma linha **nunca casa, e sem erro nenhum**. Custou uma
rodada em 2026-08-14: a regra instalou, o `udevadm verify` passou, a seção 1 e a 2
funcionaram, e a 3 simplesmente não fez nada. O diagnóstico é `udevadm test
/sys/class/input/eventNN` — o arquivo aparece em "Reading rules file" mas nenhuma linha dele
consta nas regras aplicadas.

A saída é usar `ENV{ID_VENDOR_ID}`/`ENV{ID_MODEL_ID}` (propriedades postas pelo builtin
`usb_id` em `60-persistent-input.rules`, já disponíveis quando uma regra `70-` roda), o que
deixa **uma única chave `ATTRS` por linha**. A regra da base não sofre disso porque seus dois
`ATTRS` são `idVendor` + `idProduct`, ambos no mesmo device USB.

⚠️ Ao varrer regras instaladas, **nunca casar por `*conspit*` e agir em bloco**: o glob pega
regras de outros devices da marca. Foi exatamente o bug que o `check-setup.sh` tinha — ele
lia `99-conspit-cpp.rules` (pedais) como se fosse a da Ares e mandava `sudo rm` nela.

## O backend do winebus — a descoberta que reorganizou o projeto (2026-08-15)

**Uma linha de registro na chave certa substituiu 492 linhas de shim, uma concessão de
segurança e três "pendências do app".** Esta seção substitui toda a saga do
`cpp_hid_shim.py` (2026-08-14), que está preservada nos commits `ec0ad06`..`1e29b84` caso
alguém precise do código.

### A causa raiz: o projeto escrevia numa chave que o driver nunca lê

O `winebus.sys` traz o comentário de documentação do próprio Wine, em `check_bus_option`:

```c
/* @@ Wine registry key: HKLM\System\CurrentControlSet\Services\WineBus */
```

Ele lê as opções **direto em `Services\winebus`**. Até 2026-08-15 este projeto escrevia em
`Services\winebus\`**`Parameters`** — uma subchave que o driver nunca consulta. Todas as
opções eram ignoradas **em silêncio**, e o backend continuava no SDL.

Isso invalidou quatro conclusões que estavam registradas aqui como "medidas":

| o que este arquivo afirmava | o que era de verdade |
|---|---|
| "`Enable SDL=0` configurado" | nunca leu; o SDL estava ativo e era quem fabricava os joysticks |
| "`DisableInput=1` não ajudou, `event*` continua aberto" | nunca leu; o `event*` aberto era do próprio SDL |
| "`EnableHidraw=3514:0005` não muda o backend" | nunca leu; o formato estava **certo** o tempo todo |
| "o setup configurou o hidraw para a telemetria" | a telemetria do `0300` já vinha por hidraw **por default** (usage vendor) — o passo era um no-op |

⚠️ **O canal de debug é `+hid`, não `+plugplay`.** As decisões de backend saem em
`WINEDEBUG=+hid` (`bus_main_thread`); o `+plugplay` mostra só a criação dos nós PnP e **não**
revela nada disso. Foi por olhar o canal errado (e os fds abertos do `winedevice`) que a
medição de 14/08 concluiu errado.

### Como o winebus decide, no código (wine-11.15, `dlls/winebus.sys/main.c`)

```c
if (options.disable_sdl && options.disable_input) prefer_hidraw = TRUE;
...
UINT len = swprintf(vidpid, ARRAY_SIZE(vidpid), L"%04X:%04X", vid, pid);
if (!wcsnicmp(tmp, vidpid, len)) prefer_hidraw = TRUE;
```

e, no `IRP_MN_START_DEVICE`:

```c
if (!sdl_driver_init()) options.disable_input = TRUE;
```

Três consequências que importam:

1. **`Enable SDL=0` desliga o evdev junto.** SDL desligado faz `sdl_driver_init()` falhar, o
   que liga `disable_input` — e aí a primeira linha acima passa **qualquer** joystick para
   hidraw. É a rede de segurança: um device Conspit ligado depois do setup já nasce certo,
   sem re-rodar nada.
2. **`EnableHidraw` é `REG_MULTI_SZ` no formato `VID:PID` de 4 dígitos hex**, comparado sem
   case. `3514:0005` sempre esteve correto.
3. **Não há dedup entre backends.** Cada backend cria o device e o `is_hidraw_enabled`
   rejeita o que não bate — daí as linhas `ignoring non-hidraw device` no trace, que são
   normais e esperadas.

### O que muda para o app

`tools/hidenum.c` dentro do prefixo, antes e depois:

```
ANTES (backend SDL)                              DEPOIS (backend hidraw)
3514:0005 usage 0x04 in 7                        3514:0005 &Col01 usage 0x04 in 19
                                                 3514:0005 &Col02 usage 0x3A in 64 out 64
3514:0007 usage 0x04 in 26                       3514:0007 &Col01 usage 0x04 in 52
                                                 3514:0007 &Col02 usage 0x3A in 64 out 64
3514:0300 usage 0x01 in 64                       3514:0300        usage 0x01 in 64 out 64
3514:0301 usage 0x04 in 28                       3514:0301 &mi_02 usage 0x04 in 64 out 25
```

O hidclass do Wine **separa as top-level collections em PDOs `&Col01`/`&Col02`**, exatamente
como o Windows. O problema que motivou o shim inteiro não existe nesta versão do Wine — só
estava desligado por política.

⚠️ **A enumeração tem corrida.** Logo após `wineserver -k`, a primeira passada do `hidenum`
pode não listar todos os devices (o udev ainda está enumerando). Medir sempre na **segunda**
passada, com ~3 s de intervalo. Custou uma conclusão errada sobre o H.AO.

### Configuração canônica (o que o `conspit_wine_setup.py` escreve)

Em `HKLM\System\CurrentControlSet\Services\winebus`:

| valor | tipo | papel |
|---|---|---|
| `Enable SDL` | `REG_DWORD` `0` | rede de segurança: tudo vira hidraw, inclusive device novo |
| `EnableHidraw` | `REG_MULTI_SZ` | lista explícita `3514:xxxx` dos devices presentes |

Os dois juntos de propósito: o primeiro é o que funciona sem manutenção, o segundo é o que
documenta a intenção e continua valendo se alguém religar o SDL. O script **detecta os PIDs
no barramento** — rode de novo ao ligar um device Conspit novo.

⚠️ `Enable SDL=0` vale para o **prefixo inteiro**. Como este prefixo só roda o ConspitLink,
tudo bem; num prefixo de jogos, um controle sem ACL de hidraw sumiria.

### O que isto aposentou

| removido | por quê |
|---|---|
| `tools/cpp_hid_shim.py` (492 linhas) | o Wine já entrega as duas collections |
| `udev/70-uhid-shim.rules` | **a concessão de `/dev/uhid` deixou de ser necessária** |
| joystick virtual + `--sem-eixos` | o app lê os eixos reais, na ordem do descritor |
| `HKCU\...\DirectInput\Joysticks` = `disabled` | não há mais device duplicado a esconder |
| `--capturar` do runner | ver "Captura de protocolo" abaixo |

Ganho colateral que vale nomear: sem o shim, **nenhum device virtual aparece na lista de
controles dos jogos**, e o escopo da mudança é por prefixo em vez de global no kernel.

### Validado na GUI pelo usuário (2026-08-15)

- **Base:** o ângulo do volante, que ficava travado em `+0.00°` desde 12/08, **passou a
  acompanhar o movimento em tempo real** (`-449.31°` na tela, com o volante girado).
- **Pedais:** telemetria idêntica à do Windows; haptics no modo `Customize` funcionando.
- **Volante H.AO:** botões, brilho de rev lights/botões/dashboard, paddles Hall e Launch
  Control — tudo operante no primeiro dia em que o device foi ligado, sem uma linha de código
  específica para ele. **Os 6 paddles são todos Hall** (por isso eixos, não botões) e os 6
  calibram de mínimo a máximo corretamente pela GUI.
- **Calibração dos pedais pela GUI:** o acelerador foi calibrado no próprio ConspitLink e o
  gráfico ficou **idêntico ao do Windows, fluido** — o que fecha também a antiga pendência da
  barra saturando em ~16384.

Medições de confirmação, depois da validação: `check-setup.sh` fecha com **0 falhas e 0
avisos**; `ABS_RX` dos pedais voltou a marcar `0` em repouso (marcava `4095`, saturado); os
sete eixos analógicos do H.AO estão com `fuzz 0 flat 0`.

### O volante H.AO (`3514:0007`)

Apareceu no barramento em 2026-08-15. Mesma estrutura de duas collections dos pedais
(joystick + canal vendor de 64 bytes), firmware `V1.78`.

**Não precisou de tratamento especial**, e o motivo é instrutivo: como ele **tem botões**, o
builtin `input_id` classifica a collection de joystick sozinho — então `ID_INPUT_JOYSTICK`
vem de graça e o `by-id` sai correto (`-event-joystick` no joystick, `-event-if00` no canal
vendor). Os pedais precisavam de regra porque **não têm botão nenhum**, só eixos.

Precisou, sim, da correção de fuzz/flat — sete eixos analógicos, todos ruins:

```
ABS_Y, ABS_Z, ABS_RUDDER      0..4095    fuzz  15  flat  255   (~6%)
ABS_RX, ABS_RY, ABS_RZ,
ABS_THROTTLE                  0..65535   fuzz 255  flat 4095   (~6.25%)
```

Nos paddles Hall isso é curso morto no início do acionamento — exatamente o que se compra um
paddle Hall para não ter. Seção 4 da `udev/70-conspit.rules`.

⚠️ **Não confundir com a aba `Paddles` do app**: ela grava na firmware do volante (bite
point, engate) e vale em qualquer SO. O fuzz/flat é um filtro do **kernel Linux**, por cima,
que nenhum ajuste no app desfaz — e como o app fala por hidraw, zerá-lo é invisível para ele
e só beneficia os jogos.

O protocolo do canal vendor do H.AO **ainda não foi mapeado**. Ele expõe também uma **CDC
serial própria** (`/dev/ttyACM*`), descoberta em 2026-08-15 — por isso o
`conspit_wine_setup.py` seleciona a porta da base **pelo PID**, e não "a primeira da lista":
até então acertava só por acidente da ordem alfabética (`ARES` < `H.AO`).

⚠️ **Calibração (min/max) e curva são ajustes diferentes**, e eu já os confundi uma vez. O
min/max é gravado por `$setvaluex0`/`$setvaluex1` e **não é legível por nenhuma consulta**;
a curva é o `$gdlinex`. Um `xgdl00255075100` (linear) é só a curva padrão, não sinal de
calibração perdida — diagnostique min/max **pelo eixo**, com o pedal solto e no batente.
Detalhes em `docs/protocolo-cpp-lite.md`.

### Pendências que morreram junto

- **Ângulo da base em `+0.00°`** — resolvido. A hipótese que faltava era esta: o app via o
  device sintetizado pelo SDL, **sem a collection vendor** por onde o OpenFFBoard manda as
  notificações HID. Não era defeito de `AresApexManger::Base_Angle`.
- **Barra de posição dos pedais saturando em ~16384** — resolvida. Era o app interpretando a
  escala sintética do SDL; com o descritor real de 12 bits o valor sai certo.
- **Rótulos dos pedais rotacionados** — resolvida na raiz. O Wine não sintetiza mais o device
  a partir do `evdev`, então a ordenação por código de eixo (`ABS_Y` < `ABS_Z` < `ABS_RX`)
  deixou de existir; vale a ordem do descritor, como no Windows.

⚠️ **Não reintroduzir** o shim, o joystick virtual nem o `DisableInput`. E, ao investigar
qualquer coisa de backend HID no Wine, **começar por `WINEDEBUG=+hid`** e conferir em qual
chave a opção está sendo escrita.

### Captura de protocolo, agora

O `--capturar` do runner funcionava porque o shim era um MITM. Sem ele, o app fala direto com
`/dev/hidraw*`, e a captura passa a ser no nível USB:

```bash
sudo modprobe usbmon
# descubra o barramento com: lsusb | grep -i 3514   (Bus 005 -> usbmon5)
sudo cat /sys/kernel/debug/usb/usbmon/5u | grep -i ...
```

Para os pedais isso raramente é necessário: `tools/cpp_pedal.py` fala o protocolo `$`
nativamente, sem Wine e sem app. Para mapear o canal do H.AO, o mesmo padrão deve servir.

## Portabilidade entre distros (2026-08-14)

O ambiente de desenvolvimento é **Fedora 44** (máquina de lab); a máquina do simulador é
**CachyOS (Arch)**. Tudo foi revisado para ser replicável nas duas. O que de fato varia:

| ponto | Fedora | Arch / CachyOS |
|---|---|---|
| pacote do `evdev-joystick` | `linuxconsoletools` | `linuxconsole` |
| pyserial | `python3-pyserial` | `python-pyserial` (⚠️ `pip install` barrado pelo PEP 668) |
| **grupo dono de `/dev/ttyACM*`** | `dialout` | `uucp` |
| Wine | `wine` | `wine`, exige repo **multilib** |

⚠️ **O grupo da serial é a armadilha silenciosa.** Ele vem de
`/usr/lib/udev/rules.d/50-udev-default.rules`, que cada distro patcheia. Documentação e
scripts **detectam** com `stat -c '%G' /dev/ttyACM*` em vez de assumir — nunca voltar a
escrever `dialout` fixo.

O que **não** varia e foi confirmado: a regra udev, o `TAG="uaccess"` aplicado em
`73-seat-late.rules` (daí o prefixo `70-` obrigatório), o caminho `/usr/bin/evdev-joystick`,
e todo o lado Wine.

`tools/check-setup.sh` verifica o ambiente inteiro sem assumir gerenciador de pacotes, e
imprime a correção ao lado de cada falha. Ele roda com a base desligada (pula só os testes
de hardware) — feito assim de propósito, porque numa máquina nova a verificação vem antes
de plugar. **Atualizar esse script sempre que um pré-requisito novo entrar.**

✅ **Executados na máquina do simulador (CachyOS) em 2026-08-14, com base e pedais ligados —
sem divergência.** Confirmados: `linuxconsole` é o pacote certo e instala o binário em
`/usr/bin/evdev-joystick`; o grupo da serial é mesmo `uucp`; `python-pyserial` resolve o
pyserial. A regra udev, o `uaccess` e o `RUN+` do `evdev-joystick` funcionam igual ao
Fedora. O único item não exercitado aqui é o lado Wine (o `ConspitLink2.0.exe` não está
nesta máquina).

## Escopo e disclaimers (a herdar do projeto do pedal)
- Foco **sim racing**. Um único setup: o do autor.
- Firmware, hardware e o projeto OpenFFBoard são de terceiros (Ultrawipf / Conspit) — este
  repo não redistribui nem substitui nada disso.
- Projeto pessoal, em andamento, sem garantia nem suporte.
