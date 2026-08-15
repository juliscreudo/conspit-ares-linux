# Compila as ferramentas de diagnostico que rodam DENTRO do prefixo Wine.
#
#   make -C tools            compila hidenum.exe e dinput_axes.exe
#   make -C tools clean
#
# Requer mingw-w64:  Fedora: mingw64-gcc     Arch: mingw-w64-gcc
#
# Os .exe ficam aqui em tools/ e estao no .gitignore. Rodar (ver tambem o
# README, "O app nao lista um dispositivo"):
#
#   WINEPREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/conspit-ares-linux/prefix" \
#     wine tools/hidenum.exe

CC := x86_64-w64-mingw32-gcc

all: hidenum.exe dinput_axes.exe

hidenum.exe: hidenum.c
	$(CC) $< -o $@ -lhid -lsetupapi

# dinput8 + dxguid: GetDeviceState/DIJOYSTATE2 dentro do prefixo
dinput_axes.exe: dinput_axes.c
	$(CC) $< -o $@ -ldinput8 -ldxguid -lole32 -luuid

clean:
	rm -f hidenum.exe dinput_axes.exe

.PHONY: all clean
