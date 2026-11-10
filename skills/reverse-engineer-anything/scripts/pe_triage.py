#!/usr/bin/env python3
"""pe_triage.py - offline Windows PE (.exe/.dll) triage for the REA skill.

Read-only, standard library only, never executes or writes to the target.
It answers one question before any deeper analysis: "what kind of PE is this,
and which REA route fits it?" Observations and inferences are kept separate.

Usage:
  python pe_triage.py <path>                # human-readable summary
  python pe_triage.py <path> --json         # complete JSON on stdout
  python pe_triage.py <path> --out out.json # write UTF-8 JSON to a new file

Exit codes: 0 = parsed (including partial), 2 = bad input / not a PE, 3 = I/O.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import math
import os
import struct
import sys
from collections import Counter

SCHEMA = "rea-pe-triage/1"
MAX_BYTES_DEFAULT = 256 * 1024 * 1024
DIR_NAMES = (
    "export", "import", "resource", "exception", "security", "base_relocation",
    "debug", "architecture", "global_pointer", "tls", "load_config",
    "bound_import", "import_address_table", "delay_import", "clr_header",
    "reserved",
)
MACHINES = {
    0x014C: "i386", 0x8664: "amd64", 0x01C0: "arm", 0x01C4: "armnt",
    0xAA64: "arm64", 0x0200: "ia64", 0x5032: "riscv32", 0x5064: "riscv64",
}
SUBSYSTEMS = {
    0: "unknown", 1: "native", 2: "windows_gui", 3: "windows_console",
    5: "os2_console", 7: "posix_console", 9: "windows_ce_gui",
    10: "efi_application", 14: "efi_runtime_driver", 16: "windows_boot_application",
}
DLL_CHARS = (
    (0x0020, "high_entropy_va"), (0x0040, "dynamic_base"), (0x0080, "force_integrity"),
    (0x0100, "nx_compat"), (0x0200, "no_isolation"), (0x0400, "no_seh"),
    (0x0800, "no_bind"), (0x1000, "appcontainer"), (0x2000, "wdm_driver"),
    (0x4000, "guard_cf"), (0x8000, "terminal_server_aware"),
)
IMAGE_CHARS = (
    (0x0002, "executable_image"), (0x0020, "large_address_aware"),
    (0x0100, "32bit_machine"), (0x2000, "dll"), (0x0001, "relocs_stripped"),
    (0x0200, "debug_stripped"), (0x0008, "local_syms_stripped"),
    (0x0010, "aggresive_ws_trim"), (0x0080, "little_endian"),
    (0x1000, "system"), (0x4000, "network_run_from_swap"),
)
# (kind, marker, confidence, route). Markers are byte signatures, not verdicts.
MARKERS = (
    ("pyinstaller", b"MEI\014\013\012\013\016", "high", "pyinstaller"),
    ("pyinstaller", b"PYZ-00.pyz", "high", "pyinstaller"),
    ("pyinstaller", b"pyi-runtime-tmpdir", "medium", "pyinstaller"),
    ("nuitka", b"__nuitka_", "medium", "pyinstaller"),
    ("dotnet", b"#Blob", "low", "dotnet"),
    ("dotnet", b"BSJB", "low", "dotnet"),
    ("go", b"Go build ID:", "high", "go"),
    ("go", b"runtime.main", "medium", "go"),
    ("rust", b".dep-v0", "high", "rust"),
    ("rust", b"cargo-auditable", "high", "rust"),
    ("deno", b"d3n0l4nd", "high", "deno"),
    ("bun", b"Bun v1.", "medium", "bun"),
    ("electron", b"electron.asar", "high", "electron"),
    ("electron", b"chrome_elf.dll", "medium", "electron"),
    ("nsis_installer", b"NullsoftInst", "high", "installer"),
    ("inno_setup", b"Inno Setup", "high", "installer"),
    ("autoit", b"AU3!EA", "high", "autoit"),
    ("autoit", b"AutoIt v3", "medium", "autoit"),
    ("vb6", b"MSVBVM60.DLL", "high", "vb6"),
    ("delphi", b"BORLNDMM.DLL", "medium", "delphi"),
)
PACKER_SECTIONS = {
    b"UPX0": "upx", b"UPX1": "upx", b".vmp0": "vmp", b".vmp1": "vmp",
    b".themida": "themida", b".aspack": "aspack", b".nsp0": "nspack",
    b".petite": "petite", b"MPRESS1": "mpress", b".enigma1": "enigma",
}


class PEError(Exception):
    """A bounded parse failure; the caller reports it instead of inventing facts."""


def _u16(b: bytes, o: int) -> int:
    if o + 2 > len(b):
        raise PEError("truncated u16 at offset %d" % o)
    return struct.unpack_from("<H", b, o)[0]


def _u32(b: bytes, o: int) -> int:
    if o + 4 > len(b):
        raise PEError("truncated u32 at offset %d" % o)
    return struct.unpack_from("<I", b, o)[0]


def _u64(b: bytes, o: int) -> int:
    if o + 8 > len(b):
        raise PEError("truncated u64 at offset %d" % o)
    return struct.unpack_from("<Q", b, o)[0]


def _flags(value: int, table) -> list[str]:
    return [name for bit, name in table if value & bit]


def _cstring(b: bytes, o: int, limit: int = 512) -> str | None:
    if o < 0 or o >= len(b):
        return None
    end = b.find(b"\x00", o, min(len(b), o + limit))
    if end < 0:
        end = min(len(b), o + limit)
    try:
        return b[o:end].decode("ascii", "replace")
    except Exception:
        return None


def _entropy(chunk: bytes) -> float | None:
    if not chunk:
        return None
    n = len(chunk)
    counts = Counter(chunk)
    value = -sum((c / n) * math.log2(c / n) for c in counts.values() if c)
    return abs(round(value, 3))


def parse(data: bytes, path: str) -> dict:
    issues: list[str] = []
    if data[:2] != b"MZ":
        raise PEError("missing MZ DOS signature (not a PE image)")
    pe_off = _u32(data, 0x3C)
    if pe_off + 24 > len(data) or data[pe_off:pe_off + 4] != b"PE\x00\x00":
        raise PEError("missing PE\\0\\0 signature at e_lfanew=0x%x" % pe_off)

    coff = pe_off + 4
    machine = _u16(data, coff)
    n_sections = _u16(data, coff + 2)
    timestamp = _u32(data, coff + 4)
    opt_size = _u16(data, coff + 16)
    img_chars = _u16(data, coff + 18)
    opt = coff + 20
    magic = _u16(data, opt)
    if magic == 0x10B:
        pe_format, bits, dir_base, dir_count_off = "pe32", 32, opt + 96, opt + 92
        image_base = _u32(data, opt + 28)
    elif magic == 0x20B:
        pe_format, bits, dir_base, dir_count_off = "pe32-plus", 64, opt + 112, opt + 108
        image_base = _u64(data, opt + 24)
    else:
        raise PEError("unsupported optional header magic 0x%x" % magic)

    entry_rva = _u32(data, opt + 16)
    section_alignment = _u32(data, opt + 32)
    size_of_image = _u32(data, opt + 56)
    subsystem = _u16(data, opt + 68)
    dll_chars = _u16(data, opt + 70)
    declared_dirs = _u32(data, dir_count_off)

    directories: dict[str, dict] = {}
    for i in range(min(declared_dirs, 16)):
        o = dir_base + 8 * i
        rva, size = _u32(data, o), _u32(data, o + 4)
        if rva or size:
            directories[DIR_NAMES[i]] = {"rva": rva, "size": size}

    sec_off = opt + opt_size
    sections = []
    for i in range(n_sections):
        o = sec_off + 40 * i
        if o + 40 > len(data):
            issues.append("section header %d is truncated" % i)
            break
        raw_size = _u32(data, o + 16)
        raw_ptr = _u32(data, o + 20)
        name = data[o:o + 8].rstrip(b"\x00").decode("ascii", "replace")
        item = {
            "name": name,
            "virtual_address": _u32(data, o + 12),
            "virtual_size": _u32(data, o + 8),
            "raw_size": raw_size,
            "raw_offset": raw_ptr,
            "characteristics": _u32(data, o + 36),
        }
        if raw_ptr and raw_size and raw_ptr + raw_size <= len(data) and raw_size <= 32 * 1024 * 1024:
            item["entropy"] = _entropy(data[raw_ptr:raw_ptr + raw_size])
        sections.append(item)

    def rva_to_offset(rva: int) -> int | None:
        for s in sections:
            span = max(s["virtual_size"], s["raw_size"])
            if s["virtual_address"] <= rva < s["virtual_address"] + span:
                delta = rva - s["virtual_address"]
                if delta < s["raw_size"]:
                    off = s["raw_offset"] + delta
                    return off if off < len(data) else None
                return None
        return None

    # Import descriptors (bounded, sampled). Names are observed declarations only.
    imports: dict = {"dlls": [], "function_count": 0, "sample_functions": [], "truncated": False}
    imp = directories.get("import")
    if imp:
        off = rva_to_offset(imp["rva"])
        if off is not None:
            try:
                for idx in range(256):
                    d = off + 20 * idx
                    if d + 20 > len(data):
                        break
                    name_rva = _u32(data, d + 12)
                    first_thunk = _u32(data, d + 16)
                    if not (name_rva or first_thunk):
                        break
                    dll = _cstring(data, rva_to_offset(name_rva) or -1) if rva_to_offset(name_rva) else None
                    if dll:
                        imports["dlls"].append(dll)
                    thunk_rva = _u32(data, d) or first_thunk
                    t_off = rva_to_offset(thunk_rva)
                    if t_off is None:
                        continue
                    width = 8 if bits == 64 else 4
                    for t in range(4096):
                        p = t_off + width * t
                        if p + width > len(data):
                            break
                        value = _u64(data, p) if bits == 64 else _u32(data, p)
                        if value == 0:
                            break
                        imports["function_count"] += 1
                        ordinal = bool(value & (1 << (bits - 1)))
                        if not ordinal:
                            n_off = rva_to_offset(value & 0x7FFFFFFF)
                            fn = _cstring(data, n_off + 2) if n_off else None
                            if fn and len(imports["sample_functions"]) < 40:
                                imports["sample_functions"].append("%s!%s" % (dll or "?", fn))
                        if imports["function_count"] >= 4096:
                            imports["truncated"] = True
                            break
                    if imports["truncated"]:
                        break
            except PEError as exc:
                issues.append("import walk stopped: %s" % exc)
        else:
            issues.append("import directory RVA has no mapped file offset")

    security = directories.get("security")
    authenticode = {
        "declared": bool(security),
        "file_offset": security["rva"] if security else None,
        "size": security["size"] if security else None,
        "verified": False,
        "note": "presence of a WIN_CERTIFICATE table is not a verified or trusted signature",
    }

    observed = {
        "is_pe": True,
        "pe_format": pe_format,
        "bits": bits,
        "machine": "0x%x" % machine,
        "architecture": MACHINES.get(machine, "unknown"),
        "image_characteristics": _flags(img_chars, IMAGE_CHARS),
        "dll_characteristics": _flags(dll_chars, DLL_CHARS),
        "subsystem": SUBSYSTEMS.get(subsystem, "unknown"),
        "entry_point_rva": entry_rva,
        "image_base": image_base,
        "section_alignment": section_alignment,
        "size_of_image": size_of_image,
        "timestamp_unix": timestamp,
        "timestamp_utc": _dt.datetime.fromtimestamp(timestamp, _dt.timezone.utc).isoformat()
        if 0 < timestamp < 0xFFFFFFFF else None,
        "sections": sections,
        "directories": directories,
        "imports": imports,
        "authenticode": authenticode,
    }

    # Inferences: byte markers and section names are candidates, never verdicts.
    hits: dict[str, dict] = {}
    for kind, marker, confidence, route in MARKERS:
        if marker in data and kind not in hits:
            hits[kind] = {"confidence": confidence, "route": route,
                          "evidence": marker.decode("ascii", "backslashreplace")}
    for s in sections:
        raw = s["name"].encode("ascii", "ignore")
        for prefix, packer in PACKER_SECTIONS.items():
            if raw.startswith(prefix):
                hits.setdefault("packed_" + packer, {
                    "confidence": "medium", "route": "packed",
                    "evidence": "section name %s" % s["name"],
                })
        if s.get("entropy") is not None and s["entropy"] >= 7.2 and s["raw_size"] > 4096:
            hits.setdefault("high_entropy_section", {
                "confidence": "low", "route": "packed",
                "evidence": "%s entropy %.3f" % (s["name"], s["entropy"]),
            })
    if "clr_header" in directories:
        hits["dotnet"] = {"confidence": "high", "route": "dotnet",
                          "evidence": "CLR runtime header directory present"}
    if "mscoree.dll" in [d.lower() for d in imports["dlls"]]:
        hits.setdefault("dotnet", {"confidence": "high", "route": "dotnet",
                                   "evidence": "mscoree.dll import"})
    if re_check_vb(imports["dlls"]):
        hits.setdefault("vb6", {"confidence": "medium", "route": "vb6",
                                "evidence": "Visual Basic runtime import"})

    route = choose_route(hits, "dll" if img_chars & 0x2000 else "exe")
    inferred = {
        "candidates": hits,
        "primary_route": route,
        "is_dll": bool(img_chars & 0x2000),
        "note": "candidates are byte/layout inferences; confirm with REA tools before concluding anything about behavior",
    }
    return {
        "schema": SCHEMA,
        "path": os.path.abspath(path),
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
        "observed": observed,
        "inferred": inferred,
        "next_steps": next_steps(route),
        "parse_issues": issues,
        "limitations": [
            "static read only; the target was never executed or loaded",
            "no signature verification, no malware verdict, no control-flow analysis",
            "strings/section names can be spoofed; marker hits are candidates",
            "import sampling is bounded (256 descriptors, 4096 thunks); truncated=True means more exist",
        ],
    }


def re_check_vb(dlls: list[str]) -> bool:
    lowered = [d.lower() for d in dlls]
    return any(d.startswith("msvbvm") for d in lowered)


def choose_route(hits: dict, kind: str) -> str:
    for key in ("pyinstaller", "dotnet", "go", "rust", "deno", "bun", "electron",
                "nsis_installer", "inno_setup", "autoit", "vb6", "delphi"):
        if key in hits:
            return hits[key]["route"]
    if any(k.startswith("packed_") for k in hits) or "high_entropy_section" in hits:
        return "packed"
    return "native"


def next_steps(route: str) -> list[dict]:
    common = [
        {"step": "identity", "command": "rea inspect-pe-imports <path> --format json",
         "purpose": "declared DLL/function imports and delay imports"},
        {"step": "layout", "command": "rea inspect-pe-load-config <path> --format json",
         "purpose": "TLS callbacks, load config, security cookie and guard flags"},
        {"step": "signature table", "command": "rea inspect-pe-certificates <path> --format json",
         "purpose": "WIN_CERTIFICATE identity; not a trust verdict"},
        {"step": "resources", "command": "rea inspect-pe-resources <path> --format json",
         "purpose": "version info, icons, manifests, embedded payload ranges"},
        {"step": "exports", "command": "rea inspect-native-exports <path> --format json",
         "purpose": "export directory (most useful for DLLs)"},
    ]
    by_route = {
        "dotnet": [{"step": "managed", "command": "rea inspect-managed-artifact <path> --format json",
                    "purpose": "PE/CLI identity"},
                   {"step": "members", "command": "rea inspect-managed-members <path> --format json",
                    "purpose": "types, methods and ldstr literals"}],
        "go": [{"step": "go metadata", "command": "rea inspect-go-binary <path> --format json",
                "purpose": "embedded Go version, modules and build settings"}],
        "rust": [{"step": "rust metadata", "command": "rea inspect-rust-binary <path> --format json",
                  "purpose": "cargo-auditable dependency list when present"}],
        "pyinstaller": [{"step": "archive", "command": "rea inspect-artifact <path> --detail summary --evidence_output <new.json>",
                         "purpose": "PyInstaller CArchive inventory (the application layer)"}],
        "electron": [{"step": "electron", "command": "rea analyze-javascript-application <extracted-dir> --json",
                      "purpose": "analyze the extracted app.asar / JS tree"}],
        "installer": [{"step": "archive", "command": "rea inspect-artifact <path> --detail summary --evidence_output <new.json>",
                       "purpose": "installer payload inventory"}],
        "packed": [{"step": "entropy", "command": "rea inspect-byte-entropy <path> --format json",
                    "purpose": "packed/encrypted region indication"}],
        "native": [{"step": "deep analysis", "command": "rea analyze <path> --provider <id>",
                    "purpose": "requires a configured native provider (Ghidra/Hopper/IDA); check `rea providers`"}],
    }
    return common + by_route.get(route, [])


def render_text(r: dict) -> str:
    o, inf = r["observed"], r["inferred"]
    lines = [
        "PE triage (static, read-only) - schema %s" % r["schema"],
        "file      : %s" % r["path"],
        "sha256    : %s" % r["sha256"],
        "size      : %d bytes" % r["size"],
        "format    : %s / %s / %s / subsystem=%s%s" % (
            o["pe_format"], o["architecture"], o["bits"], o["subsystem"],
            " (DLL)" if inf["is_dll"] else ""),
        "entry     : RVA 0x%x, image base 0x%x" % (o["entry_point_rva"], o["image_base"]),
        "timestamp : %s" % (o["timestamp_utc"] or "unknown"),
        "sections  : %s" % ", ".join("%s(%d%s)" % (
            s["name"], s["raw_size"],
            ", H=%.2f" % s["entropy"] if s.get("entropy") is not None else "")
            for s in o["sections"]),
        "imports   : %d DLLs, %d functions%s" % (
            len(o["imports"]["dlls"]), o["imports"]["function_count"],
            " (sampled)" if o["imports"]["truncated"] else ""),
        "signature : %s" % ("declared, NOT verified" if o["authenticode"]["declared"] else "no Authenticode table"),
        "route     : %s (inferred)" % inf["primary_route"],
    ]
    if inf["candidates"]:
        lines.append("candidates :")
        for name, hit in inf["candidates"].items():
            lines.append("  - %-24s %-6s %s" % (name, hit["confidence"], hit["evidence"]))
    lines.append("next steps :")
    for step in r["next_steps"]:
        lines.append("  - %-14s %s" % (step["step"], step["command"]))
    if r["parse_issues"]:
        lines.append("parse issues: %s" % "; ".join(r["parse_issues"]))
    lines.append("limits     : " + "; ".join(r["limitations"]))
    return "\n".join(lines) + "\n"


def _emit(text: str) -> None:
    # The host may capture stdout with a legacy codepage; emit strict UTF-8 bytes.
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def main() -> int:
    ap = argparse.ArgumentParser(description="Offline Windows PE triage for the REA skill")
    ap.add_argument("path", help="local .exe/.dll (or any PE image) to inspect; never executed")
    ap.add_argument("--json", action="store_true", help="print complete JSON instead of a summary")
    ap.add_argument("--out", help="write complete UTF-8 JSON to this new path (refuses overwrite)")
    ap.add_argument("--max-bytes", type=int, default=MAX_BYTES_DEFAULT,
                    help="refuse files larger than this (default 256 MiB)")
    args = ap.parse_args()

    if not os.path.isfile(args.path):
        _emit("ERROR: not a regular file: %s\n" % args.path)
        return 2
    size = os.path.getsize(args.path)
    if size > args.max_bytes:
        _emit("ERROR: file is %d bytes, over --max-bytes=%d\n" % (size, args.max_bytes))
        return 2
    try:
        with open(args.path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        _emit("ERROR: cannot read: %s\n" % exc)
        return 3
    try:
        result = parse(data, args.path)
    except PEError as exc:
        _emit("ERROR: %s\n" % exc)
        return 2

    if args.out:
        if os.path.exists(args.out):
            _emit("ERROR: output already exists: %s\n" % args.out)
            return 2
        with open(args.out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    _emit(json.dumps(result, ensure_ascii=False, indent=2) + "\n" if args.json else render_text(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
