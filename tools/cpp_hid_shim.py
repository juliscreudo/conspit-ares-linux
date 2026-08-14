#!/usr/bin/env python3
"""Expoe a 2a top-level collection dos pedais CPP.LITE como um device HID
proprio, para o ConspitLink sob Wine conseguir enxerga-los.

O PROBLEMA (medido em 2026-08-14)
O descritor HID do CPP.LITE declara DUAS top-level collections numa mesma
interface USB:

  1) Usage(Joystick)       report ID 1, 3 eixos de 12 bits -> os pedais
  2) Usage(Counted Buffer) report ID 2, 63 bytes vendor    -> canal do app

O Windows cria UM DEVICE POR COLLECTION (&Col01 / &Col02) e o ConspitLink
abre o segundo. O Wine cria um device so e expoe apenas a primeira: um
enumerador HID rodando dentro do prefixo reporta

  VID_3514 PID_0005  usage_page 0x0001 usage 0x04  in 7   <- so os eixos
  VID_3514 PID_0300  usage_page 0x000C usage 0x01  in 64  <- canal vendor

7 = 1 + 3*2. O canal de 64 bytes dos pedais simplesmente nao existe no
prefixo, entao o app nao tem com o que falar e nao lista os pedais.

O QUE ESTE SHIM FAZ
Cria via /dev/uhid um device HID virtual com o mesmo VID/PID contendo
APENAS a segunda collection, e repassa os relatorios nos dois sentidos
entre ele e o /dev/hidraw real. Para o Wine passa a haver um device de 64
bytes, como no Windows.

Ele nao inventa trafego: so repassa o que o app manda e o que o pedal
responde. Nao toca na base de 20 Nm -- o unico device que ele abre para
escrita e' o dos pedais.

    tools/cpp_hid_shim.py           # roda ate Ctrl-C
    tools/cpp_hid_shim.py -v        # mostra cada relatorio repassado
    tools/cpp_hid_shim.py --esperar # espera os pedais aparecerem

Sobrevive a replug: se o pedal sumir, ele derruba o device virtual, espera
o hidraw voltar e recria sozinho.

Requer /dev/uhid acessivel: sudo cp udev/70-uhid-shim.rules /etc/udev/rules.d/
"""
import argparse
import errno
import fcntl
import glob
import os
import select
import signal
import struct
import sys
import time

VID, PID = 0x3514, 0x0005
BUS_USB = 0x03

# linux/uhid.h
UHID_DESTROY, UHID_START, UHID_STOP = 1, 2, 3
UHID_OPEN, UHID_CLOSE, UHID_OUTPUT = 4, 5, 6
UHID_GET_REPORT, UHID_GET_REPORT_REPLY = 9, 10
UHID_CREATE2, UHID_INPUT2 = 11, 12
UHID_SET_REPORT, UHID_SET_REPORT_REPLY = 13, 14

UHID_FEATURE_REPORT, UHID_OUTPUT_REPORT = 0, 1

HIDIOCSFEATURE = 0xC0064806  # _IOC(WRITE|READ, 'H', 0x06, len) -- len no runtime
EV_BUF = 8192


def achar_hidraw_real():
    """Acha o /dev/hidraw dos pedais pelo modalias, ignorando devices
    virtuais (os numeros de hidrawN mudam a cada reenumeracao, e depois que
    este shim rodar havera DOIS devices com este VID/PID)."""
    alvo = "v%08Xp%08X" % (VID, PID)
    for caminho in sorted(glob.glob("/sys/class/hidraw/hidraw*")):
        dev = os.path.realpath(os.path.join(caminho, "device"))
        if "/devices/virtual/" in dev:
            continue
        try:
            with open(os.path.join(caminho, "device", "modalias")) as f:
                if alvo.lower() in f.read().strip().lower():
                    return "/dev/" + os.path.basename(caminho), caminho
        except OSError:
            continue
    return None, None


def fatiar_collections(rd):
    """Devolve a lista de fatias (inicio, fim) de cada top-level collection.

    Cada fatia comeca onde a anterior terminou, entao carrega junto os itens
    globais/locais que precedem o Collection (Usage Page, Usage) -- que sao
    exatamente os que o descritor recortado precisa para ser valido."""
    fatias, i, prof, inicio = [], 0, 0, 0
    while i < len(rd):
        b = rd[i]
        tam = b & 0x03
        tam = 4 if tam == 3 else tam
        tag = b & 0xFC
        if tag == 0xA0:          # Collection
            prof += 1
        elif tag == 0xC0:        # End Collection
            prof -= 1
            if prof == 0:
                fatias.append((inicio, i + 1 + tam))
                inicio = i + 1 + tam
        i += 1 + tam
    return fatias


def report_ids(rd):
    """IDs de relatorio declarados num descritor (item 0x85)."""
    ids, i = set(), 0
    while i < len(rd):
        b = rd[i]
        tam = b & 0x03
        tam = 4 if tam == 3 else tam
        if (b & 0xFC) == 0x84 and tam >= 1:   # Report ID
            ids.add(rd[i + 1])
        i += 1 + tam
    return ids


