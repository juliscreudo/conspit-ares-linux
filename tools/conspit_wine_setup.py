#!/usr/bin/env python3
"""Prepara um prefixo Wine para o ConspitLink 2.0 enxergar a base Ares.

Problema: o Wine expoe portas seriais como dispositivos genericos, sem
VID/PID de USB. O `QSerialPortInfo` do Qt (que o ConspitLink usa, via
Qt5SerialPort.dll) enumera pela classe `Ports` do SetupAPI, tira o nome da
porta de `Device Parameters\\PortName` e o VID/PID do device instance ID.
Sem um no na arvore PnP, a base simplesmente nao aparece na lista dele.

A arvore de dispositivos do Wine e' registro puro, em
HKLM\\System\\CurrentControlSet\\Enum -- nada impede a gente de registrar
o no que falta, com o VID/PID reais lidos do udev (nao inventados).

Tecnica herdada de ~/apps/diy-ffb-pedal-linux/pedal_wine_setup.py (secao 11.3
do CLAUDE.md de la), adaptada de .NET/WMI para Qt/SetupAPI.

    python3 tools/conspit_wine_setup.py
    python3 tools/conspit_wine_setup.py --verificar
    python3 tools/conspit_wine_setup.py --desfazer
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

PREFIXO_PADRAO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".wine-conspitlink")

# Fora da faixa 1..32, que o wineboot preenche sozinho varrendo /dev/ttyS*.
# Usar um numero de la vira corrida com o wineboot, que sobrescreve o symlink.
COM_PADRAO = 33

VID_CONSPIT = "3514"
PID_ARES = "0301"


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
    if len(achados) > 1:
        print("Mais de uma porta Conspit; usando a primeira:")
        for a in achados:
            print(f"  {a['vid']}:{a['pid']}  {a['modelo']}  ({a['dev']})")
    return achados[0]


def chave_enum(b):
    return (rf"HKLM\System\CurrentControlSet\Enum\USB"
            rf"\VID_{b['vid']}&PID_{b['pid']}\{b['serial']}")


def configurar(prefixo, b, com):
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

    # 3) Backend HID. O ConspitLink usa hidapi.dll para o canal proprietario
    #    (temperaturas, estado do motor, dash). O winebus do Wine tem dois
    #    backends: SDL, que sintetiza um descritor generico de joystick, e
    #    hidraw, que entrega o descritor REAL -- incluindo a collection
    #    vendor-defined (report ID 0xA1) que o ConspitLink precisa.
    #    Com SDL ativo o app enumera o dispositivo (aparece "Online") mas
    #    nao consegue trocar relatorios vendor: e' o cenario dos campos
    #    zerados. Este prefixo so roda o ConspitLink, entao desligar SDL aqui
    #    nao afeta mais nada.
    #    ⚠️ `DisableInput=1` foi TENTADO em 2026-08-12 e NAO ajudou: o
    #    winedevice.exe continuou abrindo /dev/input/event* junto do hidraw, e o
    #    angulo do volante continuou travado. Nao readicionar sem evidencia
    #    nova. (Os nomes validos, extraidos do proprio winebus.sys: EnableHidraw,
    #    DisableHidraw, DisableInput, DisableUdevd, "Enable SDL",
    #    "Map Controllers".)
    print("\n3. Configurando o winebus para usar o backend hidraw...")
    par = r"HKLM\System\CurrentControlSet\Services\winebus\Parameters"
    for valor, dado in [("Enable SDL", "0"), ("DisableHidraw", "0")]:
        wine(prefixo, "reg", "add", par, "/v", valor, "/t", "REG_DWORD",
             "/d", dado, "/f")
        print(f"   {valor} = {dado}")
    print("   (requer /dev/hidraw* acessivel -- ver udev/70-conspit.rules)")

    # Symlink por ultimo: `wine reg` pode disparar um wineboot que recria os
    # symlinks a partir do registro, sobrescrevendo o que criassemos antes.
    alvo = os.path.join(prefixo, "dosdevices", f"com{com}")
    os.makedirs(os.path.dirname(alvo), exist_ok=True)
    if os.path.islink(alvo) or os.path.exists(alvo):
        os.remove(alvo)
    # by-id e nao /dev/ttyACMx: o numero renumera quando o kernel reenumera, e
    # o symlink quebra em silencio.
    os.symlink(b["link"], alvo)
    print(f"   dosdevices/com{com} -> {b['link']}")


def verificar(prefixo, com):
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
    return ok


def desfazer(prefixo, com):
    print("Removendo o que este script cria...")
    b = detectar_base()
    wine(prefixo, "reg", "delete", chave_enum(b), "/f", checar=False)
    wine(prefixo, "reg", "delete", r"HKLM\Software\Wine\Ports", "/v",
         f"COM{com}", "/f", checar=False)
    alvo = os.path.join(prefixo, "dosdevices", f"com{com}")
    if os.path.islink(alvo):
        os.remove(alvo)
    print("   feito.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefixo", default=PREFIXO_PADRAO)
    ap.add_argument("--com", type=int, default=COM_PADRAO)
    ap.add_argument("--verificar", action="store_true")
    ap.add_argument("--desfazer", action="store_true")
    a = ap.parse_args()

    if not os.path.isdir(a.prefixo):
        sys.exit(f"prefixo nao existe: {a.prefixo}")

    if a.desfazer:
        desfazer(a.prefixo, a.com)
    elif a.verificar:
        sys.exit(0 if verificar(a.prefixo, a.com) else 1)
    else:
        configurar(a.prefixo, detectar_base(), a.com)
        verificar(a.prefixo, a.com)


if __name__ == "__main__":
    main()


