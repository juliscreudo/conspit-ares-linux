# Conspit Ares Platinum 20Nm no Linux

Ferramentas e passo a passo para usar a base **Conspit Ares Platinum 20 Nm** no Linux,
incluindo o **ConspitLink 2.0 rodando sob Wine** com controle da base em tempo real.

Validado em **Fedora 44**, kernel 6.x, Wine 11.14, com o hardware ligado (2026-08-12).
Projeto pessoal, sem garantia nem suporte. Firmware, hardware e o projeto OpenFFBoard são
de terceiros (Ultrawipf / Conspit) — este repo não redistribui nada disso.

## O que funciona

| | estado |
|---|---|
| FFB nativo em jogos (via `hid-generic` + `hid-pidff`) | ✅ 40 slots, todos os efeitos condicionais |
| Zona morta / serrilhado dos eixos | ✅ corrigido por regra udev |
| Protocolo de comandos direto pela serial | ✅ documentado e testado |
| **ConspitLink 2.0 sob Wine** | ✅ config e telemetria em tempo real |
| Leitura de ângulo no ConspitLink | ❌ trava em `+0.00°` (cosmético — ver Limitações) |
| Telemetria de jogo → dash dos volantes | não investigado ainda |

A base é **OpenFFBoard 1.15.0** em hardware `F407VG` com driver **ODrive**, VID/PID próprio
`3514:0301`. Detalhes técnicos e histórico da investigação em [CLAUDE.md](CLAUDE.md); o
protocolo que o ConspitLink fala está em [docs/protocolo-conspitlink.md](docs/protocolo-conspitlink.md).

---

## Pré-requisitos

```bash
sudo dnf install -y linuxconsoletools python3 git
python3 -c "import serial" || pip install --user pyserial
```

Wine (o projeto foi validado com o `wine-devel` 11.14 em `/opt/wine-devel`; o `wine` dos
repositórios também deve servir):

```bash
wine --version
```

Seu usuário precisa estar no grupo **`dialout`** (acesso à porta serial):

```bash
groups | grep -q dialout || { sudo usermod -aG dialout "$USER"; echo "faça logout/login"; }
```

Clone:

```bash
git clone <este-repo> ~/apps/conspit-ares-linux
cd ~/apps/conspit-ares-linux
```

---

## Passo 1 — Regra udev (obrigatório)

Corrige os eixos **e** libera o acesso HID que o ConspitLink precisa.

```bash
sudo cp udev/70-conspit-ares.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

> ⚠️ O prefixo **`70-`** é obrigatório. O systemd aplica o `TAG="uaccess"` em
> `73-seat-late.rules`; numerada como `99-`, a regra adiciona a tag tarde demais e o
> `/dev/hidraw*` continua root-only **em silêncio, sem erro nenhum**.

Conferir (com a base ligada) — `fuzz` e `flat` devem estar zerados:

```bash
python3 tools/evdev_info.py /dev/input/by-id/usb-CONSPIT_CONSPIT_ARES_*-if02-event-joystick
```

Antes da regra o eixo do volante vinha com `fuzz 255` e `flat 4095` — respectivamente um
serrilhado no esterço e uma **zona morta de ~12,5% em volta do centro**.

## Passo 2 — Verificar o hardware

```bash
python3 tools/probe_serial.py            # fala o protocolo OpenFFBoard (só leitura)
python3 tools/hid_watch.py 15            # posição nos dois canais (gire o volante)
```

`probe_serial.py` deve responder `sys.0.swver? -> 1.15.0` e listar as classes ativas
(`main`, `sys`, `axis`, `fx`, `odrv`, `can`, `cananalog`).

---

## Passo 3 — ConspitLink 2.0 sob Wine

Baixe o **ConspitLink2.0.exe** do site oficial da Conspit e coloque na raiz do repo (ele é
proprietário e está no `.gitignore`, ~300 MB).

```bash
cd ~/apps/conspit-ares-linux
export WINEPREFIX="$PWD/.wine-conspitlink"

