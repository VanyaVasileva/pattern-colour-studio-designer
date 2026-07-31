"""Pattern Colour Studio — private designer beta.

The beta has two deliberately narrow artwork modes:

* line + background: transparent line art, or flattened two-colour artwork
* background only: coloured motifs on transparency

Previews are reduced for speed. Downloads are rendered from the original upload
at its original pixel dimensions.
"""

from __future__ import annotations

from hashlib import sha256
import hmac
from io import BytesIO
from pathlib import Path
import re
from typing import Any

from PIL import Image, ImageChops, ImageColor, ImageOps
import streamlit as st

from palette_library import PALETTES, POPULAR_NAMES, palette_by_name, palette_categories


APP_TITLE = "Pattern Colour Studio · Designer Beta"
MAX_PREVIEW_PX = 1100
MAX_IMAGE_PIXELS = 50_000_000
DEFAULT_BACKGROUND = "#F1E8D8"
DEFAULT_LINE = "#665044"

Image.MAX_IMAGE_PIXELS = 100_000_000


def normalise_hex(value: str, fallback: str) -> str:
    """Return a valid uppercase #RRGGBB colour."""
    cleaned = value.strip()
    if not cleaned.startswith("#"):
        cleaned = "#" + cleaned
    if re.fullmatch(r"#[0-9A-Fa-f]{6}", cleaned):
        return cleaned.upper()
    return fallback.upper()


def hex_rgb(value: str) -> tuple[int, int, int]:
    return ImageColor.getrgb(normalise_hex(value, "#FFFFFF"))


def rgb_hex(value: tuple[int, int, int]) -> str:
    return "#" + "".join(f"{channel:02X}" for channel in value)


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return cleaned or "pattern-colourway"


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024**2:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024**2:.1f} MB"


def open_uploaded_image(data: bytes) -> tuple[Image.Image, dict[str, Any], str]:
    """Decode an upload, apply EXIF orientation, and retain useful metadata."""
    with Image.open(BytesIO(data)) as opened:
        original_format = opened.format or "PNG"
        metadata = dict(opened.info)
        corrected = ImageOps.exif_transpose(opened)
        image = corrected.convert("RGBA")
        image.load()
    return image, metadata, original_format


def has_useful_transparency(image: Image.Image) -> bool:
    if "A" not in image.getbands():
        return False
    minimum_alpha, _ = image.getchannel("A").getextrema()
    return minimum_alpha < 255


def derive_flat_line_mask(
    image: Image.Image,
    original_background: str,
    cleanup_tolerance: int,
) -> Image.Image:
    """Extract a clean line mask from flattened two-colour artwork.

    The selected original background is subtracted from the artwork. Small
    differences inside the cleanup tolerance are treated as JPEG noise.
    """
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, hex_rgb(original_background))
    red, green, blue = ImageChops.difference(rgb, background).split()
    difference = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    maximum = difference.getextrema()[1]
    tolerance = max(0, min(int(cleanup_tolerance), 80))
    if maximum <= tolerance:
        return Image.new("L", rgb.size, 0)

    scale = 255.0 / (maximum - tolerance)
    return difference.point(
        lambda value: 0 if value <= tolerance else min(255, round((value - tolerance) * scale))
    )


def compose_colourway(
    source: Image.Image,
    mode: str,
    background_colour: str,
    line_colour: str,
    original_background: str = "#FFFFFF",
    cleanup_tolerance: int = 8,
) -> Image.Image:
    """Render a finished RGB colourway at the source image dimensions."""
    base = Image.new("RGB", source.size, hex_rgb(background_colour))

    if mode == "line_and_background":
        if has_useful_transparency(source):
            line_mask = source.getchannel("A")
        else:
            line_mask = derive_flat_line_mask(source, original_background, cleanup_tolerance)
        ink = Image.new("RGB", source.size, hex_rgb(line_colour))
        base.paste(ink, (0, 0), line_mask)
        return base

    if mode == "background_only":
        if not has_useful_transparency(source):
            raise ValueError(
                "Background-only artwork needs a transparent PNG so the original motifs can remain unchanged."
            )
        base.paste(source.convert("RGB"), (0, 0), source.getchannel("A"))
        return base

    raise ValueError(f"Unsupported artwork mode: {mode}")


