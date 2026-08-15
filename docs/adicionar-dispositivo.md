# Adicionar um dispositivo Conspit que não está nesta lista

Este projeto foi feito numa bancada só: base **Ares Platinum 20 Nm**, pedais **CPP.LITE**,
volante **H.AO**. A Conspit tem outros produtos — Ares Apex, CPP.EVO, CPP.Apex, 290GP, PW1,
câmbio H, freio de mão — e **nenhum deles foi testado aqui**.

A boa notícia é que a maior parte do projeto **não depende do modelo**. A prova: o volante
H.AO foi ligado pela primeira vez em 2026-08-15 e funcionou 100% no mesmo dia — botões,
brilho, dashboard, paddles Hall, Launch Control — **sem uma linha de código específica para
ele**.

Este documento explica por que isso acontece, o que pode não funcionar, e como diagnosticar.

---

## O que já funciona sozinho, e por quê

| peça | como generaliza |
|---|---|
| Acesso a `/dev/hidraw*` e `event*` | `udev/70-conspit.rules` casa por `ATTRS{idVendor}=="3514"`, **sem PID** |
| Zerar fuzz/deadzone dos eixos | mesma regra, também por vendor |
| Backend hidraw no Wine | `Enable SDL=0` é catch-all do prefixo; vale até para device ligado depois |
| Lista `EnableHidraw` | `tools/conspit_wine_setup.py` **detecta os PIDs no barramento** |

Ou seja: ligue o dispositivo, rode `python3 tools/conspit_wine_setup.py` de novo, e há uma
boa chance de simplesmente funcionar.

---

## O que pode NÃO funcionar, e é impossível adivinhar

### 1. Dispositivo sem nenhum botão

Este é o problema real, e o caso clássico é o **freio de mão** (1 eixo, zero botões) — mas
também qualquer pedaleira.

Quem classifica um device como joystick é o builtin `input_id` do udev, e ele **exige
botões**. Um device só de eixos não é classificado, e aí:

- não ganha `ID_INPUT_JOYSTICK`, então pode não aparecer nos jogos;
- não ganha o symlink `-event-joystick` em `/dev/input/by-id/`;
- não recebe ACL do `70-uaccess.rules`.

Foi exatamente o que aconteceu com o CPP.LITE. A seção 3 da regra resolve, mas ela precisa
discriminar o nó real do canal vendor por `ATTRS{capabilities/abs}`, **e esse valor muda com
o conjunto de eixos** — no CPP.LITE é `e` (três eixos: `ABS_Y`, `ABS_Z`, `ABS_RX`). Num freio
de mão de um eixo será outro. **Só quem tem o hardware descobre.**

Quem provavelmente cai aqui:

- **CPP.EVO / CPP.Apex** — se tiverem os mesmos 3 eixos do CPP.LITE, o `capabilities/abs`
  deve ser `e` também, e só falta acrescentar o PID. É uma linha:

  ```
  # copie as duas linhas da secao 3 e troque ENV{ID_MODEL_ID}=="0005"
  # pelo PID do seu device; confirme o "e" com:
  #   cat /sys/class/input/inputNN/capabilities/abs
  ```

- **Freio de mão** — 1 eixo, zero botões. Caso 1 quase garantido.
- **Câmbio H** — ver abaixo; provavelmente também é eixo, não botão.

### 2. Ordem dos eixos diferente

Os pedais do CPP.LITE declaram os usages na ordem `Rx, Y, Z`. Outro modelo pode declarar
outra coisa, o que muda qual eixo é qual nos jogos.

### 3. Protocolo do canal vendor

`tools/cpp_pedal.py` fala o protocolo `$` capturado do CPP.LITE (documentado em
[protocolo-cpp-lite.md](protocolo-cpp-lite.md)) e tem o PID `0x0005` fixo. Um CPP.EVO
provavelmente fala algo parecido, mas isso é palpite, não medição.

### 4. Volante sem eixo analógico

O H.AO tem 6 paddles Hall, que viram **eixos**. Um volante com paddles digitais teria
**botões** e nenhum eixo — a correção de fuzz/flat simplesmente não se aplica.

### 5. Câmbio: não presuma que é botão

O reflexo é achar que câmbio é botão — uma marcha, uma tecla. **Provavelmente não é o caso
nos câmbios Conspit**: os que têm os dois modos (**sequencial e H**) costumam usar **sensores
Hall** lendo a posição da alavanca, e sensor Hall vira **eixo**, não botão.

Se for assim, o câmbio cai no **caso 1** junto com os pedais e o freio de mão: eixos, nenhum
botão, `input_id` não classifica como joystick. E há uma consequência a mais — a correção de
fuzz/flat passa a **importar** para ele: um `flat` alto no eixo da alavanca é zona morta em
volta de cada posição, o que pode atrasar ou perder o engate.

Diagnóstico: rode o passo 3 do roteiro e veja se aparece `ABS_*` em vez de `BTN_*`.

---

## Roteiro de diagnóstico

