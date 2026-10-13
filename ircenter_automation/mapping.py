import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .errors import ConfigurationError, DocumentParsingError
from .normalization import comparison_key, normalize_space


CONTROLS = {"text", "textarea", "date", "select", "radio", "checkbox", "autocomplete", "richtext"}


@dataclass(frozen=True)
class FieldSpec:
    key: str
    docx_label: str
    selector: str
    control: str
    required: bool
    options: dict[str, str]
    option_selector: str | None
    verification_selector: str | None
    verification_mode: str


@dataclass(frozen=True)
class FieldValue:
    spec: FieldSpec
    expected: str


def load_mapping(path: Path) -> tuple[FieldSpec, ...]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_fields = data["fields"]
        if not isinstance(raw_fields, list) or not raw_fields:
            raise ValueError("Configure at least one DOCX to website field mapping")
        specs = []
        for raw in raw_fields:
            spec = FieldSpec(
                key=str(raw["key"]), docx_label=str(raw["docx_label"]), selector=str(raw["selector"]),
                control=str(raw["control"]), required=bool(raw.get("required", True)),
                options=dict(raw.get("options", {})), option_selector=raw.get("option_selector"),
                verification_selector=raw.get("verification_selector"),
                verification_mode=str(raw.get("verification_mode", "input")),
            )
            if spec.control not in CONTROLS or not spec.key or not spec.docx_label or not spec.selector or "REPLACE_" in spec.selector:
                raise ValueError(f"Incomplete mapping for {spec.key}")
            if spec.control == "radio" and not spec.options:
                raise ValueError(f"Radio field {spec.key} needs option selectors")
            if spec.control == "autocomplete" and not spec.option_selector:
                raise ValueError(f"Autocomplete field {spec.key} needs option_selector")
            if spec.verification_mode not in ("input", "text"):
                raise ValueError(f"Invalid verification_mode for {spec.key}")
            specs.append(spec)
        if len({s.key for s in specs}) != len(specs) or len({s.selector for s in specs}) != len(specs):
            raise ValueError("Field keys and website selectors must be unique")
        return tuple(specs)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Invalid field mapping: {exc}") from exc


def normalize_field(value: str, control: str) -> str:
    if control == "date":
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(normalize_space(value), fmt).date().isoformat()
            except ValueError:
                continue
        raise DocumentParsingError("Invalid date in DOCX; use YYYY-MM-DD or DD.MM.YYYY")
    if control == "checkbox":
        key = comparison_key(value)
        if key in ("yes", "true", "1", "так", "☑", "☒"):
            return "true"
        if key in ("no", "false", "0", "ні", "☐"):
            return "false"
        raise DocumentParsingError("Invalid checkbox value in DOCX")
    return value.replace("\r\n", "\n").strip()


def map_document(fields: dict[str, str], specs: tuple[FieldSpec, ...]) -> tuple[FieldValue, ...]:
    mapped = []
    for spec in specs:
        label = comparison_key(spec.docx_label)
        if label not in fields:
            if spec.required:
                raise DocumentParsingError(f"Required DOCX label missing: {spec.docx_label}")
            continue
        raw = fields[label]
        if spec.required and not raw.strip():
            raise DocumentParsingError(f"Required DOCX value empty: {spec.docx_label}")
        value = normalize_field(raw, spec.control) if raw.strip() else ""
        if spec.control in ("select", "radio") and value and comparison_key(value) not in {comparison_key(k) for k in spec.options}:
            raise DocumentParsingError(f"Unmapped option for DOCX label: {spec.docx_label}")
        mapped.append(FieldValue(spec, value))
    if not mapped:
        raise DocumentParsingError("No DOCX fields match the configured mapping")
    return tuple(mapped)
