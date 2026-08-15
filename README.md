# Conspit no Linux — base Ares Platinum 20Nm, pedais CPP.LITE, volante H.AO

Ferramentas e passo a passo para usar os periféricos **Conspit** no Linux, incluindo o
**ConspitLink 2.0 rodando sob Wine** com configuração e telemetria em tempo real de todos os
dispositivos.

Validado com o hardware ligado em **Fedora 44** (2026-08-12, Wine 11.14) e em **CachyOS**
(2026-08-14 e 2026-08-15, kernel 7.1, Wine 11.15). Os comandos de cada distro estão
indicados onde diferem. Se algo divergir na sua, `tools/check-setup.sh` aponta o quê.

Projeto pessoal, sem garantia nem suporte. Firmware, hardware e o projeto OpenFFBoard são
de terceiros (Ultrawipf / Conspit) — este repo não redistribui nada disso.

## O que funciona

| | estado |
|---|---|
| FFB nativo em jogos (via `hid-generic` + `hid-pidff`) | ✅ 40 slots, todos os efeitos condicionais |
| Zona morta / serrilhado dos eixos (base, pedais, volante) | ✅ corrigido por regra udev |
| Pedais CPP.LITE nativos, sem Wine (ler, monitorar, calibrar) | ✅ `tools/cpp_pedal.py` |
| Protocolo de comandos direto pela serial | ✅ documentado e testado |
| **ConspitLink 2.0 sob Wine** | ✅ config e telemetria em tempo real |
| ↳ base Ares: torque, range, filtros, presets, ângulo ao vivo | ✅ |
| ↳ pedais CPP.LITE: curvas, calibração, haptics (`Customize`) | ✅ |
| ↳ volante H.AO: botões, brilho, dashboard, paddles, Launch Control | ✅ |
| Telemetria de jogo → dash dos volantes | não investigado ainda |

A base é **OpenFFBoard 1.15.0** em hardware `F407VG` com driver **ODrive**, VID/PID próprio
`3514:0301`. Detalhes técnicos e histórico da investigação em [CLAUDE.md](CLAUDE.md); o
protocolo que o ConspitLink fala está em [docs/protocolo-conspitlink.md](docs/protocolo-conspitlink.md)
(base) e [docs/protocolo-cpp-lite.md](docs/protocolo-cpp-lite.md) (pedais).

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

Rode antes de começar, e de novo ao final. Ele funciona com o hardware desligado (pula só os
testes que dependem dele).

---

## Passo 1 — Regra udev (obrigatório)

Corrige os eixos **e** libera o acesso HID que o ConspitLink precisa.

```bash
sudo cp udev/70-conspit.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger
```

