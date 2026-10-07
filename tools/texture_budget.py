#!/usr/bin/env python3
"""Texture budget gate for the NFSU2 RTX Remix mod.

Scans a directory tree for DDS textures, reads their headers (standard library
only), estimates how much GPU memory each one occupies, and flags anything that
makes the mod heavier than it needs to be:

  * uncompressed formats where a block-compressed (BCn) format would do
  * missing or partial mip chains (shimmering at distance, wasted bandwidth)
  * non power-of-two dimensions
  * textures above the resolution cap for their role
  * a material channel stored in the wrong BCn format for its role
  * PNG/TGA/JPG/... sources left inside the folder that gets shipped

Exits with status 1 when any error is found or the total exceeds --budget-mb,
so it can gate commits and CI.

    python tools/texture_budget.py rtx-remix/mods/NFSU2Remaster --budget-mb 6144
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

DDS_MAGIC = b"DDS "
DDPF_FOURCC = 0x4
DDSCAPS2_CUBEMAP = 0x200
DX10_MISC_TEXTURECUBE = 0x4

# Bytes per 4x4 block for block-compressed formats.
FOURCC_FORMATS = {
    b"DXT1": ("BC1", 8),
    b"DXT2": ("BC2", 16),
    b"DXT3": ("BC2", 16),
    b"DXT4": ("BC3", 16),
    b"DXT5": ("BC3", 16),
    b"ATI1": ("BC4", 8),
    b"BC4U": ("BC4", 8),
    b"BC4S": ("BC4", 8),
    b"ATI2": ("BC5", 16),
    b"BC5U": ("BC5", 16),
    b"BC5S": ("BC5", 16),
}

# DXGI_FORMAT values -> (name, block bytes, bits per pixel). Exactly one of
# block bytes / bits per pixel is non-zero.
DXGI_FORMATS = {
    2: ("R32G32B32A32_FLOAT", 0, 128),
    10: ("R16G16B16A16_FLOAT", 0, 64),
    24: ("R10G10B10A2_UNORM", 0, 32),
    28: ("R8G8B8A8_UNORM", 0, 32),
    29: ("R8G8B8A8_UNORM_SRGB", 0, 32),
    34: ("R16G16_FLOAT", 0, 32),
    41: ("R32_FLOAT", 0, 32),
    49: ("R8G8_UNORM", 0, 16),
    54: ("R16_FLOAT", 0, 16),
    56: ("R16_UNORM", 0, 16),
    61: ("R8_UNORM", 0, 8),
    70: ("BC1", 8, 0), 71: ("BC1", 8, 0), 72: ("BC1", 8, 0),
    73: ("BC2", 16, 0), 74: ("BC2", 16, 0), 75: ("BC2", 16, 0),
    76: ("BC3", 16, 0), 77: ("BC3", 16, 0), 78: ("BC3", 16, 0),
    79: ("BC4", 8, 0), 80: ("BC4", 8, 0), 81: ("BC4", 8, 0),
    82: ("BC5", 16, 0), 83: ("BC5", 16, 0), 84: ("BC5", 16, 0),
    87: ("B8G8R8A8_UNORM", 0, 32),
    91: ("B8G8R8A8_UNORM_SRGB", 0, 32),
    94: ("BC6H", 16, 0), 95: ("BC6H", 16, 0), 96: ("BC6H", 16, 0),
    97: ("BC7", 16, 0), 98: ("BC7", 16, 0), 99: ("BC7", 16, 0),
}

# RTX Remix names ingested PBR textures <name>.<channel>.rtex.dds. Formats
# follow what the Remix ingestor writes for each channel.
ROLE_BY_SUFFIX = {
    "a": "albedo",
    "n": "normal",
    "r": "roughness",
    "m": "metallic",
    "e": "emissive",
    "h": "height",
    "t": "transmittance",
}
ALLOWED_FORMATS = {
    "albedo": {"BC7", "BC1", "BC3"},
    "normal": {"BC5"},
    "roughness": {"BC4"},
    "metallic": {"BC4"},
    "emissive": {"BC7", "BC1"},
    "height": {"BC4"},
    "transmittance": {"BC7", "BC1"},
}
MASK_ROLES = {"roughness", "metallic", "height"}
RTEX_RE = re.compile(r"\.([a-z])\.rtex\.dds$", re.IGNORECASE)
SOURCE_IMAGE_EXTS = {".png", ".tga", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".exr", ".psd"}


class DDSError(ValueError):
    pass


@dataclass
class TextureReport:
    path: str
    width: int
    height: int
    mips: int
    layers: int
    fmt: str
    role: str | None
    vram_bytes: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def is_pow2(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def full_mip_count(width: int, height: int) -> int:
    return max(width, height).bit_length()


def surface_bytes(width: int, height: int, block_bytes: int, bpp: int) -> int:
    if block_bytes:
        return max(1, (width + 3) // 4) * max(1, (height + 3) // 4) * block_bytes
    return (width * height * bpp + 7) // 8


def parse_dds_header(data: bytes) -> dict:
    """Return width, height, mips, layers, fmt, block_bytes, bpp from a DDS header."""
    if len(data) < 128 or data[:4] != DDS_MAGIC:
        raise DDSError("not a DDS file")
    size, _flags, height, width, _pitch, _depth, mips = struct.unpack_from("<7I", data, 4)
    if size != 124:
        raise DDSError(f"bad header size {size}")
    pf_flags, fourcc, rgb_bits = struct.unpack_from("<I4sI", data, 80)
    caps2 = struct.unpack_from("<I", data, 112)[0]
    layers = 6 if caps2 & DDSCAPS2_CUBEMAP else 1
    mips = max(1, mips)

    if pf_flags & DDPF_FOURCC and fourcc == b"DX10":
        if len(data) < 148:
            raise DDSError("truncated DX10 header")
        dxgi, _dim, misc, array_size = struct.unpack_from("<4I", data, 128)
        if dxgi not in DXGI_FORMATS:
            raise DDSError(f"unsupported DXGI format {dxgi}")
        fmt, block_bytes, bpp = DXGI_FORMATS[dxgi]
        layers = max(1, array_size) * (6 if misc & DX10_MISC_TEXTURECUBE else 1)
    elif pf_flags & DDPF_FOURCC:
        if fourcc not in FOURCC_FORMATS:
            raise DDSError(f"unsupported FourCC {fourcc!r}")
        fmt, block_bytes = FOURCC_FORMATS[fourcc]
        bpp = 0
    elif rgb_bits:
        fmt, block_bytes, bpp = f"RGB{rgb_bits}", 0, rgb_bits
    else:
        raise DDSError("unknown pixel format")

    return {
        "width": width,
        "height": height,
        "mips": mips,
        "layers": layers,
        "fmt": fmt,
        "block_bytes": block_bytes,
        "bpp": bpp,
    }


def texture_vram_bytes(hdr: dict) -> int:
    total = 0
    w, h = hdr["width"], hdr["height"]
    for _ in range(hdr["mips"]):
        total += surface_bytes(w, h, hdr["block_bytes"], hdr["bpp"])
        w, h = max(1, w // 2), max(1, h // 2)
    return total * hdr["layers"]


def role_for(path: Path) -> str | None:
    m = RTEX_RE.search(path.name)
    return ROLE_BY_SUFFIX.get(m.group(1).lower()) if m else None


def check_texture(path: Path, root: Path, max_res: int, max_res_mask: int) -> TextureReport:
    with path.open("rb") as f:
        hdr = parse_dds_header(f.read(148))
    role = role_for(path)
    rep = TextureReport(
        path=path.relative_to(root).as_posix(),
        width=hdr["width"],
        height=hdr["height"],
        mips=hdr["mips"],
        layers=hdr["layers"],
        fmt=hdr["fmt"],
        role=role,
        vram_bytes=texture_vram_bytes(hdr),
    )
    w, h = hdr["width"], hdr["height"]
    if not hdr["block_bytes"]:
        rep.errors.append(f"uncompressed {hdr['fmt']}: use a BCn format")
    if not (is_pow2(w) and is_pow2(h)):
        rep.errors.append(f"non power-of-two size {w}x{h}")
    if max(w, h) > 4 and hdr["mips"] < full_mip_count(w, h):
        rep.errors.append(f"mip chain {hdr['mips']}/{full_mip_count(w, h)}")
    cap = max_res_mask if role in MASK_ROLES else max_res
    if max(w, h) > cap:
        rep.errors.append(f"{w}x{h} exceeds {cap} cap for {role or 'texture'}")
    if role and hdr["block_bytes"] and hdr["fmt"] not in ALLOWED_FORMATS[role]:
        allowed = "/".join(sorted(ALLOWED_FORMATS[role]))
        rep.warnings.append(f"{role} stored as {hdr['fmt']}, expected {allowed}")
    return rep


def scan(root: Path, max_res: int, max_res_mask: int) -> tuple[list[TextureReport], list[str]]:
    reports: list[TextureReport] = []
    problems: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        ext = path.suffix.lower()
        rel = path.relative_to(root).as_posix()
        if ext == ".dds":
            try:
                reports.append(check_texture(path, root, max_res, max_res_mask))
            except DDSError as exc:
                problems.append(f"{rel}: {exc}")
        elif ext in SOURCE_IMAGE_EXTS:
            problems.append(f"{rel}: source image in shipped folder, ingest it to DDS")
    return reports, problems


def mib(n: int) -> float:
    return n / (1024 * 1024)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root", type=Path, help="mod folder to scan")
    ap.add_argument("--budget-mb", type=float, default=6144, help="total texture VRAM budget (MiB)")
    ap.add_argument("--max-res", type=int, default=4096, help="resolution cap for colour/normal maps")
    ap.add_argument("--max-res-mask", type=int, default=2048, help="cap for roughness/metallic/height")
    ap.add_argument("--top", type=int, default=15, help="list the N largest textures")
    ap.add_argument("--json", type=Path, help="write the full report as JSON")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        ap.error(f"{args.root} is not a directory")

    reports, problems = scan(args.root, args.max_res, args.max_res_mask)
    total = sum(r.vram_bytes for r in reports)
    n_err = len(problems) + sum(len(r.errors) for r in reports)
    n_warn = sum(len(r.warnings) for r in reports)
    over_budget = mib(total) > args.budget_mb

    for msg in problems:
        print(f"ERROR   {msg}")
    for r in reports:
        for msg in r.errors:
            print(f"ERROR   {r.path}: {msg}")
        for msg in r.warnings:
            print(f"WARN    {r.path}: {msg}")

    if reports:
        print(f"\nLargest {min(args.top, len(reports))} textures:")
        for r in sorted(reports, key=lambda r: r.vram_bytes, reverse=True)[: args.top]:
            print(f"  {mib(r.vram_bytes):9.2f} MiB  {r.width:>5}x{r.height:<5} {r.fmt:<8} {r.path}")

    print(
        f"\n{len(reports)} textures, {mib(total):.1f} MiB of {args.budget_mb:g} MiB budget, "
        f"{n_err} errors, {n_warn} warnings"
    )
    if over_budget:
        print("ERROR   texture set is over budget")

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "total_bytes": total,
                    "budget_mb": args.budget_mb,
                    "problems": problems,
                    "textures": [asdict(r) for r in reports],
                },
                indent=2,
            )
        )

    return 1 if n_err or over_budget else 0


if __name__ == "__main__":
    sys.exit(main())
