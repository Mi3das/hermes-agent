#!/usr/bin/env python3
"""Generate the HERMES HQ app icon as a 1024x1024 PNG.

Motif: a glowing central "HQ" hub with orbiting subagent nodes connected by
spokes -- the multi-agent command-center identity, matching the dashboard.
"""
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont, ImageFilter

S = 1024
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# --- rounded-rect background with vertical gradient (dark navy) ---
bg = Image.new("RGBA", (S, S), (0, 0, 0, 0))
bgd = ImageDraw.Draw(bg)
top = (12, 20, 40)
bot = (6, 10, 22)
for y in range(S):
    t = y / S
    r = int(top[0] * (1 - t) + bot[0] * t)
    g = int(top[1] * (1 - t) + bot[1] * t)
    b = int(top[2] * (1 - t) + bot[2] * t)
    bgd.line([(0, y), (S, y)], fill=(r, g, b, 255))
# mask to a rounded square (macOS-style squircle-ish)
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([0, 0, S, S], radius=220, fill=255)
img.paste(bg, (0, 0), mask)
d = ImageDraw.Draw(img)

cx, cy = S / 2, S / 2 + 10
ACCENT = (54, 224, 200)      # teal
ACCENT2 = (91, 140, 255)     # blue
RUN = (255, 206, 84)         # amber

# --- spokes + orbiting nodes ---
orbit = 300
nodes = []
for i in range(6):
    a = math.radians(-90 + i * 60 + 12)
    nx = cx + math.cos(a) * orbit
    ny = cy + math.sin(a) * orbit
    nodes.append((nx, ny, i))

# glow layer for spokes/nodes (drawn on separate image then blurred)
glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
gd = ImageDraw.Draw(glow)
for nx, ny, i in nodes:
    gd.line([(cx, cy), (nx, ny)], fill=(*ACCENT, 120), width=10)
glow = glow.filter(ImageFilter.GaussianBlur(14))
img.alpha_composite(glow)

# crisp spokes
for nx, ny, i in nodes:
    d.line([(cx, cy), (nx, ny)], fill=(*ACCENT2, 150), width=7)

# subagent nodes
node_colors = [ACCENT, RUN, ACCENT, ACCENT2, RUN, ACCENT]
for (nx, ny, i) in nodes:
    c = node_colors[i % len(node_colors)]
    r = 62
    # outer glow ring
    d.ellipse([nx - r - 14, ny - r - 14, nx + r + 14, ny + r + 14], outline=(*c, 90), width=8)
    d.ellipse([nx - r, ny - r, nx + r, ny + r], fill=(16, 26, 46, 255), outline=(*c, 255), width=8)
    d.ellipse([nx - 20, ny - 20, nx + 20, ny + 20], fill=(*c, 255))

# --- central HQ hub ---
R = 188
# big soft glow under the hub
hubglow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
ImageDraw.Draw(hubglow).ellipse(
    [cx - R - 30, cy - R - 30, cx + R + 30, cy + R + 30], fill=(*ACCENT, 110)
)
hubglow = hubglow.filter(ImageFilter.GaussianBlur(40))
img.alpha_composite(hubglow)
d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(10, 61, 58, 255), outline=(*ACCENT, 255), width=12)
d.ellipse([cx - R + 26, cy - R + 26, cx + R - 26, cy + R - 26], outline=(*ACCENT, 120), width=4)

# --- "HQ" text ---
def load_font(size):
    for path in (
        "/System/Library/Fonts/SFNSRounded.ttf",
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()

font = load_font(170)
txt = "HQ"
bbox = d.textbbox((0, 0), txt, font=font)
tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
d.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), txt, font=font, fill=(225, 255, 250, 255))

out = sys.argv[1] if len(sys.argv) > 1 else "icon.png"
img.save(out)
print("wrote", out)
