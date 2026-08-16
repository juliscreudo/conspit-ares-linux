# Conspit no Linux — base Ares Platinum 20Nm, pedais CPP.LITE, volante H.AO

**🇧🇷 Português** · [🇬🇧 English](README.md)

Ferramentas e passo a passo para usar os periféricos **Conspit** no Linux, incluindo o
**ConspitLink 2.0 rodando sob Wine** com configuração e telemetria em tempo real de todos os
dispositivos.

### O que este projeto é — e o que não é

Isto é **a solução que eu usei** para fazer meus dispositivos Conspit funcionarem no Linux,
organizada para outra pessoa conseguir repetir.

**Não portei nada.** Não há driver reescrito, nem software reimplementado, nem versão Linux
do ConspitLink. O app é o **binário oficial da Conspit, sem modificação**, rodando sob Wine.
O que este repositório contém é o resultado de **análise, configuração e ajuste**:

- descobrir como cada dispositivo se apresenta ao kernel, e o que o Linux erra por padrão;
- uma regra `udev` que corrige isso;
- os ajustes de registro que fazem o Wine entregar o hardware ao app do jeito certo;
- ferramentas de diagnóstico (quase todas somente de leitura) para você conferir cada etapa;
- a documentação do que foi medido, **inclusive dos caminhos errados**.

