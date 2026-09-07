#!/usr/bin/env python3

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import argparse
from typing import Sequence
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFilter

import rawpy


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}

RAW_EXTS = {".cr2", ".cr3", ".nef", ".arw", ".dng", ".raf",
            ".orf", ".rw2", ".pef", ".srw"}

SUPPORTED_EXTS = IMAGE_EXTS | RAW_EXTS

HEADSHOT_XMP_NAMESPACE = "https://www.rit.edu/ns/headshot-kiosk/1.0/"
RDF_NAMESPACE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"


class FilmFormat(str, Enum):
    MM35 = "35mm"
    FILM_120_6X6 = "120-6x6"


@dataclass(frozen=True)
class SprocketGeometry:
    pitch_mm: float
    width_mm: float
    height_mm: float
    center_y_top_mm: float
    first_center_x_mm: float = 3.0


@dataclass(frozen=True)
class FilmGeometry:
    film_format: FilmFormat
    film_height_mm: float
    strip_length_mm: float

    frame_w_mm: float
    frame_h_mm: float
    frame_pitch_mm: float
    frame_start_x_mm: float

    strips_per_sheet: int
    frames_per_strip: int

    default_film_name: str
    sprockets: SprocketGeometry | None = None

    @property
    def frames_per_sheet(self) -> int:
        return self.strips_per_sheet * self.frames_per_strip


def make_35mm_geometry() -> FilmGeometry:
    return FilmGeometry(
        film_format=FilmFormat.MM35,
        film_height_mm=35.0,
        strip_length_mm=240.0,
        frame_w_mm=36.0,
        frame_h_mm=24.0,
        frame_pitch_mm=38.0,
        frame_start_x_mm=8.0,
        strips_per_sheet=6,
        frames_per_strip=6,
        default_film_name="KODAK SAFETY FILM 5035",
        sprockets=SprocketGeometry(
            pitch_mm=4.75,
            width_mm=2.8,
            height_mm=1.98,
            center_y_top_mm=2.35,
        ),
    )


def make_120_6x6_geometry() -> FilmGeometry:
    # 120 film is approximately 61 mm wide.  A nominal 6x6 image area is
    # about 56 x 56 mm.  Three frames per strip and four strips per sheet
    # reproduce the familiar 12-exposure 6x6 contact-sheet arrangement.
    return FilmGeometry(
        film_format=FilmFormat.FILM_120_6X6,
        film_height_mm=61.0,
        strip_length_mm=184.0,
        frame_w_mm=56.0,
        frame_h_mm=56.0,
        frame_pitch_mm=60.0,
        frame_start_x_mm=4.0,
        strips_per_sheet=4,
        frames_per_strip=3,
        default_film_name="KODAK PORTRA 160 6059",
    )


def parse_film_format(value: str) -> FilmFormat:
    aliases = {
        "35": FilmFormat.MM35,
        "35mm": FilmFormat.MM35,
        "120": FilmFormat.FILM_120_6X6,
        "6x6": FilmFormat.FILM_120_6X6,
        "120-6x6": FilmFormat.FILM_120_6X6,
    }

    key = value.strip().lower()
    if key not in aliases:
        raise argparse.ArgumentTypeError(
            "film format must be '35mm' or '120-6x6'"
        )

    return aliases[key]


def get_film_geometry(film_format: FilmFormat) -> FilmGeometry:
    if film_format == FilmFormat.MM35:
        return make_35mm_geometry()

    if film_format == FilmFormat.FILM_120_6X6:
        return make_120_6x6_geometry()

    raise ValueError(f"Unsupported film format: {film_format}")


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


def compute_layout(options: RenderOptions, geometry: FilmGeometry) -> SheetLayout:
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
    geometry: FilmGeometry,
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


