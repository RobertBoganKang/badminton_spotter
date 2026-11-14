#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把多个 HTML 合并成一个可通过按钮循环切换的单文件 HTML。"""
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
INDEX_FILE_RE = re.compile(r"^index\.html?$")

DEFAULT_PATTERN = "*.html,*.htm"
DEFAULT_TITLE = "合并页面"

# ---------------------------------------------------------------- 模板
TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${HTML_TITLE}</title>
<!-- 蜗牛 favicon 内联 SVG -->
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='90' font-size='90'>🐌</text></svg>">
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

  /* 左上角循环切换按钮 */
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
    color: inherit;
    background: rgba(255, 255, 255, .85);
    border: none;
    border-radius: 50%;
    box-shadow: 0 3px 10px rgba(0, 0, 0, .18);
    cursor: pointer;
    user-select: none;
    -webkit-tap-highlight-color: transparent; /* 去掉触摸高亮 */
    -webkit-touch-callout: none;              /* 去掉长按菜单 */
    touch-action: none;                       /* 避免触摸滚动/缩放抢拖拽 */
    outline: none;                            /* 去掉触屏 focus 方框 */
    backdrop-filter: blur(6px);
    transition: background .18s, transform .15s, box-shadow .18s;
  }
  /* 保留键盘用户的可访问性：用键盘 Tab 到时仍显示焦点环 */
  #switcher:focus-visible {
    outline: 2px solid #4a90d9;
    outline-offset: 3px;
  }
  #switcher:hover {
    background: rgba(255, 255, 255, .98);
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

  const pages     = ${PAGES_JSON};
  const mainTitle = ${JS_TITLE};

  const frameEl   = document.getElementById('frame');
  const switchBtn = document.getElementById('switcher');

  const pageCache = [];
  let   currentIndex = 0;

  /* -------------------- 渲染 -------------------- */

  function decodeBase64(text) {
    const binary = atob(text);
    const bytes  = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return new TextDecoder('utf-8').decode(bytes);
  }

  function getPageHtml(index) {
    if (pageCache[index] === undefined) {
      pageCache[index] = decodeBase64(pages[index].data);
    }
    return pageCache[index];
  }

  function renderPage(index) {
    const html = getPageHtml(index);
    if ('srcdoc' in frameEl) {
      frameEl.srcdoc = html;
      return;
    }
    if (frameEl.dataset.blobUrl) {
      URL.revokeObjectURL(frameEl.dataset.blobUrl);
    }
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    frameEl.dataset.blobUrl = url;
    frameEl.src = url;
  }

  function updateUi() {
    const title = pages[currentIndex].title;
    switchBtn.title = '当前：' + title + '（点击切换到下一页，长按拖动）';
    document.title  = title + ' · ' + mainTitle;
  }

  function showPage(index) {
    if (index < 0 || index >= pages.length) return;
    currentIndex = index;
    renderPage(index);
    updateUi();
  }

  function goNext() { showPage((currentIndex + 1) % pages.length); }
  function goPrev() { showPage((currentIndex - 1 + pages.length) % pages.length); }

  /* -------------------- 拖拽 -------------------- */

  const DRAG_THRESHOLD = 8;

  let dragging  = false;
  let didDrag   = false;
  let startX    = 0;
  let startY    = 0;
  let startLeft = 0;
  let startTop  = 0;

  function getPoint(event) {
    if (event.touches && event.touches.length) {
      return { x: event.touches[0].clientX, y: event.touches[0].clientY };
    }
    return { x: event.clientX, y: event.clientY };
  }

  function onDragStart(event) {
    // 触屏上阻止浏览器默认行为：focus、tap 高亮、长按菜单，
    // 同时避免 touchend 后浏览器再模拟一次 mousedown。
    if (event.type === 'touchstart') {
      event.preventDefault();
    }

    const point = getPoint(event);
    startX = point.x;
    startY = point.y;
    const rect = switchBtn.getBoundingClientRect();
    startLeft = rect.left;
    startTop  = rect.top;
    dragging  = true;
    didDrag   = false;

    frameEl.style.pointerEvents = 'none';

    document.addEventListener('touchmove', onDragMove, { passive: false });
    document.addEventListener('mousemove', onDragMove);
    document.addEventListener('touchend',  onDragEnd);
    document.addEventListener('mouseup',   onDragEnd);
  }

  function onDragMove(event) {
    if (!dragging) return;

    const point = getPoint(event);
    const dx = point.x - startX;
    const dy = point.y - startY;

    if (!didDrag && (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD)) {
      didDrag = true;
    }
    if (!didDrag) return;

    event.preventDefault();

    const width  = switchBtn.offsetWidth;
    const height = switchBtn.offsetHeight;
    const left   = Math.max(0, Math.min(window.innerWidth  - width,  startLeft + dx));
    const top    = Math.max(0, Math.min(window.innerHeight - height, startTop  + dy));

    switchBtn.style.left = left + 'px';
    switchBtn.style.top  = top  + 'px';
  }

  function onDragEnd() {
    if (!dragging) return;
    dragging = false;
    frameEl.style.pointerEvents = '';

    document.removeEventListener('touchmove', onDragMove);
    document.removeEventListener('mousemove', onDragMove);
    document.removeEventListener('touchend',  onDragEnd);
    document.removeEventListener('mouseup',   onDragEnd);

    if (!didDrag) goNext();
  }

  switchBtn.addEventListener('touchstart', onDragStart, { passive: false });
  switchBtn.addEventListener('mousedown',  onDragStart);

  /* -------------------- 键盘 -------------------- */

  document.addEventListener('keydown', function (event) {
    const tag = event.target && event.target.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;

    if (event.key === 'ArrowRight' || event.key === ' ') {
      event.preventDefault();
      goNext();
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      goPrev();
    }
  });

  showPage(0);
})();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------- 工具函数
def read_text(file_path: Path) -> str:
    """读取文件，自动尝试常见编码。"""
    file_bytes = file_path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    print(f"警告：无法识别 {file_path.name} 的编码，按 UTF-8 强制解码", file=sys.stderr)
    return file_bytes.decode("utf-8", errors="replace")


