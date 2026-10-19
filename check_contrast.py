"""WCAG AA contrast check for the GridLens palette.

Checks every text/background pair in figures.CONTRAST_PAIRS for the
palette and exits non-zero if any pair is below 4.5:1.

Run:  venv/bin/python check_contrast.py
"""
import sys

from figures import CONTRAST_PAIRS, PALETTES

MIN_RATIO = 4.5


def _linear(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color):
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return (0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b))


def contrast(fg, bg):
    l1, l2 = sorted((luminance(fg), luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


def main():
    failed = []
    for name, pal in PALETTES.items():
        print(f"[{name}]")
        for label, fg_key, bg_key in CONTRAST_PAIRS:
            fg, bg = pal[fg_key], pal[bg_key]
            ratio = contrast(fg, bg)
            ok = ratio >= MIN_RATIO
            if not ok:
                failed.append((name, label, ratio))
            print(f"  {'PASS' if ok else 'FAIL'}  {ratio:5.2f}:1  {label}  "
                  f"({fg} on {bg})")
    print()
    if failed:
        for name, label, ratio in failed:
            print(f"FAIL: [{name}] {label}: {ratio:.2f}:1 < {MIN_RATIO}:1")
        return 1
    print(f"PASS: every pair meets WCAG AA ({MIN_RATIO}:1).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