Nada aqui redistribui software de terceiros. O ConspitLink é da **Conspit** e você o baixa do
site oficial; o firmware da base é o **[OpenFFBoard](https://github.com/Ultrawipf/OpenFFBoard)**
(Ultrawipf); a ponte de telemetria é o
**[Winecarte](https://github.com/srounce/winecarte)** (srounce). O mérito do que funciona é
em boa parte desses projetos — aqui só se juntou as peças.

Projeto pessoal, sem garantia nem suporte.

Validado com o hardware ligado em **Fedora 44** (2026-08-12, Wine 11.14) e em **CachyOS**
(2026-08-14 e 2026-08-15, kernel 7.1, Wine 11.15). Os comandos de cada distro estão
indicados onde diferem. Se algo divergir na sua, `tools/check-setup.sh` aponta o quê.

Licenciado sob **[GPL-3.0](LICENSE)**: use, estude, modifique e forke à vontade. Quem
distribuir uma versão modificada é obrigado a manter o código aberto sob a mesma licença —
ninguém fecha isto num produto proprietário.

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
| **Telemetria de jogo → haptics e dash** | ✅ via [Winecarte](https://github.com/srounce/winecarte) — validado no Le Mans Ultimate |
| ↳ iRacing | ❌ o Winecarte não exporta o mapa do iRacing |

> **Tem outro periférico Conspit?** (Ares Apex, CPP.EVO/Apex, 290GP, PW1, câmbio, freio de
> mão.) Boa parte do projeto casa por **vendor**, não por modelo — o volante H.AO funcionou
> 100% no dia em que foi ligado, sem código específico. Veja
> [docs/adicionar-dispositivo.md](docs/adicionar-dispositivo.md) para o roteiro de
> diagnóstico e a matriz do que foi testado.

A base é **OpenFFBoard 1.15.0** em hardware `F407VG` com driver **ODrive**, VID/PID próprio
`3514:0301`. As diretivas técnicas estão em [CLAUDE.md](CLAUDE.md) e o histórico completo
da investigação em [docs/historico-investigacao.md](docs/historico-investigacao.md); o
protocolo que o ConspitLink fala está em [docs/protocolo-conspitlink.md](docs/protocolo-conspitlink.md)
(base) e [docs/protocolo-cpp-lite.md](docs/protocolo-cpp-lite.md) (pedais).

---

## O caminho, em 4 passos

| passo | o que resolve | precisa? |
|---|---|---|
| **1 — Regra udev** | zona morta e serrilhado dos eixos; acesso HID | **obrigatório**, mesmo sem Wine |
| **2 — Verificar o hardware** | confirma que a base responde antes de seguir | recomendado |
| **3 — ConspitLink sob Wine** | configurar base, pedais e volante pela GUI oficial | opcional |
| **4 — Telemetria de jogo** | haptics no modo `Customize` e dash do volante | opcional, depende do 3 |

Se você só quer **FFB nos jogos com os eixos corretos**, o Passo 1 basta e você pode parar
ali. Os passos 3 e 4 existem para ter a configuração e a telemetria como no Windows.

A qualquer momento, `tools/check-setup.sh` diz onde você está e o que falta.

---

## Pré-requisitos

```bash
git clone https://github.com/juliscreudo/conspit-linux-configurator.git ~/apps/conspit-linux-configurator
cd ~/apps/conspit-linux-configurator
```

### Pacotes

Nada aqui depende de distro; só os nomes dos pacotes mudam.

| o que | para quê | Fedora | Arch / CachyOS |
|---|---|---|---|
| `evdev-joystick` | zera fuzz/deadzone (Passo 1) | `linuxconsoletools` | `linuxconsole` |
| pyserial | ferramentas de diagnóstico (Passo 2) | `python3-pyserial` | `python-pyserial` |
| Wine | rodar o ConspitLink (Passo 3) | `wine` | `wine` — precisa do repo **multilib** |
| mingw-w64 *(opcional)* | compilar o `hidenum.exe` de diagnóstico | `mingw64-gcc` | `mingw-w64-gcc` |

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

### Winecarte (telemetria de jogo)

**Só necessário para o Passo 4.** Pule se não vai usar haptics em jogo nem o dash do
volante.

O **[Winecarte](https://github.com/srounce/winecarte)** (de
[srounce](https://github.com/srounce)) é o que faz a telemetria atravessar a fronteira entre
o prefixo do jogo e o do ConspitLink. **Não é parte deste projeto** e é instalado à parte:

| repositório | o que é |
|---|---|
| **[srounce/winecarte](https://github.com/srounce/winecarte)** | a ponte em si (`winecarte-run`, `winehub`, `wine2linux.exe`) |
| **[srounce/linux-simracing-utils](https://github.com/srounce/linux-simracing-utils)** | instalador do mesmo autor; é o **jeito mais fácil** de obter o Winecarte, e já traz SimHub e CrewChief |

O caminho recomendado é o instalador:

```bash
git clone https://github.com/srounce/linux-simracing-utils
cd linux-simracing-utils
bash install.sh          # aceite os defaults; o Winecarte é um dos componentes
```

> Ele pergunta o que instalar. **O componente obrigatório aqui é o Winecarte**; SimHub e
> CrewChief são independentes deste projeto e você pode pular.

> ⚠️ Escolha bem a pasta antes de instalar: o caminho fica gravado nos lançadores. Se mover
> depois, rode o `install.sh` de novo do novo lugar.

O `tools/run-conspitlink.sh` **acha o Winecarte sozinho** se ele estiver no `PATH` ou em
`~/apps/linux-simracing-utils/bin/`. Sem ele o app abre normalmente — só sem telemetria de
jogo.

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

## Passo 2 — Verificar o hardware (recomendado)

Com a base **ligada por USB**. Tudo aqui é somente leitura — nada é escrito no hardware.

```bash
python3 tools/probe_serial.py            # fala o protocolo OpenFFBoard (só leitura)
python3 tools/hid_watch.py 15            # posição nos dois canais (gire o volante)
python3 tools/cpp_pedal.py ler           # config gravada nos pedais (só leitura)
```

`probe_serial.py` deve responder `sys.0.swver? -> 1.15.0` e listar as classes ativas
(`main`, `sys`, `axis`, `fx`, `odrv`, `can`, `cananalog`). Ele acha a porta sozinho por
`/dev/serial/by-id/`; para forçar outra, passe o device como argumento.

---

## Passo 3 — ConspitLink 2.0 sob Wine (opcional)

Baixe o **ConspitLink2.0.exe** do site oficial da Conspit e coloque na raiz do repo. Ele é
proprietário (~300 MB), está no `.gitignore` e **não é redistribuído aqui** — você precisa
obtê-lo da Conspit.

```bash
cd ~/apps/conspit-linux-configurator # a pasta do clone
export WINEPREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/conspit-ares-linux/prefix"
mkdir -p "$WINEPREFIX"

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

### Atalho no menu (opcional)

Para abrir clicando, em vez de pelo terminal:

```bash
tools/instalar-atalho.sh              # instala
tools/instalar-atalho.sh --remover    # desinstala
```

Ele reaproveita o ícone que o Wine já extraiu do `.exe` e aponta para o
`run-conspitlink.sh` — ou seja, o atalho passa pelas mesmas verificações e sobe a ponte de
telemetria.

> O Wine cria um atalho **próprio** ao instalar o app, em
> `~/.local/share/applications/wine/Programs/`. Ele funciona, mas executa o `.lnk` direto:
> pula as verificações e não sobe a ponte. O nosso mora fora daquela pasta justamente para o
> `winemenubuilder` não o sobrescrever. O script diz como esconder o do Wine, se quiser.

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

## Passo 4 — Telemetria de jogo (opcional)

Necessário para os **haptics dos pedais no modo `Customize`** e para o **dash / rev lights do
volante**, que o próprio ConspitLink alimenta. Nada disto é preciso para configurar a base,
os pedais ou o volante.

O problema: os jogos escrevem telemetria em memória compartilhada nomeada, e o namespace de
objetos do wineserver é **por prefixo**. O jogo roda no prefixo do Proton, o ConspitLink no
dele, e um não enxerga a memória do outro — o app fica em `Not Started` para sempre.

Quem resolve é o **[Winecarte](https://github.com/srounce/winecarte)**, que faz a ponte em
duas metades — instalado nos [Pré-requisitos](#winecarte-telemetria-de-jogo).

1. **No jogo**, em *Propriedades → Opções de Lançamento* no Steam:

   ```
   winecarte-run %command%
   ```

   Isto exporta a memória compartilhada do jogo para `/dev/shm`.

2. **No ConspitLink**, nada a fazer: `tools/run-conspitlink.sh` sobe a outra metade sozinho
   (o `winehub`, apontado para este prefixo) e avisa `ponte de telemetria: no ar`. Para
   desligar, `--sem-ponte`.

Entre numa sessão do jogo: o `Select Game` deve trocar de `Not Started` para **`Started`**.

> A detecção **é** o attach à memória compartilhada — não há mecanismo separado. Se o
> `Started` apareceu, a telemetria está chegando; se não apareceu, a ponte é que falhou.

### Jogos cobertos

Validado no **Le Mans Ultimate**. Os nomes dos mapas conferem também para **Assetto Corsa**,
**AC EVO**, **rFactor 2** e **AMS2 / Project Cars 2**.

> ❌ **iRacing não funciona por esta rota** — o Winecarte não exporta o mapa dele
> (`Local\IRSDKMemMapFileName`).

> Jogos de telemetria **UDP** (família F1, DiRT Rally 2.0, EA WRC, Forza) não precisam de
> ponte nenhuma: UDP é rede no kernel e atravessa a fronteira Wine/Proton sozinho. Aponte a
> telemetria do jogo para `127.0.0.1`. **Não testado aqui** — nenhum desses jogos nesta
> bancada.

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
make -C tools     # requer mingw-w64
WINEPREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/conspit-ares-linux/prefix" wine tools/hidenum.exe
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
| `tools/conspit-prefixo.sh` | resolve o caminho do prefixo (incluído pelos outros) |
| `tools/instalar-atalho.sh` | cria o atalho do app no menu (usa o ícone do Wine) |
| `tools/run-conspitlink.sh` | abre o ConspitLink no prefixo isolado |
| `udev/70-conspit.rules` | zera fuzz/deadzone e libera hidraw |

> ⚠️ **É uma base de 20 Nm.** As ferramentas de diagnóstico são deliberadamente somente de
> leitura. Não mande `=`, `sys.0.save`, `sys.0.format` nem comandos de calibração do ODrive
> sem o volante livre e as mãos fora. As duas exceções que escrevem estão marcadas acima.
