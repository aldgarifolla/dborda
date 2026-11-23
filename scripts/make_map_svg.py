"""Фон ORDA в стиле топографической карты (ГИС): горизонтали по рельефу, подписи высот, километровая сетка,
река и дорога. Рельеф вымышленный: сумма «холмов» и плавных волн, детерминированно (без случайных чисел).

  python3 scripts/make_map_svg.py

Создаёт web/static/img/map-page.svg (светлый фон страниц) и web/static/img/map-sidebar.svg (тёмная боковая панель).
Горизонтали строятся методом marching squares, поэтому линии не пересекаются, как на настоящей карте.
"""
import math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'web' / 'static' / 'img'


def field(hills, waves, zoom=1.0):
    def h(x, y):
        x, y = x * zoom, y * zoom   # zoom > 1: рельеф мельче (виден больший участок)
        v = 0.0
        for cx, cy, amp, sx, sy in hills:
            v += amp * math.exp(-(((x - cx) / sx) ** 2 + ((y - cy) / sy) ** 2))
        for ax, ay, ph, amp in waves:
            v += amp * math.sin(x * ax + y * ay + ph)
        return v
    return h


def contours(h, width, height, step, levels):
    """Marching squares: для каждого уровня — список полилиний [(x, y), …]."""
    nx, ny = int(width / step) + 1, int(height / step) + 1
    grid = [[h(i * step, j * step) for i in range(nx)] for j in range(ny)]
    result = {}
    for level in levels:
        segs = []
        for j in range(ny - 1):
            for i in range(nx - 1):
                a, b, c, d = grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]
                idx = (a > level) | ((b > level) << 1) | ((c > level) << 2) | ((d > level) << 3)
                if idx in (0, 15):
                    continue
                x0, y0 = i * step, j * step

                def lerp(p, q):
                    return 0.5 if p == q else (level - p) / (q - p)
                top = (x0 + step * lerp(a, b), y0)
                right = (x0 + step, y0 + step * lerp(b, c))
                bottom = (x0 + step * lerp(d, c), y0 + step)
                left = (x0, y0 + step * lerp(a, d))
                table = {1: [(left, top)], 2: [(top, right)], 3: [(left, right)], 4: [(right, bottom)],
                         5: [(left, top), (right, bottom)], 6: [(top, bottom)], 7: [(left, bottom)],
                         8: [(bottom, left)], 9: [(bottom, top)], 10: [(top, right), (bottom, left)],
                         11: [(bottom, right)], 12: [(right, left)], 13: [(right, top)], 14: [(top, left)]}
                segs += table[idx]
        result[level] = join(segs)
    return result


def join(segs):
    """Сегменты -> полилинии по общим концам."""
    key = lambda p: (round(p[0], 2), round(p[1], 2))
    ends = {}
    for n, (p, q) in enumerate(segs):
        ends.setdefault(key(p), []).append(n)
        ends.setdefault(key(q), []).append(n)
    used, lines = set(), []
    for n in range(len(segs)):
        if n in used:
            continue
        used.add(n)
        line = [segs[n][0], segs[n][1]]
        for forward in (True, False):
            while True:
                tip = line[-1] if forward else line[0]
                nxt = [m for m in ends.get(key(tip), []) if m not in used]
                if not nxt:
                    break
                m = nxt[0]
                used.add(m)
                p, q = segs[m]
                other = q if key(p) == key(tip) else p
                if forward:
                    line.append(other)
                else:
                    line.insert(0, other)
        if len(line) > 3:
            lines.append(line)
    return lines


def path(line, closed=False):
    pts = line[::2] + ([line[-1]] if len(line) % 2 == 0 else [])   # прореживание: вдвое меньше точек
    d = 'M' + ' '.join(f'{x:.0f} {y:.0f}' for x, y in pts[:1]) + 'L' + ' '.join(f'{x:.0f} {y:.0f}' for x, y in pts[1:])
    return d


