# NFSU2 Remaster: Technical Blueprint

Research snapshot: **2026-10-07**. Versions, flags and driver numbers move fast;
each claim lists its source at the end of this document.

**Goal:** remaster *Need for Speed: Underground 2* (PC, 2004) with:
- new 3D models and every texture replaced;
- a stable frame rate;
- support for as many NVIDIA technologies as possible, RTX Remix included.

It should also run lighter than a naive "4K everything" pass.

---

## 1. Decision: an RTX Remix remaster of the original game

| | **A. RTX Remix remaster (chosen)** | B. Rebuild in Unreal Engine 5 (NvRTX) |
|---|---|---|
| Rendering | Path tracing: ReSTIR, Neural Radiance Cache (NRC), Opacity Micromaps (OMM) | Lumen/Nanite, or path tracing via NvRTX |
| NVIDIA features | DLSS 4.5 SR/RR, Frame Gen, Multi Frame Gen, Reflex, RTX IO, all inside the Remix runtime | Everything with a DX12 SDK, incl. Dynamic MFG, Mega Geometry (experimental), Neural Texture Compression (beta) |
| RTX Remix compatible | **Yes, by definition** | No. Remix only hooks D3D8/D3D9 games. |
| Gameplay, handling, career | Original, untouched | Must be rebuilt from scratch |
| Assets | Replaced one draw call at a time, by hash; game files are never repacked | Every asset recreated |
| Can be distributed | Mod files only; players supply their own game | Cannot use EA's code, assets or trademarks |
| Effort | One modding team | Studio-scale |

Path A wins for four reasons, each backed by the research:

1. **"RTX Remix compatible" only exists on this path.** Remix is a D3D8/9 → Vulkan path tracer. A new-engine remake can't use it.
2. **No public tool can write new world geometry back into NFSU2's files.**
   - NFS-ModTools can *export* the world, but is read-only.
   - Binary, NFS-TexEd and XNFSTPKTool re-import *textures* only.
   - Remix sidesteps this: it swaps meshes and materials as the game draws them, so `STREAML4RA.BUN` never needs to be rebuilt.
3. **The physics only work at 60 fps.** Frame generation gives a 120–360 Hz *display* while the simulation stays locked at the 60 fps it was tuned for. See [FRAME-PACING.md](FRAME-PACING.md).
4. **It is the shippable form of a "remake".** It contains only new assets plus config. A rebuild using EA's world, cars and branding cannot be distributed.

Path B is only worth it for features Remix cannot reach (§3.3). Hero assets authored for Path A (§4.3) carry over if you own them.

---

## 2. Architecture

```
 speed2.exe v1.2 NTSC (32-bit, Direct3D 9, simulation locked at 60)
   │
   ├─ dsound.dll  = ThirteenAG WidescreenFix ASI loader (renamed from dinput8.dll)
   │     resolution/FOV/HUD fixes, FPSLimit=60, thread affinity, NOS trail fix
   │     optional: NFSU2 Unlimiter (bigger memory pools, add-on cars)
   │
   └─ d3d9.dll    = RTX Remix bridge client (32-bit)
         │  IPC
         ▼
   .trex/NvRemixBridge.exe (64-bit)  →  .trex/d3d9.dll = dxvk-remix runtime (Vulkan)
         │
         ├─ path tracer: ReSTIR DI/GI (RTXDI), NRC, Opacity Micromaps, volumetrics,
         │               GPU particles, RTX Skin
         ├─ DLSS 4.5 Super Resolution / DLAA, Ray Reconstruction (Preset F)
         ├─ DLSS Frame Generation / Multi Frame Generation, Reflex, present metering
         ├─ Remix Logic (event-driven config layers), Remix API (forwarded over the bridge)
         └─ rtx-remix/mods/NFSU2Remaster/mod.usda
               replacement meshes (USD), AperturePBR materials,
               BCn *.rtex.dds textures, RTX IO .pkg for release
```

Config files shipped from this repo: [`runtime/rtx.conf`](../runtime/rtx.conf),
[`runtime/dxvk.conf`](../runtime/dxvk.conf) and
[`runtime/NFSUnderground2.WidescreenFix.overrides.ini`](../runtime/NFSUnderground2.WidescreenFix.overrides.ini).

### Runtime build to target

