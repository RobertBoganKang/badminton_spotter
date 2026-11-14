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
DEFAULT_TITLE = ""  # 留空时标签页只显示各页自身标题

# ---------------------------------------------------------------- 模板
TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${HTML_TITLE}</title>
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
    position: fixed; inset: 0;
    width: 100%; height: 100%;
    border: 0; display: block;
    background: #fff;
  }
  /* 蜗牛：只有 emoji + 自身轮廓阴影，无背景框 */
  #switcher {
    position: fixed;
    top: 12px; left: 12px;
    z-index: 2147483647;
    width: 48px; height: 48px;
    padding: 0;
    display: flex; align-items: center; justify-content: center;
    font-size: 32px; line-height: 1;
    color: inherit;
    background: transparent;
    border: none;
    cursor: grab;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
    -webkit-touch-callout: none;
    touch-action: none;
    outline: none;
    filter: drop-shadow(0 3px 4px rgba(0, 0, 0, .35));
    transition: left var(--move-duration, 0s) linear,
                top  var(--move-duration, 0s) linear,
                transform .15s, filter .18s;
  }
  #switcher:hover  { transform: scale(1.12); filter: drop-shadow(0 4px 8px rgba(0, 0, 0, .45)); }
  #switcher:active { cursor: grabbing; transform: scale(.9); }
  #switcher:focus-visible { outline: 2px solid #4a90d9; outline-offset: 2px; }
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

  /* ---------- 渲染 ---------- */

  function decodeBase64(text) {
    const binary = atob(text);
    const bytes  = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
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
    if (frameEl.dataset.blobUrl) URL.revokeObjectURL(frameEl.dataset.blobUrl);
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    frameEl.dataset.blobUrl = url;
    frameEl.src = url;
  }

  function updateUi() {
    const title = pages[currentIndex].title;
    switchBtn.title = '当前：' + title + '（点击切换到下一页，长按拖动）';
    document.title  = mainTitle ? title + ' · ' + mainTitle : title;
  }

  function showPage(index) {
    if (index < 0 || index >= pages.length) return;
    currentIndex = index;
    renderPage(index);
    updateUi();
  }

  const goNext = () => showPage((currentIndex + 1) % pages.length);
  const goPrev = () => showPage((currentIndex - 1 + pages.length) % pages.length);

  /* ---------- 位置 ---------- */

  function getMaxX() { return Math.max(0, window.innerWidth  - switchBtn.offsetWidth);  }
  function getMaxY() { return Math.max(0, window.innerHeight - switchBtn.offsetHeight); }

  function setButtonPosition(x, y) {
    switchBtn.style.left = x + 'px';
    switchBtn.style.top  = y + 'px';
  }

  function clampButtonToViewport() {
    const left = parseFloat(switchBtn.style.left) || 0;
    const top  = parseFloat(switchBtn.style.top)  || 0;
    setButtonPosition(
      Math.max(0, Math.min(getMaxX(), left)),
      Math.max(0, Math.min(getMaxY(), top)),
    );
  }

  /* ---------- 空闲检测 + 自动爬行 ---------- */

  const IDLE_BEFORE_WANDER = 60000;   // 连续多久无操作才开始爬（ms）
  const WANDER_DELAY_MIN   = 9000;    // 爬行中的歇息间隔（ms）
  const WANDER_DELAY_MAX   = 22000;
  const WANDER_SPEED_MIN   = 30;      // 爬行速度（px/s）
  const WANDER_SPEED_MAX   = 55;
  const WANDER_MIN_DUR     = 1.5;     // 单次移动时长下限（s）
  const WANDER_MAX_DUR     = 8;       // 单次移动时长上限（s）

  const ACTIVITY_EVENTS = [
    'pointerdown', 'pointermove', 'pointerup',
    'keydown', 'wheel',
    'touchstart', 'touchmove', 'touchend',
    'scroll', 'click',
  ];

  let idleTimer   = null;
  let wanderTimer = null;
  let isWandering = false;
  let lastActivityAt = 0;

  function startIdleCountdown() {
    clearTimeout(idleTimer);
    idleTimer = setTimeout(function () {
      isWandering = true;
      wander();
    }, IDLE_BEFORE_WANDER);
  }

  function freezeButtonMovement() {
    const rect = switchBtn.getBoundingClientRect();
    switchBtn.style.setProperty('--move-duration', '0s');
    setButtonPosition(rect.left, rect.top);
  }

  function stopEverything() {
    clearTimeout(idleTimer);
    clearTimeout(wanderTimer);
    wanderTimer = null;
    if (isWandering) {
      isWandering = false;
      freezeButtonMovement();
    }
  }

  function notifyUserActivity() {
    if (dragging) return;
    const now = Date.now();
    if (now - lastActivityAt < 300) return;  // 节流
    lastActivityAt = now;
    stopEverything();
    startIdleCountdown();
  }

  function scheduleWander() {
    clearTimeout(wanderTimer);
    wanderTimer = setTimeout(
      wander,
      WANDER_DELAY_MIN + Math.random() * (WANDER_DELAY_MAX - WANDER_DELAY_MIN),
    );
  }

  function wander() {
    if (!isWandering || dragging) return;

    const currentX = parseFloat(switchBtn.style.left) || 0;
    const currentY = parseFloat(switchBtn.style.top)  || 0;
    const targetX  = Math.random() * getMaxX();
    const targetY  = Math.random() * getMaxY();

    const distance = Math.hypot(targetX - currentX, targetY - currentY);
    const speed    = WANDER_SPEED_MIN + Math.random() * (WANDER_SPEED_MAX - WANDER_SPEED_MIN);
    const duration = Math.max(WANDER_MIN_DUR, Math.min(WANDER_MAX_DUR, distance / speed));

    switchBtn.style.setProperty('--move-duration', duration + 's');
    setButtonPosition(targetX, targetY);
    scheduleWander();
  }

  /* ---------- 拖拽 ---------- */

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
    if (event.type === 'touchstart') event.preventDefault();

    stopEverything();

    const rect = switchBtn.getBoundingClientRect();
    switchBtn.style.setProperty('--move-duration', '0s');
    setButtonPosition(rect.left, rect.top);

    const point = getPoint(event);
    startX    = point.x;
    startY    = point.y;
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
    setButtonPosition(
      Math.max(0, Math.min(getMaxX(), startLeft + dx)),
      Math.max(0, Math.min(getMaxY(), startTop  + dy)),
    );
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
    notifyUserActivity();
  }

  switchBtn.addEventListener('touchstart', onDragStart, { passive: false });
  switchBtn.addEventListener('mousedown',  onDragStart);

  /* ---------- 键盘 ---------- */

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

  /* ---------- 活动监听（父页面 + iframe） ---------- */

  ACTIVITY_EVENTS.forEach(function (evt) {
    window.addEventListener(evt, notifyUserActivity, { capture: true, passive: true });
  });

  function bindActivityListenersToIframe() {
    try {
      const innerWin = frameEl.contentWindow;
      if (!innerWin) return;
      ACTIVITY_EVENTS.forEach(function (evt) {
        innerWin.addEventListener(evt, notifyUserActivity, { capture: true, passive: true });
      });
    } catch (err) {
      /* 跨域等异常情况忽略 */
    }
  }
  frameEl.addEventListener('load', bindActivityListenersToIframe);

  /* ---------- 启动 ---------- */

  window.addEventListener('resize', clampButtonToViewport);

  setButtonPosition(12, 12);   // 蜗牛默认停在左上角
  showPage(0);
  startIdleCountdown();
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
    return WS_RE.sub(" ", html.unescape(title_text)).strip()


