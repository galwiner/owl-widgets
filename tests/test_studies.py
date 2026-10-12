"""Contracts for the AnyWidget study adapters."""

import json
from copy import deepcopy
from dataclasses import fields, replace
import pytest
from owl.aperture_study import ApertureStudySpec
from owl.stop_study import StopStudySpec
from owl.studies import (
    ApertureFocusStudy,
    ApertureStudy,
    PupilMapStudy,
    RayWaveStudy,
    StopRayStudy,
    StopStudy,
)


def _aperture_spec(**changes):
    return replace(
        ApertureStudySpec(),
        grid_size=64,
        longitudinal_samples=16,
        ray_count=100,
        aperture_diameter_ratios=(None, 1.0),
        **changes,
    )


def _stop_spec(**changes):
    return replace(
        StopStudySpec(),
        pupil_count=100,
        display_pupil_count=50,
        ray_z_count=20,
        illumination_field_heights_mm=(-1.0, 0.0, 1.0),
        **changes,
    )


@pytest.mark.parametrize(
    ("widget_type", "spec", "kind"),
    [
        (ApertureStudy, _aperture_spec(), "aperture_study"),
        (ApertureFocusStudy, _aperture_spec(), "aperture_study"),
        (RayWaveStudy, _aperture_spec(), "aperture_study"),
        (StopStudy, _stop_spec(), "stop_study"),
        (StopRayStudy, _stop_spec(), "stop_study"),
        (PupilMapStudy, _stop_spec(), "stop_study"),
    ],
)
def test_initializes_with_exact_spec_and_calculates(widget_type, spec, kind):
    widget = widget_type(spec)
    try:
        assert widget.view_kind == kind
        assert widget.spec == spec
        assert widget.result["schema_version"] == 1
        assert widget.error == ""
        assert json.loads(json.dumps(widget.to_dict(), allow_nan=False)) == widget.to_dict()
        json.dumps(widget.result, allow_nan=False)
    finally:
        widget.close()


def test_default_specs_are_exact():
    widgets = [
        ApertureStudy(),
        ApertureFocusStudy(),
        RayWaveStudy(),
        StopStudy(),
        StopRayStudy(),
        PupilMapStudy(),
    ]
    try:
        for widget in widgets[:3]:
            assert widget.spec == ApertureStudySpec()
            assert set(widget.to_dict()) == {field.name for field in fields(ApertureStudySpec)} | {
                "schema_version"
            }
        for widget in widgets[3:]:
            assert widget.spec == StopStudySpec()
            assert widget.to_dict() == StopStudySpec().to_dict()
    finally:
        for widget in widgets:
            widget.close()


@pytest.mark.parametrize(
    ("widget_type", "section", "kind"),
    [
        (ApertureStudy, "all", "aperture_study"),
        (ApertureFocusStudy, "focus", "aperture_study"),
        (RayWaveStudy, "comparison", "aperture_study"),
        (StopStudy, "all", "stop_study"),
        (StopRayStudy, "rays", "stop_study"),
        (PupilMapStudy, "pupils", "stop_study"),
    ],
)
def test_public_widget_traits_select_exact_view(widget_type, section, kind):
    widget = widget_type()
    try:
        assert widget.view_kind == kind
        assert widget.section == section
        assert widget.traits()["section"].metadata["sync"] is True
    finally:
        widget.close()


@pytest.mark.parametrize(
    ("widget_type", "valid_section", "invalid_section"),
    [
        (ApertureStudy, "focus", "rays"),
        (StopStudy, "pupils", "comparison"),
        (ApertureFocusStudy, "focus", "comparison"),
        (RayWaveStudy, "comparison", "focus"),
        (StopRayStudy, "rays", "pupils"),
        (PupilMapStudy, "pupils", "rays"),
    ],
)
def test_section_constructor_keyword_is_validated(widget_type, valid_section, invalid_section):
    widget = widget_type(section=valid_section)
    try:
        assert widget.section == valid_section
        with pytest.raises(ValueError, match="section"):
            widget.section = invalid_section
    finally:
        widget.close()

    with pytest.raises(ValueError, match="section"):
        widget_type(section=invalid_section)


