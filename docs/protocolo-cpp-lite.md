# Protocolo que o ConspitLink fala com os pedais CPP.LITE

Capturado no hardware em 2026-08-14, com um shim de HID no meio do caminho (ferramenta desde
então aposentada — ver "O backend do winebus" no CLAUDE.md). Não é engenharia reversa de
binário: é o tráfego real entre o app e a pedaleira.

Hoje esse canal é acessível **nativamente**, sem Wine e sem o app: `tools/cpp_pedal.py`.

**É um protocolo diferente do da base.** A Ares fala o protocolo texto do OpenFFBoard
(`cls.inst.cmd?`, ver [protocolo-conspitlink.md](protocolo-conspitlink.md)); os pedais falam
um protocolo próprio da Conspit, com prefixo `$`.

## Transporte

Canal HID vendor, **não** serial — os pedais não expõem CDC.

| | |
|---|---|
| device | `3514:0005`, segunda top-level collection do descritor |
| report ID | `2` |
| tamanho | 64 bytes (1 de report ID + 63 de payload) |
| formato | ASCII, terminado em `\0`, resto do buffer zerado |

⚠️ **Histórico:** essa segunda collection não aparecia sob Wine enquanto o `winebus` estava
no backend SDL, e por isso o app não achava os pedais. Resolvido em 2026-08-15 pondo o
`winebus` no backend hidraw — ver "O backend do winebus" no CLAUDE.md. Não é mais preciso
nenhum intermediário.

## Handshake de conexão

Os 12 comandos que o app dispara ao encontrar a pedaleira, na ordem, com as respostas reais
de uma CPP.LITE de 3 pedais (só o acelerador conectado no momento da captura):

| comando | resposta | o que é |
|---|---|---|
| `$version` | `v2.2.0` | firmware da pedaleira |
| `$getPWM1` | `getPWM1100` | intensidade do haptic 1 (0–100) |
| `$getPWM2` | `getPWM2100` | haptic 2 |
| `$getPWM3` | `getPWM3100` | haptic 3 |
| `$gselect1` | `gse16` | seleção/modo do pedal 1 |
| `$gselect2` | `gse26` | pedal 2 |
| `$gselect3` | `gse36` | pedal 3 |
| `$gdlinex` | `xgdl00051646100` | curva do eixo X |
| `$gdliney` | `ygdl00427694100` | curva do eixo Y |
| `$gdlinez` | `zgdl00255075100` | curva do eixo Z |
| `$getlimity` | `$limity100` | limite de curso |
| `$getbarlimit` | `$barlimit` | limite da barra |

Padrão das respostas: o eco do comando sem o `$`, seguido do valor. A resposta é imediata,
uma por comando; a pedaleira **não** transmite nada espontaneamente (o shim mede zero
relatórios não solicitados).

### O formato do `gdline` — a curva do pedal

As três respostas se segmentam em **cinco pontos** (quatro de dois dígitos e o último de
três), que é a curva do "Pedal Curve Mapping":

```
xgdl 00 05 16 46 100     acelerador, progressiva
ygdl 00 42 76 94 100     freio, sobe rápido e satura
zgdl 00 25 50 75 100     embreagem, exatamente linear
```

O eixo Z ter saído linear perfeito é consistente com um canal **sem pedal conectado e sem
configuração** — é a curva padrão. Decodificação inferida de três amostras; para confirmar,
mexa na curva na GUI com o shim em `-v` e veja o comando de escrita correspondente.

⚠️ **Não interpretar o valor bruto do eixo como "percentual de curso".** Cada canal tem
calibração própria guardada na pedaleira: um freio hidráulico marca uma linha de base alta
com o pedal solto, e o zero real vem da calibração, não do zero do ADC (0–4095). Confundir
isso leva a concluir que o pedal está "pisado em repouso" quando não está.

## O que ainda não foi mapeado

- **Comandos de escrita.** A captura acima é só o handshake de leitura. Os de calibração
  foram capturados (`$setvaluex0`/`$setvaluex1`, ver `tools/cpp_pedal.py`); os de curva e
  vibração ainda não. Sem o shim, a captura agora é por `usbmon` (ver CLAUDE.md).
- **Semântica do `gselect`** (`gse16` = pedal 1, valor 6?) e o formato exato do `gdline`.
- **Haptics em jogo.** O `Vibration Mode` tem `Customize`, `SimHub` e `iRacing`. No
  `Customize` o próprio ConspitLink alimenta o efeito a partir da telemetria dele; os outros
  dois esperam software externo, que sob Linux é outro problema (o SimHub teria de rodar em
  Wine e enxergar a pedaleira — provavelmente o mesmo shim serve, não testado).

## Atualização de firmware

Com o shim no ar, o app **detecta firmware novo e oferece atualizar**. Não foi feito e não é
recomendado por aqui: um flash interrompido no meio do caminho, com um canal HID
intermediado por um shim de terceiros, é risco desnecessário. Se for atualizar, faça pelo
Windows.

## Calibração vs. curva — dois ajustes diferentes (2026-08-15)

Confundi os dois numa análise anterior; vale registrar a distinção.

| ajuste | comando | é legível? |
|---|---|---|
| **min/max** de cada eixo | `$setvaluex0` / `$setvaluex1` | **não** — nenhuma das 12 consultas o devolve |
| **curva** (Pedal Curve Mapping) | `$gdlinex` e afins | sim |

Ou seja: `xgdl00255075100` (linear) **não** é sinal de calibração perdida — é só a curva
linear, que é o padrão. O que de fato havia sido perdido era o **min/max**, e a evidência
disso era o eixo, não o protocolo: `ABS_RX` marcava **4095 com o pedal solto**.

**Resolvido em 2026-08-15**, calibrando pela GUI do ConspitLink: o acelerador voltou a
marcar `0` em repouso e o gráfico do app ficou idêntico ao do Windows. O mesmo pode ser
feito sem o app com `tools/cpp_pedal.py calibrar acelerador min|max`.

⚠️ **Diagnostique min/max pelo eixo, não pelo `$gdline`.** Pedal solto deve marcar perto de
0 e no batente perto de 4095:

```bash
python3 tools/cpp_pedal.py monitorar
```

**Lição que continua valendo:** não existe `salvar`/`restaurar` desses valores, e o min/max
sequer é legível — uma ferramenta que escreva na pedaleira não tem como fazer backup do que
mais importa.
