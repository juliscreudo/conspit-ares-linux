# Conspit Ares Platinum 20Nm no Linux — análise e ferramentas

Repo deste projeto: `~/apps/conspit-ares-linux/`.

**Este arquivo contém o estado atual e as diretivas.** O *como* cada coisa foi descoberta —
incluindo as conclusões erradas e por quê — está em
[docs/historico-investigacao.md](docs/historico-investigacao.md). **Leia o histórico antes de
reinvestigar qualquer coisa**: várias hipóteses já foram testadas, e mais de uma conclusão
que parecia "medida" era artefato de erro de método.

**Projeto irmão, separado de propósito:** `~/apps/diy-ffb-pedal-linux/` (pedal ativo DIY FFB
do ChrGri). Hardware, fabricante, protocolo e upstream diferentes. O aprendizado de
**Wine + serial** de lá (seção 11 do CLAUDE.md daquele repo) foi a base da rota ConspitLink
daqui.

## Estado: funciona (validado em 2026-08-15)

Configuração e telemetria de **todos** os dispositivos pelo ConspitLink sob Wine, e
telemetria de jogo chegando ao app (haptics `Customize` + dash do volante, validado no Le
Mans Ultimate). FFB nativo nos jogos independe do Wine. `check-setup.sh` fecha com 0 falhas.

Pendências conhecidas ficam em `docs/proximos-passos.md` — **notas pessoais do autor, fora
do git** (o arquivo pode não existir num clone). O que é público está no `git log` e no
[historico-investigacao.md](docs/historico-investigacao.md).

## Hardware

- Bancada (VID `3514`): base **Ares Platinum 20 Nm** `0301` + 2º MCU `0300` (hub interno da
  base, canal do dash), pedais **CPP.LITE** `0005`, volante **H.AO** `0007`. Um app atende
  todos.
- Firmware da base: **OpenFFBoard 1.15.0 essencialmente stock** (STM32 `F407VG` +
  controladora ODrive, `axis.0.drvtype?` = 5). **Não há fork** — a única divergência do
  upstream é o VID/PID próprio, que só afeta auto-detecção.
- O `0300` é HID vendor puro (sem FFB, sem botões), com `bNumConfigurations`=64 no descritor
  (malformado; o kernel corta em 8). É canal de comunicação, não controle.
- O H.AO expõe **CDC serial própria** além do HID — por isso qualquer código que procure "a
  serial da Conspit" tem de filtrar **pelo PID da base**, nunca pegar "a primeira".
- ⚠️ O serial de fábrica da base aparece em `/dev/serial/by-id/...` — **não versionar**, é
  dado de garantia. Resolver sempre por glob.
- Periféricos de outros modelos (Ares Apex, CPP.EVO, freio de mão…):
  [docs/adicionar-dispositivo.md](docs/adicionar-dispositivo.md).

## Protocolo OpenFFBoard (referência rápida)

https://github.com/Ultrawipf/OpenFFBoard/wiki/Commands — texto, em CDC serial, HID e UART:

```
cls.(instance.)cmd?     consulta   → [cls.instance.cmd?|val]
cls.(instance.)cmd=val  escreve    → [cls.instance.cmd=val|OK]
cls.(instance.)cmd!     info
```

- Exemplos: `axis.0.power?`, `sys.0.swver?`, `sys.0.lsactive?`. `sys.0.id?` **não existe**.
- **Baudrate no CDC é irrelevante** (ignora a configuração). O ConspitLink termina comandos
  com `;`, nossas ferramentas com `\n` — a base aceita os dois.
- Interface HID de comandos: relatórios vendor report ID `0xA1`, tipos write(0), request(1),
  info(2), ACK(10), **notification(14)** — é por notification que o ângulo chega ao app.
- Os 44 comandos que o app usa: [docs/protocolo-conspitlink.md](docs/protocolo-conspitlink.md).
  Protocolo `$` dos pedais: [docs/protocolo-cpp-lite.md](docs/protocolo-cpp-lite.md).

**Plano B sem ConspitLink:** o configurador oficial OpenFFBoard (Python/PyQt6) funciona com
a base — validado em 2026-08-12 e removido do repo por decisão do usuário. Os três ajustes
para reaplicá-lo estão no histórico, Fase 1.

## Ferramentas

