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
`main.0.lsbtn?` não enumera; pode ser o volante/rim via CAN.

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
| `tools/conspit_wine_setup.py` | registra o nó PnP que faz o ConspitLink enxergar a base |
| `tools/cpp_hid_shim.py` | expõe a 2ª collection HID dos pedais (o app não os vê sem isso) |
| `tools/hidenum.c` | enumera HID **de dentro do prefixo**: o que um app Windows enxerga |
| `tools/run-conspitlink.sh` | abre o ConspitLink no prefixo isolado |
| `udev/70-conspit.rules` | zera fuzz/deadzone e libera hidraw (precisa de `sudo`) |
| `udev/70-uhid-shim.rules` | dá acesso a `/dev/uhid` para o shim (ler o cabeçalho antes) |

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
projeto: `.wine-conspitlink/` (fora do git; apagar a pasta desfaz tudo).

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
  Le Mans Ultimate, RaceRoom, ETS2, RBR. Aqui o ConspitLink precisa rodar **dentro do mesmo
  prefixo do jogo**, porque o namespace de objetos do wineserver é por prefixo. ⚠️ E a seção
  11.4 do CLAUDE.md do pedal avisa: Proton roda em container `pressure-vessel`, que restringe
  o `/dev` visível — risco real justamente para o acesso a device que o ConspitLink precisa.

Nada disso bloqueia a fase 1 (configuração da base), que não usa telemetria de jogo nenhuma.

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
- ❌ **Única pendência: a leitura de ângulo do volante fica em `+0.00°`** e não acompanha
  o movimento do eixo. Ver "O ângulo travado" abaixo.

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

### O ângulo travado em +0.00° — o que já foi ELIMINADO (2026-08-12)

Cadeia de eliminação, toda com medição. **Nenhuma camada abaixo do app tem defeito:**

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

**Conclusão: o defeito está dentro da lógica do ConspitLink** (`AresApexManger::Base_Angle`),
não no Linux, não no Wine, não no hardware. O app lê o `DIJOYSTATE2` corretamente e mesmo
assim exibe 0.00.

⚠️ **Não retentar** o caminho do `DisableInput`/duplicata de device nem o de calibração de
centro — ambos medidos e descartados. O que ainda não foi feito: desmontar
`AresApexManger::Base_Angle` no binário (os símbolos do `.pdb` dão o endereço).

**Impacto real: nenhum.** O ângulo é indicador de tela; não participa do FFB nem da
configuração. Range, torque, filtros e presets funcionam.

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

## Os pedais CPP.LITE sob Wine — resolvido com shim de uhid (2026-08-14)

**Sintoma:** o ConspitLink não listava os pedais (sem card, sem item na sidebar), embora eles
funcionassem perfeitamente no Linux nativo, inclusive em jogos.

### A causa, medida

O descritor do CPP.LITE tem **duas top-level collections** (a de joystick, com os 3 eixos, e
uma vendor de 63 bytes). O Windows cria **um device HID por collection** (`&Col01`, `&Col02`)
e o app abre o segundo. O Wine cria **um device só e expõe apenas a primeira**.

Isso não é dedução: `tools/hidenum.c`, compilado com mingw e rodado dentro do prefixo,
mostra o que qualquer app Windows enxerga. Antes do shim:

```
VID_3514 PID_0005  usage_page 0x0001 usage 0x04  in 7   out 9   "CONSPIT CPP.LITE"
VID_3514 PID_0300  usage_page 0x000C usage 0x01  in 64  out 64  "CONSPIT"
VID_3514 PID_0301  usage_page 0x0001 usage 0x04  in 28  out 18  "CONSPIT ARES"
```

`in 7` = `1 + 3×2`: só os três eixos. O canal de 64 bytes dos pedais — mesmo formato do
`0300`, que aparece normalmente — simplesmente não existe no prefixo. Se o Wine tivesse
mesclado as duas collections num device, `in` seria 64; ele descartou a segunda.

