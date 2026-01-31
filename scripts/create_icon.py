"""
Generate a compass rose icon for the Worldbuilding Interactive Program.
Creates icon.ico (multi-resolution) and icon.png (256x256).
"""
import math
from PIL import Image, ImageDraw, ImageFont

def draw_compass_rose(size=512):
    """Draw a detailed compass rose at the given size, then scale down."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size / 2, size / 2
    r = size * 0.46  # outer radius

    # Background circle with slight parchment tone
    bg_r = size * 0.48
    draw.ellipse(
        [cx - bg_r, cy - bg_r, cx + bg_r, cy + bg_r],
        fill=(245, 235, 220, 255),
        outline=(80, 60, 30, 255),
        width=max(1, size // 128),
    )

    # Outer ring
    ring_r = size * 0.44
    draw.ellipse(
        [cx - ring_r, cy - ring_r, cx + ring_r, cy + ring_r],
        fill=None,
        outline=(80, 60, 30, 200),
        width=max(1, size // 200),
    )

    # --- Draw the 8 secondary (intercardinal) points first (behind the main 4) ---
    intercardinal_len = r * 0.55
    intercardinal_half_w = r * 0.07
    for angle_deg in [45, 135, 225, 315]:
        angle = math.radians(angle_deg - 90)  # -90 so 0 deg = North
        tip_x = cx + intercardinal_len * math.cos(angle)
        tip_y = cy + intercardinal_len * math.sin(angle)

        perp = angle + math.pi / 2
        base_offset = intercardinal_half_w

        bx1 = cx + base_offset * math.cos(perp)
        by1 = cy + base_offset * math.sin(perp)
        bx2 = cx - base_offset * math.cos(perp)
        by2 = cy - base_offset * math.sin(perp)

        # Light half
        draw.polygon(
            [(tip_x, tip_y), (bx1, by1), (cx, cy)],
            fill=(180, 160, 120, 255),
            outline=(80, 60, 30, 255),
        )
        # Dark half
        draw.polygon(
            [(tip_x, tip_y), (bx2, by2), (cx, cy)],
            fill=(120, 90, 50, 255),
            outline=(80, 60, 30, 255),
        )

    # --- Draw the 4 cardinal points (N, E, S, W) ---
    cardinal_len = r * 0.92
    cardinal_half_w = r * 0.12
    colors_light = [
        (200, 50, 50, 255),   # N - red
        (220, 200, 140, 255), # E - gold-ish
        (220, 200, 140, 255), # S - gold-ish
        (220, 200, 140, 255), # W - gold-ish
    ]
    colors_dark = [
        (140, 30, 30, 255),   # N - dark red
        (160, 140, 80, 255),  # E
        (160, 140, 80, 255),  # S
        (160, 140, 80, 255),  # W
    ]

    for i, angle_deg in enumerate([0, 90, 180, 270]):
        angle = math.radians(angle_deg - 90)
        tip_x = cx + cardinal_len * math.cos(angle)
        tip_y = cy + cardinal_len * math.sin(angle)

        perp = angle + math.pi / 2
        base_offset = cardinal_half_w

        bx1 = cx + base_offset * math.cos(perp)
        by1 = cy + base_offset * math.sin(perp)
        bx2 = cx - base_offset * math.cos(perp)
        by2 = cy - base_offset * math.sin(perp)

        # Light half
        draw.polygon(
            [(tip_x, tip_y), (bx1, by1), (cx, cy)],
            fill=colors_light[i],
            outline=(80, 60, 30, 255),
        )
        # Dark half
        draw.polygon(
            [(tip_x, tip_y), (bx2, by2), (cx, cy)],
            fill=colors_dark[i],
            outline=(80, 60, 30, 255),
        )

    # Center circle
    center_r = r * 0.08
    draw.ellipse(
        [cx - center_r, cy - center_r, cx + center_r, cy + center_r],
        fill=(80, 60, 30, 255),
        outline=(40, 30, 15, 255),
        width=max(1, size // 256),
    )
    inner_r = center_r * 0.55
    draw.ellipse(
        [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
        fill=(200, 180, 140, 255),
    )

    # Cardinal letters
    font_size = int(size * 0.07)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()

    letter_r = r * 0.78
    letters = [("N", 0), ("E", 90), ("S", 180), ("W", 270)]
    for letter, angle_deg in letters:
        angle = math.radians(angle_deg - 90)
        lx = cx + letter_r * math.cos(angle)
        ly = cy + letter_r * math.sin(angle)
        bbox = font.getbbox(letter)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        draw.text(
            (lx - tw / 2, ly - th / 2 - bbox[1]),
            letter,
            fill=(60, 40, 20, 255),
            font=font,
        )

    return img


def main():
    import os
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "app", "resources")
    os.makedirs(out_dir, exist_ok=True)

    # Render at high resolution then scale down for quality
    base = draw_compass_rose(1024)

    # Create the target sizes
    sizes = [256, 128, 64, 48, 32, 16]
    images = []
    for s in sizes:
        resized = base.resize((s, s), Image.LANCZOS)
        images.append(resized)

    # Save 256x256 PNG
    png_path = os.path.join(out_dir, "icon.png")
    images[0].save(png_path, "PNG")
    print(f"Saved {png_path}  ({os.path.getsize(png_path)} bytes)")

    # Save multi-resolution ICO
    ico_path = os.path.join(out_dir, "icon.ico")
    # Pillow's ICO save: pass the largest image and provide the sizes
    images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[1:],
    )
    print(f"Saved {ico_path}  ({os.path.getsize(ico_path)} bytes)")

    # Clean up the broken SVG download if it exists and is tiny
    svg_path = os.path.join(out_dir, "compass_rose.svg")
    if os.path.exists(svg_path) and os.path.getsize(svg_path) < 500:
        os.remove(svg_path)
        print(f"Removed invalid SVG placeholder: {svg_path}")


if __name__ == "__main__":
    main()
