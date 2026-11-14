#!/usr/bin/env bash
# Check, without any game files, that this Mac can do the Custom Edition steps that use
# Wine: a fresh Wine prefix, winetricks' MFC42 runtime, and a 32-bit Windows program
# built with Homebrew's LLVM exactly as scripts/product-id.sh builds its PIDGen caller.
# The cloud build (.github/workflows/halopad-cloud-build.yml) runs it before the long
# translation, so a Wine problem fails in minutes rather than hours.
#
#   scripts/builder/check-wine.sh [--skip-mfc42]
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
MFC42=1
[ "${1:-}" != --skip-mfc42 ] || MFC42=0
LLVM=/opt/homebrew/opt/llvm/bin
LLD=$(command -v lld-link || echo "$LLVM/lld-link")
for tool in wine wineboot wineserver winepath winetricks 7zz "$LLVM/clang" "$LLD" "$LLVM/llvm-dlltool"; do
	command -v "$tool" >/dev/null || { echo "missing $tool (brew install winetricks sevenzip llvm lld; for Wine see docs/INSTALL-WINE.md)" >&2; exit 2; }
done
WORK=$(mktemp -d "${TMPDIR:-/tmp}/halopad-wine-check.XXXXXX")
export WINEPREFIX="$WORK/prefix" WINEDEBUG=-all WINEDLLOVERRIDES="mscoree,mshtml=;winedbg=d"
cleanup() { wineserver -k >/dev/null 2>&1 || true; rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

echo "Wine: $(wine --version)"
printf 'LIBRARY kernel32.dll\nEXPORTS\nGetStdHandle@4\nReadFile@20\nWriteFile@20\nExitProcess@4\n' > "$WORK/kernel32.def"
"$LLVM/llvm-dlltool" -k -m i386 -d "$WORK/kernel32.def" -l "$WORK/kernel32.lib"
"$LLVM/clang" --target=i686-pc-windows-msvc -O1 -ffreestanding -fno-builtin -c "$ROOT/scripts/builder/wine-check.c" -o "$WORK/check.obj"
"$LLD" /nologo /entry:start /subsystem:console /nodefaultlib "$WORK/check.obj" "$WORK/kernel32.lib" /out:"$WORK/check.exe"
echo "Built a 32-bit Windows test program with $("$LLVM/clang" --version | head -n 1)"

wineboot -i > "$WORK/wineboot.log" 2>&1 || { tail -20 "$WORK/wineboot.log" >&2; echo "could not create a Wine prefix" >&2; exit 3; }
wineserver -w
echo "Created a fresh Wine prefix"
if [ $MFC42 = 1 ]; then
	winetricks -q mfc42 > "$WORK/winetricks.log" 2>&1 || { tail -20 "$WORK/winetricks.log" >&2; echo "winetricks mfc42 failed" >&2; exit 4; }
	echo "Installed MFC42 with winetricks (as the product-ID step does)"
fi
RESULT=$(printf 'HALOPAD\n' | (cd "$WORK" && wine check.exe 2>/dev/null) | tr -d '\r') || true
[ "$RESULT" = "OK HALOPAD" ] || { echo "the Windows test program did not run under Wine (got: ${RESULT:-nothing})" >&2; exit 5; }
echo "Ran the 32-bit Windows test program under Wine: $RESULT"
echo "PASS: Wine is ready for the Custom Edition steps."
