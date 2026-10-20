"""Shared parsing primitives for capstone-labmate.

Every function here cites the Technical Fact number (F1..F7) it implements,
so reviewers can audit the parsing logic against the confirmed spec.

All stage scripts (probe, extract_schema, extract_data, pair_series,
detect_peaks, build_report) import from this module.

Optimization Note: 
- Replaced regex-based XML parsing with standard `xml.etree.ElementTree` for robustness.
- Replaced per-record `struct.unpack_from` with `struct.iter_unpack` for 
  significant performance gains on large datasets.
"""

from __future__ import annotations

import json
import struct
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Technical facts (auditable constants)
# ---------------------------------------------------------------------------
# F1: .cap is a zip container (magic 504b0304); fixed entry is main.xml
MAIN_XML = "main.xml"
ZIP_MAGIC = b"PK\x03\x04"  # 504b0304

# F4: each tmp record is 12 bytes: int32 flag + int32 pad + float32 value
RECORD_BYTES = 12
RECORD_STRUCT = "<iif"  # little-endian: int32, int32, float32
VALID_FLAG = 1

# F5: independent variable (time axis) is NOT stored; generated from
# <IndependentStorageElement IntervalCacheStartValue="0"
#  IntervalCacheInterval="0.05">
DEFAULT_INTERVAL = 0.05


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------
@dataclass
class DataSetRecord:
    """One <DataSet> node parsed from main.xml (F2, F3)."""

    index: int
    data_group: str
    dataset_name: str  # may be empty (F6)
    dataset_id: str
    file_name: str  # e.g. data/Z_261a6de54f0_256.tmp (F3)
    data_cache_size: int  # valid point count (F4)
    data_offset: int
    storage_type: str
    cache_start: float  # F5
    cache_interval: float  # F5
    cache_count: int  # F5
    # F6: physical-quantity inference (best effort, may be "pending")
    measurement_hint: str
    adapter_hint: str
    channel_hint: str

    def stem(self) -> str:
        return Path(self.file_name).stem

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProbeReport:
    """P1 result (F1): zip sanity + tmp manifest."""

    is_zip: bool
    main_xml_present: bool
    tmp_count: int
    tmp_files: List[str]
    warnings: List[str]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------
def is_zip(path: Path) -> bool:
    """F1: a .cap must be a zip container."""
    try:
        with open(path, "rb") as fh:
            head = fh.read(4)
        return head == ZIP_MAGIC
    except OSError:
        return False


def open_cap_zip(path: Path) -> zipfile.ZipFile:
    """F1: open .cap as a zip; verify main.xml is the fixed entry."""
    if not is_zip(path):
        raise ValueError(
            "Not a zip container (missing PK\\x03\\x04 magic). "
            "Re-export from Capstone."
        )
    zf = zipfile.ZipFile(path)
    if MAIN_XML not in zf.namelist():
        raise ValueError(
            f"{MAIN_XML!r} entry not found. Re-export from Capstone."
        )
    return zf


def parse_main_xml(zf: zipfile.ZipFile) -> ET.Element:
    """F2: main.xml is UTF-8 XML. Parse using ElementTree."""
    try:
        xml_bytes = zf.read(MAIN_XML)
        return ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise ValueError(f"Failed to parse {MAIN_XML}: {e}")


# ---------------------------------------------------------------------------
# Schema extraction (P2)
# ---------------------------------------------------------------------------
def extract_datasets(zf: zipfile.ZipFile) -> List[DataSetRecord]:
    """Extract every <DataSet> that owns a <DependentStorageElement>.

    F2/F3: each DataSet has exactly one DependentStorageElement +
    one IndependentStorageElement (F5). F6: physical quantity is inferred
    from the nearest <Measurement>/<DataAdapter>/<Channel>.
    """
    root = parse_main_xml(zf)

    # F6: physical quantity is inferred from the nearest Measurement.
    # In lab2.cap the Measurement nodes sit at the top of the document,
    # so a single document-order list of names is aligned against the DataSet sequence.
    measurement_seq = [m.get("Name", "") for m in root.iter("Measurement")]

    records: List[DataSetRecord] = []
    idx = 0
    
    for ds_node in root.iter("DataSet"):
        dep = ds_node.find("DependentStorageElement")
        if dep is None:
            continue  # DataSet without a storage element (e.g., derived)

        ind = ds_node.find("IndependentStorageElement")
        
        # F6: inference of physical quantity from the block's context
        block_measurements = [m.get("Name", "") for m in ds_node.iter("Measurement") if m.get("Name")]
        block_adapters = [a.get("Name", "") for a in ds_node.iter("DataAdapter") if a.get("Name")]
        block_channels = [c.get("Name", "") for c in ds_node.iter("Channel") if c.get("Name")]

        if block_measurements:
            measurement_hint = block_measurements[0]
        elif measurement_seq:
            measurement_hint = measurement_seq[min(idx, len(measurement_seq) - 1)]
        else:
            measurement_hint = "pending"

        if not measurement_hint:
            measurement_hint = "pending"

        adapter_hint = block_adapters[0] if block_adapters else ""
        channel_hint = block_channels[0] if block_channels else ""

        # Safely parse float values with fallbacks
        try:
            cache_interval_val = float(ind.get("IntervalCacheInterval", DEFAULT_INTERVAL)) if ind is not None else DEFAULT_INTERVAL
        except ValueError:
            cache_interval_val = DEFAULT_INTERVAL

        records.append(
            DataSetRecord(
                index=idx,
                data_group=dep.get("DataGroup", ds_node.get("DataGroup", "")),
                dataset_name=ds_node.get("Name", ""),
                dataset_id=ds_node.get("DataSetID", ""),
                file_name=dep.get("FileName", ""),
                data_cache_size=int(dep.get("DataCacheDataSize", "0") or 0),
                data_offset=int(dep.get("DataOffsetValue", "0") or 0),
                storage_type=dep.get("StorageType", ""),
                cache_start=float(ind.get("IntervalCacheStartValue", "0") or 0) if ind is not None else 0.0,
                cache_interval=cache_interval_val,
                cache_count=int(ind.get("CacheDataCount", "0") or 0) if ind is not None else 0,
                measurement_hint=measurement_hint,
                adapter_hint=adapter_hint,
                channel_hint=channel_hint,
            )
        )
        idx += 1
        
    return records


