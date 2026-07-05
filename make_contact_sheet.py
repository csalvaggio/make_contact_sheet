#!/usr/bin/env python3

from dataclasses import dataclass
from pathlib import Path
import argparse
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

import rawpy


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf",
            ".orf", ".rw2", ".pef", ".srw"}

SUPPORTED_EXTS = IMAGE_EXTS | RAW_EXTS


@dataclass(frozen=True)
class Film35mmGeometry:
    film_height_mm: float = 35.0
    strip_length_mm: float = 240.0

    frame_w_mm: float = 36.0
    frame_h_mm: float = 24.0
    frame_pitch_mm: float = 38.0
    frame_start_x_mm: float = 8.0

    perf_pitch_mm: float = 4.75
    perf_w_mm: float = 2.8
    perf_h_mm: float = 1.98
    perf_center_y_top_mm: float = 2.35

    strips_per_sheet: int = 6
    frames_per_strip: int = 6

    @property
    def perf_center_y_bottom_mm(self) -> float:
        return self.film_height_mm - self.perf_center_y_top_mm

    @property
    def frames_per_sheet(self) -> int:
        return self.strips_per_sheet * self.frames_per_strip


@dataclass(frozen=True)
class ContactSheetTheme:
    background_start: int = 3
    background_end: int = 10

    film_base_fill: tuple[int, int, int] = (24, 18, 10)
    film_base_outline: tuple[int, int, int] = (78, 62, 36)

    sprocket_fill: tuple[int, int, int] = (2, 2, 2)
    sprocket_outline: tuple[int, int, int] = (62, 54, 42)

    frame_opening_fill: tuple[int, int, int] = (1, 1, 1)

    edge_text: tuple[int, int, int] = (232, 180, 82)
    error_text: tuple[int, int, int] = (220, 120, 90)


@dataclass(frozen=True)
class RenderOptions:
    image_directory: Path
    output_dir: Path
    output_width: int | None
    dpi: int
    negative: bool
    contact_blur: bool
    rotate_portrait_ccw: bool
    prefix: str
    film_name: str


@dataclass(frozen=True)
class SheetLayout:
    sheet_w: int
    sheet_h: int
    ppm: float
    strip_w: int
    strip_h: int
    strip_gap: int
    start_x: int
    start_y: int


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "DejaVuSansMono-Bold.ttf" if bold else "DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]

    for font in candidates:
        try:
            return ImageFont.truetype(font, size)
        except Exception:
            pass

    return ImageFont.load_default()


def compute_layout(options: RenderOptions, geometry: Film35mmGeometry) -> SheetLayout:
    sheet_w = options.output_width if options.output_width else int(options.dpi * 8)
    sheet_h = int(sheet_w * 10 / 8)

    margin_x = int(sheet_w * 0.055)
    margin_y = int(sheet_h * 0.055)

    usable_w = sheet_w - 2 * margin_x
    usable_h = sheet_h - 2 * margin_y

    desired_strip_gap = int(sheet_h * 0.018)

    ppm_from_width = usable_w / geometry.strip_length_mm
    ppm_from_height = (
        usable_h - desired_strip_gap * (geometry.strips_per_sheet - 1)
    ) / (geometry.strips_per_sheet * geometry.film_height_mm)

    ppm = min(ppm_from_width, ppm_from_height)

    strip_w = int(geometry.strip_length_mm * ppm)
    strip_h = int(geometry.film_height_mm * ppm)
    strip_gap = desired_strip_gap

    stack_h = (
        geometry.strips_per_sheet * strip_h
        + (geometry.strips_per_sheet - 1) * strip_gap
    )

    start_x = (sheet_w - strip_w) // 2
    start_y = (sheet_h - stack_h) // 2

    return SheetLayout(
        sheet_w=sheet_w,
        sheet_h=sheet_h,
        ppm=ppm,
        strip_w=strip_w,
        strip_h=strip_h,
        strip_gap=strip_gap,
        start_x=start_x,
        start_y=start_y,
    )


