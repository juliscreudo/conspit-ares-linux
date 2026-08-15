# Próximos passos — análise para discussão

Levantado em **2026-08-15**, depois de o ConspitLink passar a funcionar com todos os
dispositivos (base Ares Platinum, pedais CPP.LITE, volante H.AO) via backend hidraw do
`winebus`. Nada aqui foi executado ainda — é material de decisão.

**Três decisões pendentes do usuário estão marcadas com ❓ e bloqueiam a execução.**

---

## 1. Onde ficam o prefixo Wine e o instalador

### Fatos medidos

| item | tamanho | onde |
|---|---|---|
| `.wine-conspitlink/` | **876 MB** | raiz do repo (gitignored) |
| `ConspitLink2.0.exe` | 300 MB | raiz do repo (gitignored) |
| código versionado | ~50 KB | — |

⚠️ O CLAUDE.md estimava "~500 MB" para o prefixo. São 876 MB (`drive_c/windows` 376 MB +
`Program Files (x86)` 495 MB, incluindo o `.pdb` de 77 MB).

**O prefixo é movível** — verificado: zero caminhos absolutos do repo em `system.reg` e
`user.reg`. O `dosdevices/c:` é relativo (`../drive_c`) e o `com33` aponta para
`/dev/serial/by-id/`, fora do repo. Mover = `mv` + ajustar 3 referências, todas derivadas de
`$repo`: `conspit_wine_setup.py`, `check-setup.sh`, `run-conspitlink.sh`.

### O que o arranjo atual custa

`git clean -xfd` — comando corriqueiro — **apaga 1,2 GB de estado calibrado**. Qualquer
backup de `~/apps` carrega isso junto. E conceitualmente é runtime dentro de um checkout de
código.

### Opções

| opção | prós | contras |
|---|---|---|
| **`~/.local/share/conspit-linux/prefix`** (XDG) | convenção reconhecida; sobrevive a `git clean` e a re-clonar | desinstalar vira dois lugares |
| `~/.wine-conspitlink` | simples, parecido com `~/.wine` | polui a home, não é XDG |
| manter no repo | autocontido; "apagar a pasta desfaz tudo" | os problemas acima |

### Recomendação

XDG como default, sobreponível por `CONSPIT_PREFIX`. O instalador **sai do repo**: o script
passa a aceitar `--instalador ~/Downloads/ConspitLink2.0.exe`, já que só é usado uma vez —
removendo 300 MB de vez.

Migração com o app fechado e `wineserver -k` antes.

❓ **DECISÃO A: XDG (recomendado) ou manter no repo?**

### Achado lateral a corrigir junto

O Wine mapeia `/dev/ttyACM*` sozinho em **com34/com35**, além dos `ttyS*` em com1–32. A
COM33 continua melhor (aponta para o `by-id` estável), mas o comentário no
`conspit_wine_setup.py` que diz "o wineboot preenche com1..com32 varrendo `/dev/ttyS*`" está
incompleto.

---

## 2. Atalho `.desktop`

### Fatos

O `winemenubuilder` **já criou um sozinho**:

```
~/.local/share/applications/wine/Programs/Conspit Link 2.0/Conspit Link 2.0.desktop
Exec=env "WINEPREFIX=/home/.../conspit-ares-linux/.wine-conspitlink" wine "C:\...\Conspit Link 2.0.lnk"
Icon=4796_ConspitLink2.0.0
StartupWMClass=conspitlink2.0.exe
```

Ícone já extraído em `~/.local/share/icons/hicolor/64x64/apps/4796_ConspitLink2.0.0.png`, e
o `StartupWMClass` já está correto (é o que faz o ícone agrupar direito na barra de tarefas).

### O problema

Ele executa o `.lnk` direto, **pulando os pre-flights** do `run-conspitlink.sh` — backend
hidraw e device fora do `EnableHidraw` —, que são justamente as duas verificações que evitam
a falha confusa de "o app abre mas não lista nada". Além disso o `winemenubuilder`
**sobrescreve** esse arquivo em updates, e o caminho do prefixo está hardcoded.