wineboot -u                       # cria o prefixo isolado
wine ConspitLink2.0.exe /S        # instalação silenciosa
```

Registre a base na árvore de dispositivos do Wine — **sem isto o app não a enxerga**:

```bash
python3 tools/conspit_wine_setup.py
```

O script deve terminar com `tudo certo.` e mostrar a linha do WMI com
`VID=3514  PID=0301`. Abra:

```bash
tools/run-conspitlink.sh
```

### Por que o passo do `conspit_wine_setup.py` é necessário

O Wine expõe portas seriais como dispositivos genéricos, **sem VID/PID de USB**. O
`QSerialPortInfo` do Qt (que o ConspitLink usa) enumera pela classe `Ports` do SetupAPI e
tira o VID/PID do device instance ID — então sem um nó na árvore PnP a base não aparece.
O script cria esse nó e mapeia a `COM33` nos dois lugares obrigatórios (`dosdevices/com33`
e `HKLM\Software\Wine\Ports\COM33`), sempre por `/dev/serial/by-id/...`.

Medido: **antes** do nó PnP o app não abria device nenhum; **depois**, ele abre a serial da
base. Técnica herdada da seção 11.3 do projeto irmão `~/apps/diy-ffb-pedal-linux/`,
adaptada de .NET/WMI para Qt/SetupAPI.

---

## Problemas conhecidos

### "Error: The base port is occupied"

Acontece ao **tirar o USB com o app aberto**: o handle da porta fica órfão no wineserver.
Costuma ser inofensivo (o app segue funcionando), mas para limpar:

```bash
tools/run-conspitlink.sh --limpo
```

Evita-se fechando o app antes de desconectar a base.

### Os números de `/dev/ttyACM*`, `hidraw*` e `event*` mudam

A cada reenumeração do kernel (replug, suspend/resume) os números trocam — inclusive
**entre a base e o segundo MCU da base**. Nunca fixe `ttyACM2`/`hidraw2`/`event21` em lugar
nenhum. Resolva sempre por `/dev/serial/by-id/`, `/dev/input/by-id/` ou pelo VID/PID em
`/sys/class/hidraw/*/device/uevent`. Todas as ferramentas deste repo já fazem isso.

### O ângulo do ConspitLink fica em `+0.00°`

Defeito **dentro da lógica do ConspitLink**, não do Linux nem do Wine. Todas as camadas
abaixo foram medidas e estão corretas: o kernel recebe a posição, ela está no report HID
(report ID 1, bytes 18–19), e o `wine control joy.cpl` mostra o eixo X acompanhando o
volante perfeitamente. O app chega a chamar `GetDeviceState` 1534×/20s e ainda assim
exibe 0.00. A cadeia de eliminação completa está no CLAUDE.md.

**Não afeta nada**: é indicador de tela, não participa do FFB nem da configuração. Se o
número interessar, ele está disponível nativamente (`axis.0.pos?` pela serial, ou
`tools/hid_watch.py`).

---

## Ferramentas

| arquivo | o que faz |
|---|---|
| `tools/probe_serial.py` | sonda **somente leitura** da CDC (só `?` e `!`, nunca `=`) |
| `tools/evdev_info.py` | eixos com fuzz/flat e capacidades de FFB, sem disparar efeito |
| `tools/parse_hid_rdesc.py` | decodifica report descriptor, destaca a PID usage page |
| `tools/hid_watch.py` | posição do volante em evdev e hidraw ao mesmo tempo |
| `tools/conspit_wine_setup.py` | registra o nó PnP que faz o ConspitLink enxergar a base |
| `tools/run-conspitlink.sh` | abre o ConspitLink no prefixo isolado |
| `udev/70-conspit-ares.rules` | zera fuzz/deadzone e libera hidraw |

> ⚠️ **É uma base de 20 Nm.** As ferramentas de diagnóstico são deliberadamente somente de
> leitura. Não mande `=`, `sys.0.save`, `sys.0.format` nem comandos de calibração do ODrive
> sem o volante livre e as mãos fora.
