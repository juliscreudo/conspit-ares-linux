#!/usr/bin/env python3
"""Prepara um prefixo Wine para o ConspitLink 2.0 enxergar os devices Conspit.

Faz duas coisas independentes:

1. REGISTRA A PORTA SERIAL NA ARVORE PnP (configuracao da base)
   O Wine expoe portas seriais como dispositivos genericos, sem VID/PID de
   USB. O `QSerialPortInfo` do Qt (que o ConspitLink usa, via
   Qt5SerialPort.dll) enumera pela classe `Ports` do SetupAPI, tira o nome
   da porta de `Device Parameters\\PortName` e o VID/PID do device instance
   ID. Sem um no na arvore PnP, a base simplesmente nao aparece na lista.

2. POE O winebus NO BACKEND hidraw (telemetria, pedais, volantes)
   Sem isto o Wine entrega os devices HID sintetizados pelo SDL, que tem
   UMA collection so -- os canais vendor de 64 bytes (pedais, volantes) e a
   collection de comandos da base nao existem, e o app nao ve nada alem do
   basico. Ver "O backend do winebus" no CLAUDE.md.

    python3 tools/conspit_wine_setup.py
    python3 tools/conspit_wine_setup.py --verificar
    python3 tools/conspit_wine_setup.py --desfazer

⚠️ RODE DE NOVO ao ligar um device Conspit novo: a lista `EnableHidraw` e'
montada a partir do que esta no barramento. (A rede de seguranca cobre o caso
mesmo sem re-rodar, mas a lista explicita e' o que documenta a intencao.)
"""
import argparse
import glob
import os
import re
import subprocess
import sys

# {4D36E978-E325-11CE-BFC1-08002BE10318} = GUID_DEVCLASS_PORTS, a classe que
# o QSerialPortInfo varre no Windows.
GUID_PORTS = "{4D36E978-E325-11CE-BFC1-08002BE10318}"

def prefixo_padrao():
    """Prefixo Wine do projeto. Mesma regra do tools/conspit-prefixo.sh.

    Dedicado (nao o ~/.wine) porque o `Enable SDL=0` vale para o prefixo
    INTEIRO, e num prefixo compartilhado quebraria a enumeracao de controle
    de todo outro app Windows dali. Fora do repo porque passa de 870 MB e um
    `git clean -xfd` apagaria a configuracao junto.
    """
    if os.environ.get("CONSPIT_PREFIX"):
        return os.environ["CONSPIT_PREFIX"]
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "conspit-ares-linux", "prefix")


# Fora da faixa 1..32, que o wineboot preenche sozinho. Ele varre /dev/ttyS*
# E TAMBEM /dev/ttyACM*, que caem depois de 32 (aqui: com34, com35) -- por
# isso 33 continua livre, mas nao conte com numeros muito acima.
COM_PADRAO = 33

VID_CONSPIT = "3514"
PID_ARES = "0301"

# ⚠️ A CHAVE E' `Services\winebus`, NAO `Services\winebus\Parameters`.
#
# Esta e' a correcao mais importante deste script. O `check_bus_option` do
# winebus.sys carrega o comentario de documentacao do proprio Wine:
#
#     /* @@ Wine registry key: HKLM\System\CurrentControlSet\Services\WineBus */
#
# ou seja, ele le os valores direto em `Services\winebus`. Ate 2026-08-15
# este script escrevia em `...\winebus\Parameters`, uma subchave que o
# driver NUNCA consulta -- entao todas as opcoes eram silenciosamente
# ignoradas e o backend continuava no SDL. Isso invalidou varias medicoes
# antigas; ver "A chave errada" no CLAUDE.md.
CHAVE_WINEBUS = r"HKLM\System\CurrentControlSet\Services\winebus"
CHAVE_WINEBUS_LEGADA = CHAVE_WINEBUS + r"\Parameters"


def wine(prefixo, *args, checar=True, timeout=180):
    env = dict(os.environ, WINEPREFIX=prefixo, WINEDEBUG="-all")
    return subprocess.run(["wine", *args], env=env, capture_output=True,
                          text=True, check=checar, timeout=timeout)


def propriedades_udev(dev):
    r = subprocess.run(["udevadm", "info", "-q", "property", "-n", dev],
                       capture_output=True, text=True, check=True)
    return dict(l.split("=", 1) for l in r.stdout.splitlines() if "=" in l)


