#!/usr/bin/env python3
"""
MinerU 进度桥接模块 — 通过子进程调用 MinerU venv，管道传回逐页进度。

用法:
    from vision_ocr_mineru import MinerUConverter
    converter = MinerUConverter()
    result = converter.convert(
        pdf_path="/path/to/file.pdf",
        output_dir="/path/to/output",
        progress_callback=lambda cur, total, msg: print(f"{cur}/{total} {msg}"),
    )
    # result.md_path -> 输出的 markdown 文件路径
    # result.success -> 是否成功
"""

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# ── 配置 ──────────────────────────────────────────────────────────────
MINERU_VENV = Path.home() / "MinerU-src" / ".venv"
MINERU_PYTHON = MINERU_VENV / "bin" / "python3"
MINERU_SRC = Path.home() / "MinerU-src"

# ── 进度回调类型 ──────────────────────────────────────────────────────
ProgressCallback = Callable[[int, int, str], None]  # (current, total, message)


# ── 转换结果 ──────────────────────────────────────────────────────────
@dataclass
class ConvertResult:
    success: bool
    md_path: Optional[str] = None
    error: Optional[str] = None
    total_pages: int = 0


# ── 子进程 worker 脚本 ────────────────────────────────────────────────
# 这段代码在 MinerU venv 的 Python 中执行
_WORKER_SCRIPT = r'''
import json
import os
import sys
import contextlib
from pathlib import Path

os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["MINERU_MODEL_SOURCE"] = "modelscope"

# tqdm 拦截器
class _ProgressTqdm:
    """拦截 tqdm，将页面级进度通过 stdout 发送给主进程。"""

    def __init__(self, iterable=None, total=None, desc="", *args, **kwargs):
        self._iterable = iterable
        if total is None and iterable is not None:
            try:
                self._total = len(iterable)
            except TypeError:
                self._total = 0
        else:
            self._total = total if isinstance(total, int) else 0
        self._current = 0
        self._desc = desc
        # 只对 "Processing pages" 发送进度（过滤子步骤 tqdm）
        self._is_page = "Processing pages" in str(desc)
        if self._total > 0 and self._is_page:
            self._emit(0, self._total, self._desc or "Processing")

    def __iter__(self):
        """tqdm(iterable) 模式：遍历元素并逐个更新进度。"""
        for item in self._iterable:
            yield item
            self.update(1)

    def update(self, n=1):
        self._current += n
        if self._is_page and self._total > 0:
            self._emit(self._current, self._total, self._desc or "Processing")

    def set_description(self, desc):
        self._desc = desc

    def close(self):
        if self._total > 0:
            self._emit(self._total, self._total, self._desc or "Done")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def n(self):
        return self._current

    @n.setter
    def n(self, value):
        self._current = value

    @property
    def total(self):
        return self._total

    def refresh(self):
        pass

    def set_postfix(self, *args, **kwargs):
        pass

    def __len__(self):
        return self._total

    @staticmethod
    def _emit(cur, total, msg):
        """通过 stdout 发送进度 JSON，用特殊前缀标记。"""
        print(f"__PROGRESS__:{json.dumps({'cur': cur, 'total': total, 'msg': msg})}", flush=True)


def main():
    args = json.loads(sys.argv[1])
    pdf_path = Path(args["pdf_path"])
    output_dir = Path(args["output_dir"])
    backend = args.get("backend", "pipeline")
    lang = args.get("lang", "ch")
    start_page = args.get("start_page", 0)
    end_page = args.get("end_page")

    output_dir.mkdir(parents=True, exist_ok=True)

    from mineru.cli.common import do_parse, read_fn
    import tqdm as tqdm_mod

    # 拦截 tqdm
    tqdm_mod.tqdm = _ProgressTqdm

    try:
        pdf_bytes = read_fn(pdf_path)
        stem = pdf_path.stem

        do_parse(
            output_dir=str(output_dir),
            pdf_file_names=[stem],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=[lang],
            backend=backend,
            parse_method="auto",
            formula_enable=True,
            table_enable=True,
            start_page=start_page,
            end_page=end_page,
            f_draw_layout_bbox=False,
            f_draw_span_bbox=False,
            f_dump_middle_json=False,
            f_dump_model_output=False,
            f_dump_orig_pdf=False,
            f_dump_content_list=False,
        )

        # 查找输出的 .md 文件
        md_path = None
        candidates = list(output_dir.glob(f"{stem}/**/*.md"))
        if candidates:
            md_path = str(candidates[0])
        else:
            candidates = list(output_dir.glob("**/*.md"))
            if candidates:
                md_path = str(candidates[0])

        if md_path:
            print(f"__RESULT__:{json.dumps({'success': True, 'md_path': md_path})}", flush=True)
        else:
            print(f"__RESULT__:{json.dumps({'success': False, 'error': 'MinerU 未生成 .md 文件'})}", flush=True)

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(f"__RESULT__:{json.dumps({'success': False, 'error': str(e), 'traceback': tb[-1000:]})}", flush=True)


if __name__ == "__main__":
    main()
'''