⚠️ **Não confundir os dois caminhos.** O pedal funcionar em jogo (Le Mans Ultimate etc.) usa
o caminho **nativo** (evdev, 3 eixos); o ConspitLink usa o canal **HID vendor** dentro do
Wine. Mesmo cabo USB, dois canais independentes — um funcionar não diz nada sobre o outro.

### A solução

`tools/cpp_hid_shim.py` cria, via `/dev/uhid`, um device HID virtual com o mesmo `3514:0005`
contendo **só a segunda collection**, e repassa relatórios nos dois sentidos entre ele e o
`/dev/hidraw` real. Depois dele o enumerador mostra a linha que faltava:

```
VID_3514 PID_0005  usage_page 0x0001 usage 0x3A  in 64 out 64  "CONSPIT CPP.LITE"
```

E o app passa a: listar `CPP LITE` como **Online** no lugar do CPP EVO, ler o firmware
(`v2.2.0`), mostrar as abas Calibration/Vibration/Launch Control, acionar o haptic pelo botão
`Test`, e até detectar firmware novo e oferecer atualização (**não atualizar por aqui** — ver
`docs/protocolo-cpp-lite.md`). O `run-conspitlink.sh` sobe e derruba o shim junto com o app.

O protocolo desse canal é **outro**, com prefixo `$` (`$version`, `$gdlinex`, `$getPWM1`),
documentado em `docs/protocolo-cpp-lite.md`. Nada a ver com o protocolo OpenFFBoard da base.

### Detalhes que não são óbvios

1. **A regra udev precisou de outro discriminador.** O device virtual não tem pai USB, então
   `ATTRS{idVendor}=="3514"` não casa. A linha nova casa por
   `ATTRS{modalias}=="hid:b*v00003514p*"`, que existe nos dois casos. Sem ela o `hidraw`
   virtual fica root-only e o Wine não abre.
2. **O shim tem de ignorar devices virtuais ao procurar o hidraw real** — senão, depois de
   subir, ele acha a si mesmo. Filtra por `/devices/virtual/` no realpath.
3. **`/dev/uhid` é root-only por padrão.** A concessão está em `udev/70-uhid-shim.rules`,
   **arquivo separado de propósito**: é uma capacidade do sistema, não um device Conspit.
   Decisão consciente do usuário em 2026-08-14, com o trade-off entendido — quem tem acesso
   a `/dev/uhid` pode fabricar um teclado virtual e digitar como o usuário da sessão, o que
   numa sessão **Wayland** contorna o isolamento de entrada do compositor (no X11 seria quase
   irrelevante, já que XTEST já permite isso). Alternativa mais fechada, se um dia
   interessar: grupo dedicado + shim como usuário de serviço.
4. **A pedaleira não fala sozinha:** zero relatórios não solicitados. Todo o tráfego é
   pergunta/resposta iniciada pelo app.
5. ⚠️ **O shim repassa escrita.** As outras ferramentas do repo são deliberadamente
   read-only; esta não é — ao mexer em curva/calibração na GUI, vira escrita real na
   pedaleira. Não confundir com as sondas.

### Cuidado ao matar processos

`pkill -f <padrão>` casa também com **a própria linha de comando do shell** que roda o
`pkill`, e mata a si mesmo (aconteceu três vezes em 2026-08-14). O truque do colchete
(`pkill -f 'cpp_hid_sh[i]m'`) **não basta** se o nome literal aparecer em qualquer outro
ponto do mesmo comando — foi o que aconteceu na terceira vez. O que funciona sempre é matar
pelo PID: `pid=$(pgrep -f 'cpp_hid_shim\.py' | grep -v "^$$\$")`, ou guardar o `$!` na hora
de subir (é o que o `run-conspitlink.sh` faz). E `winedevice.exe` órfão às vezes sobrevive a `wineserver -k`,
inclusive `-k9`: aí é `kill -9` por PID, senão os processos velhos continuam segurando os
`hidraw` e a medição seguinte sai errada.

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
