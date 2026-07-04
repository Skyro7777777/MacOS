#!/usr/bin/env python3
"""
 =============================================================================
  mac_ocr_helper.py  —  Apple Vision OCR helper for finding + clicking UI
  elements by their text label.

  Uses the macOS BUILT-IN Vision framework (VNRecognizeTextRequest) via
  PyObjC.  Zero model download, ~100 MB RAM, no GPU.

  screencapture + cliclick are used for capture + input — they inherit bash's
  Screen Recording + Accessibility TCC permission (the "responsible process"
  model).  No TCC grant needed for Python itself.

  Usage:
    python3 mac_ocr_helper.py find <text>          → prints "x y" center of first match, or "NOT_FOUND"
    python3 mac_ocr_helper.py click <text>          → clicks center of first match, prints OK/NOT_FOUND
    python3 mac_ocr_helper.py click_right <text> <offset>
                                                    → clicks <offset> px right of first match's right edge
    python3 mac_ocr_helper.py click_toggle <app_name>
                                                    → clicks the toggle ~120px right of <app_name>'s right edge
    python3 mac_ocr_helper.py type <text>           → types text via cliclick
    python3 mac_ocr_helper.py dump                   → prints all OCR text + boxes (for debugging)
    python3 mac_ocr_helper.py wait_for <text> <timeout>
                                                    → waits up to <timeout>s for <text> to appear, prints OK/TIMEOUT
    python3 mac_ocr_helper.py shot <path>            → takes a screenshot to <path>
 =============================================================================
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path


def log(msg: str) -> None:
    print(f"[ocr] {msg}", file=sys.stderr, flush=True)


def screenshot(path: str = "/tmp/ocr_shot.png") -> str:
    subprocess.run(["screencapture", "-x", "-C", path], check=True)
    return path


def click_at(x: int, y: int) -> None:
    subprocess.run(["cliclick", f"c:{x},{y}"], check=True)
    time.sleep(0.5)


def type_text(text: str) -> None:
    subprocess.run(["cliclick", f"t:{text}"], check=True)
    time.sleep(0.3)


def ocr(img_path: str) -> list[tuple[str, int, int, int, int]]:
    """Run macOS Vision OCR. Returns [(text, x1, y1, x2, y2), ...] in pixel coords."""
    try:
        import Quartz  # noqa: F401
        from Vision import VNRecognizeTextRequest, VNImageRequestHandler
        from Foundation import NSURL
        from PIL import Image
    except ImportError as e:
        log(f"PyObjC/Pillow missing: {e}")
        return []

    url = NSURL.fileURLWithPath_(img_path)
    request = VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(1)  # accurate
    request.setRecognitionLanguages_(["en-US"])

    handler = VNImageRequestHandler.alloc().initWithURL_options_(url, None)
    success = handler.performRequests_error_([request], None)
    if not success:
        log("Vision request failed")
        return []

    results = request.results() or []

    with Image.open(img_path) as img:
        w, h = img.size

    boxes = []
    for obs in results:
        try:
            candidate = obs.topCandidates_(1)
            if not candidate:
                continue
            text = candidate[0].string()
            bbox = obs.boundingBox()  # normalized CGRect, origin bottom-left
            x1 = int(bbox.origin.x * w)
            y1 = int((1 - bbox.origin.y - bbox.size.height) * h)
            x2 = int((bbox.origin.x + bbox.size.width) * w)
            y2 = int((1 - bbox.origin.y) * h)
            boxes.append((text, x1, y1, x2, y2))
        except Exception:
            continue
    return boxes


def find_text(boxes: list, target: str) -> tuple[int, int, int, int, int] | None:
    """Find first box whose text contains target (case-insensitive).
    Returns (text, x1, y1, x2, y2) or None."""
    target_lower = target.lower()
    for text, x1, y1, x2, y2 in boxes:
        if target_lower in text.lower():
            return (text, x1, y1, x2, y2)
    return None


def find_all(boxes: list, target: str) -> list[tuple[int, int, int, int, int]]:
    """Find ALL boxes whose text contains target."""
    target_lower = target.lower()
    matches = []
    for text, x1, y1, x2, y2 in boxes:
        if target_lower in text.lower():
            matches.append((text, x1, y1, x2, y2))
    return matches


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: mac_ocr_helper.py <command> [args]", file=sys.stderr)
        return 1

    cmd = sys.argv[1]

    if cmd == "shot":
        path = sys.argv[2] if len(sys.argv) > 2 else "/tmp/ocr_shot.png"
        screenshot(path)
        print(path)
        return 0

    if cmd == "type":
        text = sys.argv[2]
        type_text(text)
        print("OK")
        return 0

    if cmd == "dump":
        shot = screenshot()
        boxes = ocr(shot)
        for text, x1, y1, x2, y2 in boxes:
            print(f"{text!r:40s} ({x1},{y1})-({x2},{y2})  center=({(x1+x2)//2},{(y1+y2)//2})")
        return 0

    if cmd == "find":
        target = sys.argv[2]
        shot = screenshot()
        boxes = ocr(shot)
        match = find_text(boxes, target)
        if match:
            text, x1, y1, x2, y2 = match
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            print(f"{cx} {cy}")
            return 0
        else:
            print("NOT_FOUND")
            return 1

    if cmd == "click":
        target = sys.argv[2]
        shot = screenshot()
        boxes = ocr(shot)
        match = find_text(boxes, target)
        if match:
            text, x1, y1, x2, y2 = match
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            log(f"clicking '{text.strip()}' at ({cx},{cy})")
            click_at(cx, cy)
            print("OK")
            return 0
        else:
            log(f"'{target}' not found in {len(boxes)} text boxes")
            print("NOT_FOUND")
            return 1

    if cmd == "click_right":
        target = sys.argv[2]
        offset = int(sys.argv[3]) if len(sys.argv) > 3 else 120
        shot = screenshot()
        boxes = ocr(shot)
        match = find_text(boxes, target)
        if match:
            text, x1, y1, x2, y2 = match
            click_x = x2 + offset
            click_y = (y1 + y2) // 2
            log(f"clicking {offset}px right of '{text.strip()}' at ({click_x},{click_y})")
            click_at(click_x, click_y)
            print("OK")
            return 0
        else:
            print("NOT_FOUND")
            return 1

    if cmd == "click_toggle":
        app_name = sys.argv[2]
        shot = screenshot()
        boxes = ocr(shot)
        match = find_text(boxes, app_name)
        if match:
            text, x1, y1, x2, y2 = match
            toggle_x = x2 + 120  # toggle is ~120px right of the app name
            toggle_y = (y1 + y2) // 2
            log(f"clicking toggle for '{app_name}' at ({toggle_x},{toggle_y})")
            click_at(toggle_x, toggle_y)
            print("OK")
            return 0
        else:
            print("NOT_FOUND")
            return 1

    if cmd == "wait_for":
        target = sys.argv[2]
        timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 30
        deadline = time.time() + timeout
        while time.time() < deadline:
            shot = screenshot()
            boxes = ocr(shot)
            if find_text(boxes, target):
                print("OK")
                return 0
            time.sleep(1)
        print("TIMEOUT")
        return 1

    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