def read_image(path: Path, options: RenderOptions) -> Image.Image:
    ext = path.suffix.lower()

    if ext in RAW_EXTS:
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(
                use_camera_wb=True,
                no_auto_bright=False,
                gamma=(2.222, 4.5),      # power, toe slope
                output_bps=8
            )
        img = Image.fromarray(rgb, mode="RGB")
    else:
        img = Image.open(path)
        img = ImageOps.exif_transpose(img).convert("RGB")

    if options.rotate_portrait_ccw and img.height > img.width:
        img = img.rotate(90, expand=True)

    if options.negative:
        img = ImageOps.invert(img)

    return img


def fit_image_contain(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.contain(img, size, method=Image.Resampling.LANCZOS)


def draw_background(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    theme: ContactSheetTheme,
) -> None:
    for y in range(height):
        v = int(theme.background_start + (theme.background_end - theme.background_start) * y / height)
        draw.line([(0, y), (width, y)], fill=(v, v, v))


def mm_rect(
    x_mm: float,
    y_mm: float,
    w_mm: float,
    h_mm: float,
    x0: int,
    y0: int,
    ppm: float,
) -> list[int]:
    return [
        int(x0 + x_mm * ppm),
        int(y0 + y_mm * ppm),
        int(x0 + (x_mm + w_mm) * ppm),
        int(y0 + (y_mm + h_mm) * ppm),
    ]


def draw_film_base(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    ppm: float,
    geometry: Film35mmGeometry,
    theme: ContactSheetTheme,
) -> None:
    w = int(geometry.strip_length_mm * ppm)
    h = int(geometry.film_height_mm * ppm)

    draw.rounded_rectangle(
        [x, y, x + w, y + h],
        radius=max(4, int(1.2 * ppm)),
        fill=theme.film_base_fill,
        outline=theme.film_base_outline,
        width=max(1, int(0.18 * ppm)),
    )

    highlight_h = max(1, int(2.5 * ppm))
    for i in range(highlight_h):
        a = int(12 * (1 - i / highlight_h))
        draw.line(
            [(x + 2, y + i), (x + w - 2, y + i)],
            fill=(
                theme.film_base_fill[0] + a,
                theme.film_base_fill[1] + a // 2,
                theme.film_base_fill[2],
            ),
        )


def draw_sprockets(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    ppm: float,
    geometry: Film35mmGeometry,
    theme: ContactSheetTheme,
) -> None:
    first_perf_x = 3.0
    count = int((geometry.strip_length_mm - 6.0) / geometry.perf_pitch_mm)

    for i in range(count):
        cx_mm = first_perf_x + i * geometry.perf_pitch_mm

        for cy_mm in (
            geometry.perf_center_y_top_mm,
            geometry.perf_center_y_bottom_mm,
        ):
            box = mm_rect(
                cx_mm - geometry.perf_w_mm / 2,
                cy_mm - geometry.perf_h_mm / 2,
                geometry.perf_w_mm,
                geometry.perf_h_mm,
                x,
                y,
                ppm,
            )

            draw.rounded_rectangle(
                box,
                radius=max(1, int(0.25 * ppm)),
                fill=theme.sprocket_fill,
                outline=theme.sprocket_outline,
                width=1,
            )


def draw_frame_opening(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    ppm: float,
    frame_x_mm: float,
    geometry: Film35mmGeometry,
    theme: ContactSheetTheme,
) -> list[int]:
    frame_y_mm = (geometry.film_height_mm - geometry.frame_h_mm) / 2

    box = mm_rect(
        frame_x_mm,
        frame_y_mm,
        geometry.frame_w_mm,
        geometry.frame_h_mm,
        x,
        y,
        ppm,
    )

    draw.rounded_rectangle(
        [box[0] - 2, box[1] - 2, box[2] + 2, box[3] + 2],
        radius=max(2, int(0.5 * ppm)),
        fill=theme.frame_opening_fill,
    )

    return box


def draw_text_centered(
    draw: ImageDraw.ImageDraw,
    center_x: int,
    y: int,
    text: str,
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int],
) -> None:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text((center_x - text_w // 2, y), text, fill=fill, font=font)


def draw_edge_markings(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    ppm: float,
    frame_numbers: Sequence[int],
    options: RenderOptions,
    geometry: Film35mmGeometry,
    theme: ContactSheetTheme,
) -> None:
    edge_font = load_font(max(8, int(0.78 * ppm)), bold=True)
    num_font = load_font(max(8, int(0.78 * ppm)), bold=True)

    top_label_y = y + int(3.85 * ppm)
    bottom_margin_y = y + int(30.10 * ppm)

    for tx_mm in (10, 86, 162):
        draw.text(
            (x + int(tx_mm * ppm), top_label_y),
            options.film_name,
            fill=theme.edge_text,
            font=edge_font,
        )

    for tx_mm in (10, 86, 162):
        draw.text(
            (x + int(tx_mm * ppm), bottom_margin_y),
            "SAFETY FILM",
            fill=theme.edge_text,
            font=edge_font,
        )

    for i, n in enumerate(frame_numbers):
        frame_x_mm = geometry.frame_start_x_mm + i * geometry.frame_pitch_mm
        center_x = x + int((frame_x_mm + geometry.frame_w_mm / 2) * ppm)

        draw_text_centered(
            draw,
            center_x,
            bottom_margin_y,
            f"{n}A",
            num_font,
            theme.edge_text,
        )


def draw_image_frame(
    sheet: Image.Image,
    draw: ImageDraw.ImageDraw,
    image_path: Path,
    frame_box: list[int],
    options: RenderOptions,
    error_font: ImageFont.ImageFont,
    theme: ContactSheetTheme,
) -> None:
    try:
        img = read_image(image_path, options)

        frame_w = frame_box[2] - frame_box[0]
        frame_h = frame_box[3] - frame_box[1]

        img = fit_image_contain(img, (frame_w, frame_h))

        if options.contact_blur:
            img = img.filter(ImageFilter.GaussianBlur(radius=0.35))

        paste_x = frame_box[0] + (frame_w - img.width) // 2
        paste_y = frame_box[1] + (frame_h - img.height) // 2

        sheet.paste(img, (paste_x, paste_y))

    except Exception:
        draw.text(
            (frame_box[0] + 8, frame_box[1] + 8),
            "LOAD ERROR",
            fill=theme.error_text,
            font=error_font,
        )


def draw_strip(
    sheet: Image.Image,
    draw: ImageDraw.ImageDraw,
    image_paths: Sequence[Path],
    strip_idx: int,
    sheet_number: int,
    layout: SheetLayout,
    options: RenderOptions,
    geometry: Film35mmGeometry,
    theme: ContactSheetTheme,
    error_font: ImageFont.ImageFont,
) -> tuple[int, int, list[int]]:
    ppm = layout.ppm

    strip_x = layout.start_x + int((strip_idx % 3 - 1) * 0.35 * ppm)
    strip_y = layout.start_y + strip_idx * (layout.strip_h + layout.strip_gap)

    first_frame_number = (
        (sheet_number - 1) * geometry.frames_per_sheet
        + strip_idx * geometry.frames_per_strip
        + 1
    )

    frame_numbers = [
        first_frame_number + i
        for i in range(geometry.frames_per_strip)
    ]

    draw_film_base(draw, strip_x, strip_y, ppm, geometry, theme)
    draw_sprockets(draw, strip_x, strip_y, ppm, geometry, theme)

    for frame_idx in range(geometry.frames_per_strip):
        img_idx = strip_idx * geometry.frames_per_strip + frame_idx
        frame_x_mm = geometry.frame_start_x_mm + frame_idx * geometry.frame_pitch_mm

        frame_box = draw_frame_opening(
            draw,
            strip_x,
            strip_y,
            ppm,
            frame_x_mm,
            geometry,
            theme,
        )

        if img_idx < len(image_paths):
            draw_image_frame(
                sheet,
                draw,
                image_paths[img_idx],
                frame_box,
                options,
                error_font,
                theme,
            )

    return strip_x, strip_y, frame_numbers


def make_sheet(
    image_paths: Sequence[Path],
    output_path: Path,
    sheet_number: int,
    options: RenderOptions,
    geometry: Film35mmGeometry,
    theme: ContactSheetTheme,
) -> None:
    layout = compute_layout(options, geometry)

    sheet = Image.new("RGB", (layout.sheet_w, layout.sheet_h), (0, 0, 0))
    draw = ImageDraw.Draw(sheet)

    draw_background(draw, layout.sheet_w, layout.sheet_h, theme)

    error_font = load_font(max(7, int(0.65 * layout.ppm)))

    strip_data = []

    for strip_idx in range(geometry.strips_per_sheet):
        strip_data.append(
            draw_strip(
                sheet,
                draw,
                image_paths,
                strip_idx,
                sheet_number,
                layout,
                options,
                geometry,
                theme,
                error_font,
            )
        )

    for strip_x, strip_y, frame_numbers in strip_data:
        draw_edge_markings(
            draw,
            strip_x,
            strip_y,
            layout.ppm,
            frame_numbers,
            options,
            geometry,
            theme,
        )

    sheet.save(output_path, quality=95)


def collect_images(image_dir: Path) -> list[Path]:
    return sorted(
        p
        for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create realistic 35mm photographic contact sheets"
    )

    parser.add_argument("image_directory", help="directory containing source images")

    size_group = parser.add_mutually_exclusive_group()

    size_group.add_argument(
        "--output-width",
        type=int,
        metavar="PIXELS",
        help="width of the output image in pixels",
    )

    size_group.add_argument(
        "--dpi",
        type=int,
        help="contact sheet DPI [default is 1200]",
    )

    parser.add_argument(
        "--negative",
        action="store_true",
        help="render the images as photographic negatives",
    )

    parser.add_argument(
        "--contact-blur",
        action="store_true",
        help="apply a subtle blur to simulate a traditional contact print",
    )

    parser.add_argument(
        "--rotate-portrait-ccw",
        action="store_true",
        help="rotate portrait-oriented source images 90 degrees CCW",
    )

    parser.add_argument(
        "--film-name",
        default="KODAK SAFETY FILM 5035",
        help="film-edge name to print along the top sprocket margin/lane",
    )

    parser.add_argument(
        "--output-dir",
        default=".",
        help="directory where contact sheets will be written [default is the current directory]",
    )

    parser.add_argument(
        "--prefix",
        default="contact_sheet",
        help="output filename prefix [default is 'contact_sheet']",
    )

    return parser.parse_args()


def make_options(args: argparse.Namespace) -> RenderOptions:
    image_dir = Path(args.image_directory).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()

    dpi = args.dpi
    if args.output_width is None and dpi is None:
        dpi = 1200

    if args.output_width is not None and args.output_width <= 0:
        raise SystemExit("--output-width must be greater than 0")

    if dpi is not None and dpi <= 0:
        raise SystemExit("--dpi must be greater than 0")

    return RenderOptions(
        image_directory=image_dir,
        output_dir=output_dir,
        output_width=args.output_width,
        dpi=dpi,
        negative=args.negative,
        contact_blur=args.contact_blur,
        rotate_portrait_ccw=args.rotate_portrait_ccw,
        prefix=args.prefix,
        film_name=args.film_name,
    )


def main() -> None:
    args = parse_args()
    options = make_options(args)

    if not options.image_directory.is_dir():
        raise SystemExit(f"Not a directory: {options.image_directory}")

    options.output_dir.mkdir(parents=True, exist_ok=True)

    images = collect_images(options.image_directory)

    if not images:
        raise SystemExit(f"No images found in {options.image_directory}")

    geometry = Film35mmGeometry()
    theme = ContactSheetTheme()

    batches = [
        images[i:i + geometry.frames_per_sheet]
        for i in range(0, len(images), geometry.frames_per_sheet)
    ]

    for sheet_number, batch in enumerate(batches, start=1):
        output_path = options.output_dir / f"{options.prefix}_{sheet_number:03d}.png"
        make_sheet(batch, output_path, sheet_number, options, geometry, theme)
        print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