# ── 主转换器 ──────────────────────────────────────────────────────────
class MinerUConverter:
    """MinerU PDF 转换器，通过子进程调用，管道传回逐页进度。"""

    def __init__(self, backend: str = "pipeline", lang: str = "ch"):
        self.backend = backend
        self.lang = lang

    def convert(
        self,
        pdf_path: str,
        output_dir: str,
        progress_callback: Optional[ProgressCallback] = None,
        start_page: int = 0,
        end_page: Optional[int] = None,
    ) -> ConvertResult:
        """
        转换 PDF 为 Markdown。

        Args:
            pdf_path: PDF 文件路径
            output_dir: 输出目录
            progress_callback: (current_page, total_pages, message) 回调
            start_page: 起始页（0-based）
            end_page: 结束页（不含），None 表示到最后

        Returns:
            ConvertResult
        """
        pdf_path = str(Path(pdf_path).resolve())
        output_dir = str(Path(output_dir).resolve())

        if not Path(pdf_path).exists():
            return ConvertResult(success=False, error=f"文件不存在: {pdf_path}")

        if not MINERU_PYTHON.exists():
            return ConvertResult(success=False, error=f"MinerU Python 不存在: {MINERU_PYTHON}")

        # 构建参数
        args = json.dumps({
            "pdf_path": pdf_path,
            "output_dir": output_dir,
            "backend": self.backend,
            "lang": self.lang,
            "start_page": start_page,
            "end_page": end_page,
        })

        try:
            proc = subprocess.Popen(
                [str(MINERU_PYTHON), "-c", _WORKER_SCRIPT, args],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=str(MINERU_SRC),
            )

            result_data = None

            for line in proc.stdout:
                line = line.strip()
                if line.startswith("__PROGRESS__:"):
                    if progress_callback:
                        try:
                            data = json.loads(line[13:])
                            progress_callback(data["cur"], data["total"], data["msg"])
                        except (json.JSONDecodeError, KeyError):
                            pass
                elif line.startswith("__RESULT__:"):
                    try:
                        result_data = json.loads(line[11:])
                    except json.JSONDecodeError:
                        pass

            proc.wait()

            if result_data:
                if result_data.get("success"):
                    return ConvertResult(
                        success=True,
                        md_path=result_data.get("md_path"),
                    )
                else:
                    err = result_data.get("error", "未知错误")
                    tb = result_data.get("traceback", "")
                    return ConvertResult(
                        success=False,
                        error=f"{err}\n{tb}" if tb else err,
                    )
            else:
                stderr = proc.stderr.read() if proc.stderr else ""
                return ConvertResult(
                    success=False,
                    error=f"MinerU 进程退出码 {proc.returncode}，stderr: {stderr[-500:]}",
                )

        except Exception as e:
            return ConvertResult(success=False, error=f"执行失败: {e}")


# ── CLI 测试入口 ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MinerU 转换（带进度）")
    parser.add_argument("pdf", help="PDF 文件路径")
    parser.add_argument("-o", "--output", default="/tmp/mineru-test", help="输出目录")
    parser.add_argument("-b", "--backend", default="pipeline", help="后端")
    args = parser.parse_args()

    def progress(cur, total, msg):
        bar_len = 30
        filled = int(bar_len * cur / total) if total > 0 else 0
        bar = "=" * filled + ">" + " " * (bar_len - filled)
        pct = cur / total * 100 if total > 0 else 0
        print(f"\r[{bar}] {cur}/{total} ({pct:.0f}%) {msg}", end="", flush=True)
        if cur >= total:
            print()

    converter = MinerUConverter(backend=args.backend)
    result = converter.convert(args.pdf, args.output, progress_callback=progress)

    if result.success:
        print(f"\n✅ 成功: {result.md_path}")
        md = Path(result.md_path).read_text(encoding="utf-8")
        print(f"--- 前 500 字 ---")
        print(md[:500])
    else:
        print(f"\n❌ 失败: {result.error}")
        sys.exit(1)
