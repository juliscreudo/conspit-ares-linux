/* Mostra como o DirectInput do Wine monta os eixos de um device, na ordem
 * de enumeracao e com o offset dentro do DIJOYSTATE2.
 *
 * Serve para responder: quando o ConspitLink le o eixo do acelerador, em
 * qual campo do DIJOYSTATE2 ele cai? O Windows mapeia usage -> campo por
 * nome (Usage Rx -> lRx); se o Wine fizer diferente, o app rotula o pedal
 * errado, e e' isso que este programa mede.
 *
 * x86_64-w64-mingw32-gcc dinput_axes.c -o dinput_axes.exe \
 *     -ldinput8 -ldxguid -lole32 -luuid
 *
 * WINEPREFIX=.../.wine-conspitlink wine dinput_axes.exe
 */
#include <windows.h>
#include <dinput.h>
#include <stdio.h>
#include <stdlib.h>

#define ALVO_VID 0x3514
#define ALVO_PID 0x0005

static IDirectInput8W *di;
static IDirectInputDevice8W *dev;
static int ordem;

static const char *campo_do_guid(const GUID *g)
{
    if (IsEqualGUID(g, &GUID_XAxis))  return "lX";
    if (IsEqualGUID(g, &GUID_YAxis))  return "lY";
    if (IsEqualGUID(g, &GUID_ZAxis))  return "lZ";
    if (IsEqualGUID(g, &GUID_RxAxis)) return "lRx";
    if (IsEqualGUID(g, &GUID_RyAxis)) return "lRy";
    if (IsEqualGUID(g, &GUID_RzAxis)) return "lRz";
    if (IsEqualGUID(g, &GUID_Slider)) return "slider";
    return "?";
}

static const char *nome_usage(WORD page, WORD usage)
{
    if (page != 0x01) return "";
    switch (usage) {
    case 0x30: return "Usage X";
    case 0x31: return "Usage Y";
    case 0x32: return "Usage Z";
    case 0x33: return "Usage Rx";
    case 0x34: return "Usage Ry";
    case 0x35: return "Usage Rz";
    default:   return "";
    }
}

static BOOL CALLBACK ao_achar_objeto(const DIDEVICEOBJECTINSTANCEW *o, void *ctx)
{
    if (!(o->dwType & DIDFT_ABSAXIS)) return DIENUM_CONTINUE;
    printf("  %d) %-9s dwOfs %2lu   usage_page 0x%02X usage 0x%02X %-9s  \"%ls\"\n",
           ordem++, campo_do_guid(&o->guidType), (unsigned long)o->dwOfs,
           o->wUsagePage, o->wUsage, nome_usage(o->wUsagePage, o->wUsage),
           o->tszName);
    return DIENUM_CONTINUE;
}

static BOOL CALLBACK ao_achar_device(const DIDEVICEINSTANCEW *inst, void *ctx)
{
    DWORD id = inst->guidProduct.Data1;
    WORD vid = LOWORD(id), pid = HIWORD(id);
    printf("device: VID_%04X PID_%04X  \"%ls\"  devtype 0x%lX\n",
           vid, pid, inst->tszProductName, (unsigned long)inst->dwDevType);
    if (vid == ALVO_VID && pid == ALVO_PID) {
        if (SUCCEEDED(IDirectInput8_CreateDevice(di, &inst->guidInstance,
                                                 &dev, NULL)))
            return DIENUM_STOP;
    }
    return DIENUM_CONTINUE;
}

int main(int argc, char **argv)
{
    int segundos = (argc > 1) ? atoi(argv[1]) : 0;

    if (FAILED(DirectInput8Create(GetModuleHandleW(NULL), DIRECTINPUT_VERSION,
                                  &IID_IDirectInput8W, (void **)&di, NULL))) {
        printf("DirectInput8Create falhou\n");
        return 1;
    }

    printf("=== devices de jogo enumerados ===\n");
    IDirectInput8_EnumDevices(di, DI8DEVCLASS_GAMECTRL, ao_achar_device,
                              NULL, DIEDFL_ATTACHEDONLY);
    if (!dev) {
        printf("\n%04X:%04X nao encontrado no DirectInput\n", ALVO_VID, ALVO_PID);
        return 1;
    }

    /* dwOfs so faz sentido depois do SetDataFormat: e' o deslocamento
     * dentro do DIJOYSTATE2, que e' o que o app efetivamente le. */
    IDirectInputDevice8_SetDataFormat(dev, &c_dfDIJoystick2);

    printf("\n=== eixos, NA ORDEM DE ENUMERACAO ===\n");
    printf("(dwOfs 0=lX 4=lY 8=lZ 12=lRx 16=lRy 20=lRz)\n");
    IDirectInputDevice8_EnumObjects(dev, ao_achar_objeto, NULL, DIDFT_ABSAXIS);

    /* Modo monitor: le o DIJOYSTATE2 igual o app faz e mostra quais campos
     * se mexem. E' a unica forma de saber qual PEDAL alimenta qual campo --
     * modelar a partir do descritor HID leva ao erro, porque o Wine pode
     * estar sintetizando o device a partir do evdev. */
    if (segundos > 0) {
        DIJOYSTATE2 st;
        LONG lo[6], hi[6];
        const char *nome[6] = { "lX", "lY", "lZ", "lRx", "lRy", "lRz" };
        int i, primeiro = 1;

        IDirectInputDevice8_SetCooperativeLevel(dev, NULL,
                                                DISCL_BACKGROUND | DISCL_NONEXCLUSIVE);
        IDirectInputDevice8_Acquire(dev);
        printf("\n=== monitorando %d s -- PISE UM PEDAL DE CADA VEZ ===\n",
               segundos);
        fflush(stdout);

        DWORD fim = GetTickCount() + segundos * 1000;
        DWORD ultimo = 0;
        while (GetTickCount() < fim) {
            IDirectInputDevice8_Poll(dev);
            if (FAILED(IDirectInputDevice8_GetDeviceState(dev, sizeof(st), &st))) {
                IDirectInputDevice8_Acquire(dev);
                Sleep(20);
                continue;
            }
            LONG v[6] = { st.lX, st.lY, st.lZ, st.lRx, st.lRy, st.lRz };
            if (primeiro) {
                for (i = 0; i < 6; i++) lo[i] = hi[i] = v[i];
                printf("repouso:");
                for (i = 0; i < 6; i++) printf("  %s=%ld", nome[i], v[i]);
                printf("\n");
                primeiro = 0;
            }
            for (i = 0; i < 6; i++) {
                if (v[i] < lo[i]) lo[i] = v[i];
                if (v[i] > hi[i]) hi[i] = v[i];
            }
            DWORD seg = (GetTickCount() - (fim - segundos * 1000)) / 1000;
            if (seg != ultimo) {
                ultimo = seg;
                for (i = 0; i < 6; i++) {
                    if (hi[i] - lo[i] > 3000) {
                        printf("  %3lus  %s mexeu (%ld..%ld)\n",
                               (unsigned long)seg, nome[i], lo[i], hi[i]);
                        lo[i] = hi[i] = v[i];
                    }
                }
                fflush(stdout);
            }
            Sleep(10);
        }
        IDirectInputDevice8_Unacquire(dev);
    }
    return 0;
}