def detectar_base():
    """Acha a interface CDC da Ares em /dev/serial/by-id."""
    achados = []
    for link in sorted(glob.glob("/dev/serial/by-id/*")):
        try:
            p = propriedades_udev(link)
        except subprocess.CalledProcessError:
            continue
        if p.get("ID_VENDOR_ID", "").lower() != VID_CONSPIT:
            continue
        achados.append({
            "link": link,
            "dev": os.path.realpath(link),
            "vid": p.get("ID_VENDOR_ID", "").upper(),
            "pid": p.get("ID_MODEL_ID", "").upper(),
            "serial": p.get("ID_SERIAL_SHORT", ""),
            "modelo": p.get("ID_MODEL", "").replace("_", " "),
        })
    if not achados:
        sys.exit("Nenhuma interface serial Conspit encontrada.\n"
                 "A base esta ligada? Confira com: ls -l /dev/serial/by-id/")

    # ⚠️ A BASE NAO E' A UNICA COM CDC. Descoberto em 2026-08-15: o volante
    # H.AO (0007) tambem expoe uma porta serial. Escolher "a primeira" da
    # lista so acertava por acidente da ordem alfabetica (ARES < H.AO) --
    # basta um device novo com nome antes de "ARES" para o script registrar
    # a porta errada, e o app nao acharia a base. Selecionar pelo PID.
    da_base = [a for a in achados if a["pid"].lower() == PID_ARES]
    if len(achados) > 1:
        print("Mais de uma porta serial Conspit no barramento:")
        for a in achados:
            marca = "  <- base, escolhida" if a in da_base[:1] else ""
            print(f"  {a['vid']}:{a['pid']}  {a['modelo']}  ({a['dev']}){marca}")
        print()
    if not da_base:
        sys.exit(f"Nenhuma porta serial com PID {PID_ARES} (a base Ares).\n"
                 "A base esta ligada?")
    return da_base[0]


def detectar_conspit_usb():
    """Todos os devices Conspit no barramento, para a lista EnableHidraw.

    Devolve [(pid, nome)] ordenado por pid, sem repeticao."""
    vistos = {}
    for d in sorted(glob.glob("/sys/bus/usb/devices/*")):
        try:
            with open(os.path.join(d, "idVendor")) as f:
                if f.read().strip().lower() != VID_CONSPIT:
                    continue
            with open(os.path.join(d, "idProduct")) as f:
                pid = f.read().strip().lower()
        except OSError:
            continue
        nome = ""
        try:
            with open(os.path.join(d, "product")) as f:
                nome = f.read().strip()
        except OSError:
            pass
        vistos.setdefault(pid, nome)
    return sorted(vistos.items())


def chave_enum(b):
    return (rf"HKLM\System\CurrentControlSet\Enum\USB"
            rf"\VID_{b['vid']}&PID_{b['pid']}\{b['serial']}")


