"""Shared paths and unit conversions. Everything per-building lives under WORK (git-ignored)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORK = Path(os.environ.get("EBEWE_WORK", ROOT / "data" / "runs" / "_ebewe"))
KWH_PER_M2_TO_KBTU_PER_FT2 = 3.412 / 10.7639          # 1 kWh/m2 = 0.3170 kBtu/ft2
EBEWE_URL = "https://data.lacity.org/resource/9yda-i4ya.json?$limit=100000"
USABLE_YEARS = {"2016", "2017", "2018", "2019", "2022", "2023", "2024"}   # 2020-21 (COVID) excluded up front