# ---------------------------------------------------------------------------
# Data extraction (P3)
# ---------------------------------------------------------------------------
def read_tmp_values(
    zf: zipfile.ZipFile, file_name: str, expected_count: int
) -> List[float]:
    """F4: decode a tmp file; keep only flag==1 points.

    Uses struct.iter_unpack for high performance.
    Raises ValueError if the record layout is not a multiple of 12 bytes or
    if the valid-point count does not equal expected_count (the validity gate).
    """
    raw = zf.read(file_name)
    if len(raw) % RECORD_BYTES != 0:
        raise ValueError(
            f"{file_name}: size {len(raw)} is not a multiple of {RECORD_BYTES}. "
            "Diagnostic: do not continue to P3."
        )
    
    # iter_unpack is significantly faster than unpack_from in a loop
    values: List[float] = [
        val for flag, _pad, val in struct.iter_unpack(RECORD_STRUCT, raw) 
        if flag == VALID_FLAG
    ]
    
    if len(values) != expected_count:
        raise ValueError(
            f"{file_name}: valid points {len(values)} != "
            f"DataCacheDataSize {expected_count}. Diagnostic: do not continue."
        )
    return values


def build_time_axis(start: float, interval: float, count: int) -> List[float]:
    """F5: the independent variable (time) is generated, not stored.

    t[k] = start + k * interval, k in 0..count-1.
    """
    return [start + k * interval for k in range(count)]


# ---------------------------------------------------------------------------
# docx/PDF text extraction (P7 input, F7)
# ---------------------------------------------------------------------------
def extract_document_text(file_path: Path) -> str:
    """F7: extract experiment text from a .docx or .pdf.

    .docx is a zip; body in word/document.xml. .pdf via pypdf (optional);
    falls back to plain-text read for .txt.
    """
    suffix = file_path.suffix.lower()
    
    if suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(file_path))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except ImportError:
            # Fall through: return file content as raw text (best effort).
            return file_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            return f"[PDF extraction failed: {e}]"
            
    if suffix in (".docx", ".doc"):
        try:
            with zipfile.ZipFile(file_path) as zf:
                xml_content = zf.read("word/document.xml").decode("utf-8")
            # Replace paragraph and break tags with newlines, then strip all XML tags
            xml_content = xml_content.replace("</w:p>", "\n").replace("<w:br/>", "\n")
            import re
            text = re.sub(r"<[^>]+>", "", xml_content)
            import html as _html
            text = _html.unescape(text)
            return "\n".join(line.strip() for line in text.splitlines() if line.strip())
        except zipfile.BadZipFile:
            return f"[DOCX extraction failed: Invalid ZIP format]"
            
    # Plain text fallback.
    return file_path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    "peaks": {
        "prominence": 0.05,
        "min_distance": 5,
        "min_peak_count": 2,
    },
    "measurement_overrides": {},
}


def load_config(path: Optional[Path]) -> Dict[str, Any]:
    """Load built-in defaults plus an optional user config given via *path*.

    The defaults carry generic peak-detection parameters (prominence,
    minimum spacing, minimum peak count) and per-measurement label
    overrides. Any user-supplied JSON is deep-merged on top, so a lab can
    retune detection or rename measurement labels without touching code.
    """
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if path and Path(path).exists():
        try:
            with open(path, "r", encoding="utf-8") as fh:
                _deep_update(cfg, json.load(fh))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file {path}: {e}")
    return cfg


def _deep_update(base: Dict[str, Any], upd: Dict[str, Any]) -> Dict[str, Any]:
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
    return base


def json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