def configurar_backend(prefixo, devices):
    """Poe o winebus no backend hidraw para os devices Conspit.

    Duas chaves, com papeis diferentes e complementares:

    `EnableHidraw` = lista "VID:PID"
        E' QUEM FAZ O TRABALHO. Marca explicitamente cada device Conspit
        presente. Formato do proprio winebus.sys:

            UINT len = swprintf(vidpid, ARRAY_SIZE(vidpid), L"%04X:%04X", vid, pid);
            if (!wcsnicmp(tmp, vidpid, len)) prefer_hidraw = TRUE;

        REG_MULTI_SZ, uma entrada por device, comparacao sem case.

    `Enable SDL` = 0  +  `DisableInput` = 1
        A rede de seguranca, e SO' FUNCIONA COM OS DOIS JUNTOS:

            if (options.disable_sdl && options.disable_input)
                prefer_hidraw = TRUE;

        -> qualquer joystick passa a vir por hidraw, inclusive um device
        Conspit ligado depois deste script rodar.

        ⚠️ Ate 2026-08-15 este arquivo afirmava que `Enable SDL=0`
        SOZINHO bastava, porque "SDL desligado tambem desliga o evdev":

            if (!sdl_driver_init()) options.disable_input = TRUE;

        Isso esta' invertido. `sdl_driver_init()` devolve STATUS_SUCCESS
        (=0) quando da' certo, entao o `!` liga o disable_input quando o
        SDL FUNCIONA (para nao duplicar device). Com `Enable SDL=0` ele
        devolve STATUS_NOT_SUPPORTED (!=0) e o disable_input fica FALSE
        -- o backend evdev continua ativo e sintetiza os devices.

        MEDIDO em 2026-08-15, removendo o EnableHidraw e reiniciando o
        wineserver: com so' `Enable SDL=0` os devices voltam a sair
        sintetizados (usage 0x05, out 0, sem canal vendor). Com os dois,
        saem reais (usage 0x04 + 0x3A). Foi o mesmo sintoma do prefixo do
        SimHub, que tinha `Enable SDL=0` e nao enxergava o volante.

        ⚠️ Vale para o prefixo inteiro. Como este prefixo so roda o
        ConspitLink, tudo bem; num prefixo de jogos, um controle sem ACL
        de hidraw sumiria.
    """
    print("\n3. Poe o winebus no backend hidraw...")

    # Limpa a subchave errada que este script usou ate 2026-08-15. Deixa-la
    # para tras nao quebra nada (o driver nao le), mas confunde quem for
    # diagnosticar depois.
    r = wine(prefixo, "reg", "query", CHAVE_WINEBUS_LEGADA, checar=False)
    if r.returncode == 0:
        wine(prefixo, "reg", "delete", CHAVE_WINEBUS_LEGADA, "/f", checar=False)
        print(r"   removida a subchave legada \Parameters (o driver nao a le)")

    # Os dois juntos: e' a combinacao que liga prefer_hidraw para qualquer
    # joystick. Um sozinho nao faz nada -- ver docstring.
    for valor in ("Enable SDL", "DisableInput"):
        dado = "0" if valor == "Enable SDL" else "1"
        wine(prefixo, "reg", "add", CHAVE_WINEBUS, "/v", valor,
             "/t", "REG_DWORD", "/d", dado, "/f")
    print("   Enable SDL = 0 + DisableInput = 1   (rede de seguranca; so' juntos)")

    if devices:
        lista = [f"{VID_CONSPIT}:{pid}" for pid, _ in devices]
        # `wine reg` usa a sequencia literal \0 como separador de REG_MULTI_SZ
        wine(prefixo, "reg", "add", CHAVE_WINEBUS, "/v", "EnableHidraw",
             "/t", "REG_MULTI_SZ", "/d", "\\0".join(lista), "/f")
        print("   EnableHidraw:")
        for (pid, nome), entrada in zip(devices, lista):
            print(f"     {entrada}  {nome}")
    else:
        print("   (nenhum device Conspit no barramento; lista nao escrita)")

    print("   requer /dev/hidraw* acessivel -- ver udev/70-conspit.rules")


def caminho_steam():
    """Acha a raiz do Steam nativo do usuario, ou None."""
    for p in ("~/.local/share/Steam", "~/.steam/steam", "~/.steam/root"):
        c = os.path.expanduser(p)
        if os.path.isdir(os.path.join(c, "steamapps")):
            return os.path.realpath(c)
    return None


def configurar_steam(prefixo):
    """Ponte para o app achar os jogos do Steam NATIVO.

    O ConspitLink le HKCU\\SOFTWARE\\Valve\\Steam\\SteamPath e a partir dai
    abre `<SteamPath>/config/libraryfolders.vdf` e `steamapps/common/...`
    (medido nas strings do binario; ha um `GameData::readVdf` no .pdb). Num
    Linux com Steam nativo essa chave simplesmente nao existe no prefixo --
    o Steam nativo nunca escreve no registro do Wine -- e o app nao acha
    jogo nenhum.

    Apontar direto para o Steam via Z: nao basta: os caminhos DENTRO do
    libraryfolders.vdf sao Linux absolutos (`/home/...`), que como caminho
    Windows cairiam na raiz do drive atual. Por isso montamos um diretorio
    ponte em C:\\SteamBridge com:

      config/libraryfolders.vdf   copia com os caminhos reescritos para Z:
      steamapps -> symlink        para o steamapps real

    Assim o app acha os jogos tanto pela biblioteca primaria (= SteamPath)
    quanto pelas bibliotecas listadas no vdf.

    ⚠️ Isto so' resolve LOCALIZAR o jogo instalado. Saber que ele esta
    RODANDO, e receber telemetria, e' outro problema -- ver a secao da ponte
    de telemetria em tools/run-conspitlink.sh.
    """
    steam = caminho_steam()
    if not steam:
        print("\n3. Steam nativo nao encontrado; pulando a ponte de jogos.")
        return

    ponte = os.path.join(prefixo, "drive_c", "SteamBridge")
    os.makedirs(os.path.join(ponte, "config"), exist_ok=True)

    vdf_orig = os.path.join(steam, "config", "libraryfolders.vdf")
    if os.path.isfile(vdf_orig):
        with open(vdf_orig, encoding="utf-8", errors="replace") as f:
            txt = f.read()
        # "path"  "/home/..."   ->   "path"  "Z:/home/..."
        txt = re.sub(r'("path"\s+")(/[^"]*)"', r'\1Z:\2"', txt)
        with open(os.path.join(ponte, "config", "libraryfolders.vdf"), "w",
                  encoding="utf-8") as f:
            f.write(txt)

    alvo = os.path.join(ponte, "steamapps")
    if os.path.islink(alvo) or os.path.exists(alvo):
        if os.path.islink(alvo):
            os.remove(alvo)
    if not os.path.exists(alvo):
        os.symlink(os.path.join(steam, "steamapps"), alvo)

    print("\n3. Ponte para o Steam nativo...")
    wine(prefixo, "reg", "add", r"HKCU\SOFTWARE\Valve\Steam", "/v", "SteamPath",
         "/t", "REG_SZ", "/d", "C:/SteamBridge", "/f")
    print(f"   Steam nativo : {steam}")
    print(r"   SteamPath    = C:/SteamBridge")
    print(f"   steamapps    -> {os.path.join(steam, 'steamapps')}")