| arquivo | o que faz |
|---|---|
| `tools/check-setup.sh` | verifica o ambiente inteiro, correção ao lado de cada falha |
| `tools/probe_serial.py` | sonda **read-only** da CDC (só `?` e `!`, nunca `=`) |
| `tools/evdev_info.py` | eixos com fuzz/flat + capacidades de FFB |
| `tools/parse_hid_rdesc.py` | decodifica report descriptor, destaca a PID usage page |
| `tools/hid_watch.py` | posição do volante em evdev e hidraw ao mesmo tempo |
| `tools/cpp_pedal.py` | lê, monitora e **calibra** os pedais nativamente (⚠️ `calibrar` escreve) |
| `tools/conspit_wine_setup.py` | nó PnP da serial + backend hidraw + SteamBridge |
| `tools/conspit-prefixo.sh` | resolve o caminho do prefixo (incluído pelos scripts) |
| `tools/run-conspitlink.sh` | abre o app com pre-flights + ponte de telemetria |
| `tools/instalar-atalho.sh` | atalho .desktop que passa pelo runner |
| `tools/hidenum.c` | enumera HID **de dentro do prefixo**: o que o app enxerga |
| `tools/dinput_axes.c` | mapeamento de eixos do DirectInput no prefixo |
| `udev/70-conspit.rules` | acesso hidraw/event por vendor + fuzz/flat + symlink dos pedais |

⚠️ **Segurança: é uma base de 20 Nm.** Ferramentas de diagnóstico são deliberadamente
somente de leitura. Não mandar `=`, `sys.0.save`, `sys.0.format`, `odrv.*` de calibração nem
carregar efeitos FFB sem o volante livre e as mãos fora.

## A solução no Wine — arquitetura e diretivas

### Prefixo

**`~/.local/share/conspit-ares-linux/prefix`** (`$XDG_DATA_HOME`), override em
`$CONSPIT_PREFIX`, resolvido por `tools/conspit-prefixo.sh`. Apagar a pasta desfaz tudo.

- **Fora do repo** porque passa de 870 MB e `git clean -xfd` apagava a configuração junto.
- ⚠️ **Nunca usar o `~/.wine` compartilhado:** o `Enable SDL=0` vale para o prefixo inteiro
  e quebraria a enumeração de controle de qualquer outro app Windows dali.
- App: Qt 5.15.2 x86-64. Fala com o hardware via `Qt5SerialPort.dll` (CDC), `hidapi.dll`
  (canal HID vendor) e `libusb-1.0.dll` (DFU). Acompanha **`ConspitLink2.0.pdb` de 77 MB —
  símbolos completos**; consulte-o antes de inferir comportamento por imports.
- ⚠️ Strings do app são **UTF-16**: use `strings -el`. Sem `-el` você conclui errado que
  algo "não está no binário".
- Logs do app saem como `?` no console (codepage chinês); `LANG=zh_CN.gb18030` recupera.

### Serial: nó PnP + COM33

O Wine expõe portas seriais sem VID/PID; o `QSerialPortInfo` enumera pela classe `Ports` do
SetupAPI e tira o VID/PID do device instance ID — sem nó PnP a base não aparece no app. O
`conspit_wine_setup.py` cria `HKLM\...\Enum\USB\VID_3514&PID_0301\<serial>` e mapeia a
COM33 nos **dois** lugares obrigatórios (`dosdevices/com33` **e**
`HKLM\Software\Wine\Ports\COM33`), sempre pelo `/dev/serial/by-id/`.

- ⚠️ COM33 e não COM3: o `wineboot` preenche `com1..com32` varrendo `/dev/ttyS*` e
  sobrescreve qualquer symlink nessa faixa. Ele também mapeia `/dev/ttyACM*` acima de 32
  (com34, com35…), então **a base fica mapeada duas vezes — é esperado e inofensivo**: só a
  COM33 tem nó PnP com VID/PID, e o app filtra por VID/PID. Não adianta apagar os symlinks
  extras (o wineboot recria); a COM33 se auto-repara pelo registro. Suspeito do erro
  `The base port is occupied`: algo varrendo e abrindo todas as portas abre a COM34, que é a
  mesma base.
- `dosdevices` é **por prefixo** — não há colisão com SimHub, jogos ou o projeto irmão.

### Backend HID: winebus em hidraw

O passo que faz pedais, volante e a telemetria completa da base funcionarem. Por padrão o
Wine entrega devices sintetizados pelo SDL, **com uma collection só** — os canais vendor de
64 bytes e a collection de comandos da base não existem para o app. Em hidraw, o hidclass
separa as top-level collections em PDOs `&Col01`/`&Col02`, como o Windows.

Configuração canônica, em `HKLM\System\CurrentControlSet\Services\winebus`:

| valor | tipo | papel |
|---|---|---|
| `EnableHidraw` | `REG_MULTI_SZ` | **é quem faz o trabalho**: lista `3514:xxxx` (4 díg. hex, sem case) dos devices |
| `Enable SDL` | `REG_DWORD` `0` | metade da rede de segurança |
| `DisableInput` | `REG_DWORD` `1` | a outra metade — **só funciona com as duas** |

