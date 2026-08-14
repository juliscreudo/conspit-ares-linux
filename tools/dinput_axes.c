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

int main(void)
{
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
    return 0;
}