Com o dispositivo ligado por USB. Tudo aqui é **somente leitura**.

### Passo 1 — Ele aparece?

```bash
lsusb | grep -i 3514
python3 tools/evdev_info.py /dev/input/by-id/usb-*<seu-device>*-event-joystick
```

Anote o **PID** (o `3514:XXXX`).

### Passo 2 — Como é o descritor HID?

```bash
# ache o hidraw do device pelo VID/PID (os números mudam a cada replug)
for h in /sys/class/hidraw/hidraw*; do
  grep -q "v00003514p0000XXXX" "$h/device/modalias" && echo "$h"
done

python3 tools/parse_hid_rdesc.py /sys/class/hidraw/hidrawN/device/report_descriptor
```

Isto responde: quantas top-level collections? Tem canal vendor? Tem botões?

### Passo 3 — O kernel classificou como joystick?

```bash
udevadm info -q property -n /dev/input/eventNN | grep -E "ID_INPUT|ID_VENDOR_ID|ID_MODEL_ID"
cat /sys/class/input/inputNN/capabilities/abs
```

Se **não** houver `ID_INPUT_JOYSTICK=1`, você caiu no caso 1 acima. O valor de
`capabilities/abs` é o que falta para escrever a regra.

### Passo 4 — O que o app enxerga dentro do Wine?

```bash
x86_64-w64-mingw32-gcc tools/hidenum.c -o /tmp/hidenum.exe -lhid -lsetupapi
WINEPREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/conspit-ares-linux/prefix" wine /tmp/hidenum.exe
```

Deve aparecer uma linha por collection (`&Col01`, `&Col02`). Se aparecer só uma, o backend
hidraw não pegou — rode `tools/conspit_wine_setup.py` de novo.

> ⚠️ A enumeração tem corrida: logo após `wineserver -k`, a primeira passada pode não listar
> tudo. Meça sempre na **segunda**, com ~3 s de intervalo.

### Passo 5 — Capturar o protocolo do canal vendor

```bash
sudo modprobe usbmon
lsusb | grep -i 3514          # descubra o barramento (Bus 005 -> usbmon5)
sudo cat /sys/kernel/debug/usb/usbmon/5u
```

Mexa na GUI do ConspitLink e o tráfego aparece.

---

## Pedindo ajuda a um LLM

Este repositório foi construído em conversa com um agente de IA, e a documentação foi escrita
para isso funcionar de novo. O `CLAUDE.md` na raiz é um **relato completo da investigação** —
inclusive dos caminhos errados e por que estavam errados.

Um jeito que funciona:

1. Clone o repo e abra-o com um agente que leia o `CLAUDE.md` (Claude Code, por exemplo).
2. Rode o roteiro acima e colete as saídas.
3. Peça a análise dando o contexto:

   > "Este repo suporta a base Ares Platinum, pedais CPP.LITE e volante H.AO da Conspit.
   > Tenho um `<seu produto>` (`3514:XXXX`) que `<não aparece / aparece errado / ...>`.
   > Segue a saída de `lsusb`, `parse_hid_rdesc.py`, `evdev_info.py` e `hidenum.exe`.
   > Leia o CLAUDE.md, principalmente as seções sobre a regra udev e o backend do winebus,
   > e diga o que ajustar."

O caminho das pedras já está mapeado; o que falta é sempre o dado do **seu** hardware.

⚠️ **Não deixe o agente escrever na base sem você entender o comando.** É um motor de 20 Nm.
As ferramentas deste repo são de leitura de propósito — as exceções (`cpp_pedal.py calibrar`)
estão marcadas.

---

## Matriz de suporte

| dispositivo | PID | estado |
|---|---|---|
| Ares Platinum 20 Nm | `0301` | ✅ testado |
| 2º MCU da base | `0300` | ✅ testado |
| Pedais CPP.LITE | `0005` | ✅ testado |
| Volante H.AO | `0007` | ✅ testado |
| Ares Apex | ? | ⚠️ não testado — mesma família OpenFFBoard, deve funcionar |
| CPP.EVO / CPP.Apex | ? | ⚠️ não testado — provavelmente 3 eixos como o CPP.LITE: caso 1, e o `capabilities/abs` deve ser o mesmo `e` (falta só o PID). Protocolo do canal vendor: caso 3 |
| 290GP / PW1 | ? | ⚠️ não testado — se tiver botões, deve sair de graça como o H.AO |
| Câmbio (sequencial + H) | ? | ⚠️ não testado — **provavelmente eixos, não botões** (sensor Hall lendo a alavanca): caso 1 e caso 5 |
| Freio de mão | ? | ⚠️ não testado — **caso 1 é quase certo**: 1 eixo, zero botões |

O `.pdb` do ConspitLink traz classes `Ace15`, `CppLite`, `CppPro`, `CppEvo`, `FR280`,
`CSDV2` e `BootLoader` — ou seja, o mesmo app atende essa linha toda.

**Conseguiu fazer funcionar?** Abra um issue com a saída do roteiro e o modelo, para a
matriz acima crescer.
