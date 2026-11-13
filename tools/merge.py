#!/usr/bin/env python3
# -*- coding: utf-8 -*-
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
<!-- 蜗牛 favicon 内联SVG，标签页图标 -->
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
  var pageList     = ${PAGES_JSON};
  var documentMainTitle = ${JS_TITLE};
  var frameElement    = document.getElementById('frame');
  var switchButton = document.getElementById('switcher');
  var pageContentCache   = [];
  var currentPageIndex = 0;

  // ========== 拖拽相关 ==========
  let isDragging = false;
  let pointerStartX, pointerStartY, buttonStartLeft, buttonStartTop;
  const dragThresholdPx = 8; // 移动超过8px才算拖拽，否则判定为点击
  let hasPerformedDrag = false;

  function decodeBase64String(base64Text) {
    var binaryRaw = atob(base64Text);
    var byteArray = new Uint8Array(binaryRaw.length);
    for (var i = 0; i < binaryRaw.length; i++) {
        byteArray[i] = binaryRaw.charCodeAt(i);
    }
    return new TextDecoder('utf-8').decode(byteArray);
  }

  function renderPage(pageIndex) {
    if (pageContentCache[pageIndex] === undefined) {
      pageContentCache[pageIndex] = decodeBase64String(pageList[pageIndex].data);
    }
    if ('srcdoc' in frameElement) {
      frameElement.srcdoc = pageContentCache[pageIndex];
    } else {
      if (frameElement.dataset.blobUrl) {
          URL.revokeObjectURL(frameElement.dataset.blobUrl);
      }
      var blobUrl = URL.createObjectURL(
          new Blob([pageContentCache[pageIndex]], { type: 'text/html' })
      );
      frameElement.dataset.blobUrl = blobUrl;
      frameElement.src = blobUrl;
    }
  }

  function updateUiTooltip() {
    switchButton.title = '当前：' + pageList[currentPageIndex].title + '（点击切换到下一页，长按拖动）';
    document.title = pageList[currentPageIndex].title + ' · ' + documentMainTitle;
  }

  function showPage(pageIndex) {
    if (pageIndex < 0 || pageIndex >= pageList.length) return;
    currentPageIndex = pageIndex;
    renderPage(pageIndex);
    updateUiTooltip();
  }

  function goNextPage() {
    showPage((currentPageIndex + 1) % pageList.length);
  }

  function goPrevPage() {
    showPage((currentPageIndex - 1 + pageList.length) % pageList.length);
  }

  // 统一获取坐标
  function getPointerPosition(event) {
    if(event.touches) {
        return {x: event.touches[0].clientX, y: event.touches[0].clientY};
    }
    return {x: event.clientX, y: event.clientY};
  }

  function onPointerDownHandler(event) {
    const pos = getPointerPosition(event);
    pointerStartX = pos.x;
    pointerStartY = pos.y;
    const rect = switchButton.getBoundingClientRect();
    buttonStartLeft = rect.left;
    buttonStartTop = rect.top;
    hasPerformedDrag = false;
    isDragging = true;
    // 拖拽开始，让iframe不抢事件
    frameElement.style.pointerEvents = 'none';
    document.addEventListener('touchmove', onPointerMoveHandler, {passive:false});
    document.addEventListener('mousemove', onPointerMoveHandler);
    document.addEventListener('touchend', onPointerUpHandler);
    document.addEventListener('mouseup', onPointerUpHandler);
  }

  function onPointerMoveHandler(event) {
    if(!isDragging) return;
    const pos = getPointerPosition(event);
    const deltaX = pos.x - pointerStartX;
    const deltaY = pos.y - pointerStartY;

    if(!hasPerformedDrag && (Math.abs(deltaX) > dragThresholdPx || Math.abs(deltaY) > dragThresholdPx)){
      hasPerformedDrag = true;
    }

    if(hasPerformedDrag) {
      event.preventDefault();
      let newButtonLeft = buttonStartLeft + deltaX;
      let newButtonTop = buttonStartTop + deltaY;
      // 边界限制
      const btnWidth = switchButton.offsetWidth;
      const btnHeight = switchButton.offsetHeight;
      newButtonLeft = Math.max(0, Math.min(window.innerWidth - btnWidth, newButtonLeft));
      newButtonTop  = Math.max(0, Math.min(window.innerHeight - btnHeight, newButtonTop));
      switchButton.style.left = newButtonLeft + 'px';
      switchButton.style.top = newButtonTop + 'px';
    }
  }

  function onPointerUpHandler() {
    isDragging = false;
    // 恢复iframe交互
    frameElement.style.pointerEvents = '';
    document.removeEventListener('touchmove', onPointerMoveHandler);
    document.removeEventListener('mousemove', onPointerMoveHandler);
    document.removeEventListener('touchend', onPointerUpHandler);
    document.removeEventListener('mouseup', onPointerUpHandler);
    // 只有不是拖拽，才触发翻页
    if(!hasPerformedDrag) goNextPage();
  }

  switchButton.addEventListener('touchstart', onPointerDownHandler, {passive:false});
  switchButton.addEventListener('mousedown', onPointerDownHandler);

  // 键盘快捷键：空格 / → 下一页，← 上一页（不影响 iframe 内部交互）
  document.addEventListener('keydown', function (event) {
    if (event.target && (event.target.tagName === 'INPUT' || event.target.tagName === 'TEXTAREA')) return;
    if (event.key === 'ArrowRight' || event.key === ' ') { event.preventDefault(); goNextPage(); }
    if (event.key === 'ArrowLeft') { event.preventDefault(); goPrevPage(); }
  });

  const initialPageIndex = 0;
  showPage(initialPageIndex);
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
    match_result = TITLE_RE.search(html_raw)
    if not match_result:
        return ""
    title_text = TAG_RE.sub("", match_result.group(1))
    title_text = html.unescape(title_text)
    title_text = WS_RE.sub(" ", title_text).strip()
    return title_text


