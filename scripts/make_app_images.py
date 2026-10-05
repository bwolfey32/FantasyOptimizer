"""Build the installed-app images from assets/icon-512.png: the maskable icon Android crops to a circle or squircle, and
the iPhone launch screens (apple-touch-startup-image). Rerun after changing the icon.

Usage: python3 scripts/make_app_images.py        (needs Pillow: pip install pillow)

assets/icon-maskable-512.png   the icon's inner green panel on a full-bleed field of the same green, scaled so the BP
                               letters sit inside the central 80% circle every launcher keeps
assets/splash/splash-WxH.png   brand green (#075b37, the manifest's background) with the icon centered, one per current
                               iPhone screen in portrait; SPLASH below lists them and index.html links each one
"""
import os
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
ICON = os.path.join(ROOT, "assets", "icon-512.png")
PANEL_GREEN = (2, 78, 48)          # the icon's own green, inside its gold frame
BRAND_GREEN = (7, 91, 55)          # #075b37: theme_color and background_color in the manifest
# [CSS width, CSS height, device pixel ratio, phones] in portrait
SPLASH = [
    (440, 956, 3, "iPhone 17 Pro Max, 16 Pro Max"),
    (402, 874, 3, "iPhone 17, 17 Pro, 16 Pro"),
    (420, 912, 3, "iPhone Air"),
    (430, 932, 3, "iPhone 16 Plus, 15 Plus, 15 Pro Max, 14 Pro Max"),
    (393, 852, 3, "iPhone 16, 15, 15 Pro, 14 Pro"),
    (390, 844, 3, "iPhone 16e, 14, 13, 13 Pro, 12, 12 Pro"),
    (428, 926, 3, "iPhone 14 Plus, 13 Pro Max, 12 Pro Max"),
    (375, 812, 3, "iPhone 13 mini, 12 mini, 11 Pro, XS, X"),
    (414, 896, 3, "iPhone 11 Pro Max, XS Max"),
    (414, 896, 2, "iPhone 11, XR"),
    (414, 736, 3, "iPhone 8 Plus"),
    (375, 667, 2, "iPhone SE (2nd and 3rd gen), 8"),
]


def maskable(icon):
    # the panel inside the gold frame (the frame ends about 26px in), with soft rounded edges so it melts into the field
    box = (28, 28, 484, 484)
    panel = icon.crop(box)
    mask = Image.new("L", panel.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((6, 6, panel.size[0] - 7, panel.size[1] - 7), radius=90, fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(5))
    # letters span about 431 x 243 px; their diagonal must fit the 80% safe circle (410px), with a little room
    scale = 400 / (431 ** 2 + 243 ** 2) ** 0.5
    size = round(panel.size[0] * scale)
    panel, mask = panel.resize((size, size), Image.LANCZOS), mask.resize((size, size), Image.LANCZOS)
    out = Image.new("RGB", (512, 512), PANEL_GREEN)
    out.paste(panel.convert("RGB"), ((512 - size) // 2, (512 - size) // 2), mask)
    return out


def splash(icon, w, h):
    out = Image.new("RGB", (w, h), BRAND_GREEN)
    side = round(w * 0.38)
    logo = icon.resize((side, side), Image.LANCZOS)
    out.paste(logo, ((w - side) // 2, round(h * 0.44 - side / 2)), logo)
    return out


def main():
    icon = Image.open(ICON).convert("RGBA")
    maskable(icon).save(os.path.join(ROOT, "assets", "icon-maskable-512.png"), optimize=True)
    os.makedirs(os.path.join(ROOT, "assets", "splash"), exist_ok=True)
    for cw, ch, dpr, _ in SPLASH:
        w, h = cw * dpr, ch * dpr
        # 256 colors keeps each file small; the icon is flat enough that it doesn't show
        splash(icon, w, h).quantize(256, dither=Image.Dither.NONE).save(os.path.join(ROOT, "assets", "splash", f"splash-{w}x{h}.png"), optimize=True)
    for cw, ch, dpr, phones in SPLASH:
        w, h = cw * dpr, ch * dpr
        print(f'<link rel="apple-touch-startup-image" href="assets/splash/splash-{w}x{h}.png" media="(device-width: {cw}px) and (device-height: {ch}px) and (-webkit-device-pixel-ratio: {dpr}) and (orientation: portrait)">')


if __name__ == "__main__":
    main()