⚠️ **Corrigido em 2026-08-15: `Enable SDL=0` sozinho NÃO basta.** Este arquivo afirmava que
ele "desliga o evdev junto" e seria rede de segurança por si só. O raciocínio estava
invertido:

```c
if (!sdl_driver_init()) options.disable_input = TRUE;
```

`sdl_driver_init()` devolve `STATUS_SUCCESS` (=0) quando **dá certo**, então o `!` liga o
`disable_input` quando o SDL **funciona** (para não duplicar device). Com `Enable SDL=0` ele
devolve `STATUS_NOT_SUPPORTED` (≠0) e o `disable_input` fica **FALSE** — o backend evdev
segue ativo e sintetiza os devices.

**Medido** (removendo o `EnableHidraw` e reiniciando o wineserver): só com `Enable SDL=0` os
devices voltam a sair sintetizados (`usage 0x05`, `out 0`, sem canal vendor). Com
`Enable SDL=0` **+** `DisableInput=1`, saem reais (`usage 0x04` + `0x3A`). Foi o mesmo
sintoma do prefixo do SimHub, que tinha só o primeiro e não enxergava o volante.

Não há dedup entre backends: cada um cria o device e `is_hidraw_enabled` rejeita o que não
bate (as linhas `ignoring non-hidraw device` no trace são normais).

- ⚠️ **A chave é `Services\winebus`, NÃO `Services\winebus\Parameters`.** O driver nunca lê
  a subchave; escrever lá é ignorado **em silêncio**. Esse erro custou três dias e invalidou
  quatro conclusões "medidas" (histórico, Fase 3).
- ⚠️ **O canal de debug é `WINEDEBUG=+hid`** (`bus_main_thread`); `+plugplay` não mostra as
  decisões de backend.
- ⚠️ **A enumeração tem corrida:** logo após `wineserver -k`, a primeira passada do
  `hidenum` pode não listar tudo. Medir sempre na **segunda**, com ~3 s de intervalo.
- ⚠️ **Não reintroduzir** o shim de uhid nem o joystick virtual — foram aposentados pela
  raiz (histórico, Fase 3; código do shim nos commits `ec0ad06..1e29b84`). *(O
  `DisableInput` também constava desta lista até 2026-08-15, por engano: ele nunca chegou a
  ser testado de verdade, porque era escrito na subchave errada. Hoje é metade da rede de
  segurança — ver a tabela acima.)*

### Steam: o SteamBridge

O app localiza jogos lendo `HKCU\SOFTWARE\Valve\Steam\SteamPath` → `libraryfolders.vdf` →
`steamapps/common/`. Com Steam **nativo** a chave não existe no prefixo, e apontá-la direto
não basta: os caminhos dentro do vdf são Linux absolutos. O setup monta `C:\SteamBridge`
(vdf reescrito para `Z:` + symlink do `steamapps`) e aponta o `SteamPath` para lá.

### Telemetria de jogo: Winecarte