### Recomendação

`tools/instalar-atalho.sh` que gera `~/.local/share/applications/conspit-link.desktop`
chamando o `run-conspitlink.sh`, reaproveita o ícone já extraído, mantém o `StartupWMClass`,
e desativa o `winemenubuilder` no prefixo para não voltar.

⚠️ **Depende do ponto 1** (o `Exec` carrega o caminho do prefixo). Fazer **1 antes de 2**.

---

## 3. Reorganizar `tools/` em subpastas

### Fatos

10 arquivos, 1806 linhas. Categorias naturais:

| categoria | arquivos |
|---|---|
| setup / execução | `check-setup.sh`, `conspit_wine_setup.py`, `run-conspitlink.sh` |
| diagnóstico read-only | `probe_serial.py`, `evdev_info.py`, `hid_watch.py`, `parse_hid_rdesc.py` |
| diagnóstico dentro do Wine (mingw) | `hidenum.c`, `dinput_axes.c` |
| escreve no device | `cpp_pedal.py` |

### Recomendação: **não reorganizar**

O custo é real — README e CLAUDE.md têm dezenas de referências `tools/x.py` que quebrariam —
e 10 arquivos numa pasta plana são perfeitamente navegáveis. O ganho seria estético. A
distinção que de fato importa numa base de 20 Nm (**read-only vs. escreve**) já está
resolvida por convenção documentada nas tabelas.

**O que vale, e é barato:** um `tools/Makefile` de ~5 linhas para os dois `.c`, cujo comando
de compilação hoje só existe no cabeçalho do arquivo.

Reavaliar se um dia passar de ~15 ferramentas.

---

## 4. Outros periféricos Conspit

### O projeto já é ~80% genérico — e há prova empírica

**O volante H.AO funcionou 100% no dia em que foi ligado, sem uma linha de código específica
para ele** (botões, brilho, dashboard, paddles Hall, Launch Control). Isso não foi sorte:

- `udev/70-conspit.rules` seção 1 casa por `ATTRS{idVendor}=="3514"` **sem PID** → qualquer
  device Conspit ganha ACL de hidraw e `uaccess` automaticamente;
- `conspit_wine_setup.py` **detecta os PIDs do barramento** e escreve o `EnableHidraw`;
- `Enable SDL=0` é catch-all que cobre até device ligado depois do setup.

### O que NÃO é genérico

17 das 28 ocorrências de PID no repo estão em `udev/70-conspit.rules`.

1. **fuzz/flat** — hoje uma linha por PID, porque os valores se medem device a device. Mas dá
   para generalizar: uma regra que zere fuzz/flat de *qualquer* joystick Conspit cobriria
   tudo de uma vez. O por-PID era conservadorismo. **Vale rediscutir.**
2. **A armadilha do `by-id` em device sem botões** — os pedais precisam de
   `ATTRS{capabilities/abs}=="e"` porque o `input_id` não os classifica sozinho (não têm
   botão). Um CPP.EVO/Apex deve ter a mesma estrutura mas **outro conjunto de eixos** → outro
   valor de `capabilities`. Não dá para adivinhar.
   ⚠️ **Freio de mão é o caso clássico do problema**: 1 eixo, zero botões.
3. **`cpp_pedal.py`** — PID `0x0005` fixo; o protocolo `$` foi capturado do CPP.LITE.

### Recomendação

Criar `docs/adicionar-dispositivo.md` com:

- **roteiro de diagnóstico**: `lsusb` → `parse_hid_rdesc.py` → `hidenum.exe` (dentro do
  prefixo) → `evdev_info.py` → o que reportar num issue;