def configurar(prefixo, b, com, devices):
    nome = f"{b['modelo']} (COM{com})"
    k = chave_enum(b)

    print(f"Base detectada : {b['vid']}:{b['pid']}  {b['modelo']}")
    print(f"Dispositivo    : {b['link']}")
    print(f"                 (-> {b['dev']})")
    print(f"Porta Wine     : COM{com}")
    print(f"Prefixo        : {prefixo}\n")

    print("1. Registrando a base na arvore de dispositivos do Wine...")
    for valor, tipo, dado in [
        ("Class",        "REG_SZ",       "Ports"),
        ("ClassGUID",    "REG_SZ",       GUID_PORTS),
        ("DeviceDesc",   "REG_SZ",       nome),
        ("FriendlyName", "REG_SZ",       nome),
        ("Mfg",          "REG_SZ",       "CONSPIT"),
        ("Service",      "REG_SZ",       "Serial"),
        ("ConfigFlags",  "REG_DWORD",    "0"),
        ("Driver",       "REG_SZ",       rf"{GUID_PORTS}\0000"),
        ("HardwareId",   "REG_MULTI_SZ", rf"USB\VID_{b['vid']}&PID_{b['pid']}"),
    ]:
        wine(prefixo, "reg", "add", k, "/v", valor, "/t", tipo, "/d", dado, "/f")

    # E daqui que o QSerialPortInfo tira o nome da porta quando enumera pela
    # classe Ports. Sem isto o no existe mas a porta sai sem nome.
    wine(prefixo, "reg", "add", rf"{k}\Device Parameters", "/v", "PortName",
         "/t", "REG_SZ", "/d", f"COM{com}", "/f")
    print(f"   {k}")
    print(f"   DeviceDesc = {nome}")
    print(f"   Device Parameters\\PortName = COM{com}")

    # O mapeamento vai nos DOIS lugares: o wineboot recria o symlink a partir
    # do registro, entao mexer so no symlink e' revertido no proximo boot.
    print(f"\n2. Apontando COM{com} para o dispositivo...")
    wine(prefixo, "reg", "add", r"HKLM\Software\Wine\Ports", "/v", f"COM{com}",
         "/t", "REG_SZ", "/d", b["link"], "/f")
    print(rf"   HKLM\Software\Wine\Ports\COM{com} = {b['link']}")

    configurar_backend(prefixo, devices)
    configurar_steam(prefixo)

    # Symlink por ultimo: `wine reg` pode disparar um wineboot que recria os
    # symlinks a partir do registro, sobrescrevendo o que criassemos antes.
    alvo = os.path.join(prefixo, "dosdevices", f"com{com}")
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    if os.path.islink(alvo) or os.path.exists(alvo):
        os.remove(alvo)
    # by-id e nao /dev/ttyACMx: o numero renumera quando o kernel reenumera, e
    # o symlink quebra em silencio.
    os.symlink(b["link"], alvo)
    print(f"\n   dosdevices/com{com} -> {b['link']}")