def escape_js_unsafe_chars(text: str) -> str:
    """转义会提前结束 <script> 或干扰解析的字符。"""
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def js_escape_string(value: str) -> str:
    """把 Python 字符串安全地嵌入 JS（带引号）。"""
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
        return (0 if INDEX_FILE_RE.match(name_lower) else 1, name_lower)
    return sorted(file_list, key=sort_key)


def apply_custom_file_order(file_list: list[Path], order_config: str | None) -> list[Path]:
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

    return ordered + [f for f in default_file_sort(file_list) if f not in used]


def build_exclude_set(exclude_args: list[str]) -> set[str]:
    """把可重复传入、又可能逗号分隔的 --exclude 参数合并成一个集合。"""
    return {
        part.strip().lower()
        for item in exclude_args
        for part in item.split(",")
        if part.strip()
    }


# ---------------------------------------------------------------- 主流程
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="把文件夹里的多个 HTML 合并成一个带循环切换按钮的单文件 HTML",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("folder", help="包含 HTML 文件的文件夹")
    parser.add_argument("-o", "--output", help="输出文件路径（默认 <folder>/merged.html）")
    parser.add_argument("-t", "--title", default=DEFAULT_TITLE,
                        help="总标题，留空则标签页只显示各页自身标题")
    parser.add_argument("--pattern", default=DEFAULT_PATTERN,
                        help="文件匹配模式，逗号分隔（默认 *.html,*.htm）")
    parser.add_argument("--order", help="逗号分隔的文件名/主干名，用于指定循环顺序")
    parser.add_argument("--labels", help="逗号分隔的标题文字，按最终顺序对应")
    parser.add_argument("--exclude", action="append", default=[], metavar="NAME",
                        help="要跳过的文件名或主干名，可重复，也可逗号分隔")
    args = parser.parse_args(argv)

    target_folder = Path(args.folder).expanduser().resolve()
    if not target_folder.is_dir():
        parser.error(f"不是文件夹：{target_folder}")

    output_file = (Path(args.output).expanduser().resolve()
                   if args.output else target_folder / "merged.html")

    file_list = collect_matching_files(target_folder, args.pattern)
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

    frontend_payload = [{k: p[k] for k in ("title", "data")} for p in page_info_list]
    pages_json_text = escape_js_unsafe_chars(
        json.dumps(frontend_payload, ensure_ascii=False, separators=(",", ":"))
    )

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