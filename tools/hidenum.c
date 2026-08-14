/* Enumera todos os devices HID visiveis para uma aplicacao Windows,
 * do mesmo jeito que o hidapi faz: SetupDiGetClassDevs(HidD_GetHidGuid) ->
 * CreateFile -> HidD_GetAttributes + HidP_GetCaps.
 *
 * Serve para responder: o ConspitLink consegue ver o canal vendor dos
 * pedais CPP.LITE dentro do Wine?
 *
 * x86_64-w64-mingw32-gcc hidenum.c -o hidenum.exe -lhid -lsetupapi
 */
#include <windows.h>
#include <setupapi.h>
#include <hidsdi.h>
#include <stdio.h>

int main(void)
{
    GUID guid;
    HidD_GetHidGuid(&guid);

    HDEVINFO set = SetupDiGetClassDevsW(&guid, NULL, NULL,
                                        DIGCF_PRESENT | DIGCF_DEVICEINTERFACE);
    if (set == INVALID_HANDLE_VALUE) { printf("SetupDiGetClassDevs falhou\n"); return 1; }

    SP_DEVICE_INTERFACE_DATA iface = { .cbSize = sizeof(iface) };
    for (DWORD i = 0; SetupDiEnumDeviceInterfaces(set, NULL, &guid, i, &iface); i++) {
        DWORD need = 0;
        SetupDiGetDeviceInterfaceDetailW(set, &iface, NULL, 0, &need, NULL);
        SP_DEVICE_INTERFACE_DETAIL_DATA_W *det = malloc(need);
        if (!det) continue;
        det->cbSize = sizeof(*det);
        if (!SetupDiGetDeviceInterfaceDetailW(set, &iface, det, need, NULL, NULL)) {
            free(det); continue;
        }

        HANDLE h = CreateFileW(det->DevicePath, GENERIC_READ | GENERIC_WRITE,
                               FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                               OPEN_EXISTING, 0, NULL);
        if (h == INVALID_HANDLE_VALUE)
            h = CreateFileW(det->DevicePath, 0,
                            FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
                            OPEN_EXISTING, 0, NULL);

        if (h != INVALID_HANDLE_VALUE) {
            HIDD_ATTRIBUTES attr = { .Size = sizeof(attr) };
            HidD_GetAttributes(h, &attr);

            if (attr.VendorID == 0x3514) {   /* so os Conspit */
                PHIDP_PREPARSED_DATA pp = NULL;
                HIDP_CAPS caps = { 0 };
                if (HidD_GetPreparsedData(h, &pp)) {
                    HidP_GetCaps(pp, &caps);
                    HidD_FreePreparsedData(pp);
                }
                WCHAR prod[256] = { 0 };
                HidD_GetProductString(h, prod, sizeof(prod));

                printf("VID_%04X PID_%04X  usage_page 0x%04X usage 0x%02X  "
                       "in %u out %u feat %u  \"%ls\"\n",
                       attr.VendorID, attr.ProductID,
                       caps.UsagePage, caps.Usage,
                       caps.InputReportByteLength, caps.OutputReportByteLength,
                       caps.FeatureReportByteLength, prod);
                printf("    path: %ls\n", det->DevicePath);
            }
            CloseHandle(h);
        }
        free(det);
    }
    SetupDiDestroyDeviceInfoList(set);
    return 0;
}
