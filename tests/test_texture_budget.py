import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import texture_budget as tb  # noqa: E402


def make_dds(path: Path, width: int, height: int, mips: int, fourcc: bytes = b"DXT1",
             dxgi: int | None = None, rgb_bits: int = 0, cube: bool = False) -> None:
    header = bytearray(128)
    header[:4] = b"DDS "
    struct.pack_into("<7I", header, 4, 124, 0x1007, height, width, 0, 0, mips)
    if rgb_bits:
        struct.pack_into("<I4sI", header, 80, 0x40, b"\0\0\0\0", rgb_bits)
    else:
        struct.pack_into("<I4sI", header, 80, 0x4, b"DX10" if dxgi is not None else fourcc, 0)
    struct.pack_into("<I", header, 112, 0x200 if cube else 0)
    if dxgi is not None:
        header += struct.pack("<5I", dxgi, 3, 0, 1, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(header))


class TextureBudgetTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, name, **kw):
        path = self.root / name
        make_dds(path, **kw)
        return tb.check_texture(path, self.root, max_res=4096, max_res_mask=2048)

    def test_bc7_full_chain_is_clean(self):
        r = self.check("car.a.rtex.dds", width=2048, height=2048, mips=12, dxgi=98)
        self.assertEqual((r.fmt, r.role, r.errors, r.warnings), ("BC7", "albedo", [], []))
        # 2048^2 BC7 = 4 MiB top level; a full chain adds ~1/3.
        self.assertEqual(r.vram_bytes, sum(max(1, (2048 >> i) // 4) ** 2 * 16 for i in range(12)))

    def test_bc1_size(self):
        r = self.check("x.dds", width=256, height=256, mips=1)
        self.assertEqual(r.vram_bytes, 64 * 64 * 8)

    def test_uncompressed_and_missing_mips(self):
        r = self.check("road.dds", width=1024, height=1024, mips=1, rgb_bits=32)
        self.assertEqual(r.vram_bytes, 1024 * 1024 * 4)
        self.assertTrue(any("uncompressed" in e for e in r.errors))
        self.assertTrue(any("mip chain 1/11" in e for e in r.errors))

    def test_non_pow2_and_mask_cap(self):
        r = self.check("hood.r.rtex.dds", width=3000, height=3000, mips=12, fourcc=b"ATI1")
        self.assertEqual(r.role, "roughness")
        self.assertTrue(any("power-of-two" in e for e in r.errors))
        self.assertTrue(any("2048 cap" in e for e in r.errors))

    def test_wrong_format_for_role_warns(self):
        r = self.check("rim.n.rtex.dds", width=512, height=512, mips=10, fourcc=b"DXT5")
        self.assertEqual(r.errors, [])
        self.assertEqual(r.warnings, ["normal stored as BC3, Remix ingests it as BC5"])

    def test_two_letter_suffix_roles(self):
        r = self.check("glass.tr.rtex.dds", width=256, height=256, mips=9, dxgi=98)
        self.assertEqual((r.role, r.warnings), ("transmittance", []))
        r = self.check("paint.an.rtex.dds", width=4096, height=4096, mips=13, fourcc=b"BC4U")
        self.assertEqual(r.role, "anisotropy")
        self.assertTrue(any("2048 cap" in e for e in r.errors))

    def test_hdr_sky_uses_sky_cap(self):
        r = self.check("night.s.rtex.dds", width=8192, height=4096, mips=14, dxgi=95)
        self.assertEqual((r.role, r.fmt, r.errors, r.warnings), ("skybox", "BC6H", [], []))

    def test_cubemap_counts_six_faces(self):
        r = self.check("sky.dds", width=64, height=64, mips=1, cube=True)
        self.assertEqual(r.vram_bytes, 16 * 16 * 8 * 6)

    def test_scan_flags_sources_and_bad_files(self):
        make_dds(self.root / "ok" / "a.dds", width=64, height=64, mips=7)
        (self.root / "src.png").write_bytes(b"\x89PNG")
        (self.root / "broken.dds").write_bytes(b"nope")
        reports, problems = tb.scan(self.root, 4096, 2048)
        self.assertEqual([r.path for r in reports], ["ok/a.dds"])
        self.assertEqual(len(problems), 2)

    def test_main_exit_codes(self):
        make_dds(self.root / "a.dds", width=1024, height=1024, mips=11, dxgi=98)
        self.assertEqual(tb.main([str(self.root), "--budget-mb", "64"]), 0)
        self.assertEqual(tb.main([str(self.root), "--budget-mb", "0.5"]), 1)


if __name__ == "__main__":
    unittest.main()