def build(width, height, hills, waves, step, interval, colors, zoom=1.0, labels=True, grid=True, river=None, road=None):
    h = field(hills, waves, zoom)
    values = [h(x, y) for x in range(0, width, 40) for y in range(0, height, 40)]
    lo, hi = min(values), max(values)
    first = math.ceil(lo / interval) * interval
    levels = [first + k * interval for k in range(int((hi - first) / interval) + 1)]
    lines = contours(h, width, height, step, levels)
    stroke, index_stroke, text_fill, grid_stroke, water, road_stroke = colors
    out = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}' "
           "preserveAspectRatio='xMidYMid slice'>"]
    if grid:   # километровая сетка
        out.append(f"<g stroke='{grid_stroke}' stroke-width='1'>")
        for x in range(0, width + 1, 200):
            out.append(f"<line x1='{x}' y1='0' x2='{x}' y2='{height}'/>")
        for y in range(0, height + 1, 200):
            out.append(f"<line x1='0' y1='{y}' x2='{width}' y2='{y}'/>")
        out.append('</g>')
        out.append(f"<g fill='{text_fill}' font-family='IBM Plex Mono,monospace' font-size='10'>")
        for k, x in enumerate(range(200, width, 200)):
            out.append(f"<text x='{x + 4}' y='14'>{44 + k}</text>")
        for k, y in enumerate(range(200, height, 200)):
            out.append(f"<text x='4' y='{y - 4}'>{63 - k}</text>")
        out.append('</g>')
    out.append(f"<g fill='none' stroke-linejoin='round' stroke-linecap='round'>")
    label_spots = []
    for n, level in enumerate(levels):
        is_index = round(level / interval) % 5 == 0
        for line in lines[level]:
            out.append(f"<path d='{path(line)}' stroke='{index_stroke if is_index else stroke}' "
                       f"stroke-width='{1.0 if is_index else 0.6}'/>")
            if is_index and labels and len(line) > 60:
                mid = line[len(line) // 2]
                if all(abs(mid[0] - x) + abs(mid[1] - y) > 260 for x, y, _ in label_spots):
                    label_spots.append((mid[0], mid[1], level))
    out.append('</g>')
    if river:
        out.append(f"<path d='{river}' fill='none' stroke='{water}' stroke-width='2.2' stroke-linecap='round'/>")
    if road:
        out.append(f"<path d='{road}' fill='none' stroke='{road_stroke}' stroke-width='1.3' stroke-dasharray='7 5'/>")
    if labels:
        out.append(f"<g fill='{text_fill}' font-family='IBM Plex Mono,monospace' font-size='9' text-anchor='middle'>")
        for x, y, level in label_spots:
            out.append(f"<text x='{x:.0f}' y='{y + 3:.0f}' paint-order='stroke' stroke='#F3F5F6' stroke-width='3'>"
                       f"{int(200 + level * 2)}</text>")
        out.append('</g>')
    out.append('</svg>')
    return ''.join(out)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    page = build(
        1600, 1000,
        hills=[(260, 230, 60, 230, 170), (760, 640, 75, 260, 210), (1330, 260, 55, 210, 160), (1180, 820, 40, 200, 140),
               (560, 120, 30, 160, 110), (90, 820, 35, 180, 150), (1500, 620, 28, 150, 170), (980, 330, -30, 180, 120)],
        waves=[(0.004, 0.003, 0.7, 6), (0.0025, -0.005, 1.9, 5), (0.009, 0.006, 2.6, 2.2)],
        step=8, interval=10, zoom=1.4,
        colors=('rgba(18,52,56,.075)', 'rgba(18,52,56,.14)', 'rgba(18,52,56,.30)', 'rgba(18,52,56,.05)',
                'rgba(63,138,150,.30)', 'rgba(18,52,56,.16)'),
        river='M -20 560 C 160 520 300 600 430 540 S 640 420 820 470 S 1060 600 1220 540 S 1450 430 1620 470',
        road='M 120 -20 C 180 200 320 330 430 420 S 640 760 720 1020',
    )
    (OUT / 'map-page.svg').write_text(page)
    side = build(
        320, 1000,
        hills=[(120, 180, 50, 140, 120), (230, 560, 60, 160, 170), (60, 860, 40, 130, 120)],
        waves=[(0.012, 0.004, 0.3, 4), (0.006, -0.009, 2.1, 3)],
        step=6, interval=10, zoom=1.4,
        colors=('rgba(255,255,255,.055)', 'rgba(255,255,255,.10)', 'rgba(255,255,255,.18)', 'rgba(255,255,255,.035)',
                'rgba(159,208,208,.22)', 'rgba(255,255,255,.10)'),
        labels=False, grid=False,
        river='M -10 720 C 80 690 140 760 210 730 S 300 650 340 670',
    )
    (OUT / 'map-sidebar.svg').write_text(side)
    for name in ('map-page.svg', 'map-sidebar.svg'):
        print(name, (OUT / name).stat().st_size // 1024, 'КБ')


if __name__ == '__main__':
    main()
