# Protocolo que o ConspitLink 2.0 fala com a base

Extraído das strings de `ConspitLink2.0.exe` (v1.1.21) em 2026-08-12, e confirmado contra o
hardware. Não é engenharia reversa de binário: são literais de formato Qt (`%1`) legíveis
com `strings`.

```
strings -a "ConspitLink2.0.exe" | grep -aE "^[a-z]{2,10}\.[0-9]\.[a-zA-Z_]+[?=;:]"
```

## Formato

É o **protocolo texto do OpenFFBoard**, o mesmo documentado em
https://github.com/Ultrawipf/OpenFFBoard/wiki/Commands — com uma diferença:

> ⚠️ O ConspitLink termina cada comando com **`;`**, não com `\n`.
> As nossas ferramentas usam `\n` e a base aceita os dois.

Consulta é `cls.0.cmd?`, escrita é `cls.0.cmd=<valor>`. A resposta vem como
`[cls.0.cmd?|valor]`.

## Os 44 comandos que o app usa

### axis (23) — configuração do eixo
| comando | o que é na UI |
|---|---|
| `axis.0.power?` `=` | Max Force |
| `axis.0.degrees?` `=` | Range (360/540/900/1080) |
| `axis.0.esgain?` `=` | Stop Feel (Soft/Medium/Stiff) |
| `axis.0.axisdamper?` `=` | Mechanical Damper |
| `axis.0.axisfriction?` `=` | Mechanical Friction |
| `axis.0.axisinertia?` `=` | Mechanical Inertia |
| `axis.0.idlespring?` `=` | mola de repouso |
| `axis.0.fxratio?` `=` | Effects Gain |
| `axis.0.maxspeed?` `=` | Rotation Speed |
| `axis.0.invert?` `=`, `axis.0.invertEffect=` | inversão |
| `axis.0.zeroenc?` | **Center Calibration** |
| `axis.0.connected?` | ⚠️ **não existe** no `axis.0.help` do firmware |

### fx (12) — efeitos e filtros
`fx.0.damper`, `fx.0.friction`, `fx.0.inertia`, `fx.0.spring`,
`fx.0.filterCfFreq` (Filter Frequency), `fx.0.filterCfQ` (Filter Sharpness) — todos com
`?` e `=`.

### odrv (5) — controladora de motor
`odrv.0.errors?`, `odrv.0.state?`, `odrv.0.vbus?`, `odrv.0.hostname?` `=`
(o `hostname` é descrito no firmware como "AresName").

### sys (1)
`sys.0.save?` — grava na flash.

### estrs (3) — classe não presente neste firmware
`estrs.0.Boot:`, `estrs.0.CodeRight`, `estrs.0.Retrieval:`. Também aparecem
`esths.0.*` (`Version`, `iap`, `Set_Host`, `Get_Sleep`, `Set_Sleep`, `Clr_Sleep`,
`Retrieval`). Nenhuma delas está no `sys.0.lsactive?` da Ares — devem pertencer a outros
produtos Conspit (volantes/pedais) ou ao bootloader.

## O que NÃO está na lista, e por que importa

**Não há nenhum comando de leitura de posição/ângulo.** Nem `axis.0.pos`, nem
`axis.0.curpos`, nem equivalente. Confirmado por busca exaustiva na lista.

Ou seja: o display de ângulo (`+0.00°`) do ConspitLink **não vem da serial**. Ele vem do
DirectInput — o app chama `GetDeviceState` com `DIJOYSTATE2` (272 bytes) em laço
(1534 chamadas em 20 s, medido com `WINEDEBUG=+dinput`).

Isso é relevante porque o firmware **tem** os comandos de posição (`axis.0.pos?`,
`axis.0.curpos?`, ambos respondendo ao vivo — ver CLAUDE.md). O ConspitLink só não os usa.

## Nomes internos (do `ConspitLink2.0.pdb`, 77 MB de símbolos)

A base **Ares Platinum é tratada internamente pelas classes `AresApex*`** — "Ares Platinum"
só aparece como string de exibição. O caminho do ângulo é
`AresApexManger::Base_Angle` → `Base_SetHomePageAngle` / `HomePage_SetAngle`, alimentado por
`AresApexWidget::onAceAngleValue`.

Outras famílias de dispositivo nas classes: `Ace15`, `CppLite`, `CppPro`, `CppEvo`,
`FR280`, `CSDV2`, `BootLoader`.
