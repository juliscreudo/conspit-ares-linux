# Protocolo que o ConspitLink fala com os pedais CPP.LITE

Capturado no hardware em 2026-08-14, com o `tools/cpp_hid_shim.py -v` no meio do caminho.
Não é engenharia reversa de binário: é o tráfego real entre o app e a pedaleira.

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

⚠️ Essa segunda collection **não existe sob Wine sem o shim** — ver a seção "Pedais CPP.LITE"
no CLAUDE.md. É por isso que o app não achava os pedais.

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

Padrão das respostas: o eco do comando sem o `$`, seguido do valor. O `gdline` traz três
grupos de números — provavelmente os pontos da curva do pedal. A resposta é imediata, uma
por comando; a pedaleira **não** transmite nada espontaneamente (o shim mede zero relatórios
não solicitados).

## O que ainda não foi mapeado

- **Comandos de escrita.** A captura acima é só o handshake de leitura. Mexer em curva,
  vibração ou calibração na GUI gera comandos que ainda não foram capturados — rode o shim
  com `-v` enquanto mexe, e o tráfego aparece.
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
