"""Privacy-safe crop for the accepted full Webull chart layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image


@dataclass(frozen=True, slots=True)
class RelativeCrop:
    left: float
    top: float
    right: float
    bottom: float


# Removes left navigation/watchlist, account header, and bottom account ticker.
# Retains chart ticker/timeframe header and bottom interval verification bar.
WEBULL_CHART_PRIVACY_CROP = RelativeCrop(0.137, 0.095, 0.998, 0.975)
# Market-data tables extend closer to Webull's persistent bottom ticker than
# charts do. Stop above that strip while retaining the complete readable table.
WEBULL_MARKET_SCREEN_PRIVACY_CROP = RelativeCrop(0.137, 0.095, 0.998, 0.94)


def crop_chart_in_place(
    path: Path,
    crop: RelativeCrop = WEBULL_CHART_PRIVACY_CROP,
    *,
    profile: str = "webull_chart_privacy_20260725_v1",
) -> dict[str, object]:
    with Image.open(path) as source:
        width, height = source.size
        box = (
            round(width * crop.left),
            round(height * crop.top),
            round(width * crop.right),
            round(height * crop.bottom),
        )
        chart = source.crop(box)
        cropped_width, cropped_height = chart.size
        temporary = path.with_suffix(".cropped.tmp.png")
        chart.save(temporary, "PNG")
    temporary.replace(path)
    return {
        "profile": profile,
        "source_dimensions": [width, height],
        "crop_box_pixels": list(box),
        "output_dimensions": [cropped_width, cropped_height],
        "removed_regions": ["ACCOUNT_HEADER", "WATCHLIST", "NAVIGATION_RAIL", "BOTTOM_ACCOUNT_TICKER"],
    }