# Descritor do joystick virtual: 3 eixos de 12 bits declarados como
# X, Y, Z. O Wine batiza os eixos na ORDEM DE APARICAO (foi assim que o
# Rx do descritor real virou lX), entao declarar X/Y/Z deixa explicito
# onde cada um vai cair no DIJOYSTATE2 que o app le.
RD_EIXOS = bytes([
    0x05, 0x01,        # Usage Page (Generic Desktop)
    0x09, 0x04,        # Usage (Joystick)
    0xA1, 0x01,        # Collection (Application)
    0x85, 0x01,        #   Report ID (1)
    0x15, 0x00,        #   Logical Minimum (0)
    0x26, 0xFF, 0x0F,  #   Logical Maximum (4095)
    0x75, 0x10,        #   Report Size (16)
    0x95, 0x03,        #   Report Count (3)
    0x09, 0x30,        #   Usage (X)
    0x09, 0x31,        #   Usage (Y)
    0x09, 0x32,        #   Usage (Z)
    0x81, 0x02,        #   Input (Data,Var,Abs)
    0xC0,              # End Collection
])

# Ordem padrao: qual campo do relatorio REAL alimenta cada eixo virtual.
#
#   relatorio real: campo 0 = acelerador, 1 = freio, 2 = embreagem
#   o app le:       lX = Throttle, lY = Brake, lZ = Clutch
#
# Como o descritor virtual declara X, Y, Z NESSA ORDEM, e o Wine ordena os
# eixos pelo codigo do evdev (ABS_X=0 < ABS_Y=1 < ABS_Z=2), alimentar os
# campos na ordem do descritor real ja poe cada pedal no lugar certo:
# identidade.
#
# O device REAL sai errado justamente porque seus usages sao Rx, Y, Z -- no
# evdev viram ABS_RX(3), ABS_Y(1), ABS_Z(2), e o Wine ordena por codigo:
# freio, embreagem, acelerador. Dai a rotacao que o app mostra.
ORDEM_PADRAO = (0, 1, 2)
NOME_EIXOS = "CONSPIT CPP.LITE Axis"


def uhid_criar(fd, rd, nome, uniq):
    """`uniq` PRECISA ser diferente entre os devices virtuais: o Wine
    deduplica por VID/PID + serial, e com uniq vazio nos dois ele expunha
    so o primeiro -- o segundo sumia sem erro nenhum."""
    ev = struct.pack("<I128s64s64sHHIIII",
                     UHID_CREATE2,
                     nome.encode()[:127],
                     b"conspit-cpp-shim",
                     uniq.encode()[:63],
                     len(rd), BUS_USB, VID, PID, 0, 0)
    os.write(fd, ev + rd)


def uhid_input(fd, dados):
    os.write(fd, struct.pack("<IH", UHID_INPUT2, len(dados)) + dados)