def extract_title(html_raw: str) -> str:
    """从 HTML 中提取 <title> 文本，没有则返回空串。"""
    match = TITLE_RE.search(html_raw)
    if not match:
        return ""
    title_text = TAG_RE.sub("", match.group(1))
    title_text = html.unescape(title_text)
    return WS_RE.sub(" ", title_text).strip()


def escape_js_unsafe_chars(text: str) -> str:
    """把会提前结束 <script> 或干扰解析的字符转义。"""
    return (
        text
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def js_escape_string(value: str) -> str:
    """把 Python 字符串安全地嵌入 JS 代码（带引号）。"""
    return escape_js_unsafe_chars(json.dumps(value, ensure_ascii=False))


def collect_matching_files(folder: Path, glob_pattern: str) -> list[Path]:
    """按逗号分隔的多个 glob 收集文件，自动去重。"""
    found: dict[Path, Path] = {}
    for single_pattern in glob_pattern.split(","):
        single_pattern = single_pattern.strip()
        if not single_pattern:
            continue
        for file_item in folder.glob(single_pattern):
            if file_item.is_file():
                found[file_item.resolve()] = file_item
    return list(found.values())


def default_file_sort(file_list: list[Path]) -> list[Path]:
    """默认顺序：index.html 优先，其余按文件名（不区分大小写）排序。"""
    def sort_key(file_item: Path):
        name_lower = file_item.name.lower()
        is_index = 0 if INDEX_FILE_RE.match(name_lower) else 1
        return (is_index, name_lower)

    return sorted(file_list, key=sort_key)


def apply_custom_file_order(
    file_list: list[Path],
    order_config: str | None,
) -> list[Path]:
    """按 --order 指定的顺序排序，未匹配到的放到最后（默认顺序）。"""
    if not order_config:
        return default_file_sort(file_list)

    wanted_names = [s.strip().lower() for s in order_config.split(",") if s.strip()]
    ordered: list[Path] = []
    used: set[Path] = set()

    for wanted in wanted_names:
        for file_item in file_list:
            if file_item in used:
                continue
            if file_item.name.lower() == wanted or file_item.stem.lower() == wanted:
                ordered.append(file_item)
                used.add(file_item)
                break
        else:
            print(f"警告：--order 中的 \"{wanted}\" 没有匹配到文件", file=sys.stderr)

    rest = [f for f in default_file_sort(file_list) if f not in used]
    return ordered + rest


def build_exclude_set(exclude_args: list[str]) -> set[str]:
    """把可重复传入、又可能逗号分隔的 --exclude 参数合并成一个集合。"""
    result: set[str] = set()
    for item in exclude_args:
        for part in item.split(","):
            part = part.strip().lower()
            if part:
                result.add(part)
    return result


# ---------------------------------------------------------------- 主流程
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="把文件夹里的多个 HTML 合并成一个带循环切换按钮的单文件 HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("folder", help="包含 HTML 文件的文件夹")
    parser.add_argument("-o", "--output", help="输出文件路径（默认 <folder>/merged.html）")
    parser.add_argument("-t", "--title", default=DEFAULT_TITLE, help="合并后的总标题")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN,
                        help="文件匹配模式，逗号分隔（默认 *.html,*.htm）")
    parser.add_argument("--order", help="逗号分隔的文件名/主干名，用于指定循环顺序")
    parser.add_argument("--labels", help="逗号分隔的标题文字（只用于提示/页面标题），按最终顺序对应")
    parser.add_argument("--exclude", action="append", default=[], metavar="NAME",
                        help="要跳过的文件名或主干名，可重复，也可逗号分隔")
    args = parser.parse_args(argv)

    target_folder = Path(args.folder).expanduser().resolve()
    if not target_folder.is_dir():
        parser.error(f"不是文件夹：{target_folder}")

    if args.output:
        output_file = Path(args.output).expanduser().resolve()
    else:
        output_file = target_folder / "merged.html"

    file_list = collect_matching_files(target_folder, args.pattern)
    # 排除输出文件自身，避免自我嵌入
    file_list = [f for f in file_list if f.resolve() != output_file]

    exclude_set = build_exclude_set(args.exclude)
    if exclude_set:
        file_list = [
            f for f in file_list
            if f.name.lower() not in exclude_set and f.stem.lower() not in exclude_set
        ]

    if not file_list:
        parser.error(f"在 {target_folder} 中没有找到匹配 {args.pattern} 的文件")

    file_list = apply_custom_file_order(file_list, args.order)

    custom_labels: list[str] | None = None
    if args.labels:
        custom_labels = [s.strip() for s in args.labels.split(",")]
        if len(custom_labels) != len(file_list):
            print(
                f"提示：--labels 有 {len(custom_labels)} 项，文件有 {len(file_list)} 个，多余的将被忽略",
                file=sys.stderr,
            )

    page_info_list = []
    for page_idx, html_file in enumerate(file_list):
        html_content = read_text(html_file)

        page_title = ""
        if custom_labels and page_idx < len(custom_labels) and custom_labels[page_idx]:
            page_title = custom_labels[page_idx]
        if not page_title:
            page_title = extract_title(html_content) or html_file.stem

        page_info_list.append({
            "title": page_title,
            "data": base64.b64encode(html_content.encode("utf-8")).decode("ascii"),
            "_file_size_bytes": html_file.stat().st_size,
        })

    # 输出给前端的 JSON：只保留 title / data
    frontend_payload = [{k: page[k] for k in ("title", "data")} for page in page_info_list]
    pages_json_text = json.dumps(frontend_payload, ensure_ascii=False, separators=(",", ":"))
    pages_json_text = escape_js_unsafe_chars(pages_json_text)

    final_html = Template(TEMPLATE).substitute(
        HTML_TITLE=html.escape(args.title),
        JS_TITLE=js_escape_string(args.title),
        PAGES_JSON=pages_json_text,
    )

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(final_html, encoding="utf-8")

    output_size_kb = output_file.stat().st_size / 1024
    print(f"✅ 已生成：{output_file}")
    print(f"   共 {len(page_info_list)} 个页面，输出大小 {output_size_kb:.1f} KB")
    for idx, page in enumerate(page_info_list, 1):
        print(f"   {idx}. {page['title']}  ({page['_file_size_bytes'] / 1024:.1f} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())