É **um arquivo só para todos os dispositivos Conspit** (VID `3514`): a seção de acesso casa
por vendor, então base, 2º MCU, pedais e volantes ficam cobertos sem uma regra por device —
foi o que fez o volante H.AO funcionar no dia em que foi ligado, sem tocar no arquivo. Se
você tinha regras antigas (`70-conspit-ares.rules`, `99-conspit*.rules`, ou a
`70-uhid-shim.rules` de versões anteriores deste repo), remova-as. O `tools/check-setup.sh`
lista o que sobrou, uma a uma.

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
python3 tools/evdev_info.py /dev/input/conspit-cpp-lite                    # pedais
python3 tools/evdev_info.py /dev/input/by-id/usb-Conspit_CONSPIT_H.AO_*-event-joystick
```

O que a regra corrige, medido antes dela:

| device | antes | o que isso é |
|---|---|---|
| base, `ABS_X` | `fuzz 255`, `flat 4095` | serrilhado no esterço + **zona morta de ~12,5%** no centro |
| pedais, 3 eixos | `fuzz 15`, `flat 255` (0–4095) | **~6% de curso morto** no começo de cada pedal |
| volante, 7 eixos | `fuzz 15/255`, `flat 255/4095` | idem nos **paddles Hall** (embreagem, bite point) |

> ⚠️ Nos pedais, **não** use `/dev/input/by-id/`. O CPP.LITE expõe duas collections HID na
> mesma interface USB, o `by-id` acaba apontando para o canal vendor (um eixo de 0–255) e
> não para os pedais. O symlink `/dev/input/conspit-cpp-lite`, criado pela regra, é o
> caminho estável para os três eixos reais. (O H.AO não sofre disso: como tem botões, o
> `input_id` classifica a collection certa sozinho.)

## Passo 2 — Verificar o hardware

```bash
python3 tools/probe_serial.py            # fala o protocolo OpenFFBoard (só leitura)
python3 tools/hid_watch.py 15            # posição nos dois canais (gire o volante)
python3 tools/cpp_pedal.py ler           # config gravada nos pedais (só leitura)
```

`probe_serial.py` deve responder `sys.0.swver? -> 1.15.0` e listar as classes ativas
(`main`, `sys`, `axis`, `fx`, `odrv`, `can`, `cananalog`). Ele acha a porta sozinho por
`/dev/serial/by-id/`; para forçar outra, passe o device como argumento.

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

Prepare o prefixo — **sem isto o app não enxerga os dispositivos**:

```bash
python3 tools/conspit_wine_setup.py
```

O script deve terminar com `tudo certo.`. Abra:

```bash
tools/run-conspitlink.sh
```

> ⚠️ **Rode o `conspit_wine_setup.py` de novo ao ligar um device Conspit novo.** Ele monta a
> lista de dispositivos a partir do que está no barramento. (Na prática o device novo já
> funciona sem isso, pela rede de segurança descrita abaixo — mas a lista é o que documenta
> a intenção, e o `check-setup.sh` cobra.)

### O que o `conspit_wine_setup.py` faz, e por quê

Duas coisas independentes:

**1. Registra a porta serial na árvore PnP do Wine.** O Wine expõe portas seriais como
dispositivos genéricos, **sem VID/PID de USB**. O `QSerialPortInfo` do Qt (que o ConspitLink
usa) enumera pela classe `Ports` do SetupAPI e tira o VID/PID do device instance ID — então
sem um nó na árvore PnP a base não aparece. O script cria esse nó e mapeia a `COM33` nos dois
lugares obrigatórios (`dosdevices/com33` e `HKLM\Software\Wine\Ports\COM33`), sempre por
`/dev/serial/by-id/...`.

**2. Põe o `winebus` no backend hidraw.** Este é o passo que faz os pedais, o volante e a
telemetria completa da base funcionarem. Por padrão o Wine entrega devices HID **sintetizados
pelo SDL**, com uma collection só: os canais vendor de 64 bytes (pedais, volantes) e a
collection de comandos da base simplesmente não existem para o app. Com o backend hidraw, o
Wine passa o descritor real e o `hidclass` separa as collections em `&Col01`/`&Col02`,
exatamente como o Windows.

> ⚠️ A chave é `HKLM\System\CurrentControlSet\Services\`**`winebus`**, **não** a subchave
> `...\winebus\Parameters`. O `winebus.sys` documenta a chave no próprio código
> (`/* @@ Wine registry key: HKLM\System\CurrentControlSet\Services\WineBus */`) e nunca lê a
> subchave. Escrever no lugar errado é ignorado **em silêncio** — foi o que atrasou este
> projeto por três dias. Se for diagnosticar backend HID no Wine, o canal é
> `WINEDEBUG=+hid` (o `+plugplay` **não** mostra essas decisões).

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
`/sys/class/hidraw/*/device/uevent`. Todas as ferramentas deste repo fazem isso.

### O app não lista um dispositivo que está ligado

Quase sempre é uma destas duas:

1. **`/dev/hidraw*` sem ACL** — o backend hidraw depende disso. `tools/check-setup.sh`
   seção 3 diz quais estão sem acesso; a correção é a regra udev do Passo 1.
2. **`winebus` fora do backend hidraw** — seção 7 do `check-setup.sh`; a correção é
   `python3 tools/conspit_wine_setup.py`.

Para ver exatamente o que o app enxerga, compile o enumerador e rode dentro do prefixo:

```bash
x86_64-w64-mingw32-gcc tools/hidenum.c -o /tmp/hidenum.exe -lhid -lsetupapi
WINEPREFIX="$PWD/.wine-conspitlink" wine /tmp/hidenum.exe
```

Cada device Conspit deve aparecer com suas duas collections (`usage 0x04` para o joystick,
`usage 0x3A` para o canal vendor de 64 bytes). ⚠️ A enumeração tem corrida: logo após um
`wineserver -k`, rode **duas vezes** com alguns segundos de intervalo.

### Calibrar os pedais

A calibração de **min/max** mora na pedaleira, não no PC, e **não é legível** por nenhum
comando — diagnostique pelo eixo: pedal solto deve marcar perto de `0`, no batente perto de
`4095`.

```bash
python3 tools/cpp_pedal.py monitorar                  # leitura crua dos três
python3 tools/cpp_pedal.py calibrar acelerador min    # com o pedal SOLTO
python3 tools/cpp_pedal.py calibrar acelerador max    # com o pedal no BATENTE
```

Dá para fazer o mesmo pela GUI do ConspitLink, que também expõe a *curva* (ajuste separado
do min/max — ver [docs/protocolo-cpp-lite.md](docs/protocolo-cpp-lite.md)).

---

## Ferramentas

| arquivo | o que faz |
|---|---|
| `tools/check-setup.sh` | verifica o ambiente inteiro e diz o que falta corrigir |
| `tools/probe_serial.py` | sonda **somente leitura** da CDC (só `?` e `!`, nunca `=`) |
| `tools/evdev_info.py` | eixos com fuzz/flat e capacidades de FFB, sem disparar efeito |
| `tools/parse_hid_rdesc.py` | decodifica report descriptor, destaca a PID usage page |
| `tools/hid_watch.py` | posição do volante em evdev e hidraw ao mesmo tempo |
| `tools/cpp_pedal.py` | lê, monitora e calibra os pedais **nativamente** (⚠️ `calibrar` escreve) |
| `tools/conspit_wine_setup.py` | nó PnP da serial + backend hidraw do winebus |
| `tools/hidenum.c` | enumera HID de dentro do prefixo Wine (diagnóstico) |
| `tools/dinput_axes.c` | mede o mapeamento de eixos do DirectInput no prefixo (diagnóstico) |
| `tools/run-conspitlink.sh` | abre o ConspitLink no prefixo isolado |
| `udev/70-conspit.rules` | zera fuzz/deadzone e libera hidraw |

> ⚠️ **É uma base de 20 Nm.** As ferramentas de diagnóstico são deliberadamente somente de
> leitura. Não mande `=`, `sys.0.save`, `sys.0.format` nem comandos de calibração do ODrive
> sem o volante livre e as mãos fora. As duas exceções que escrevem estão marcadas acima.