| Build | DLSS | Minimum driver | Use for |
|---|---|---|---|
| `remix-1.5.2` (16 Jun 2026, latest tagged release) | DLSS 4 (MFG up to 4 generated frames) | 572.18 | Stable baseline, public releases |
| dxvk-remix CI build `rtx-remix-for-x86-games-1340-…` (Aug 2026) | DLSS 4.5 RR Preset F, MFG up to 6 | 610.47 | Development, and releases once tagged |

NVIDIA's DLSS 4.5 Remix article mentions "RTX Remix 1.6", but no 1.6 tag existed on 2026-10-07. Re-check before each release.

---

## 3. NVIDIA technology coverage

### 3.1 Inside the RTX Remix runtime (no engine work needed)

| Technology | How it's used here | GPU |
|---|---|---|
| Path tracing (RTXDI/ReSTIR DI, ReSTIR GI) | Replaces the 2004 lighting: wet roads, neon, car paint | Any RTX |
| Neural Radiance Cache | Indirect light: `rtx.integrateIndirectMode = 2` | Any RTX |
| DLSS Super Resolution / DLAA (4.5 transformer model in CI builds) | Main lever for keeping 60 real fps | RTX 20+ |
| DLSS Ray Reconstruction (Preset F in CI build) | Denoising; very visible on reflections | RTX 20+ |
| DLSS Frame Generation (2x) | 60 fps simulation shown at 120 Hz | RTX 40+ |
| DLSS Multi Frame Generation (up to 4x in 1.5.2, 6x in CI) | 240–360 Hz output | RTX 50 |
| NVIDIA Reflex (+ Boost) | Cuts back the latency frame generation adds | GeForce |
| Opacity Micromaps | Cheaper alpha-tested geometry: fences, foliage, chain-link | RTX 40+ for hardware gain |
| RTX IO packaging (Remix 1.5) | GPU-decompressed `.pkg` assets: smaller download, faster streaming | Any RTX |
| RTX Volumetrics | Night haze, streetlight shafts, rain atmosphere | Any RTX |
| Path-traced GPU particles / Particle VFX 2.0 | Rain, sparks, tyre smoke, NOS | Any RTX |
| RTX Skin (subsurface scattering) | Only for character models in the garage and cutscenes | Any RTX |
| Remix Logic | Config layers driven by runtime events (e.g. garage vs. street look) | — |
| Remix API (C, forwarded over the 32-bit bridge) | Lights or geometry driven from an ASI plugin, e.g. headlights bound to car state | — |
| Toolkit AI Tools (ComfyUI), REST API, MCP server | Bulk PBR/upscale pass, scripted ingestion | ≥ 8 GB VRAM (12 GB+ recommended) |

### 3.2 Driver-level (works on top, no integration)

| Technology | Verdict |
|---|---|
| G-SYNC / VRR | **Use it.** It absorbs the leftover frame-time variance. |
| RTX HDR | Optional. The NVIDIA app lists DX9 and Vulkan. Test it together with Frame Generation. |
| Smooth Motion | Redundant: Remix already has native DLSS FG. It is also RTX 40/50 only. |
| DSR/DLDSR, NIS | Redundant with DLSS/DLAA. NIS is also a Remix upscaler option (`rtx.upscalerType`). |
| Ultra Low Latency mode | Doesn't apply: Remix presents through Vulkan with Reflex. |

### 3.3 Not reachable through Remix today

| Technology | Why not | Path |
|---|---|---|
| DLSS 5 (3D-guided neural rendering) | Shipped Sep 2026 on RTX 50; no public SDK found. `rtx.dlssNeuralRendering.*` options exist in dxvk-remix `main` but in no release. | Watch the Remix releases |
| Dynamic Multi Frame Generation | D3D12-only in Streamline | Path B |
| RTX Mega Geometry | Only in the "not suitable for shipping" NvRTX experimental branch | Path B |
| Neural Texture Compression | v0.10 beta; no Remix option | Path B (later) |
| Neural Materials / Neural Faces | Not released | — |
| Reflex 2 Frame Warp | Not generally available | — |
| ACE / Audio2Face | No conversational characters in NFSU2 | Out of scope |

No single path gives "every" NVIDIA technology. Path A covers the full shipping
DLSS/Reflex/path-tracing stack. Path B would add only beta or D3D12-only extras.

---

## 4. Asset pipeline: every texture, new models, lighter

### 4.1 Inventory every texture