def preview_source(source: Image.Image) -> Image.Image:
    preview = source.copy()
    preview.thumbnail((MAX_PREVIEW_PX, MAX_PREVIEW_PX), Image.Resampling.LANCZOS)
    return preview


def safe_dpi(metadata: dict[str, Any]) -> tuple[int, int]:
    value = metadata.get("dpi")
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        try:
            horizontal = max(1, min(2400, round(float(value[0]))))
            vertical = max(1, min(2400, round(float(value[1]))))
            return horizontal, vertical
        except (TypeError, ValueError):
            pass
    return 300, 300


def encode_png(image: Image.Image, metadata: dict[str, Any]) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True, dpi=safe_dpi(metadata))
    return output.getvalue()


def encode_jpeg(image: Image.Image, metadata: dict[str, Any]) -> bytes:
    output = BytesIO()
    image.convert("RGB").save(
        output,
        format="JPEG",
        quality=98,
        subsampling=0,
        optimize=True,
        dpi=safe_dpi(metadata),
    )
    return output.getvalue()


def relative_luminance(colour: str) -> float:
    channels = []
    for channel in hex_rgb(colour):
        value = channel / 255.0
        channels.append(value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: str, second: str) -> float:
    light, dark = sorted((relative_luminance(first), relative_luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def initialise_colours() -> None:
    defaults = {
        "background_colour": DEFAULT_BACKGROUND,
        "background_picker": DEFAULT_BACKGROUND,
        "background_hex": DEFAULT_BACKGROUND,
        "line_colour": DEFAULT_LINE,
        "line_picker": DEFAULT_LINE,
        "line_hex": DEFAULT_LINE,
        "palette_name": "Oat Milk & Walnut",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def sync_colour_from_picker(colour_type: str) -> None:
    value = st.session_state[f"{colour_type}_picker"].upper()
    st.session_state[f"{colour_type}_colour"] = value
    st.session_state[f"{colour_type}_hex"] = value
    st.session_state.palette_name = "Custom"


def sync_colour_from_hex(colour_type: str) -> None:
    value = normalise_hex(
        st.session_state[f"{colour_type}_hex"],
        st.session_state[f"{colour_type}_picker"],
    )
    st.session_state[f"{colour_type}_colour"] = value
    st.session_state[f"{colour_type}_picker"] = value
    st.session_state[f"{colour_type}_hex"] = value
    st.session_state.palette_name = "Custom"


def select_palette(name: str, mode: str) -> None:
    palette = palette_by_name(name)
    st.session_state.background_colour = palette["bg"]
    st.session_state.background_picker = palette["bg"]
    st.session_state.background_hex = palette["bg"]
    if mode == "line_and_background":
        st.session_state.line_colour = palette["line"]
        st.session_state.line_picker = palette["line"]
        st.session_state.line_hex = palette["line"]
    st.session_state.palette_name = palette["name"]


def swap_colours() -> None:
    old_background = st.session_state.background_colour
    old_line = st.session_state.line_colour
    st.session_state.background_colour = old_line
    st.session_state.background_picker = old_line
    st.session_state.background_hex = old_line
    st.session_state.line_colour = old_background
    st.session_state.line_picker = old_background
    st.session_state.line_hex = old_background
    st.session_state.palette_name = "Custom · Reversed"


def render_palette_controls(mode: str) -> tuple[str, str, str]:
    st.subheader("2. Explore curated colours")
    category = st.selectbox(
        "Colour collection",
        ["Popular", *palette_categories()],
    )
    visible = (
        [palette_by_name(name) for name in POPULAR_NAMES]
        if category == "Popular"
        else [palette for palette in PALETTES if palette["category"] == category]
    )

    columns = st.columns(4)
    for index, palette in enumerate(visible):
        with columns[index % 4]:
            if mode == "background_only":
                colour_html = f'<span style="flex:1;background:{palette["bg"]}"></span>'
            else:
                colour_html = (
                    f'<span style="flex:1;background:{palette["bg"]}"></span>'
                    f'<span style="flex:1;background:{palette["line"]}"></span>'
                )
            st.markdown(
                f'<div class="palette-chip">{colour_html}</div>',
                unsafe_allow_html=True,
            )
            if st.button(
                palette["name"],
                key=f'palette_{mode}_{palette["name"]}',
                use_container_width=True,
            ):
                select_palette(palette["name"], mode)
                st.rerun()

    if mode == "line_and_background" and st.button(
        "↔ Swap line and background colours",
        use_container_width=True,
    ):
        swap_colours()
        st.rerun()

    with st.expander("Custom colour or exact HEX code"):
        if mode == "line_and_background":
            background_column, line_column = st.columns(2)
        else:
            background_column, line_column = st.container(), None

        with background_column:
            st.color_picker(
                "Background colour",
                key="background_picker",
                on_change=sync_colour_from_picker,
                args=("background",),
            )
            st.text_input(
                "Background HEX",
                key="background_hex",
                on_change=sync_colour_from_hex,
                args=("background",),
            )

        if line_column is not None:
            with line_column:
                st.color_picker(
                    "Line colour",
                    key="line_picker",
                    on_change=sync_colour_from_picker,
                    args=("line",),
                )
                st.text_input(
                    "Line HEX",
                    key="line_hex",
                    on_change=sync_colour_from_hex,
                    args=("line",),
                )

    return (
        st.session_state.background_colour,
        st.session_state.line_colour,
        st.session_state.palette_name,
    )


def configured_password() -> str:
    try:
        return str(st.secrets.get("DESIGNER_BETA_PASSWORD", "")).strip()
    except Exception:
        return ""


def beta_access_granted() -> bool:
    password = configured_password()
    if not password:
        return True
    if st.session_state.get("designer_beta_access") is True:
        return True

    st.title(APP_TITLE)
    st.write("Enter the private beta access code.")
    entered = st.text_input("Access code", type="password")
    if st.button("Open Designer Beta", type="primary", use_container_width=True):
        if hmac.compare_digest(entered, password):
            st.session_state.designer_beta_access = True
            st.rerun()
        else:
            st.error("That access code is not correct.")
    return False


def export_signature(
    upload_hash: str,
    mode: str,
    background_colour: str,
    line_colour: str,
    original_background: str,
    cleanup_tolerance: int,
) -> str:
    settings = "|".join(
        (
            upload_hash,
            mode,
            background_colour,
            line_colour,
            original_background,
            str(cleanup_tolerance),
        )
    )
    return sha256(settings.encode("utf-8")).hexdigest()


def render_app() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🎨", layout="wide")
    st.markdown(
        """
        <style>
        .block-container {max-width: 1040px; padding-top: 2rem; padding-bottom: 4rem;}
        .palette-chip {
            height: 34px;
            border: 1px solid rgba(70, 65, 60, 0.18);
            border-radius: 10px;
            display: flex;
            overflow: hidden;
            margin-bottom: 0.35rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    if not beta_access_granted():
        return

    initialise_colours()
    st.title(APP_TITLE)
    st.write(
        "Upload artwork, explore curated muted colourways and download the finished result "
        "at the original pixel dimensions."
    )
    st.caption(
        "Private beta · This version does not save uploads to a permanent pattern library."
    )

    st.subheader("1. Upload your artwork")
    uploaded = st.file_uploader(
        "Transparent PNG recommended",
        type=("png", "jpg", "jpeg"),
        help=(
            "Use transparent PNG line art for the cleanest result. Flattened two-colour PNG or JPEG "
            "can also be tested in line-art mode."
        ),
    )
    if uploaded is None:
        st.info(
            "Best input: transparent line art for changing line and background colours, "
            "or coloured motifs on transparency for changing the background only."
        )
        return

    upload_data = uploaded.getvalue()
    upload_hash = sha256(upload_data).hexdigest()
    try:
        source, source_metadata, original_format = open_uploaded_image(upload_data)
    except Exception as exc:
        st.error(f"The artwork could not be opened: {exc}")
        return

    width, height = source.size
    pixel_count = width * height
    if pixel_count > MAX_IMAGE_PIXELS:
        st.error(
            f"This beta currently accepts up to {MAX_IMAGE_PIXELS / 1_000_000:.0f} megapixels. "
            f"Your upload is {pixel_count / 1_000_000:.1f} megapixels."
        )
        return

    transparency = has_useful_transparency(source)
    st.caption(
        f"{uploaded.name} · {width} × {height} px · {pixel_count / 1_000_000:.1f} MP · "
        f"{original_format} · {'transparent' if transparency else 'flattened'}"
    )

    mode_label = st.radio(
        "What may change?",
        (
            "Line + background colours",
            "Background colour only",
        ),
        horizontal=True,
    )
    mode = "line_and_background" if mode_label.startswith("Line") else "background_only"

    detected_background = rgb_hex(source.convert("RGB").getpixel((0, 0)))
    if st.session_state.get("active_upload_hash") != upload_hash:
        st.session_state.active_upload_hash = upload_hash
        st.session_state.original_background_picker = detected_background
        st.session_state.original_background_hex = detected_background

    original_background = detected_background
    cleanup_tolerance = 8
    if mode == "line_and_background" and not transparency:
        st.info(
            "Flattened two-colour artwork detected. Confirm its current background colour so the "
            "studio can separate the lines cleanly."
        )
        extraction_left, extraction_right = st.columns(2)
        with extraction_left:
            original_background = st.color_picker(
                "Current artwork background",
                key="original_background_picker",
            )
            st.session_state.original_background_hex = original_background
        with extraction_right:
            cleanup_tolerance = st.slider(
                "Background cleanup",
                min_value=0,
                max_value=40,
                value=8,
                help="Increase slightly if JPEG speckles remain in the new background.",
            )
    elif mode == "background_only" and not transparency:
        st.error(
            "Background-only mode requires a transparent PNG. A flattened image does not contain "
            "enough information to preserve the motifs while replacing its background perfectly."
        )
        return

    background_colour, line_colour, palette_name = render_palette_controls(mode)

    st.subheader("3. Preview your colourway")
    try:
        preview = compose_colourway(
            preview_source(source),
            mode,
            background_colour,
            line_colour,
            original_background,
            cleanup_tolerance,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    st.image(preview, use_container_width=True)
    if mode == "line_and_background":
        ratio = contrast_ratio(background_colour, line_colour)
        if ratio < 1.5:
            st.warning(
                "This is a very low-contrast combination. Fine lines may become difficult to see "
                "on some screens or printed fabrics."
            )
        st.markdown(
            f"**{palette_name}** · Background `{background_colour}` · Line `{line_colour}`"
        )
    else:
        st.markdown(f"**{palette_name}** · Background `{background_colour}` · Original motif colours")

    st.subheader("4. Prepare original-resolution files")
    project_name = st.text_input(
        "Colourway name",
        value=Path(uploaded.name).stem,
        help="Used only for the downloaded filenames.",
    )
    st.caption(
        f"The download will remain {width} × {height} px. PNG is lossless; JPEG uses maximum-quality settings."
    )

    current_signature = export_signature(
        upload_hash,
        mode,
        background_colour,
        line_colour,
        original_background,
        cleanup_tolerance,
    )
    if st.button(
        "Prepare high-resolution downloads",
        type="primary",
        use_container_width=True,
    ):
        try:
            with st.spinner("Preparing the original-resolution colourway…"):
                result = compose_colourway(
                    source,
                    mode,
                    background_colour,
                    line_colour,
                    original_background,
                    cleanup_tolerance,
                )
                png_data = encode_png(result, source_metadata)
                jpeg_data = encode_jpeg(result, source_metadata)
        except Exception as exc:
            st.error(f"The full-resolution files could not be prepared: {exc}")
        else:
            st.session_state.designer_export = {
                "signature": current_signature,
                "png": png_data,
                "jpeg": jpeg_data,
            }

    prepared = st.session_state.get("designer_export")
    if prepared and prepared.get("signature") == current_signature:
        filename_base = slugify(project_name)
        download_left, download_right = st.columns(2)
        with download_left:
            st.download_button(
                f"Download lossless PNG · {format_bytes(len(prepared['png']))}",
                data=prepared["png"],
                file_name=f"{filename_base}.png",
                mime="image/png",
                use_container_width=True,
            )
        with download_right:
            st.download_button(
                f"Download high-quality JPEG · {format_bytes(len(prepared['jpeg']))}",
                data=prepared["jpeg"],
                file_name=f"{filename_base}.jpg",
                mime="image/jpeg",
                use_container_width=True,
            )
        st.success("The files were created at the original uploaded dimensions.")
    elif prepared:
        st.info("The colours changed. Prepare the high-resolution downloads again for this version.")

    st.divider()
    st.caption(
        "Designer beta: full-resolution downloads are available only here. The future customer link "
        "will show a protected preview and send the selected colours without exposing the source file."
    )


if __name__ == "__main__":
    render_app()
