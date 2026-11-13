#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_html.py
把文件夹里的多个 HTML 文件合并成一个单文件 HTML。
左上角一个固定的圆形 emoji 按钮，点击循环切换页面，不占布局空间。
修改：放大按钮、去掉边框、悬浮效果更强
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import re
import sys
from pathlib import Path
from string import Template


TITLE_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


# ---------------------------------------------------------------- 模板
TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${HTML_TITLE}</title>
<style>
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    font-family: system-ui, -apple-system, "Segoe UI", "PingFang SC",
                "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    background: #fff;
  }
  #frame {
    position: fixed;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
    display: block;
    background: #fff;
  }
  /* 左上角循环切换按钮：放大、无边框、悬浮 */
  #switcher {
    position: fixed;
    top: 12px;
    left: 12px;
    z-index: 2147483647;
    width: 48px;
    height: 48px;
    padding: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    line-height: 1;
    background: rgba(255, 255, 255, .85);
    border: none;
    border-radius: 50%;
    box-shadow: 0 3px 10px rgba(0, 0, 0, .18);
    cursor: pointer;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
    backdrop-filter: blur(6px);
    transition: background .18s, transform .15s, box-shadow .18s;
  }
  touch-action: none;
  #switcher:hover {
    background: rgba(255, 255, 255, 0.98);
    box-shadow: 0 6px 18px rgba(0, 0, 0, .24);
    transform: scale(1.08);
  }
  #switcher:active { transform: scale(.94); }
</style>
</head>
<body>
<iframe id="frame" title="内容"></iframe>
<button id="switcher" type="button" title="切换页面">🐌</button>