@pytest.mark.parametrize(
    ("widget_type", "spec", "field", "value"),
    [
        (ApertureStudy, _aperture_spec(), "seed", 9),
        (StopStudy, _stop_spec(), "seed", 9),
    ],
)
def test_complete_settings_update_recalculates(widget_type, spec, field, value):
    widget = widget_type(spec)
    try:
        previous = deepcopy(widget.result)
        settings = widget.to_dict()
        settings[field] = value
        widget.settings = settings
        assert getattr(widget.spec, field) == value
        assert widget.error == ""
        assert widget.result != previous
    finally:
        widget.close()


@pytest.mark.parametrize("widget", [ApertureStudy(_aperture_spec()), StopStudy(_stop_spec())])
def test_invalid_update_rolls_back_atomically(widget):
    try:
        settings_before = widget.to_dict()
        result_before = deepcopy(widget.result)
        invalid = widget.to_dict()
        invalid.pop("seed")
        widget.settings = invalid
        assert widget.to_dict() == settings_before
        assert widget.settings == settings_before
        assert widget.result == result_before
        assert widget.error

        widget.settings = settings_before
        assert widget.error == ""
    finally:
        widget.close()


@pytest.mark.parametrize(
    ("widget_type", "spec"),
    [(ApertureStudy, _aperture_spec(seed=4)), (StopStudy, _stop_spec(seed=4))],
)
def test_json_round_trip_is_detached_and_independent(widget_type, spec):
    first = widget_type(spec)
    restored = widget_type.from_dict(json.loads(json.dumps(first.to_dict(), allow_nan=False)))
    try:
        assert restored.view_kind == first.view_kind
        assert restored.spec == first.spec
        assert restored.result == first.result
        changed = restored.to_dict()
        changed["seed"] = 7
        restored.settings = changed
        assert restored.spec.seed == 7
        assert first.spec.seed == 4
        assert restored.result != first.result
    finally:
        first.close()
        restored.close()


def test_assets_are_packaged_local_files_without_cdn_references():
    js = ApertureStudy._esm._path
    css = ApertureStudy._css._path
    for widget_type in (ApertureFocusStudy, RayWaveStudy, StopStudy, StopRayStudy, PupilMapStudy):
        assert widget_type._esm._path == js and js.name == "studies.js"
        assert widget_type._css._path == css and css.name == "studies.css"
    for asset in (js, css):
        assert asset.is_file()
        text = asset.read_text()
        assert "https://" not in text
        assert "unpkg.com" not in text
        assert "jsdelivr.net" not in text
        assert "cdnjs.cloudflare.com" not in text


@pytest.mark.parametrize(
    "widget_type",
    [ApertureStudy, ApertureFocusStudy, RayWaveStudy, StopStudy, StopRayStudy, PupilMapStudy],
)
def test_constructor_and_from_dict_reject_wrong_or_partial_specs(widget_type):
    with pytest.raises(ValueError, match="spec"):
        widget_type(object())
    with pytest.raises(ValueError, match="keys"):
        widget_type.from_dict({"schema_version": 1})


@pytest.mark.parametrize(
    ("widget_type", "spec", "section"),
    [
        (ApertureFocusStudy, _aperture_spec(seed=4), "focus"),
        (RayWaveStudy, _aperture_spec(seed=4), "comparison"),
        (StopRayStudy, _stop_spec(seed=4), "rays"),
        (PupilMapStudy, _stop_spec(seed=4), "pupils"),
    ],
)
def test_wrapper_serialization_contains_settings_only_and_restores_independently(
    widget_type, spec, section
):
    first = widget_type(spec)
    restored = widget_type.from_dict(first.to_dict())
    try:
        assert "section" not in first.to_dict()
        assert "view_kind" not in first.to_dict()
        assert restored.section == section
        changed = restored.to_dict()
        changed["seed"] = 8
        restored.settings = changed
        assert first.spec.seed == 4
        assert restored.spec.seed == 8
    finally:
        first.close()
        restored.close()
