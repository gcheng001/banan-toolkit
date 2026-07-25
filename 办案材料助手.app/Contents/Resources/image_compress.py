"""image_compress.py — 包装 baoyu-compress-image (Bun CLI) 的迭代压缩引擎。

返回纯 dict，GUI 直接消费。所有路径走绝对路径并 expanduser+resolve。
无需 macOS 之外的额外依赖；可选 EXIF 剥离用 sips（系统自带）。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

BAOYU_DIR = Path(
    os.environ.get(
        "BAOYU_COMPRESS_DIR",
        "/Users/Apple/.shared-skills/baoyu-compress-image",
    )
)
BAOYU_MAIN = BAOYU_DIR / "scripts" / "main.ts"

QUALITY_LADDER = [80, 70, 60, 50, 40]
FORMAT_OPTIONS = ("webp", "jpeg", "png")

PRESET_SOCIAL = "social"
PRESET_ID = "id"
PRESET_CUSTOM = "custom"

DEFAULT_SOCIAL_QUALITY = 90
DEFAULT_ID_QUALITY = 80
DEFAULT_ID_TARGET_KB = 200
DEFAULT_OUTPUT_DIR = Path.home() / "Desktop" / "图片压缩输出"


def _resolve_bun() -> str:
    found = shutil.which("bun")
    if found:
        return found
    fallback = Path("/Users/Apple/.bun/bin/bun")
    if fallback.is_file() and os.access(fallback, os.X_OK):
        return str(fallback)
    raise FileNotFoundError(
        "找不到 bun 可执行文件。请先安装 bun（brew install bun）后重试。"
    )


def _resolve_path(p: str) -> Path:
    return Path(p).expanduser().resolve()


def _new_output_path(src: Path, out_dir: Path, fmt: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{src.stem}.{fmt}"


def _file_size(p: Path) -> int:
    return p.stat().st_size if p.exists() else 0


def _run_baoyu(src: Path, dst: Path, fmt: str, quality: int) -> dict:
    """Invoke Bun-bundled baoyu-compress-image, parse textual fallback or JSON."""
    if not BAOYU_MAIN.is_file():
        return {
            "ok": False,
            "error": f"找不到 baoyu 脚本: {BAOYU_MAIN}",
        }
    bun = _resolve_bun()
    cmd = [
        bun,
        str(BAOYU_MAIN),
        str(src),
        "-o", str(dst),
        "-f", fmt,
        "-q", str(quality),
        "--keep",
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "压缩超时（>120s）"}
    except FileNotFoundError as e:
        return {"ok": False, "error": f"无法执行 bun: {e}"}
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": (proc.stderr or proc.stdout or "baoyu 退出非零").strip()[:500],
        }
    return {"ok": True, "stdout": proc.stdout.strip()}


def _strip_metadata(output_path: Path) -> None:
    """Best-effort metadata strip using `sips` (always present on macOS).

    sips cannot strip all EXIF tags for PNG cleanly; for WebP/JPEG it works
    reasonably well. We use a transactional profile rotation as a safety net.
    """
    if not output_path.exists():
        return
    try:
        subprocess.run(
            ["/usr/bin/sips", "-s", "profile", "none", str(output_path)],
            capture_output=True,
            timeout=15,
            check=False,
        )
    except Exception:
        pass


def compress_for_social(
    input_path: str,
    output_dir: str,
    *,
    fmt: str = "webp",
    quality: int = DEFAULT_SOCIAL_QUALITY,
    strip_metadata: bool = True,
) -> dict:
    """一次性高画质预设，体积不限。失败时不抛异常，error 字段说明原因。"""
    try:
        src = _resolve_path(input_path)
        out = _new_output_path(src, _resolve_path(output_dir), fmt)
    except Exception as e:
        return {"ok": False, "error": f"路径解析失败: {e}"}
    if not src.is_file():
        return {"ok": False, "error": f"输入文件不存在: {src}"}
    res = _run_baoyu(src, out, fmt, quality)
    if not res["ok"]:
        return {
            "ok": False,
            "input": str(src),
            "output": str(out),
            "error": res.get("error", "压缩失败"),
            "quality": quality,
        }
    if strip_metadata:
        _strip_metadata(out)
    return {
        "ok": True,
        "preset": PRESET_SOCIAL,
        "input": str(src),
        "output": str(out),
        "before_bytes": _file_size(src),
        "after_bytes": _file_size(out),
        "iterations": 1,
        "quality": quality,
        "fmt": fmt,
        "warning": None,
    }


def compress_to_target(
    input_path: str,
    output_dir: str,
    target_bytes: int,
    *,
    fmt: str = "webp",
    start_quality: int = DEFAULT_ID_QUALITY,
    strip_metadata: bool = True,
) -> dict:
    """迭代逼近：从 start_quality 起按 QUALITY_LADDER 依次尝试，找到 ≤target_bytes 的最早一档。"""
    try:
        src = _resolve_path(input_path)
        out = _new_output_path(src, _resolve_path(output_dir), fmt)
    except Exception as e:
        return {"ok": False, "error": f"路径解析失败: {e}"}
    if not src.is_file():
        return {"ok": False, "error": f"输入文件不存在: {src}"}
    ladder = [q for q in QUALITY_LADDER if q <= start_quality]
    if not ladder:
        ladder = [start_quality]
    chosen_q = None
    chosen_size = None
    iters = 0
    last_error = None
    for q in ladder:
        iters += 1
        res = _run_baoyu(src, out, fmt, q)
        if not res["ok"]:
            last_error = res.get("error", "")
            continue
        sz = _file_size(out)
        if sz <= target_bytes:
            chosen_q, chosen_size = q, sz
            break
        chosen_q, chosen_size = q, sz
    if chosen_q is None:
        return {
            "ok": False,
            "input": str(src),
            "output": str(out),
            "iterations": iters,
            "error": last_error or "全部档位均失败",
        }
    if strip_metadata:
        _strip_metadata(out)
    final_size = _file_size(out)
    target_met = final_size <= target_bytes
    return {
        "ok": True,
        "preset": PRESET_ID,
        "input": str(src),
        "output": str(out),
        "before_bytes": _file_size(src),
        "after_bytes": final_size,
        "iterations": iters,
        "quality": chosen_q,
        "fmt": fmt,
        "target_bytes": target_bytes,
        "target_met": target_met,
        "warning": None if target_met else (
            f"未达目标 {target_bytes // 1024} KB；已用最低档 q{chosen_q}（实际 {final_size // 1024} KB）"
        ),
    }


def compress_custom(
    input_path: str,
    output_dir: str,
    *,
    fmt: str = "webp",
    quality: int = 80,
    strip_metadata: bool = True,
) -> dict:
    return compress_for_social(
        input_path,
        output_dir,
        fmt=fmt,
        quality=quality,
        strip_metadata=strip_metadata,
    )


def run_for_files(
    files: list,
    output_dir: str,
    preset: str = PRESET_SOCIAL,
    *,
    target_kb: Optional[int] = None,
    fmt: str = "webp",
    quality: int = 80,
    strip_metadata: bool = True,
    progress_cb: Optional[Callable[[int, int, dict], None]] = None,
) -> dict:
    """批量压缩入口，progress_cb(idx, total, partial_result) 会被回调。"""
    results = []
    total = len(files)
    for idx, path in enumerate(files, start=1):
        if preset == PRESET_SOCIAL:
            r = compress_for_social(
                path,
                output_dir,
                fmt=fmt,
                quality=quality,
                strip_metadata=strip_metadata,
            )
        elif preset == PRESET_ID:
            r = compress_to_target(
                path,
                output_dir,
                max(20, int(target_kb or DEFAULT_ID_TARGET_KB)) * 1024,
                fmt=fmt,
                start_quality=quality,
                strip_metadata=strip_metadata,
            )
        else:
            r = compress_custom(
                path,
                output_dir,
                fmt=fmt,
                quality=quality,
                strip_metadata=strip_metadata,
            )
        r["idx"] = idx
        r["name"] = Path(path).name
        results.append(r)
        if progress_cb:
            try:
                progress_cb(idx, total, r)
            except Exception:
                pass
    return {
        "ok": all(r.get("ok") for r in results),
        "total": total,
        "results": results,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="图片压缩 CLI（封装 baoyu-compress-image）")
    ap.add_argument("input")
    ap.add_argument("output_dir")
    ap.add_argument("--preset", default=PRESET_SOCIAL, choices=[PRESET_SOCIAL, PRESET_ID, PRESET_CUSTOM])
    ap.add_argument("--target-kb", type=int, default=DEFAULT_ID_TARGET_KB)
    ap.add_argument("--format", default="webp", choices=FORMAT_OPTIONS)
    ap.add_argument("--quality", type=int, default=DEFAULT_SOCIAL_QUALITY)
    ap.add_argument("--no-strip", action="store_true")
    args = ap.parse_args()
    if args.preset == PRESET_SOCIAL:
        out = compress_for_social(args.input, args.output_dir, fmt=args.format, quality=args.quality, strip_metadata=not args.no_strip)
    elif args.preset == PRESET_ID:
        out = compress_to_target(args.input, args.output_dir, args.target_kb * 1024, fmt=args.format, start_quality=args.quality, strip_metadata=not args.no_strip)
    else:
        out = compress_custom(args.input, args.output_dir, fmt=args.format, quality=args.quality, strip_metadata=not args.no_strip)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if out.get("ok") else 1)
