"""Typed, safe-to-render lesson content metadata for Content Engine v2.

Version 2 is deliberately a data contract only.  It describes a small,
allow-listed set of blocks and lesson-local image assets; it neither renders
blocks nor reads or writes asset files.  Keeping parsing here lets the runtime
loader and filesystem validator apply exactly the same rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional, Union


_SUPPORTED_CONTENT_VERSIONS = frozenset({1, 2})
_CALLOUT_VARIANTS = frozenset({"info", "warning", "important"})
_ASSET_KINDS = frozenset({"image"})


@dataclass(frozen=True)
class RichLessonContentError(ValueError):
    """A validation error with a stable code and lesson-relative location."""

    code: str
    message: str
    location: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class LessonAssetSource:
    document: str
    page: Optional[int] = None
    slide: Optional[int] = None


@dataclass(frozen=True)
class LessonAsset:
    id: str
    file: str
    kind: str
    alt: str = ""
    caption: str = ""
    source: Optional[LessonAssetSource] = None


@dataclass(frozen=True)
class ParagraphBlock:
    text: str


@dataclass(frozen=True)
class HeadingBlock:
    level: int
    text: str


@dataclass(frozen=True)
class ImageBlock:
    asset_id: str
    alt: str
    caption: str = ""


@dataclass(frozen=True)
class KeyFactBlock:
    label: str
    value: str
    text: str = ""


@dataclass(frozen=True)
class Step:
    title: str
    text: str
    asset_id: Optional[str] = None


@dataclass(frozen=True)
class StepsBlock:
    items: tuple[Step, ...]


@dataclass(frozen=True)
class TableBlock:
    columns: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class CalloutBlock:
    variant: str
    title: str
    text: str


LessonBlock = Union[
    ParagraphBlock,
    HeadingBlock,
    ImageBlock,
    KeyFactBlock,
    StepsBlock,
    TableBlock,
    CalloutBlock,
]


@dataclass(frozen=True)
class RichLessonContent:
    content_version: int
    blocks: tuple[LessonBlock, ...]
    assets: tuple[LessonAsset, ...]


def parse_rich_lesson_content(metadata: dict) -> Optional[RichLessonContent]:
    """Parse optional v2 content metadata from one ``lesson.json`` object.

    A missing version, or explicit version 1, deliberately remains legacy v1:
    unknown extension fields stay ignored just as they were before v2 existed.
    V2, in contrast, is strict so future renderers never need to infer or
    execute arbitrary structures from lesson JSON.
    """
    raw_version = metadata.get("content_version", 1)
    if isinstance(raw_version, bool) or not isinstance(raw_version, int):
        raise _error(
            "lesson_content_version_invalid",
            "Field content_version must be an integer.",
            "content_version",
        )
    if raw_version not in _SUPPORTED_CONTENT_VERSIONS:
        raise _error(
            "lesson_content_version_unsupported",
            "Unsupported lesson content_version.",
            "content_version",
        )
    if raw_version == 1:
        return None

    blocks = _parse_blocks(metadata)
    assets = _parse_assets(metadata)
    asset_kinds = {asset.id: asset.kind for asset in assets}
    _validate_block_asset_references(blocks, asset_kinds)
    return RichLessonContent(content_version=2, blocks=blocks, assets=assets)


def _parse_blocks(metadata: dict) -> tuple[LessonBlock, ...]:
    if "blocks" not in metadata or not isinstance(metadata["blocks"], list):
        raise _error(
            "lesson_blocks_invalid_type",
            "V2 lessons require blocks to be a non-empty array.",
            "blocks",
        )
    raw_blocks = metadata["blocks"]
    if not raw_blocks:
        raise _error(
            "lesson_blocks_empty",
            "V2 lessons require at least one content block.",
            "blocks",
        )

    parsed: list[LessonBlock] = []
    for index, raw_block in enumerate(raw_blocks):
        location = f"blocks[{index}]"
        block = _require_object(raw_block, location)
        block_type = _required_string(block, "type", location)
        parser = {
            "paragraph": _parse_paragraph,
            "heading": _parse_heading,
            "image": _parse_image,
            "key_fact": _parse_key_fact,
            "steps": _parse_steps,
            "table": _parse_table,
            "callout": _parse_callout,
        }.get(block_type)
        if parser is None:
            raise _error(
                "lesson_block_type_unknown",
                f"Unsupported lesson block type: {block_type}.",
                f"{location}.type",
            )
        parsed.append(parser(block, location))
    return tuple(parsed)


def _parse_paragraph(block: dict, location: str) -> ParagraphBlock:
    _ensure_fields(block, {"type", "text"}, set(), location)
    return ParagraphBlock(text=_required_string(block, "text", location))


def _parse_heading(block: dict, location: str) -> HeadingBlock:
    _ensure_fields(block, {"type", "level", "text"}, set(), location)
    level = block["level"]
    if isinstance(level, bool) or not isinstance(level, int) or level not in {2, 3, 4}:
        raise _error(
            "lesson_heading_level_invalid",
            "Heading level must be one of 2, 3, or 4.",
            f"{location}.level",
        )
    return HeadingBlock(level=level, text=_required_string(block, "text", location))


def _parse_image(block: dict, location: str) -> ImageBlock:
    _ensure_fields(block, {"type", "asset_id", "alt"}, {"caption"}, location)
    return ImageBlock(
        asset_id=_required_string(block, "asset_id", location),
        alt=_required_string(block, "alt", location),
        caption=_optional_string(block, "caption", location),
    )


def _parse_key_fact(block: dict, location: str) -> KeyFactBlock:
    _ensure_fields(block, {"type", "label", "value"}, {"text"}, location)
    return KeyFactBlock(
        label=_required_string(block, "label", location),
        value=_required_string(block, "value", location),
        text=_optional_string(block, "text", location),
    )


def _parse_steps(block: dict, location: str) -> StepsBlock:
    _ensure_fields(block, {"type", "items"}, set(), location)
    raw_items = block["items"]
    if not isinstance(raw_items, list) or not raw_items:
        raise _error(
            "lesson_steps_items_invalid",
            "Steps block requires a non-empty items array.",
            f"{location}.items",
        )
    items: list[Step] = []
    for index, raw_item in enumerate(raw_items):
        item_location = f"{location}.items[{index}]"
        item = _require_object(raw_item, item_location)
        _ensure_fields(item, {"title", "text"}, {"asset_id"}, item_location)
        raw_asset_id = item.get("asset_id")
        if raw_asset_id is not None and not isinstance(raw_asset_id, str):
            raise _error(
                "lesson_steps_asset_id_invalid",
                "Step asset_id must be a string or null.",
                f"{item_location}.asset_id",
            )
        if isinstance(raw_asset_id, str) and not raw_asset_id.strip():
            raise _error(
                "lesson_steps_asset_id_invalid",
                "Step asset_id must not be blank.",
                f"{item_location}.asset_id",
            )
        items.append(
            Step(
                title=_required_string(item, "title", item_location),
                text=_required_string(item, "text", item_location),
                asset_id=raw_asset_id,
            )
        )
    return StepsBlock(items=tuple(items))


def _parse_table(block: dict, location: str) -> TableBlock:
    _ensure_fields(block, {"type", "columns", "rows"}, set(), location)
    columns = _string_array(block["columns"], f"{location}.columns", non_empty=True)
    raw_rows = block["rows"]
    if not isinstance(raw_rows, list) or not raw_rows:
        raise _error(
            "lesson_table_rows_invalid",
            "Table block requires a non-empty rows array.",
            f"{location}.rows",
        )
    rows: list[tuple[str, ...]] = []
    for index, raw_row in enumerate(raw_rows):
        row_location = f"{location}.rows[{index}]"
        row = _string_array(raw_row, row_location, non_empty=False)
        if len(row) != len(columns):
            raise _error(
                "lesson_table_row_width_invalid",
                "Every table row must match the number of columns.",
                row_location,
            )
        rows.append(row)
    return TableBlock(columns=columns, rows=tuple(rows))


def _parse_callout(block: dict, location: str) -> CalloutBlock:
    _ensure_fields(block, {"type", "variant", "text"}, {"title"}, location)
    variant = _required_string(block, "variant", location)
    if variant not in _CALLOUT_VARIANTS:
        raise _error(
            "lesson_callout_variant_invalid",
            "Callout variant must be info, warning, or important.",
            f"{location}.variant",
        )
    return CalloutBlock(
        variant=variant,
        title=_optional_string(block, "title", location),
        text=_required_string(block, "text", location),
    )


def _parse_assets(metadata: dict) -> tuple[LessonAsset, ...]:
    if "assets" not in metadata:
        return ()
    raw_assets = metadata["assets"]
    if not isinstance(raw_assets, list):
        raise _error(
            "lesson_assets_invalid_type",
            "Field assets must be an array.",
            "assets",
        )

    assets: list[LessonAsset] = []
    asset_ids: set[str] = set()
    for index, raw_asset in enumerate(raw_assets):
        location = f"assets[{index}]"
        asset = _require_object(raw_asset, location)
        _ensure_fields(
            asset,
            {"id", "file", "kind"},
            {"alt", "caption", "source"},
            location,
        )
        asset_id = _required_string(asset, "id", location)
        if asset_id in asset_ids:
            raise _error(
                "lesson_asset_id_duplicate",
                "Asset IDs must be unique within a lesson.",
                f"{location}.id",
            )
        asset_ids.add(asset_id)
        asset_file = _required_string(asset, "file", location)
        _validate_asset_path(asset_file, f"{location}.file")
        kind = _required_string(asset, "kind", location)
        if kind not in _ASSET_KINDS:
            raise _error(
                "lesson_asset_kind_invalid",
                "Asset kind must be image.",
                f"{location}.kind",
            )
        assets.append(
            LessonAsset(
                id=asset_id,
                file=asset_file,
                kind=kind,
                alt=_optional_string(asset, "alt", location),
                caption=_optional_string(asset, "caption", location),
                source=_parse_asset_source(asset, location),
            )
        )
    return tuple(assets)


def _parse_asset_source(asset: dict, location: str) -> Optional[LessonAssetSource]:
    if "source" not in asset:
        return None
    source = _require_object(asset["source"], f"{location}.source")
    source_location = f"{location}.source"
    _ensure_fields(source, {"document"}, {"page", "slide"}, source_location)
    page = _optional_positive_integer(source, "page", source_location)
    slide = _optional_positive_integer(source, "slide", source_location)
    if page is not None and slide is not None:
        raise _error(
            "lesson_asset_source_location_invalid",
            "Asset source may identify a page or a slide, not both.",
            source_location,
        )
    return LessonAssetSource(
        document=_required_string(source, "document", source_location),
        page=page,
        slide=slide,
    )


def _validate_block_asset_references(
    blocks: tuple[LessonBlock, ...], asset_kinds: dict[str, str]
) -> None:
    for index, block in enumerate(blocks):
        references: tuple[str, ...] = ()
        if isinstance(block, ImageBlock):
            references = (block.asset_id,)
        elif isinstance(block, StepsBlock):
            references = tuple(
                item.asset_id for item in block.items if item.asset_id is not None
            )
        for asset_id in references:
            if asset_kinds.get(asset_id) != "image":
                raise _error(
                    "lesson_block_asset_missing",
                    "Image references must point to a declared image asset.",
                    f"blocks[{index}]",
                )


def _validate_asset_path(value: str, location: str) -> None:
    if "\\" in value or "\x00" in value:
        raise _error(
            "lesson_asset_path_unsafe",
            "Asset file path must be a safe relative POSIX path.",
            location,
        )
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or len(path.parts) < 2
        or path.parts[0] != "assets"
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise _error(
            "lesson_asset_path_unsafe",
            "Asset file path must be below the lesson assets directory.",
            location,
        )


def _require_object(value: object, location: str) -> dict:
    if not isinstance(value, dict):
        raise _error(
            "lesson_rich_content_invalid_type",
            "Rich lesson content objects must be JSON objects.",
            location,
        )
    return value


def _ensure_fields(
    data: dict,
    required: set[str],
    optional: set[str],
    location: str,
) -> None:
    for field_name in required:
        if field_name not in data:
            raise _error(
                "lesson_rich_content_field_missing",
                f"Required field is missing: {field_name}.",
                f"{location}.{field_name}",
            )
    allowed = required | optional
    for field_name in data:
        if field_name not in allowed:
            raise _error(
                "lesson_rich_content_field_unknown",
                f"Unknown field: {field_name}.",
                f"{location}.{field_name}",
            )


def _required_string(data: dict, field_name: str, location: str) -> str:
    if field_name not in data or not isinstance(data[field_name], str):
        raise _error(
            "lesson_rich_content_string_invalid",
            f"Field {field_name} must be a string.",
            f"{location}.{field_name}",
        )
    value = data[field_name].strip()
    if not value:
        raise _error(
            "lesson_rich_content_string_empty",
            f"Field {field_name} must not be blank.",
            f"{location}.{field_name}",
        )
    return value


def _optional_string(data: dict, field_name: str, location: str) -> str:
    if field_name not in data:
        return ""
    value = data[field_name]
    if not isinstance(value, str):
        raise _error(
            "lesson_rich_content_string_invalid",
            f"Field {field_name} must be a string.",
            f"{location}.{field_name}",
        )
    return value.strip()


def _string_array(value: object, location: str, *, non_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or (non_empty and not value):
        raise _error(
            "lesson_rich_content_array_invalid",
            "Field must be an array with the required values.",
            location,
        )
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise _error(
                "lesson_rich_content_string_invalid",
                "Array values must be non-empty strings.",
                f"{location}[{index}]",
            )
        result.append(item.strip())
    return tuple(result)


def _optional_positive_integer(data: dict, field_name: str, location: str) -> Optional[int]:
    if field_name not in data:
        return None
    value = data[field_name]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise _error(
            "lesson_asset_source_position_invalid",
            f"Field {field_name} must be a positive integer.",
            f"{location}.{field_name}",
        )
    return value


def _error(code: str, message: str, location: str) -> RichLessonContentError:
    return RichLessonContentError(code=code, message=message, location=location)