def js_escape_string(value: str) -> str:
    """把 Python 字符串安全地嵌入 JS 代码。"""
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def collect_matching_files(folder: Path, glob_pattern: str) -> list[Path]:
    found_file_map: dict[Path, Path] = {}
    for single_pattern in glob_pattern.split(","):
        single_pattern = single_pattern.strip()
        if not single_pattern:
            continue
        for file_item in folder.glob(single_pattern):
            if file_item.is_file():
                found_file_map[file_item.resolve()] = file_item
    return list(found_file_map.values())


def default_file_sort(file_list: list[Path]) -> list[Path]:
    def sort_key(file_item: Path):
        filename_lower = file_item.name.lower()
        # index.html优先排前面
        is_index_file = 0 if re.match(r"^index\.html?$", filename_lower) else 1
        return (is_index_file, filename_lower)
    return sorted(file_list, key=sort_key)


def apply_custom_file_order(file_list: list[Path], order_config: str | None) -> list[Path]:
    if not order_config:
        return default_file_sort(file_list)
    wanted_names = [s.strip().lower() for s in order_config.split(",") if s.strip()]
    ordered_result: list[Path] = []
    used_files: set[Path] = set()
    for wanted_name in wanted_names:
        for file_item in file_list:
            if file_item in used_files:
                continue
            if file_item.name.lower() == wanted_name or file_item.stem.lower() == wanted_name:
                ordered_result.append(file_item)
                used_files.add(file_item)
                break
        else:
            print(f"警告：--order 中的 \"{wanted_name}\" 没有匹配到文件", file=sys.stderr)
    rest_files = [f for f in default_file_sort(file_list) if f not in used_files]
    return ordered_result + rest_files


