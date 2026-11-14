/* scripts/builder/check-wine.sh: a 32-bit Windows console program built and run the
   way scripts/product-id.sh builds and runs its PIDGen caller, without any game files.
   Reads a line from stdin and prints "OK <line>". */
typedef unsigned long DWORD;
typedef void *HANDLE;
__declspec(dllimport) HANDLE __stdcall GetStdHandle(DWORD);
__declspec(dllimport) int __stdcall ReadFile(HANDLE, void *, DWORD, DWORD *, void *);
__declspec(dllimport) int __stdcall WriteFile(HANDLE, const void *, DWORD, DWORD *, void *);
__declspec(dllimport) void __stdcall ExitProcess(unsigned);
void __stdcall start(void)
{
	char line[64];
	DWORD got = 0, wrote, n;
	HANDLE out = GetStdHandle((DWORD)-11);
	ReadFile(GetStdHandle((DWORD)-10), line, sizeof line - 1, &got, 0);
	for (n = 0; n < got && line[n] != '\r' && line[n] != '\n'; n++) {}
	WriteFile(out, "OK ", 3, &wrote, 0);
	WriteFile(out, line, n, &wrote, 0);
	WriteFile(out, "\n", 1, &wrote, 0);
	ExitProcess(0);
}