Jogos de memória compartilhada não atravessam prefixos (namespace do wineserver é por
prefixo). O [Winecarte](https://github.com/srounce/winecarte) resolve em duas metades:

| componente | papel |
|---|---|
| `winecarte-run %command%` | nas opções do jogo no Steam; **exporta** a shm para `/dev/shm` |
| `winehub` | contra um prefixo alvo; **importa** `/dev/shm` para dentro dele |

O `run-conspitlink.sh` sobe o `winehub` sozinho (e o derruba junto, **por PID guardado** —
nunca `pkill -f`, que casaria com o winehub do SimHub e com o próprio shell). `/dev/shm`
aceita vários consumidores: ConspitLink e SimHub convivem.

- **A detecção de jogo É o attach à shm** (símbolos `GanmeOf<Jogo>::Get_GameStatus` +
  `Slot_initShareMemory` no `.pdb`). Se `Started` apareceu, a telemetria está chegando; não
  procure mecanismo separado de detecção.
- Mapas conferidos: AC (`acpmf_*`), LMU (`LMU_Data`, ✅ validado), rF2 (`$rFactor2SMMP_*$`),
  AC EVO (`acevo_pmf_*`), AMS2/PCars2 (`$pcars2$`). ⚠️ ETS2/ATS: o app abre `SCSTelemetry`,
  o Winecarte exporta `SHSCSTelemetry` — não testado. ❌ **iRacing não é exportado pelo
  Winecarte** (`Local\IRSDKMemMapFileName` + `IRSDKDataValidEvent` + `IRSDK_BROADCASTMSG`,
  se alguém for atacar).
- Jogos UDP (F1, DiRT 2.0, EA WRC, Forza) dispensam ponte — UDP para `127.0.0.1` atravessa
  sozinho. Não testado nesta bancada.

## Pegadinhas (cada uma custou uma rodada)

1. **Regra udev tem de ser `70-`**, por dois motivos: o systemd efetiva `TAG="uaccess"` em
   `73-seat-late.rules` (em `99-` a tag chega tarde e o hidraw fica root-only **em
   silêncio**); e quem dá ACL a joystick é `70-uaccess.rules` via `ID_INPUT_JOYSTICK`, que
   precisa estar atribuído **antes** (`70-conspit` < `70-uaccess` por `c` < `u`).
2. **`ATTRS{}` múltiplos têm de casar no MESMO device da cadeia.** `idVendor` mora no device
   USB; `capabilities/abs` no device de input — juntos na mesma linha **nunca casam, sem
   erro**. Saída: `ENV{ID_VENDOR_ID}`/`ENV{ID_MODEL_ID}` (postos pelo builtin `usb_id`),
   deixando uma única chave `ATTRS` por linha. Diagnóstico: `udevadm test`.
3. **O `by-id` dos pedais aponta para o canal vendor**, não para os eixos (duas collections
   na mesma interface → mesmo nome de symlink, a última vence). Usar sempre
   `/dev/input/conspit-cpp-lite`, criado pela nossa regra.
4. **O `input_id` só classifica joystick se houver botões.** Pedais (e provavelmente freio
   de mão/câmbio Hall) precisam do `ENV{ID_INPUT_JOYSTICK}="1"` manual — e por isso a linha
   genérica de fuzz/flat vem **por último** no arquivo de regras: dentro de um arquivo o
   udev processa na ordem.
5. **Nunca casar `*conspit*` em bloco** ao varrer regras instaladas — o glob pega regras de
   outros devices da marca. O `check-setup.sh` já teve esse bug e mandava `sudo rm` na regra
   errada.
6. **Os números de `hidrawN`/`eventN`/`ttyACMN` trocam a cada reenumeração** — inclusive
   entre a base e o 2º MCU. Resolver por `/dev/serial/by-id/`, `/dev/input/by-id/` (exceto
   pedais, ver 3) ou pelo `HID_ID` em `/sys/class/hidraw/*/device/uevent`, comparado **como
   número** (vem com zeros à esquerda de largura variável).
7. **Calibração (min/max) e curva dos pedais são ajustes diferentes.** Min/max é gravado
   por `$setvaluex0/1` e **não é legível de volta** — diagnostique pelo eixo (solto ≈ 0,
   batente ≈ 4095). Curva linear `xgdl00255075100` é só o default, não sinal de calibração
   perdida.
8. **Fuzz/flat é filtro do kernel Linux**, invisível para o app (que fala por hidraw) — não
   confundir com a aba `Paddles` do app, que grava na firmware do volante e vale em
   qualquer SO.

## Captura de protocolo

O app fala direto com `/dev/hidraw*`; a captura é no nível USB:

```bash
sudo modprobe usbmon
lsusb | grep -i 3514                        # Bus 005 -> usbmon5
sudo cat /sys/kernel/debug/usb/usbmon/5u
```

Para os pedais raramente é preciso: `tools/cpp_pedal.py` fala o protocolo `$` nativamente.
O canal vendor do H.AO **ainda não foi mapeado** — o mesmo padrão deve servir.

## Portabilidade entre distros

Desenvolvimento em **Fedora 44**; máquina do simulador em **CachyOS (Arch)** — ambas
validadas com hardware. O que varia:

| ponto | Fedora | Arch / CachyOS |
|---|---|---|
| pacote do `evdev-joystick` | `linuxconsoletools` | `linuxconsole` |
| pyserial | `python3-pyserial` | `python-pyserial` (⚠️ `pip` barrado pelo PEP 668) |
| **grupo dono de `/dev/ttyACM*`** | `dialout` | `uucp` |
| Wine | `wine` | `wine`, exige repo **multilib** |

⚠️ O grupo da serial é a armadilha silenciosa — **detectar** com `stat -c '%G'
/dev/ttyACM*`, nunca escrever `dialout` fixo. O que não varia: a regra udev, o `uaccess`,
`/usr/bin/evdev-joystick`, e todo o lado Wine.

**Atualizar o `check-setup.sh` sempre que um pré-requisito novo entrar.** Ele roda com o
hardware desligado de propósito (numa máquina nova a verificação vem antes de plugar).

## Escopo e disclaimers

- Foco **sim racing**. Um único setup: o do autor. Licença GPL-3.0.
- Nada aqui porta ou redistribui software de terceiros: o ConspitLink é o binário oficial da
  Conspit sob Wine; firmware/OpenFFBoard são de Ultrawipf/Conspit; a ponte de telemetria é o
  Winecarte (srounce). Este repo é análise, configuração e ajuste.
- Projeto pessoal, sem garantia nem suporte.