- **matriz de suporte**, separando claramente:
  - ✅ **testado**: Ares Platinum 20 Nm, CPP.LITE, H.AO
  - ⚠️ **deve funcionar, não testado**: Ares Apex, CPP.EVO, CPP.Apex, 290GP, PW1, câmbio H,
    freio de mão — com o aviso de que podem divergir (ordem de eixos diferente, volante sem
    eixo analógico, device sem botões);
- um parágrafo explícito dizendo que o repo carrega o **CLAUDE.md como contexto** para pedir
  análise a um LLM sobre um produto Conspit específico. O caminho das pedras já existe;
  falta empacotá-lo.

Generalizar a regra de fuzz/flat por vendor, mantendo exceções por-PID só onde medido.

---

## 5. README para a comunidade

### Fatos

291 linhas, bem escritas — mas para *uma* pessoa com *um* setup.

### Problemas para quem chega de fora

1. `git clone git@github.com:...` é **SSH**; alguém de fora precisa de HTTPS.
2. Falta um "o que isto resolve" em 3 linhas, e um **screenshot** (já existem dois).
3. Falta troubleshooting **por sintoma** ("não vejo meus pedais"), não por causa.
4. Não está claro que o CLAUDE.md (671 linhas) é opcional / material de investigação.
5. **Não tem licença** — sem ela o repo é legalmente "todos os direitos reservados" e
   ninguém pode usar ou forkar com segurança.

### A decisão de maior impacto da lista inteira

O README está em **PT-BR** e a comunidade sim-racing/Linux é majoritariamente internacional.
Um README em **inglês** (mantendo CLAUDE.md e `docs/` em português) provavelmente multiplica
o alcance mais do que todos os outros itens somados.

❓ **DECISÃO B: README em inglês ou português?**
❓ **DECISÃO C: qual licença?** (MIT e Apache-2.0 são as usuais para ferramentas assim; a
segunda tem cláusula de patentes. "Nenhuma" também é uma resposta válida, mas convém ser
explícita.)

---

## 6. Integração com a telemetria do jogo

Levantado em 2026-08-15 depois de o usuário testar: **o ConspitLink não reconhece que o jogo
está aberto** (fica em `Not Started` ao lado de `Select Game`).

### São TRÊS problemas empilhados, não um

Investigado no binário e no prefixo. O que é **medido** vs. o que é **inferido** está
marcado.

#### (a) Detecção do jogo — enumeração de processos

**Medido:** o `ConspitLink2.0.exe` importa `CreateToolhelp32Snapshot` e `OpenProcess`.

**Inferido:** é assim que ele decide se o jogo está rodando.

⚠️ Sob Wine, `CreateToolhelp32Snapshot` enxerga **apenas processos do mesmo wineserver**, ou
seja, do mesmo prefixo. Um jogo rodando no Proton está em **outro prefixo** e é invisível; um
jogo nativo Linux é invisível de qualquer forma. Isso explica o `Not Started` **sozinho**,
independentemente de a telemetria estar chegando ou não.

#### (b) Localização da instalação — a chave do Steam não existe no prefixo

**Medido:** o binário contém `HKEY_CURRENT_USER\SOFTWARE\Valve\Steam`, `SteamPath`,
`/config/libraryfolders.vdf`, `steamapps`, `/steamapps/common/` e caminhos específicos como
`SteamLibrary/steamapps/common/Le Mans Ultimate/`. O `GameMatchSteamGame.json` mapeia cada ID
interno para o **nome de exibição do jogo no Steam**.

**Medido:** `HKCU\SOFTWARE\Valve\Steam\SteamPath` **não existe** neste prefixo
(`reg query` → *Unable to find the specified registry value*). O Steam real do usuário é o
**nativo Linux**, em `~/.local/share/Steam`, que nunca escreve no registro do prefixo.

**Consequência:** o app não acha a biblioteca do Steam → não acha a pasta do jogo → não
consegue ler nem **escrever** a configuração de telemetria do jogo.

