# Conspit Ares Platinum 20Nm no Linux

Ferramentas e passo a passo para usar a base **Conspit Ares Platinum 20 Nm** no Linux,
incluindo o **ConspitLink 2.0 rodando sob Wine** com controle da base em tempo real.

Validado com o hardware ligado em **Fedora 44** (2026-08-12, Wine 11.14) e em **CachyOS**
(2026-08-14, kernel 7.1, Wine 11.15) — nos dois casos incluindo o ConspitLink sob Wine.
Os comandos de cada distro estão indicados onde diferem. Se algo divergir na sua,
`tools/check-setup.sh` aponta o quê.

Projeto pessoal, sem garantia nem suporte. Firmware, hardware e o projeto OpenFFBoard são
de terceiros (Ultrawipf / Conspit) — este repo não redistribui nada disso.

## O que funciona

| | estado |
|---|---|
| FFB nativo em jogos (via `hid-generic` + `hid-pidff`) | ✅ 40 slots, todos os efeitos condicionais |
| Zona morta / serrilhado dos eixos | ✅ corrigido por regra udev |
| Pedais CPP.LITE (3 eixos, curso morto, enumeração) | ✅ mesma regra udev, via `/dev/input/conspit-cpp-lite` |
| Protocolo de comandos direto pela serial | ✅ documentado e testado |
| **ConspitLink 2.0 sob Wine** | ✅ config e telemetria em tempo real |
| Leitura de ângulo no ConspitLink | ❌ trava em `+0.00°` (cosmético — ver Limitações) |
| **Pedais CPP.LITE no ConspitLink** | ✅ via `tools/cpp_hid_shim.py` (Online, haptics, curvas) |
| Telemetria de jogo → dash dos volantes | não investigado ainda |

A base é **OpenFFBoard 1.15.0** em hardware `F407VG` com driver **ODrive**, VID/PID próprio
`3514:0301`. Detalhes técnicos e histórico da investigação em [CLAUDE.md](CLAUDE.md); o
protocolo que o ConspitLink fala está em [docs/protocolo-conspitlink.md](docs/protocolo-conspitlink.md).

---

## Pré-requisitos

```bash
git clone git@github.com:juliscreudo/conspit-ares-linux.git ~/apps/conspit-ares-linux
cd ~/apps/conspit-ares-linux
```

### Pacotes

Nada aqui depende de distro; só os nomes dos pacotes mudam.

| o que | Fedora | Arch / CachyOS |
|---|---|---|
| `evdev-joystick` (zera fuzz/deadzone) | `linuxconsoletools` | `linuxconsole` |
| pyserial | `python3-pyserial` | `python-pyserial` |
| Wine (só p/ o ConspitLink) | `wine` | `wine` — precisa do repo **multilib** habilitado |

```bash
# Fedora
sudo dnf install -y linuxconsoletools python3-pyserial python3 git wine

# Arch / CachyOS
sudo pacman -S --needed linuxconsole python-pyserial python git wine
```

Se algum nome não bater na sua distro, descubra pelo arquivo em vez de adivinhar:

```bash
pacman -F evdev-joystick          # Arch (precisa de 'pacman -Fy' uma vez)
dnf provides '*/evdev-joystick'   # Fedora
```

> ⚠️ No Arch, **não** use `pip install pyserial`: o PEP 668 bloqueia instalação global e o
> pacote da distro é o caminho certo.

### Acesso à porta serial

O grupo dono de `/dev/ttyACM*` **muda entre distros** — é `dialout` no Fedora e `uucp` no
Arch. Não chute; detecte:

```bash
# com a base ligada
grupo=$(stat -c '%G' /dev/ttyACM*)
echo "grupo do device: $grupo"
id -nG | tr ' ' '\n' | grep -qx "$grupo" || sudo usermod -aG "$grupo" "$USER"
```

Depois de `usermod` é **obrigatório fazer logout/login** — grupo novo não vale na sessão
atual.

### Verificação

Este script confere tudo o que este README pede e diz o que falta, com a correção ao lado:

```bash
tools/check-setup.sh
```

Rode antes de começar, e de novo ao final. Ele funciona com a base desligada (pula só os
testes de hardware).

---

## Passo 1 — Regra udev (obrigatório)

Corrige os eixos **e** libera o acesso HID que o ConspitLink precisa.

