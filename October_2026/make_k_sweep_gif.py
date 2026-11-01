"""K-sweep animation: run the stage-1 CP-SAT for a list of K values and build
a GIF whose frames are the real solver solutions."""

import colorsys
import math
import os
import time

from PIL import Image, ImageDraw, ImageFont

from stage1 import PUZZLE_11X11_CLUES, Stage1Config, solve
import validate_stage1

N = 11
CELL = 46
MARGIN = 20
TITLE = 30

KS = [int(x) for x in os.environ.get(
    "KS", "4,5,6,7,8,9,10,11,12,13,14").split(",")]
PER = float(os.environ.get("PER_TIME", "400"))


def font(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def star(draw, cx, cy, r, fill):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=fill, outline="black")


def make_frame(sol, K, status):
    states = [(frozenset(cells), cap) for cells, cap in sol.states]
    big = set(sol.big)
    big_caps = set(sol.big_capitols)

    palette = []
    for i in range(len(states)):
        h = i / max(1, len(states))
        r, g, b = colorsys.hsv_to_rgb(h, 0.42, 0.98)
        palette.append((int(r * 255), int(g * 255), int(b * 255)))

    cell_color = {}
    cell_label = {}
    cap_cell = set()
    for i, (cells, cap) in enumerate(states):
        label = chr(65 + i) if i < 26 else "?"
        for c in cells:
            cell_color[c] = palette[i]
            cell_label[c] = label
        if cap is not None:
            cap_cell.add(cap)

    W = MARGIN * 2 + N * CELL
    H = TITLE + MARGIN * 2 + N * CELL
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    f_title = font(15)
    f_label = font(14)
    f_clue = font(10)

    draw.text(
        (MARGIN, 6),
        f"K = {K}   ({status})   {len(states)} small states, "
        f"{len(big)} BIG cells",
        font=f_title, fill=(0, 0, 0))

    x0, y0 = MARGIN, TITLE
    for r in range(N):
        for c in range(N):
            cell = (r, c)
            x = x0 + c * CELL
            y = y0 + r * CELL
            if cell in big_caps:
                fill = (255, 204, 0)
            elif cell in big:
                fill = (208, 208, 208)
            else:
                fill = cell_color.get(cell, (255, 255, 255))
            draw.rectangle([x, y, x + CELL, y + CELL], fill=fill,
                           outline=(90, 90, 90))

            if cell in PUZZLE_11X11_CLUES:
                draw.text((x + 3, y + 2), str(PUZZLE_11X11_CLUES[cell]),
                          font=f_clue, fill=(20, 20, 20))

            if cell in cell_label:
                lab = cell_label[cell]
                bbox = draw.textbbox((0, 0), lab, font=f_label)
                tw = bbox[2] - bbox[0]
                th = bbox[3] - bbox[1]
                draw.text((x + (CELL - tw) / 2, y + (CELL - th) / 2 + 2),
                          lab, font=f_label, fill=(0, 0, 0))

            if cell in cap_cell:
                star(draw, x + CELL - 10, y + CELL - 10, 6, (0, 0, 0))
            if cell in big_caps:
                star(draw, x + CELL - 10, y + CELL - 10, 6, (200, 0, 0))

    return img


def main():
    frames = []
    log = []
    for K in KS:
        cfg = Stage1Config(
            n=N, clues=PUZZLE_11X11_CLUES, K=K,
            time_limit=PER,
            workers=16,
            big_min=K + 1,
            max_big_caps=1,
            big_connected_min=True,
            manhattan_ring=True,
            seed=1,
        )
        res = solve(cfg, verbose=False)
        print(f"K={K}: status={res.status} wall={res.wall:.1f}s "
              f"placements={res.placements_used}", flush=True)
        log.append((K, res.status, round(res.wall, 1)))
        if res.solution is None:
            continue
        rep = validate_stage1.validate_stage1(
            res.solution, PUZZLE_11X11_CLUES, K)
        if not rep.ok:
            print(f"  K={K}: validator failed", flush=True)
            continue
        frames.append(make_frame(res.solution, K, res.status))
        print(f"  K={K}: frame {len(frames)}", flush=True)

    if not frames:
        print("no frames")
        return
    out = os.path.join("..", "..", "k_sweep.gif")
    frames[0].save(out, save_all=True, append_images=frames[1:],
                   duration=900, loop=0)
    print("wrote", os.path.abspath(out), len(frames), "frames")
    print("log:", log)


if __name__ == "__main__":
    main()
