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
- ⚠️ Nada disto foi verificado no hardware ainda — **a base não estava conectada** quando
  esta análise foi escrita (2026-08-12). Tudo abaixo é pesquisa de mesa e precisa de
  confirmação com o dispositivo plugado.

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
| firmware stock, VID/PID próprio | `lsusb` + responde aos comandos padrão | conecta, mas sem auto-detecção; ajuste pequeno |
| firmware forkado, comandos próprios | comandos padrão falham ou faltam classes | ConspitLink pode ser necessário para features específicas |

**Aposta inicial:** há fork. O OpenFFBoard padrão usa TMC4671 como driver de motor; esta
base usa **ODrive**, o que exige uma classe de driver própria. O núcleo do protocolo
(`sys`, `axis`, FFB) provavelmente continua igual — a divergência deve estar na classe do
motor e em features exclusivas da Conspit.

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

Perguntas a responder nessa sessão, em ordem:
1. Qual o VID/PID? Bate com `1209:ffb0`?
2. A base expõe **CDC serial**? (se sim, o caminho 3 acima é imediato)
3. Ela já aparece como joystick com FFB? (a regra udev do wiki é aplicável?)
4. O configurador oficial abre e reconhece?
5. Responde a `sys.0.id?` na serial?

## Escopo e disclaimers (a herdar do projeto do pedal)
- Foco **sim racing**. Um único setup: o do autor.
- Firmware, hardware e o projeto OpenFFBoard são de terceiros (Ultrawipf / Conspit) — este
  repo não redistribui nem substitui nada disso.
- Projeto pessoal, em andamento, sem garantia nem suporte.