# ---------------------------------------------------------------- 主流程
def main(argv=None) -> int:
    argument_parser = argparse.ArgumentParser(
        description="把文件夹里的多个 HTML 合并成一个带循环切换按钮的单文件 HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    argument_parser.add_argument("folder", help="包含 HTML 文件的文件夹")
    argument_parser.add_argument("-o", "--output", help="输出文件路径（默认 <folder>/merged.html）")
    argument_parser.add_argument("-t", "--title", default="合并页面", help="合并后的总标题")
    argument_parser.add_argument("--pattern", default="*.html,*.htm",
                    help="文件匹配模式，逗号分隔（默认 *.html,*.htm）")
    argument_parser.add_argument("--order", help="逗号分隔的文件名/主干名，用于指定循环顺序")
    argument_parser.add_argument("--labels", help="逗号分隔的标题文字（只用于提示/页面标题），按最终顺序对应")
    argument_parser.add_argument("--exclude", action="append", default=[], metavar="NAME",
                    help="要跳过的文件名或主干名，可重复，也可逗号分隔")
    args = argument_parser.parse_args(argv)

    target_folder = Path(args.folder).expanduser().resolve()
    if not target_folder.is_dir():
        argument_parser.error(f"不是文件夹：{target_folder}")

    if args.output:
        output_file_path = Path(args.output).expanduser().resolve()
    else:
        output_file_path = target_folder / "merged.html"

    file_list = collect_matching_files(target_folder, args.pattern)
    # 排除输出文件自身
    file_list = [f for f in file_list if f.resolve() != output_file_path]

    exclude_name_set: set[str] = set()
    for exclude_item in args.exclude:
        for part in exclude_item.split(","):
            part = part.strip().lower()
            if part:
                exclude_name_set.add(part)

    if exclude_name_set:
        file_list = [
            f for f in file_list
            if f.name.lower() not in exclude_name_set and f.stem.lower() not in exclude_name_set
        ]

    if not file_list:
        argument_parser.error(f"在 {target_folder} 中没有找到匹配 {args.pattern} 的文件")

    file_list = apply_custom_file_order(file_list, args.order)

    custom_labels = None
    if args.labels:
        custom_labels = [s.strip() for s in args.labels.split(",")]
        if len(custom_labels) != len(file_list):
            print(f"提示：--labels 有 {len(custom_labels)} 项，文件有 {len(file_list)} 个，多余的将被忽略",
                  file=sys.stderr)

    page_info_list = []
    for page_idx, html_file in enumerate(file_list):
        html_content = read_text(html_file)
        page_title = ""
        if custom_labels and page_idx < len(custom_labels) and custom_labels[page_idx]:
            page_title = custom_labels[page_idx]
        if not page_title:
            page_title = extract_title(html_content) or html_file.stem

        base64_encoded = base64.b64encode(html_content.encode("utf-8")).decode("ascii")
        page_info_list.append({
            "title": page_title,
            "data": base64_encoded,
            "_file_size_bytes": html_file.stat().st_size,
        })

    # 输出给前端JSON
    frontend_payload = [{k: page[k] for k in ("title", "data")} for page in page_info_list]
    pages_json_text = json.dumps(frontend_payload, ensure_ascii=False, separators=(",", ":"))
    pages_json_text = (pages_json_text
                  .replace("<", "\\u003c")
                  .replace(">", "\\u003e")
                  .replace("&", "\\u0026"))

    final_html_output = Template(TEMPLATE).substitute(
        HTML_TITLE=html.escape(args.title),
        JS_TITLE=js_escape_string(args.title),
        PAGES_JSON=pages_json_text,
    )

    output_file_path.parent.mkdir(parents=True, exist_ok=True)
    output_file_path.write_text(final_html_output, encoding="utf-8")

    output_size_kb = output_file_path.stat().st_size / 1024
    print(f"✅ 已生成：{output_file_path}")
    print(f"   共 {len(page_info_list)} 个页面，输出大小 {output_size_kb:.1f} KB")
    for idx, page in enumerate(page_info_list, 1):
        print(f"   {idx}. {page['title']}  ({page['_file_size_bytes'] / 1024:.1f} KB)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