```bash
sudo cp udev/70-conspit.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

É **um arquivo só para todos os dispositivos Conspit** (VID `3514`): a seção de acesso casa
por vendor, então base, 2º MCU e pedais ficam cobertos sem uma regra por device. Se você
tinha regras antigas (`70-conspit-ares.rules`, `99-conspit*.rules`), remova-as — esta as
substitui. O `tools/check-setup.sh` lista o que sobrou, uma a uma.

> ⚠️ O prefixo **`70-`** é obrigatório, e por **dois** motivos:
>
> 1. O systemd efetiva o `TAG="uaccess"` em `73-seat-late.rules`. Numerada como `99-`, a
>    regra adiciona a tag tarde demais e o `/dev/hidraw*` continua root-only **em silêncio,
>    sem erro nenhum**.
> 2. Quem dá ACL a joystick é `70-uaccess.rules:61`
>    (`ENV{ID_INPUT_JOYSTICK}=="?*", TAG+="uaccess"`). Como `70-conspit` ordena antes de
>    `70-uaccess` (`c` < `u`), atribuir `ID_INPUT_JOYSTICK="1"` aqui ainda é visto por ela.

Conferir (com o hardware ligado) — `fuzz` e `flat` devem estar zerados:

```bash
python3 tools/evdev_info.py /dev/input/by-id/usb-CONSPIT_CONSPIT_ARES_*-if02-event-joystick
python3 tools/evdev_info.py /dev/input/conspit-cpp-lite    # se tiver os pedais
```

Antes da regra o eixo do volante vinha com `fuzz 255` e `flat 4095` — respectivamente um
serrilhado no esterço e uma **zona morta de ~12,5% em volta do centro**. Os três eixos dos
pedais CPP.LITE vinham com `fuzz 15` e `flat 255` em escala 0–4095, ou seja **~6% de curso
morto no começo de cada pedal**.

> ⚠️ Nos pedais, **não** use `/dev/input/by-id/`. O CPP.LITE expõe duas collections HID na
> mesma interface USB, o `by-id` acaba apontando para o canal vendor (um eixo de 0–255) e
> não para os pedais. O symlink `/dev/input/conspit-cpp-lite`, criado pela regra, é o
> caminho estável para os três eixos reais.

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

### Pedais CPP.LITE (opcional)

O `run-conspitlink.sh` sobe sozinho o `tools/cpp_hid_shim.py` quando detecta os pedais. Sem
ele o app **não lista a pedaleira** — o Wine expõe só a primeira das duas collections HID do
CPP.LITE, e o canal por onde o app conversa é justamente a segunda. O shim precisa de acesso
a `/dev/uhid`:

```bash
sudo cp udev/70-uhid-shim.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

> ⚠️ Leia o cabeçalho do arquivo antes: ele concede ao usuário da sessão a capacidade de
> criar dispositivos de entrada virtuais no kernel, o que numa sessão Wayland contorna o
> isolamento de entrada do compositor. É uma decisão consciente, não um detalhe.

Com isso o `CPP LITE` aparece Online, com Calibration, Vibration (o botão `Test` faz o haptic
vibrar) e Launch Control. O protocolo desse canal está em
[docs/protocolo-cpp-lite.md](docs/protocolo-cpp-lite.md).

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
| `tools/check-setup.sh` | verifica o ambiente inteiro e diz o que falta corrigir |
| `tools/probe_serial.py` | sonda **somente leitura** da CDC (só `?` e `!`, nunca `=`) |
| `tools/evdev_info.py` | eixos com fuzz/flat e capacidades de FFB, sem disparar efeito |
| `tools/parse_hid_rdesc.py` | decodifica report descriptor, destaca a PID usage page |
| `tools/hid_watch.py` | posição do volante em evdev e hidraw ao mesmo tempo |
| `tools/conspit_wine_setup.py` | registra o nó PnP que faz o ConspitLink enxergar a base |
| `tools/cpp_hid_shim.py` | expõe a 2ª collection HID dos pedais CPP.LITE ao app |
| `tools/hidenum.c` | enumera HID de dentro do prefixo Wine (diagnóstico) |
| `tools/run-conspitlink.sh` | abre o ConspitLink no prefixo isolado |
| `udev/70-conspit.rules` | zera fuzz/deadzone e libera hidraw |
| `udev/70-uhid-shim.rules` | acesso a `/dev/uhid` para o shim dos pedais |

> ⚠️ **É uma base de 20 Nm.** As ferramentas de diagnóstico são deliberadamente somente de
> leitura. Não mande `=`, `sys.0.save`, `sys.0.format` nem comandos de calibração do ODrive
> sem o volante livre e as mãos fora.
