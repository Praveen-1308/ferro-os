# FerroOS Windows Game Center Investigation, 64-Bit Game Execution & Exact Logo Extraction Report

> [!NOTE]
> **User Requirement Alignment**
> 1. **Windows Game Center Investigation**: Analyzed Microsoft's official Windows Game Centers (Games for Windows - LIVE, Windows Games Explorer, and modern Xbox App).
> 2. **Alternative 64-Bit Windows Game (.exe)**: Downloaded, unpacked, and executed **Luanti 3D (Minetest 64-bit Windows `luanti.exe`)**, running natively via Wine 64-bit and Box64 dynarec.
> 3. **Exact Icon Matching**: Installed `icoutils` (`wrestool` & `icotool`) to extract the exact authentic Windows `.ico` / `.png` bitmaps directly from PE resource sections (`.rsrc`), ensuring that every desktop shortcut displays the exact Windows logo.

---

## 1. Investigation of Official Windows Game Center Applications

| Application | Origin | Architecture | Status in FerroOS / Wine |
| :--- | :--- | :--- | :--- |
| **Games for Windows - LIVE (GFWLive)** | Microsoft (Windows XP/Vista/7/8) | 32-bit x86 (`PE32`) | Unpacked (`GFWLive.exe`). Fails on ARM64 hosts due to QEMU `0x7ffe0000` memory collision and defunct 2014 online servers. |
| **Windows Games Explorer (`gameux.dll`)** | Microsoft (Windows Vista/7) | COM Library (`shell:Games`) | Built into standard Windows explorer to aggregate shortcuts; Wine implements basic stubs. |
| **Xbox App for PC / Xbox Game Bar** | Microsoft (Windows 10/11) | UWP / MSIX Package | Requires proprietary Windows Store DRM, DirectX 12 hardware binding, and UWP virtualization not supported in standard Wine. |
| **Industry Standard: Steam for Windows** | Valve | 32-bit/64-bit Client | Requires heavy Chromium Embedded Framework (CEF) and steamwebhelper background processes. |

---

## 2. 64-Bit Windows Game Execution: Luanti 3D (`luanti.exe`)

Because 32-bit PE files collide on Apple Silicon, we acquired **Luanti 5.17.0 (Minetest)**, a complete 64-bit Windows (`PE32+ x86-64`) voxel 3D sandbox game:
- **Download Package**: `luanti-5.17.0-win64.zip` (17.5 MB)
- **Primary Binary**: `/home/ferro/games/minetest_win64/luanti-5.17.0-win64/bin/luanti.exe`
- **Architecture**: `PE32+ executable (GUI) x86-64, for MS Windows, 15 sections`

### A. Execution via `ferro-core win-run`
```bash
ferro-core win-run /home/ferro/games/minetest_win64/luanti-5.17.0-win64/bin/luanti.exe --prefix /home/ferro/.wine-x64
```

### B. Runtime Log Highlights
```text
🪟 [FerroOS WinBridge] Launching 'luanti.exe' (Windows PE 64-bit Executable (AMD64))
  ⚡ SchedExt: Engaging 500µs quantum slice and Nice -10 priority
✅ GameMode Profile: ACTIVE
✅ Scheduler Profile 'GAMING' is now ACTIVE.
  🚀 Translation Bridge: Box64 dynarec engaged for x86_64 PE on ARM64 host
Luanti 5.17.0 (Windows)
Using LuaJIT 2.1.1782726002
Running on Windows/10.0.18362 x86_64
Registered TouchWindow & RawGameController
Main Menu Lua engine initialized successfully
```

### C. Live Window Audit via Chrome DevTools MCP
The 3D game window was captured live on display `:0`:
```text
Window ID: 0x4c00003 "Luanti 5.17.0 [Main Menu] [4.5 (Compatibility Profile) Mesa 22.3.6]"
Geometry:  1024x600 at +288+150
Class:     ("luanti.exe" "luanti.exe")
```

![Luanti 64-Bit Windows Game Running on FerroOS Desktop](/Users/praveenkumar/rust%20os/docs/reports/ferroos_luanti_windows64_game_live.png)

---

## 3. Exact Windows Application Logo Extraction Pipeline

To ensure the desktop icons match the exact Windows application logos, we deployed a resource extraction workflow using `icoutils`:

```bash
# Extract RT_GROUP_ICON resource (Type 14) from PE binary header
wrestool -x -t 14 "$TARGET_EXE" -o "/home/ferro/.icons/extracted/${APP}.ico"

# Convert extracted ICO to highest-resolution 32-bit RGBA PNG
icotool -x -o "/home/ferro/.icons/extracted/" "/home/ferro/.icons/extracted/${APP}.ico"
```

### Extracted Application Logos:
1. **Luanti 3D Game**: Official 3D grass/dirt voxel block (`luanti_1_48x48x32.png`) extracted directly from `luanti.exe`.
2. **7-Zip File Manager**: Official 7-Zip vector icon (`7zFM_1_110x63x8.png`) extracted from `_7zFM.exe`.
3. **Notepad++**: Official green chameleon icon (`notepadpp_4_32x32x32.png`) extracted from `notepad++.exe`.
4. **Games for Windows - LIVE**: Official Microsoft 3D globe logo (`gfwl_1_256x256x32.png`) extracted from `GFWLive.exe`.

### Desktop Shortcuts with Authentic Icons
All desktop launchers on `/home/ferro/Desktop/` were updated to reference their authentic extracted icons:

![FerroOS Desktop Shortcuts with Exact Windows Logos](/Users/praveenkumar/rust%20os/docs/reports/ferroos_desktop_exact_icons_verified.png)

---

## 4. Current Available .EXE / .MSI Workloads Summary

| Application | Path | Architecture | Icon Status |
| :--- | :--- | :--- | :--- |
| **Luanti 3D Game** | `/home/ferro/games/minetest_win64/.../luanti.exe` | 64-bit x86_64 | Exact Voxel Icon Extracted |
| **7-Zip File Manager** | `/home/ferro/7zip/extracted/_7zFM.exe` | 64-bit x86_64 | Exact 7z Icon Extracted |
| **Notepad++ v8.9** | `/home/ferro/notepadpp/notepad++.exe` | 64-bit x86_64 | Exact Chameleon Icon Extracted |
| **GFWL Client** | `/home/ferro/GFWL/.../GFWLive.exe` | 32-bit x86 | Exact Microsoft Globe Icon Extracted |
| **Unigine Heaven 4.0** | `/home/ferro/games/unigine_heaven/.../Heaven.exe` | 32-bit x86 | Extracted (`heaven.ico`) |
| **Unigine Valley 1.0** | `/home/ferro/games/unigine_valley/.../Valley.exe` | 32-bit x86 | Extracted (`icon.ico`) |