Remix identifies each texture and mesh by **hash**. "Every texture used" means
every captured hash ends in exactly one of three states:

- **replaced**
- **tagged** (UI, sky, decal, particle, terrain, …)
- **deliberately ignored**

1. **Capture plan.** In-game: Alt+X → Enhancements → *Capture Frame in USD*. Capture each of these, at night and in rain where it applies:
   - every district of Bayview
   - every closed race track (`STREAML4RD`)
   - every shop and garage interior
   - the front-end menus
   - every car with each body-kit/rim/spoiler family
2. **Tag before replacing.** Use the Game Setup tab to fill `rtx.uiTextures`, `rtx.skyBoxTextures`, `rtx.ignoreTextures`, `rtx.decalTextures`, `rtx.particleTextures` and `rtx.postfx.motionBlurMaskOutTextures`, then append the lists to `runtime/rtx.conf`.
   - The community config ([Ekozmaster/NFSU2-RTX-Remix](https://github.com/Ekozmaster/NFSU2-RTX-Remix)) already tags 78 UI and 33 ignore hashes. Its repo has no license, so ask before reusing them.
3. **Coverage sheet.** Track hash → state → owner. Release only at 100% coverage of the capture plan.

### 4.2 Bulk pass (AI-assisted)

- Run every captured legacy texture through the Toolkit AI Tools or the
  [ComfyUI-RTX-Remix](https://github.com/NVIDIAGameWorks/ComfyUI-RTX-Remix) node pack:
  - upscale
  - remove baked lighting
  - generate normal, roughness and height maps
- Script it with the Toolkit REST API, or the MCP server for agent-driven batches.
- The originals are DXT1/DXT3 at low resolution. AI upscaling mangles text, so signage, logos and HUD-adjacent textures need a manual pass.
- Ingest everything through the Toolkit. It validates assets, writes `<name>.<suffix>.rtex.dds` with full mip chains, and picks the block format per texture type:

| Type (suffix) | Format |
|---|---|
| albedo `.a`, emissive `.e`, transmittance `.tr`, single scattering `.ss` | BC7 |
| normal `.n` (OpenGL, DirectX or octahedral) | BC5 |
| roughness `.r`, metallic `.m`, height `.h`, anisotropy `.an`, measurement distance `.md` | BC4 |
| skybox `.s` | BC6H (set `rtx.skyForceHDR = True`) |

### 4.3 Hero assets (hand-made)

**Reference geometry**
- Export the original cars and world with NFS-ModTools AssetDumper (FBX/Collada).
- Use the export only as a scale and placement blockout, then model new assets in Blender (or any DCC that outputs FBX/OBJ/glTF).
- Ingest them as USD and replace by hash.

**Cars and parts**
- NFSU2 assembles each car from parts (bodies, kits, rims, spoilers, hoods, lights, …).
- Each part is its own draw call with its own hash, so it gets its own replacement.
- Build cars **part by part** so customization keeps working.

**Distance LODs**
- The game draws distant LODs as separate meshes with their own hashes.
- Give each one a lighter replacement instead of reusing the hero mesh.

**Materials**
- Use `AperturePBR_Opacity` for most surfaces.
- Use `AperturePBR_Translucent` for glass, headlight covers and taillights. Names containing "glass"/"translucent"/"trans" convert automatically.

**Paint colour (R&D risk, check in phase 1)**
- In the NFS Carbon Remix port the player's paint colour wasn't captured.
- Confirm NFSU2's paint/vinyl tint reaches Remix.
- If it doesn't, feed it through the Remix API from an ASI plugin.

**Asset provenance**
- Author originals, or use properly licensed sources.
- Never use rips from other games: they are the fastest way to get a mod taken down.

### 4.4 Budgets that keep it light

These are project policy, chosen to hold a stable 60 real fps on a 12 GB RTX 4070-class GPU (NVIDIA's recommended spec for Remix). Profile and adjust.

| Asset | Budget |
|---|---|
| Player/hero car, complete | ≤ 250k triangles across all parts |
| Traffic and AI cars | 30–60k triangles |
| Props | 1–20k triangles; repeated props **instanced** (PointInstancer) |
| Buildings | Modular, instanced kits; one replacement per game LOD |
| Albedo/normal maps | ≤ 4096 for hero cars, ≤ 2048 for the world |
| Roughness/metallic/height | ≤ 2048 (usually 1024 is enough) |
| HDR sky | ≤ 8192 × 4096, BC6H |
| Whole texture set | ≤ 6 GiB of VRAM (`--budget-mb 6144`) |
| Hand-placed lights | Emissive-first: let ReSTIR sample neon and street-lamp emissives. A community light pass with 100+ lights in view proved too slow. |

`tools/texture_budget.py` enforces the texture rows, and its exit code can gate commits or CI:

```sh
python3 tools/texture_budget.py rtx-remix/mods/NFSU2Remaster --budget-mb 6144
```

It fails a build on any of the following:
- uncompressed formats
- partial mip chains
- non-power-of-two sizes
- textures over their resolution cap
- loose PNG/TGA/etc. in the shipped folder
- the total over budget

It warns when a channel isn't in the format the Remix ingestor uses.

### 4.5 Packaging

1. Package from the Toolkit's Packaging tab.
2. Use **binary USD** and **override flattening**, which make the mod smaller and faster to load.
3. Produce **RTX IO `.pkg`** output; `rtx.io.enabled = True` is already set.
4. Ship the zip; players drop it into `rtx-remix/mods/`.
5. Never include `speed2.exe`, any `.BUN/.BIN/.LZC` file or a capture. `.gitignore` already blocks them.

---

## 5. Frame-rate stabilization (summary)

Full rationale and settings: [FRAME-PACING.md](FRAME-PACING.md).

1. **One clock for the simulation:** WidescreenFix `FPSLimit = 60`. Gear changes, physics and NOS trails are frame-rate dependent.
2. **The AI handles the display:** DLSS Frame Generation (2x, RTX 40+) or Multi Frame Generation (4x–6x, RTX 50) turns 60 real frames into 120–360 Hz output.
3. **Latency claw-back:** Reflex on (Boost if CPU-bound). G-SYNC absorbs the rest.
4. **Hold the real 60:** DLSS SR mode, NRC, light count, anti-culling scope, texture budget.
5. **Measure:** NVIDIA FrameView/PresentMon on a fixed worst-case route (night, rain, City Core).

---

## 6. Roadmap

| Phase | Work | Exit criteria |
|---|---|---|
| 0. Baseline | v1.2 NTSC exe, WidescreenFix, Remix 1.5.2, `runtime/*` configs | Boots path-traced; first captures |
| 1. Compatibility | Sky, UI/ignore/decal/particle tags, anti-culling, motion-blur masks, neon/underglow emissives, rain, paint-colour check | Full race at night in rain with no missing geometry or UI artifacts |
| 2. Texture coverage | Capture plan, AI bulk pass, manual fixes, ingestion | 100% of captured hashes resolved; `texture_budget.py` green |
| 3. Hero models | Player cars and parts, then traffic, then the world district by district | Every car and part replaced; world LODs replaced |
| 4. Lighting and look | Street/neon light pass, wet-road materials, volumetrics, Remix Logic layers | Art sign-off on reference shots |
| 5. Performance | Budgets, FrameView passes, CI-build DLSS 4.5 | Targets in FRAME-PACING.md met on an RTX 4070 |
| 6. Release | Binary USD, flattening, RTX IO `.pkg`, install guide | Clean install on a fresh v1.2 game |

---

## 7. Risks and open questions

**Paint colour capture**
- Carbon's Remix port lost the player's paint colour.
- Mitigation: verify in phase 1, with a Remix API plugin as the fallback.

**Shader-path draws**
- With `rtx.useVertexCapture = False`, any draw that uses a vertex shader is skipped by the ray tracer.
- Watch for missing effects. The community config runs this way, so most geometry is fixed-function.

**CPU bottleneck**
- The game is a 32-bit single-threaded process, and every call also crosses the bridge.
- Carbon's Remix port became CPU-bound.
- Mitigation: Reflex Boost, the thread-affinity fix, and no extra draw calls (replacements don't add any).

**Windows 11 24H2**
- WidescreenFix has open issues: black screen (#1649) and hang/crash with `SingleCoreAffinity` (#1573, #1748).

**DXVK upstream issues**
- Smoke hitches (#5333) and an endless loading screen with "render state 161" (#5677).
- Check whether dxvk-remix inherits them.

**Legal**
- EA's content policy: "In general, we don't allow any modifications to our games."
- GitHub's DMCA repository shows no EA takedown of an NFS fan mod or remake to date.
- Keep it non-commercial, ship replacements only, credit community tools, and get permission before reusing unlicensed community configs or assets.
- This is not legal advice.

---

## Sources

**RTX Remix**
- Releases: https://github.com/NVIDIAGameWorks/rtx-remix/releases
- Release notes: https://docs.omniverse.nvidia.com/kit/docs/rtx_remix/latest/docs/changelog/remix-releasenotes.html
- Options: https://raw.githubusercontent.com/NVIDIAGameWorks/dxvk-remix/main/RtxOptions.md
- Config layers: https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/documentation/RemixConfig.md
- Remix API: https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/documentation/RemixSDK.md
- Compatibility: https://github.com/NVIDIAGameWorks/toolkit-remix/blob/main/docs/introduction/intro-compatibility.md
- Requirements: https://github.com/NVIDIAGameWorks/toolkit-remix/blob/main/docs/introduction/intro-requirements.md
- Ingestion: https://github.com/NVIDIAGameWorks/toolkit-remix/blob/main/docs/howto/learning-ingestion.md
- Packaging: https://github.com/NVIDIAGameWorks/toolkit-remix/blob/main/docs/howto/learning-packaging.md
- AI tools: https://github.com/NVIDIAGameWorks/toolkit-remix/blob/main/docs/howto/learning-aitools.md
- Texture suffixes and formats, toolkit-remix source:
  - `omni.flux.asset_importer.core/.../data_models/constants.py`
  - `lightspeed.trex.asset_pipeline.core/.../constants.py`
- DLSS 4.5 in Remix: https://www.nvidia.com/en-us/geforce/news/rtx-remix-dlss-4-5-ray-reconstruction-painkiller-morrowind/
- Remix Logic: https://www.nvidia.com/en-us/geforce/news/rtx-remix-logic-new-game-mods-new-plugins/

**NVIDIA**
- DLSS 4.5 (Gamescom 2026): https://www.nvidia.com/en-us/geforce/news/gamescom-2026-nvidia-geforce-rtx-dlss-4-5-announcements/
- Dynamic MFG: https://www.nvidia.com/en-us/geforce/news/nvidia-app-dlss-4-5-dynamic-multi-frame-generation-available-now/
- DLSS 5: https://www.nvidia.com/en-us/geforce/news/dlss-5-3d-guided-neural-rendering/
- Streamline: https://github.com/NVIDIA-RTX/Streamline
- RTX Kit: https://developer.nvidia.com/rtx-kit
- Mega Geometry: https://github.com/NVIDIA-RTX/RTXMG
- Reflex: https://developer.nvidia.com/performance-rendering-tools/reflex
- Smooth Motion: https://www.nvidia.com/en-us/geforce/news/nvidia-app-global-dlss-overrides-rtx-40-series-smooth-motion/
- NvRTX: https://developer.nvidia.com/game-engines/unreal-engine/rtx-branch

**NFSU2**
- PCGamingWiki: https://www.pcgamingwiki.com/wiki/Need_for_Speed:_Underground_2
- WidescreenFix: https://github.com/ThirteenAG/WidescreenFixesPack (source `source/NFSUnderground2.WidescreenFix/`, release tag `nfsu2`, issues #1180, #1573, #1649, #1748)
- ExtraOptions: https://github.com/ExOptsTeam/NFSU2ExOpts
- Unlimiter: https://github.com/nlgxzef/NFSU2Unlimiter
- Binarius: https://github.com/nlgxzef/Binarius
- NFS-ModTools: https://github.com/NFSTools/NFS-ModTools
- XNFSTPKTool: https://github.com/xan1242/xnfstpktool

**Community Remix work**
- NFSU2 Remix mod on ModDB: https://www.moddb.com/mods/need-for-speed-underground-2-remix
- Ekozmaster's config: https://github.com/Ekozmaster/NFSU2-RTX-Remix
- adamplayer's lights pass: https://github.com/adamplayer/Underground2RTX
- xoxor4d's Carbon port: https://github.com/xoxor4d/nfsc-rtx

**DXVK issues and EA policy**
- DXVK issues: https://github.com/doitsujin/dxvk/issues/5333, https://github.com/doitsujin/dxvk/issues/5677
- EA content policy: https://help.ea.com/en/articles/security-and-rules/ea-content-policy/
- GitHub DMCA repository: https://github.com/github/dmca