def sessao(args, dev_real, sysfs):
    """Uma sessao com o device real. Devolve True se deve tentar de novo
    (pedal sumiu), False se foi pedido para encerrar."""
    with open(os.path.join(sysfs, "device", "report_descriptor"), "rb") as f:
        rd = f.read()
    fatias = fatiar_collections(rd)
    if len(fatias) < 2:
        sys.exit("o descritor tem %d top-level collection(s); esperava 2. "
                 "O firmware mudou? Rode tools/parse_hid_rdesc.py" % len(fatias))

    ini, fim = fatias[1]
    rd_vendor = rd[ini:fim]
    ids = report_ids(rd_vendor)

    print("pedais reais : %s (descritor %d bytes, %d collections)"
          % (dev_real, len(rd), len(fatias)))
    print("canal vendor : bytes %d..%d do descritor, report ID(s) %s"
          % (ini, fim, sorted(ids) or "nenhum"))

    try:
        hidraw = os.open(dev_real, os.O_RDWR | os.O_NONBLOCK)
    except PermissionError:
        sys.exit("sem acesso a %s -- instale udev/70-conspit.rules" % dev_real)
    try:
        uhid = os.open("/dev/uhid", os.O_RDWR)
    except PermissionError:
        sys.exit("sem acesso a /dev/uhid -- instale udev/70-uhid-shim.rules "
                 "(sudo cp udev/70-uhid-shim.rules /etc/udev/rules.d/ && "
                 "sudo udevadm control --reload-rules && sudo udevadm trigger)")

    uhid_criar(uhid, rd_vendor, "CONSPIT CPP.LITE", "shim-vendor")
    print("canal vendor virtual criado.")

    uhid_eixos = None
    if args.eixos:
        uhid_eixos = os.open("/dev/uhid", os.O_RDWR)
        uhid_criar(uhid_eixos, RD_EIXOS, NOME_EIXOS, "shim-eixos")
        print("joystick virtual criado (%s): lX<-campo%d  lY<-campo%d  "
              "lZ<-campo%d" % ((NOME_EIXOS,) + args.ordem))
    print("Ctrl-C para remover.\n")

    n_in = n_out = n_eixos = 0
    voltar = False
    try:
        while not PARAR[0]:
            fds = [hidraw, uhid] + ([uhid_eixos] if uhid_eixos else [])
            r, _, _ = select.select(fds, [], [], 0.5)

            if hidraw in r:                      # pedal -> app
                try:
                    dados = os.read(hidraw, 256)
                except OSError as e:
                    if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                        dados = b""
                    else:
                        # EIO tipico de replug: o device sumiu debaixo de nos
                        print("pedal desconectado (%s) -- aguardando voltar"
                              % e.strerror)
                        voltar = True
                        break
                if dados and (not ids or dados[0] in ids):
                    uhid_input(uhid, dados)
                    n_in += 1
                    if args.verbose:
                        print("  pedal->app  %s" % dados[:16].hex(" "))
                elif dados and uhid_eixos and dados[0] == 1 and len(dados) >= 7:
                    # posicoes dos pedais, permutadas para o app rotular certo
                    campos = [struct.unpack_from("<H", dados, 1 + i * 2)[0]
                              for i in range(3)]
                    rep = bytes([1]) + b"".join(
                        struct.pack("<H", campos[i]) for i in args.ordem)
                    uhid_input(uhid_eixos, rep)
                    n_eixos += 1

            if uhid_eixos and uhid_eixos in r:
                os.read(uhid_eixos, EV_BUF)   # o app so le; nada a fazer

            if uhid in r:                        # app -> pedal
                buf = os.read(uhid, EV_BUF)
                buf += b"\x00" * (EV_BUF - len(buf))
                tipo = struct.unpack_from("<I", buf, 0)[0]

                if tipo == UHID_OUTPUT:
                    tam = struct.unpack_from("<H", buf, 4 + 4096)[0]
                    dados = buf[4:4 + tam]
                    if dados:
                        os.write(hidraw, dados)
                        n_out += 1
                        if args.verbose:
                            print("  app->pedal  %s" % dados[:16].hex(" "))

                elif tipo == UHID_GET_REPORT:
                    rid, = struct.unpack_from("<I", buf, 4)
                    # a collection vendor nao declara feature report
                    os.write(uhid, struct.pack("<IHH", UHID_GET_REPORT_REPLY,
                                               rid, errno.EIO) + b"\x00" * 2)

                elif tipo == UHID_SET_REPORT:
                    rid, rnum, rtype, tam = struct.unpack_from("<IBBH", buf, 4)
                    dados = buf[12:12 + tam]
                    err = 0
                    try:
                        if rtype == UHID_FEATURE_REPORT:
                            fcntl.ioctl(hidraw, 0xC0004806 | (len(dados) << 16),
                                        bytearray(dados))
                        else:
                            os.write(hidraw, dados)
                        n_out += 1
                    except OSError as e:
                        err = e.errno or errno.EIO
                    os.write(uhid, struct.pack("<IH", UHID_SET_REPORT_REPLY,
                                               rid) + struct.pack("<H", err))

                elif tipo == UHID_OPEN:
                    print("  [app abriu o canal virtual]")
                elif tipo == UHID_CLOSE:
                    print("  [app fechou o canal virtual]")
                elif tipo == UHID_STOP:
                    break
    finally:
        for fd in (uhid, uhid_eixos):
            if fd is None:
                continue
            try:
                os.write(fd, struct.pack("<I", UHID_DESTROY))
            except OSError:
                pass
            os.close(fd)
        os.close(hidraw)
        print("sessao encerrada: %d vendor pedal->app, %d app->pedal, "
              "%d de posicao" % (n_in, n_out, n_eixos))
    return voltar and not PARAR[0]


PARAR = [False]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="mostra cada relatorio repassado")
    ap.add_argument("--sem-eixos", dest="eixos", action="store_false",
                    help="nao criar o joystick virtual de eixos permutados")
    ap.add_argument("--ordem", default=",".join(str(i) for i in ORDEM_PADRAO),
                    help="quais campos reais alimentam lX,lY,lZ (padrao %s)"
                         % ",".join(str(i) for i in ORDEM_PADRAO))
    ap.add_argument("--esperar", action="store_true",
                    help="se os pedais nao estiverem ligados, espera em vez "
                         "de sair (util para subir junto com o app)")
    args = ap.parse_args()
    try:
        args.ordem = tuple(int(x) for x in args.ordem.split(","))
        if sorted(args.ordem) != [0, 1, 2]:
            raise ValueError
    except ValueError:
        sys.exit("--ordem precisa ser uma permutacao de 0,1,2 (ex.: 2,0,1)")

    def encerrar(*_):
        PARAR[0] = True
    signal.signal(signal.SIGINT, encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    primeira = True
    while not PARAR[0]:
        dev_real, sysfs = achar_hidraw_real()
        if not dev_real:
            if primeira and not args.esperar:
                sys.exit("pedais CPP.LITE (%04x:%04x) nao encontrados. "
                         "Confira: lsusb | grep -i 3514" % (VID, PID))
            # replug: o hidrawN novo pode demorar a aparecer
            time.sleep(2)
            continue
        primeira = False
        if not sessao(args, dev_real, sysfs):
            break
    print("encerrado.")


if __name__ == "__main__":
    main()
