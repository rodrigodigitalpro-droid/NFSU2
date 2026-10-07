# Frame-rate stabilization

## Principle: one clock for the simulation, AI frames for the display

NFSU2's simulation is tuned for 60 fps. Above 60:
- gear changes misbehave (WidescreenFixesPack issue #1180, closed "not planned");
- the NOS trail length scales with frame rate (the fix has a dedicated `FixNOSTrailLength`);
- rain particles break;
- the fix itself caps cutscenes at 60 because "car physics are buggy above 60 FPS" (`source/NFSUnderground2.WidescreenFix/Misc.ixx`).

So uncapping the game is the wrong way to get smoothness. The stable design is:

```
 simulation + real frames ── locked 60 (WidescreenFix FPSLimit)
            │
            ▼
 RTX Remix: DLSS SR/RR renders each real frame cheaply
            │
            ▼
 DLSS Frame Generation / MFG: 1–5 generated frames per real frame
            │
            ▼
 display at 120 / 240 / 300 / 360 Hz, Reflex trimming latency, G-SYNC absorbing jitter
```

Generated frames never advance the game loop, so physics, AI and timing stay exactly as the game was tuned.

## Settings

| Layer | Setting | Value | Why |
|---|---|---|---|
| WidescreenFix `[MISC]` | `FPSLimit` | `60` | The only frame limiter in the chain; throttles the game loop itself |
| | `HighFPSCutscenes` | `1` | Cutscenes at up to 60 instead of 30 |
| | `SingleCoreAffinity` | `1` (`0` if it hangs on Windows 11 24H2) | Applied to the game's threads, this fixes crashes and stutter (PR #1045) |
| | `WindowedMode` | `4` (borderless fullscreen) | Avoids exclusive-fullscreen particle lag; used by community Remix setups |
| WidescreenFix `[NOSTrail]` | `FixNOSTrailLength` | `1` | Frame-rate-independent NOS trail |
| `dxvk.conf` | `d3d9.maxFrameRate` | `0` | No second limiter. DXVK's limiter runs in the active presenter, including the frame-generation one. |
| `rtx.conf` | `rtx.isReflexEnabled` / `rtx.reflexMode` | `True` / `1` (`2` = Boost when CPU-bound) | Reflex is what keeps frame generation's added latency acceptable |
| | `rtx.dlfg.enable` | `True` | Frame generation (RTX 40/50) |
| | `rtx.dlfg.maxInterpolatedFrames` | See the next table | Matches output to refresh rate |
| | `rtx.dlfg.enablePresentMetering` | `True` | Hardware flip metering instead of CPU pacing |
| NVIDIA driver | G-SYNC | On | Absorbs residual variance |
| | Max Frame Rate | Off | Keeps the single-limiter rule |

## Choosing the frame-generation multiplier

Rule: generated frames = refresh ÷ 60 − 1, rounded down.

| Display | `maxInterpolatedFrames` | Output | Needs |
|---|---|---|---|
| 60 Hz | Frame generation off | 60 | Any RTX |
| 120–165 Hz | `1` | 120 | RTX 40/50 |
| 180–239 Hz | `2` | 180 | RTX 50 |
| 240–299 Hz | `3` | 240 | RTX 50 |
| 300–359 Hz | `4` | 300 | RTX 50 |
| 360 Hz+ | `5` | 360 | RTX 50, dxvk-remix CI build (remix-1.5.2 stops at 4) |

**RTX 20/30 cards** have no DLSS Frame Generation. Run a locked 60 with DLSS SR and Reflex, which gives stability over smoothness. Smooth Motion is RTX 40/50 only and redundant where native frame generation exists.

## Holding the real 60

Frame generation multiplies whatever it is fed. Uneven real frames give uneven generated frames, so the 60 real frames must stay flat. Frame generation runs on the same GPU, so leave headroom below 16.7 ms.

Levers, cheapest first:

1. **DLSS SR mode:** Quality → Balanced → Performance (DLSS 4.5's transformer model holds up well at Performance).
2. **Indirect lighting:** keep NRC (`rtx.integrateIndirectMode = 2`).
3. **Light count:** emissive surfaces before hand-placed lights. A community lights pass with 100+ lights in view was too slow.
4. **Anti-culling scope:** lower `rtx.antiCulling.object.numObjectsToKeep` before disabling anti-culling.
5. **Texture set:** stay inside `tools/texture_budget.py` limits, so the texture manager never has to stream mips down mid-race.
6. **Streaming hitches:**
   - Ship RTX IO `.pkg` assets (GPU decompression).
   - Install on NVMe.
   - Keep replacement meshes instanced, so district transitions don't spike the BVH.
7. **CPU side:**
   - Reflex Boost (`rtx.reflexMode = 2`).
   - Keep the affinity fix.
   - Replacements never add draw calls, but every D3D9 call already crosses the 32-bit→64-bit bridge, so the draw-call count of the original game is the CPU floor.

## Measuring

**Tools**
- NVIDIA FrameView or PresentMon on the Vulkan swapchain.
- With Reflex on, FrameView also reports PC latency.

**Test route**
- Repeat the same route every time: City Core at night, in rain, in traffic, with NOS.
- It combines the worst cases: rain particles, wet reflections, neon and fast streaming.

**Project targets on the reference GPU (RTX 4070, 12 GB)**

| Metric | Target |
|---|---|
| Real-frame average | 60 |
| Real-frame 1% low | ≥ 57 |
| Real-frame p99 frame time | ≤ 18 ms |
| Visible hitches > 50 ms on the route | 0 |

## Sources

**WidescreenFix**
- ini: https://github.com/ThirteenAG/WidescreenFixesPack/blob/master/data/NFSUnderground2.WidescreenFix/scripts/NFSUnderground2.WidescreenFix.ini
- Physics comment in the source: https://github.com/ThirteenAG/WidescreenFixesPack/blob/master/source/NFSUnderground2.WidescreenFix/Misc.ixx
- Issues and PR: https://github.com/ThirteenAG/WidescreenFixesPack/issues/1180, https://github.com/ThirteenAG/WidescreenFixesPack/pull/1045

**PCGamingWiki** (rain particles, exclusive-fullscreen lag)
- https://www.pcgamingwiki.com/wiki/Need_for_Speed:_Underground_2

**RTX Remix**
- Options (`rtx.dlfg.*`, `rtx.reflexMode`, `rtx.integrateIndirectMode`): https://raw.githubusercontent.com/NVIDIAGameWorks/dxvk-remix/main/RtxOptions.md
- `d3d9.maxFrameRate` in the frame-generation presenter: https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/src/d3d9/d3d9_swapchain.cpp