✅ **Este é o mais barato de corrigir, e é o mesmo padrão do nó PnP da serial:** criar
`HKCU\SOFTWARE\Valve\Steam\SteamPath` apontando para o caminho Windows do Steam nativo —
`Z:\home\<usuário>\.local\share\Steam` (o `z:` do prefixo já aponta para `/`).
**Deve ser o primeiro experimento.**

#### (c) Transporte da telemetria — dois regimes, com destinos opostos

**Medido:** o binário contém `127.0.0.1`, `20777` e `20778` (as portas da família F1), e
nomes de memória compartilhada como `LMU_Data`, `LMU_SharedMemoryLockData`,
`rFactor2SharedMemoryMapPlugin64.dll`. Os símbolos do `.pdb` trazem
`ACEvoTelemetry::attach` / `::detach` / `::SharedMemoryHandle`.

| regime | jogos | atravessa a fronteira Wine/Proton? |
|---|---|---|
| **UDP** | F1 22/23/24/25, DiRT Rally 2.0, EA WRC, WRC Generations, FH5, FM8 | ✅ **sim** — é só rede no kernel Linux |
| **memória compartilhada** | AC, ACC, AC EVO, AC Rally, iRacing, AMS2, rFactor 2, LMU, RaceRoom, ETS2, RBR | ❌ **não** — o namespace de objetos do wineserver é por prefixo |

### A cadeia provável, e por que a ordem importa

```
SteamPath ausente
   └─> app não acha a pasta do jogo
        └─> não escreve a config de telemetria UDP do jogo
             └─> nenhum dado chega
E, em paralelo e independente:
CreateToolhelp32Snapshot só vê o próprio prefixo
   └─> "Not Started" mesmo que a telemetria chegasse
```

### Plano de ataque proposto

1. **Escrever o `SteamPath`** no prefixo e reabrir o app. Barato, reversível, e destrava (b).
   Verificar se ele passa a listar os jogos instalados.
2. **Testar um jogo UDP** (F1 ou DiRT Rally 2.0) — é o único regime que pode funcionar com o
   jogo no Proton e o app no prefixo dele. Configurar a saída de telemetria do jogo para
   `127.0.0.1:20777` **na mão**, se o app não conseguir escrever sozinho.
3. **Verificar se o `Not Started` sobrevive** mesmo com telemetria chegando. Se sim, confirma
   que a detecção é por processo e é um problema separado.
4. **Só então** avaliar o caminho caro dos jogos de memória compartilhada: rodar o
   ConspitLink **dentro do prefixo do Proton do jogo**. ⚠️ O Proton roda em container
   `pressure-vessel`, que restringe o `/dev` visível — risco direto para o acesso a
   `/dev/hidraw*` de que o app depende. Ver seção 11.4 do CLAUDE.md do projeto irmão
   `~/apps/diy-ffb-pedal-linux/`.

### O que isso significa para os haptics e o dash

O modo `Customize` de vibração dos pedais e o dash dos volantes são alimentados **pela
telemetria que o próprio ConspitLink recebe**. Ou seja: eles dependem inteiramente deste
ponto. Enquanto a telemetria não chega, os haptics em jogo e o dash não têm fonte — o botão
`Test` funciona porque não usa telemetria.

Os outros dois modos de vibração (`SimHub`, `iRacing`) esperam software externo, o que sob
Linux é outro problema em aberto.

---

## Ordem sugerida de execução

```
6a. SteamPath           experimento barato e isolado; pode ir a qualquer momento
1.  prefixo (XDG)       bloqueia o 2
2.  atalho .desktop
6b. telemetria UDP      depende de 6a; é o que destrava haptics e dash
4.  generalizar devices muda o conteúdo do README
5.  README              por último, para documentar o estado final
3.  tools/              descartado, exceto o Makefile
```

O ponto **6a** (escrever o `SteamPath`) é independente de todos os outros e é o de melhor
relação custo/informação — vale rodar antes de qualquer coisa, só para saber onde estamos.
