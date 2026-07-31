from io import BytesIO
import unittest

from PIL import Image

from app import (
    compose_colourway,
    contrast_ratio,
    encode_jpeg,
    encode_png,
    has_useful_transparency,
)
from palette_library import PALETTES, POPULAR_NAMES, palette_by_name


class ColourEngineTests(unittest.TestCase):
    def test_transparent_line_art_recolours_line_and_background(self) -> None:
        source = Image.new("RGBA", (12, 9), (0, 0, 0, 0))
        for x in range(3, 9):
            source.putpixel((x, 4), (20, 30, 40, 255))

        result = compose_colourway(
            source,
            "line_and_background",
            "#F1E8D8",
            "#665044",
        )

        self.assertEqual(result.size, source.size)
        self.assertEqual(result.getpixel((0, 0)), (241, 232, 216))
        self.assertEqual(result.getpixel((4, 4)), (102, 80, 68))

    def test_background_only_preserves_coloured_motif(self) -> None:
        source = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        source.putpixel((4, 4), (180, 90, 70, 255))

        result = compose_colourway(
            source,
            "background_only",
            "#E8ECE7",
            "#000000",
        )

        self.assertEqual(result.getpixel((0, 0)), (232, 236, 231))
        self.assertEqual(result.getpixel((4, 4)), (180, 90, 70))

    def test_flattened_two_colour_artwork_is_supported(self) -> None:
        source = Image.new("RGBA", (10, 10), (250, 250, 250, 255))
        for y in range(2, 8):
            source.putpixel((5, y), (30, 30, 30, 255))

        self.assertFalse(has_useful_transparency(source))
        result = compose_colourway(
            source,
            "line_and_background",
            "#FFFFFF",
            "#355B51",
            original_background="#FAFAFA",
            cleanup_tolerance=4,
        )

        self.assertEqual(result.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(result.getpixel((5, 4)), (53, 91, 81))

    def test_exports_keep_original_dimensions(self) -> None:
        source = Image.new("RGB", (37, 29), (100, 120, 140))
        png_data = encode_png(source, {"dpi": (300, 300)})
        jpeg_data = encode_jpeg(source, {"dpi": (300, 300)})

        with Image.open(BytesIO(png_data)) as png:
            self.assertEqual(png.size, (37, 29))
        with Image.open(BytesIO(jpeg_data)) as jpeg:
            self.assertEqual(jpeg.size, (37, 29))

    def test_palette_library_has_unique_names_and_valid_popular_entries(self) -> None:
        names = [palette["name"] for palette in PALETTES]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(PALETTES), 69)
        for name in POPULAR_NAMES:
            self.assertEqual(palette_by_name(name)["name"], name)

    def test_contrast_ratio_is_symmetric(self) -> None:
        first = contrast_ratio("#FFFFFF", "#000000")
        second = contrast_ratio("#000000", "#FFFFFF")
        self.assertAlmostEqual(first, 21.0)
        self.assertAlmostEqual(first, second)


if __name__ == "__main__":
    unittest.main()