<script>
(function () {
  'use strict';

  var PAGES     = ${PAGES_JSON};
  var PAGE_TITLE = ${JS_TITLE};

  var frame    = document.getElementById('frame');
  var switcher = document.getElementById('switcher');

  var cache   = [];
  var current = 0;

  // ========== 拖拽相关 ==========
  let dragging = false;
  let startX, startY, btnStartLeft, btnStartTop;
  const dragThreshold = 8; // 移动超过8px才算拖拽，否则判定为点击
  let isDragAction = false;

  function decodeBase64(b64) {
    var bin = atob(b64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder('utf-8').decode(bytes);
  }

  function render(index) {
    if (cache[index] === undefined) {
      cache[index] = decodeBase64(PAGES[index].data);
    }
    if ('srcdoc' in frame) {
      frame.srcdoc = cache[index];
    } else {
      if (frame.dataset.blobUrl) URL.revokeObjectURL(frame.dataset.blobUrl);
      var url = URL.createObjectURL(new Blob([cache[index]], { type: 'text/html' }));
      frame.dataset.blobUrl = url;
      frame.src = url;
    }
  }

  function updateLabel() {
    switcher.title = '当前：' + PAGES[current].title + '（点击切换到下一页，长按拖动）';
    document.title = PAGES[current].title + ' · ' + PAGE_TITLE;
  }

  function show(index) {
    if (index < 0 || index >= PAGES.length) return;
    current = index;
    render(index);
    updateLabel();
    try {
      history.replaceState(null, '', '#' + encodeURIComponent(PAGES[current].slug));
    } catch (e) { /* file:// 下可能被限制 */ }
  }

  function next() {
    show((current + 1) % PAGES.length);
  }

  // 统一获取坐标
  function getPointerPos(e) {
    if(e.touches) return {x: e.touches[0].clientX, y: e.touches[0].clientY};
    return {x: e.clientX, y: e.clientY};
  }

  function onPointerDown(e) {
    const p = getPointerPos(e);
    startX = p.x;
    startY = p.y;
    const rect = switcher.getBoundingClientRect();
    btnStartLeft = rect.left;
    btnStartTop = rect.top;
    isDragAction = false;
    dragging = true;
    // 拖拽开始，让iframe不抢事件
    frame.style.pointerEvents = 'none';
    document.addEventListener('touchmove', onPointerMove, {passive:false});
    document.addEventListener('mousemove', onPointerMove);
    document.addEventListener('touchend', onPointerUp);
    document.addEventListener('mouseup', onPointerUp);
  }

  function onPointerMove(e) {
    if(!dragging) return;
    const p = getPointerPos(e);
    const dx = p.x - startX;
    const dy = p.y - startY;
    if(!isDragAction && (Math.abs(dx) > dragThreshold || Math.abs(dy) > dragThreshold)){
      isDragAction = true;
    }
    if(isDragAction) {
      e.preventDefault();
      let newLeft = btnStartLeft + dx;
      let newTop = btnStartTop + dy;
      // 边界限制
      const w = switcher.offsetWidth;
      const h = switcher.offsetHeight;
      newLeft = Math.max(0, Math.min(window.innerWidth - w, newLeft));
      newTop  = Math.max(0, Math.min(window.innerHeight - h, newTop));
      switcher.style.left = newLeft + 'px';
      switcher.style.top = newTop + 'px';
    }
  }

  function onPointerUp() {
    dragging = false;
    // 恢复iframe交互
    frame.style.pointerEvents = '';
    document.removeEventListener('touchmove', onPointerMove);
    document.removeEventListener('mousemove', onPointerMove);
    document.removeEventListener('touchend', onPointerUp);
    document.removeEventListener('mouseup', onPointerUp);
    // 只有不是拖拽，才触发翻页
    if(!isDragAction) next();
  }

  switcher.addEventListener('touchstart', onPointerDown, {passive:false});
  switcher.addEventListener('mousedown', onPointerDown);

  // 键盘快捷键：空格 / → 下一页，← 上一页（不影响 iframe 内部交互）
  document.addEventListener('keydown', function (e) {
    if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
    if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); next(); }
    if (e.key === 'ArrowLeft') { e.preventDefault(); show((current - 1 + PAGES.length) % PAGES.length); }
  });

  // 通过 #slug 直接打开某一页
  var start = 0;
  try {
    var hash = decodeURIComponent(location.hash.slice(1));
    var idx = PAGES.findIndex(function (p) { return p.slug === hash; });
    if (idx >= 0) start = idx;
  } catch (e) { /* ignore */ }

  show(start);
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- 工具函数
def read_text(path: Path) -> str:
    """读取文件，自动尝试常见编码。"""
    data = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    print(f"警告：无法识别 {path.name} 的编码，按 UTF-8 强制解码", file=sys.stderr)
    return data.decode("utf-8", errors="replace")


def extract_title(raw: str) -> str:
    """从 HTML 中提取 <title> 文本，没有则返回空串。"""
    m = TITLE_RE.search(raw)
    if not m:
        return ""
    text = TAG_RE.sub("", m.group(1))
    text = html.unescape(text)
    return WS_RE.sub(" ", text).strip()


def js_str(value: str) -> str:
    """把 Python 字符串安全地嵌入 JS 代码。"""
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def collect_files(folder: Path, pattern: str) -> list[Path]:
    found: dict[Path, Path] = {}
    for pat in pattern.split(","):
        pat = pat.strip()
        if not pat:
            continue
        for p in folder.glob(pat):
            if p.is_file():
                found[p.resolve()] = p
    return list(found.values())


def default_sort(files: list[Path]) -> list[Path]:
    def key(p: Path):
        name = p.name.lower()
        is_index = 0 if re.match(r"^index\.html?$", name) else 1
        return (is_index, name)
    return sorted(files, key=key)


def apply_order(files: list[Path], order: str | None) -> list[Path]:
    if not order:
        return default_sort(files)

    wanted = [s.strip().lower() for s in order.split(",") if s.strip()]
    ordered: list[Path] = []
    used: set[Path] = set()

    for w in wanted:
        for f in files:
            if f in used:
                continue
            if f.name.lower() == w or f.stem.lower() == w:
                ordered.append(f)
                used.add(f)
                break
        else:
            print(f"警告：--order 中的 \"{w}\" 没有匹配到文件", file=sys.stderr)

    rest = [f for f in default_sort(files) if f not in used]
    return ordered + rest


# ---------------------------------------------------------------- 主流程
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="把文件夹里的多个 HTML 合并成一个带循环切换按钮的单文件 HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("folder", help="包含 HTML 文件的文件夹")
    ap.add_argument("-o", "--output", help="输出文件路径（默认 <folder>/merged.html）")
    ap.add_argument("-t", "--title", default="合并页面", help="合并后的总标题")
    ap.add_argument("--pattern", default="*.html,*.htm",
                    help="文件匹配模式，逗号分隔（默认 *.html,*.htm）")
    ap.add_argument("--order", help="逗号分隔的文件名/主干名，用于指定循环顺序")
    ap.add_argument("--labels", help="逗号分隔的标题文字（只用于提示/页面标题），按最终顺序对应")
    ap.add_argument("--exclude", action="append", default=[], metavar="NAME",
                    help="要跳过的文件名或主干名，可重复，也可逗号分隔")
    args = ap.parse_args(argv)

    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        ap.error(f"不是文件夹：{folder}")

    out_path = (Path(args.output).expanduser().resolve()
                if args.output else folder / "merged.html")

    files = collect_files(folder, args.pattern)
    files = [f for f in files if f.resolve() != out_path]

    excludes: set[str] = set()
    for item in args.exclude:
        for part in item.split(","):
            part = part.strip().lower()
            if part:
                excludes.add(part)
    if excludes:
        files = [f for f in files
                 if f.name.lower() not in excludes and f.stem.lower() not in excludes]

    if not files:
        ap.error(f"在 {folder} 中没有找到匹配 {args.pattern} 的文件")

    files = apply_order(files, args.order)

    labels = None
    if args.labels:
        labels = [s.strip() for s in args.labels.split(",")]
        if len(labels) != len(files):
            print(f"提示：--labels 有 {len(labels)} 项，文件有 {len(files)} 个，多余的将被忽略",
                  file=sys.stderr)

    pages = []
    used_slugs: set[str] = set()
    for idx, f in enumerate(files):
        raw = read_text(f)

        title = ""
        if labels and idx < len(labels) and labels[idx]:
            title = labels[idx]
        if not title:
            title = extract_title(raw) or f.stem

        slug = f.stem
        n = 2
        while slug in used_slugs:
            slug = f"{f.stem}-{n}"
            n += 1
        used_slugs.add(slug)

        b64 = base64.b64encode(raw.encode("utf-8")).decode("ascii")
        pages.append({
            "title": title,
            "slug": slug,
            "data": b64,
            "_size": f.stat().st_size,
        })

    payload = [{k: p[k] for k in ("title", "slug", "data")} for p in pages]
    pages_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    pages_json = (pages_json
                  .replace("<", "\\u003c")
                  .replace(">", "\\u003e")
                  .replace("&", "\\u0026"))

    out_html = Template(TEMPLATE).substitute(
        HTML_TITLE=html.escape(args.title),
        JS_TITLE=js_str(args.title),
        PAGES_JSON=pages_json,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(out_html, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    print(f"✅ 已生成：{out_path}")
    print(f"   共 {len(pages)} 个页面，输出大小 {size_kb:.1f} KB")
    for i, p in enumerate(pages, 1):
        print(f"   {i}. {p['title']}  ({p['_size'] / 1024:.1f} KB, slug: {p['slug']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