def draw_35mm_sprockets(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    ppm: float,
    geometry: FilmGeometry,
    theme: ContactSheetTheme,
) -> None:
    sprockets = geometry.sprockets
    if sprockets is None:
        return

    count = int(
        (geometry.strip_length_mm - 2 * sprockets.first_center_x_mm)
        / sprockets.pitch_mm
    )
    bottom_center_y_mm = geometry.film_height_mm - sprockets.center_y_top_mm

    for i in range(count):
        cx_mm = sprockets.first_center_x_mm + i * sprockets.pitch_mm

        for cy_mm in (sprockets.center_y_top_mm, bottom_center_y_mm):
            box = mm_rect(
                cx_mm - sprockets.width_mm / 2,
                cy_mm - sprockets.height_mm / 2,
                sprockets.width_mm,
                sprockets.height_mm,
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


def draw_film_details(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    ppm: float,
    geometry: FilmGeometry,
    theme: ContactSheetTheme,
) -> None:
    if geometry.film_format == FilmFormat.MM35:
        draw_35mm_sprockets(draw, x, y, ppm, geometry, theme)


def draw_frame_opening(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    ppm: float,
    frame_x_mm: float,
    geometry: FilmGeometry,
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


def draw_35mm_edge_markings(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    ppm: float,
    frame_numbers: Sequence[int],
    options: RenderOptions,
    geometry: FilmGeometry,
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


def draw_120_edge_markings(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    ppm: float,
    frame_numbers: Sequence[int],
    options: RenderOptions,
    geometry: FilmGeometry,
    theme: ContactSheetTheme,
) -> None:
    # 120 film has no sprocket holes.  Its edge information occupies the narrow
    # clear lanes above and below the image area.  The frame numbers and small
    # triangular index marks are modeled after typical 120 edge printing, while
    # the film name is repeated along the opposite edge.
    edge_font = load_font(max(8, int(0.72 * ppm)), bold=True)
    num_font = load_font(max(8, int(0.78 * ppm)), bold=True)

    frame_y_mm = (geometry.film_height_mm - geometry.frame_h_mm) / 2
    top_margin_y = y + max(1, int(0.25 * ppm))
    bottom_margin_y = y + int(
        (frame_y_mm + geometry.frame_h_mm + 0.30) * ppm
    )

    triangle_w = max(2, int(0.65 * ppm))
    triangle_h = max(2, int(0.45 * ppm))

    for i, n in enumerate(frame_numbers):
        frame_x_mm = geometry.frame_start_x_mm + i * geometry.frame_pitch_mm
        center_x = x + int((frame_x_mm + geometry.frame_w_mm / 2) * ppm)

        draw_text_centered(
            draw,
            center_x,
            top_margin_y,
            str(n),
            num_font,
            theme.edge_text,
        )

        marker_x = center_x + int(geometry.frame_w_mm * 0.22 * ppm)
        marker_y = y + max(1, int(0.55 * ppm))
        draw.polygon(
            [
                (marker_x, marker_y),
                (marker_x + triangle_w, marker_y),
                (marker_x + triangle_w // 2, marker_y + triangle_h),
            ],
            fill=theme.edge_text,
        )

        draw_text_centered(
            draw,
            center_x,
            bottom_margin_y,
            options.film_name,
            edge_font,
            theme.edge_text,
        )


def draw_edge_markings(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    ppm: float,
    frame_numbers: Sequence[int],
    options: RenderOptions,
    geometry: FilmGeometry,
    theme: ContactSheetTheme,
) -> None:
    if geometry.film_format == FilmFormat.MM35:
        draw_35mm_edge_markings(
            draw, x, y, ppm, frame_numbers, options, geometry, theme
        )
        return

    if geometry.film_format == FilmFormat.FILM_120_6X6:
        draw_120_edge_markings(
            draw, x, y, ppm, frame_numbers, options, geometry, theme
        )
        return

    raise ValueError(f"Unsupported film format: {geometry.film_format}")


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
    geometry: FilmGeometry,
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
    draw_film_details(draw, strip_x, strip_y, ppm, geometry, theme)

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
    geometry: FilmGeometry,
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


def read_xmp_name(path: Path) -> tuple[str | None, str | None]:
    """Return the custom headshot-kiosk XMP LastName and FirstName values."""
    try:
        with Image.open(path) as img:
            xmp = img.info.get("xmp")

        if not xmp:
            return None, None

        if isinstance(xmp, str):
            xmp = xmp.encode("utf-8")

        root = ET.fromstring(xmp)
        description_tag = f"{{{RDF_NAMESPACE}}}Description"
        last_name_tag = f"{{{HEADSHOT_XMP_NAMESPACE}}}LastName"
        first_name_tag = f"{{{HEADSHOT_XMP_NAMESPACE}}}FirstName"

        for description in root.iter(description_tag):
            # The headshot kiosk currently writes these values as RDF
            # Description attributes, but also accept element forms.
            last_name = description.attrib.get(last_name_tag)
            first_name = description.attrib.get(first_name_tag)

            if last_name is None:
                element = description.find(last_name_tag)
                if element is not None:
                    last_name = element.text

            if first_name is None:
                element = description.find(first_name_tag)
                if element is not None:
                    first_name = element.text

            if last_name is not None:
                last_name = last_name.strip() or None

            if first_name is not None:
                first_name = first_name.strip() or None

            return last_name, first_name

    except (OSError, ET.ParseError, ValueError):
        pass

    return None, None


def collect_images(image_dir: Path) -> list[Path]:
    # Start with the script's original filename ordering.  If every image has
    # the custom XMP LastName field, sort by LastName and then FirstName.
    # Filename remains a final deterministic tie-breaker when both names match
    # (or when FirstName is absent).
    image_paths = sorted(
        p
        for p in image_dir.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )

    names = {path: read_xmp_name(path) for path in image_paths}

    if image_paths and all(names[path][0] is not None for path in image_paths):
        return sorted(
            image_paths,
            key=lambda path: (
                names[path][0].casefold(),
                names[path][1].casefold() if names[path][1] is not None else "",
                path.name.casefold(),
            ),
        )

    return image_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create realistic photographic contact sheets for 35mm or 120 film"
    )

    parser.add_argument("image_directory", help="directory containing source images")

    parser.add_argument(
        "--film-format",
        type=parse_film_format,
        default=FilmFormat.MM35,
        metavar="{35mm,120-6x6}",
        help=(
            "film format to simulate; '120' and '6x6' are accepted aliases "
            "for '120-6x6' [default is 35mm]"
        ),
    )

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
        default=None,
        help=(
            "film-edge name to print; the default depends on --film-format "
            "('KODAK SAFETY FILM 5035' for 35mm, "
            "'KODAK PORTRA 160 6059' for 120-6x6)"
        ),
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


def make_options(args: argparse.Namespace, geometry: FilmGeometry) -> RenderOptions:
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
        film_name=args.film_name or geometry.default_film_name,
    )


def main() -> None:
    args = parse_args()
    geometry = get_film_geometry(args.film_format)
    options = make_options(args, geometry)

    if not options.image_directory.is_dir():
        raise SystemExit(f"Not a directory: {options.image_directory}")

    options.output_dir.mkdir(parents=True, exist_ok=True)

    images = collect_images(options.image_directory)

    if not images:
        raise SystemExit(f"No images found in {options.image_directory}")

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