def verificar(prefixo, com, devices):
    print("\n4. Verificando...")
    ok = True

    alvo = os.path.join(prefixo, "dosdevices", f"com{com}")
    if os.path.islink(alvo) and os.path.exists(os.path.realpath(alvo)):
        print(f"   symlink  com{com} -> {os.path.realpath(alvo)}  OK")
    else:
        print(f"   !! symlink com{com} ausente ou quebrado")
        ok = False

    r = wine(prefixo, "reg", "query",
             r"HKLM\HARDWARE\DEVICEMAP\SERIALCOMM", checar=False)
    if re.search(rf"\bCOM{com}\b", r.stdout):
        print(f"   SERIALCOMM contem COM{com}  OK")
    else:
        print(f"   !! COM{com} ausente do SERIALCOMM")
        ok = False

    # backend do winebus
    r = wine(prefixo, "reg", "query", CHAVE_WINEBUS, checar=False)
    if re.search(r"Enable SDL\s+REG_DWORD\s+0x0\b", r.stdout):
        print("   winebus: Enable SDL = 0  OK")
    else:
        print("   !! winebus: 'Enable SDL' nao esta 0 -- o backend continua no SDL")
        ok = False

    faltando = [f"{VID_CONSPIT}:{pid}" for pid, _ in devices
                if not re.search(rf"{VID_CONSPIT}:{pid}", r.stdout, re.I)]
    if not devices:
        print("   (sem devices Conspit no barramento para conferir)")
    elif faltando:
        print(f"   !! EnableHidraw nao lista: {', '.join(faltando)}")
        ok = False
    else:
        print(f"   winebus: EnableHidraw cobre os {len(devices)} device(s)  OK")

    r = wine(prefixo, "reg", "query", CHAVE_WINEBUS_LEGADA, checar=False)
    if r.returncode == 0:
        print(r"   !! sobrou a subchave \Parameters (inerte, mas confunde)")

    # Mesma query que o wbemprox do Wine responde a partir da arvore Enum.
    try:
        r = wine(prefixo, "wmic", "path", "Win32_PnPEntity", "get",
                 "Name,DeviceID", checar=False, timeout=200)
        linha = next((l for l in r.stdout.splitlines()
                      if re.search(rf"\(COM{com}\)", l)), None)
        if linha:
            print(f"   WMI: {linha.strip()}")
            vid = re.search(r"VID_([0-9a-fA-F]{4})", linha)
            pid = re.search(r"PID_([0-9a-fA-F]{4})", linha)
            print(f"   -> VID={vid.group(1) if vid else '?'}  "
                  f"PID={pid.group(1) if pid else '?'}")
        else:
            print(f"   !! nenhuma entrada (COM{com}) no Win32_PnPEntity")
            ok = False
    except subprocess.TimeoutExpired:
        print("   !! wmic demorou demais; verifique a mao com:")
        print("      wine wmic path Win32_PnPEntity get Name,DeviceID")

    print("\n   " + ("tudo certo." if ok else "algo faltou -- veja acima."))
    if ok:
        print("   Para conferir o que o app enxerga, compile e rode o "
              "tools/hidenum.c\n   dentro do prefixo (ver cabecalho do arquivo).")
    return ok


def desfazer(prefixo, com):
    print("Removendo o que este script cria...")
    b = detectar_base()
    wine(prefixo, "reg", "delete", chave_enum(b), "/f", checar=False)
    wine(prefixo, "reg", "delete", r"HKLM\Software\Wine\Ports", "/v",
         f"COM{com}", "/f", checar=False)
    for valor in ("Enable SDL", "DisableInput", "EnableHidraw"):
        wine(prefixo, "reg", "delete", CHAVE_WINEBUS, "/v", valor, "/f",
             checar=False)
    alvo = os.path.join(prefixo, "dosdevices", f"com{com}")
    if os.path.islink(alvo):
        os.remove(alvo)
    print("   feito.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefixo", default=prefixo_padrao())
    ap.add_argument("--com", type=int, default=COM_PADRAO)
    ap.add_argument("--verificar", action="store_true")
    ap.add_argument("--desfazer", action="store_true")
    a = ap.parse_args()

    if not os.path.isdir(a.prefixo):
        sys.exit(f"prefixo nao existe: {a.prefixo}")

    devices = detectar_conspit_usb()

    if a.desfazer:
        desfazer(a.prefixo, a.com)
    elif a.verificar:
        sys.exit(0 if verificar(a.prefixo, a.com, devices) else 1)
    else:
        configurar(a.prefixo, detectar_base(), a.com, devices)
        verificar(a.prefixo, a.com, devices)


if __name__ == "__main__":
    main()
