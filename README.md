# NFSU2 Remaster

A path-traced remaster of *Need for Speed: Underground 2* (PC, 2004), built on **NVIDIA RTX Remix**. It has these goals:
- new 3D models and every texture replaced;
- a locked, frame-generated frame rate;
- the full shipping NVIDIA stack: DLSS 4.5 SR/RR, Frame Generation and Multi Frame Generation, Reflex, Neural Radiance Cache and RTX IO.

The repository ships **only new assets, configs and tools**. Players bring their own copy of the game.

## Why RTX Remix instead of a new-engine remake

- **RTX Remix only exists on this path.** It path-traces the original D3D9 game, so "RTX Remix compatible" is only possible by remastering the original executable.
- **No world repacking needed.** No public tool can write new world geometry back into NFSU2's files. Remix replaces meshes and textures as the game draws them.
- **The physics stay safe.** They break above 60 fps, so the simulation stays locked at 60 and DLSS Frame Generation produces the 120–360 Hz display.

Full reasoning, technology matrix, asset pipeline, budgets and roadmap: [docs/BLUEPRINT.md](docs/BLUEPRINT.md).
Frame-rate design: [docs/FRAME-PACING.md](docs/FRAME-PACING.md).

## Setup (development)

1. Install NFSU2 and apply **patch 1.2**. Tools in this chain expect the `speed2.exe` v1.2 NTSC build (4,800,512 bytes).
2. Install **ThirteenAG's WidescreenFix** (release `nfsu2`).
   - Apply [`runtime/NFSUnderground2.WidescreenFix.overrides.ini`](runtime/NFSUnderground2.WidescreenFix.overrides.ini) to its ini.
   - Rename `dinput8.dll` to `dsound.dll`.
3. Install the **RTX Remix runtime** next to `speed2.exe`.
   - remix-1.5.2 needs NVIDIA driver 572.18+.
   - The DLSS 4.5 CI builds need driver 610.47+.
4. Copy [`runtime/rtx.conf`](runtime/rtx.conf) and [`runtime/dxvk.conf`](runtime/dxvk.conf) next to `speed2.exe`.
5. Create an RTX Remix Toolkit project named `NFSU2Remaster`. The Toolkit links its mod folder into `rtx-remix/mods/`. Commit that mod layer (`mod.usda` plus the ingested assets) to this repo; captures stay local.

Requirements:
- **Players:** an RTX GPU, Windows 10/11.
- **Recommended:** RTX 4070 12 GB.
- **Frame generation:** RTX 40+. Multi Frame Generation needs RTX 50.

## Tools

| Tool | What it does |
|---|---|
| [`tools/texture_budget.py`](tools/texture_budget.py) | Reads DDS headers and totals the VRAM the textures use. Fails on uncompressed or mip-less textures, non-power-of-two sizes, oversized textures, loose source images and an over-budget set. Warns when a channel isn't in the BC format the Remix ingestor writes. Standard library only. |

```sh
python3 tools/texture_budget.py path/to/rtx-remix/mods/NFSU2Remaster --budget-mb 6144 --json report.json
python3 -m unittest discover -s tests
```

## Repository rules

- Binary art (DDS, PNG, FBX, Blender, USD crate files) goes through **Git LFS**; see `.gitattributes`. Text USD (`.usda`) stays in Git so replacements diff and review like code.
- `.gitignore` blocks EA's files (`speed2.exe`, `.BUN/.BIN/.LZC`, game folders) and Remix `captures/`. These must never be committed or distributed.
- Author original models and textures, or use properly licensed ones. Never rip assets from other games.
- Ask before reusing community configs or assets that carry no license.

## Credits

This project builds on the work of others:
- NVIDIA RTX Remix
- ThirteenAG (WidescreenFixesPack)
- nlgxzef (NFSU2 Unlimiter, Binarius)
- NFSTools (NFS-ModTools)
- xan1242 (XNFSTPKTool)
- the community NFSU2 Remix efforts by UncleBurrito, Ekozmaster and adamplayer

*Need for Speed* and *Underground 2* are trademarks of Electronic Arts. This is an unofficial, non-commercial fan project.
