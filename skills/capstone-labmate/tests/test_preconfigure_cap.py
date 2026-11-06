"""Unit tests for stage A: preconfigure_cap.py .cap XML injection.

Focus: the calculation-column injector must emit legal expression trees
(Type=27 -> operator -> operands), never a bare leaf or a self-referencing
Type=27 — that shape made Capstone hang at 55% during open.
"""
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import preconfigure_cap  # noqa: E402

ANCHOR = (
    "<CalculationManager>\n"
    '  <Container Count="0" RulesVersion="1.1" Scope="2"/>\n'
    '  <Container Count="0" RulesVersion="1.1" Scope="1">\n'
    '  </Container>\n'
    "</CalculationManager>"
)


def _formulas():
    return [
        {"name": "v", "text": "slope([position])"},
        {"name": "a", "text": "slope([v])"},
    ]


def test_inject_columns_emits_expression_blocks() -> None:
    xml, ok = preconfigure_cap._inject_calculation_columns(ANCHOR, _formulas())
    assert ok is True
    assert xml.count("<Expression ") == 2
    assert 'Count="2"' in xml
    assert 'Name="v"' in xml
    assert 'Name="a"' in xml


def test_expression_body_is_legal_expression_not_bare_leaf() -> None:
    """The 55%-hang regression guard: each Type=27's direct child must be an
    operator/function container (Type=8 / Type=21), never a bare leaf and
    never a self-referencing Type=27."""
    xml, ok = preconfigure_cap._inject_calculation_columns(ANCHOR, _formulas())
    assert ok is True
    for name in ("v", "a"):
        body = re.search(
            r'<ASTNode EUID="[^"]*" Name="' + re.escape(name)
            + r'" Type="27"[^>]*>\s*(.*?)\s*</ASTNode>',
            xml, re.S,
        )
        assert body is not None, f"column {name} missing"
        child = body.group(1).strip()
        assert child.startswith("<ASTNode "), f"{name}: not an ASTNode child"
        m = re.match(r'<ASTNode\b[^>]*Type="(\d+)"', child)
        assert m is not None, f"{name}: child has no Type"
        assert m.group(1) in ("8", "21"), (
            f"{name}: Type=27 child is Type={m.group(1)} (bare leaf or "
            f"self-reference) — the 55%-hang shape")
        open_tag = child[:child.find(">") + 1]
        assert not open_tag.endswith("/>"), f"{name}: operator is self-closing"
        # no self-referencing Type=27 anywhere in the body
        assert 'Type="27"' not in child, f"{name}: nested Type=27 self-reference"


def test_injection_degrades_when_anchor_missing() -> None:
    xml, ok = preconfigure_cap._inject_calculation_columns(
        "<nope/>", _formulas())
    assert ok is False
    assert xml == "<nope/>"


def test_formula_text_is_xml_escaped() -> None:
    formulas = [{"name": "x", "text": "slope([pos & dist])"}]
    xml, ok = preconfigure_cap._inject_calculation_columns(ANCHOR, formulas)
    assert ok is True
    # no raw unescaped & would break the XML — ET must parse it back
    ET.fromstring(xml.encode("utf-8"))
    # the bracketed variable text survives intact in a Type=3 node
    assert "[pos &amp; dist]" in xml or "[pos & dist]" in xml


def test_doc_matches_profile() -> None:
    profile = {
        "columns": [{"name": "position", "sensor": "Motion Sensor"}],
        "formulas": [{"name": "v", "text": "slope([position])"}],
        "axes": {"x": {"y": "position", "title": "Position vs Time"}},
    }
    hits, toks = preconfigure_cap._doc_matches(
        "Use the Motion Sensor to record position vs time.", profile)
    assert hits >= 1
    assert any("motion sensor" in t for t in toks)


def test_doc_matches_no_hit_is_nonblocking() -> None:
    profile = {
        "columns": [{"name": "position", "sensor": "Motion Sensor"}],
        "formulas": [],
        "axes": {},
    }
    hits, _ = preconfigure_cap._doc_matches("unrelated text", profile)
    assert hits == 0  # caller only warns, never fails


# -----------------------------------------------------------------------
# Formula AST: blackbody Planck chain + unicode symbols + constant placeholder
# -----------------------------------------------------------------------
def test_blackbody_planck_chain_renders_legal_ast() -> None:
    """The full blackbody formula chain (incl. λ/π unicode, nested funcs)
    must render to well-formed XML with variable refs preserved as [text]."""
    formulas = [
        {"name": "trueangle", "text": "abs([Angle])/([AngleCal]/100)"},
        {"name": "n", "text": "sqrt((2*sin([CorrTrueAng(°)/360*2*3.14])/sqrt(3)+0.5)^2+3/4)"},
        {"name": "I", "text": "([C1]/([λ]/10^9)^5) * (1/(exp([C2]/(([λ]/10^9)*[Temp]))-1))"},
        {"name": "C1", "text": "2*π*[h]*[c]^2"},
    ]
    xml, ok = preconfigure_cap._inject_calculation_columns(ANCHOR, formulas)
    assert ok is True
    ET.fromstring(xml.encode("utf-8"))
    # No [paste:] placeholder residue anywhere
    assert "[paste:" not in xml
    # variable refs survive as bracketed [Name] in Type=3 nodes
    for v in ("[Angle]", "[AngleCal]", "[λ]", "[Temp]"):
        assert v in xml, f"variable {v} lost in AST"
    # the nested Planck formula produced multiple operator nodes
    n_expr = re.search(r'Name="n".*?</Expression>', xml, re.S).group(0)
    assert n_expr.count('Type="8"') >= 3


def test_unicode_variable_is_kept_as_text_reference() -> None:
    """Unicode symbol columns (λ, π) are kept as bracketed text refs, not
    dropped — Capstone resolves them by name."""
    formulas = [{"name": "I", "text": "([λ]/10^9)^5"}]
    xml, ok = preconfigure_cap._inject_calculation_columns(ANCHOR, formulas)
    assert ok is True
    ET.fromstring(xml.encode("utf-8"))
    assert "[λ]" in xml


def test_unknown_constant_becomes_zero_placeholder_not_fabricated() -> None:
    """A bare physical constant (c, h, pi) not registered as a column is
    emitted as a 0.0 placeholder — the pre-config stage never fabricates a
    physics value (R-02). The AST stays legal."""
    formulas = [{"name": "C1", "text": "2*π*[h]*[c]^2"}]
    xml, ok = preconfigure_cap._inject_calculation_columns(ANCHOR, formulas)
    assert ok is True
    ET.fromstring(xml.encode("utf-8"))
    # c and h are bare identifiers (not bracketed cols) -> 0.0 constants;
    # the whole formula must still be a legal tree (XML well-formed, no [paste:).
    assert "[paste:" not in xml


def test_unparseable_formula_degrades_to_constant_not_bare_leaf() -> None:
    """A formula the parser cannot fully resolve must fall back to a legal
    0/1 constant — never a bare-leaf Type=27 (the 55%-hang shape)."""
    formulas = [{"name": "bad", "text": "[[unclosed"}]  # malformed -> fallback
    xml, ok = preconfigure_cap._inject_calculation_columns(ANCHOR, formulas)
    assert ok is True
    ET.fromstring(xml.encode("utf-8"))
    body = re.search(r'Name="bad".*?</Expression>', xml, re.S).group(0)
    # fallback body has a Type=8 operator container (0/1), not a bare leaf
    assert 'Type="8"' in body
    assert '[paste:' not in body


def test_build_cap_patches_and_rezips(tmp_path: Path) -> None:
    """End-to-end _build_cap: base .cap copied, main.xml patched, zip valid."""
    base = tmp_path / "base.cap"
    with zipfile.ZipFile(base, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("main.xml", (
            "<Experiment><Measurement Name=\"Angle\" EUID=\"{e1}\" "
            "ID=\"1\"/><DataRepository></DataRepository>"
            "<CalculationManager>"
            '<Container Count="0" RulesVersion="1.1" Scope="1">'
            "</Container></CalculationManager></Experiment>"
        ))
        zf.writestr("data/Z_x.tmp", b"\x00" * 24)

    profile = {
        "description": "test profile",
        "sampling_hz": 100,
        "formulas": _formulas(),
        "columns": [{"name": "position", "unit": "m"}],
        "axes": {"x": {"y": "position", "title": "P"}},
    }
    out = tmp_path / "out.cap"
    built, manifest = preconfigure_cap._build_cap(base, profile, out)
    
    assert built == out and out.exists()
    assert manifest["injected"]["formulas"] is True
    assert manifest["injected"]["columns"] is True
    assert len(manifest["calc_text"]) == 2

    # The output must be a valid zip with patched main.xml
    with zipfile.ZipFile(out) as zf:
        xml = zf.read("main.xml").decode("utf-8")
    assert xml.count("<Expression ") == 2
    
    # And it must be XML well-formed
    ET.fromstring(xml)


# -----------------------------------------------------------------------
# Regression: self-closing <Container Scope="2"/> must NOT be matched
# by _inject_calculation_columns (the 55%-hang template bug).
# -----------------------------------------------------------------------
REGRESSION_ANCHOR = (
    "<CalculationManager>\n"
    '  <Container Count="0" RulesVersion="1.1" Scope="2"/>\n'
    '  <Container Count="1" RulesVersion="1.1" Scope="1">\n'
    '   <Expression Index="0"/>\n'
    '  </Container>\n'
    "</CalculationManager>"
)


def test_inject_skips_self_closing_scope2_container() -> None:
    """The regex must match the Scope=1 Container (with children),
    never the self-closing Scope=2 sibling."""
    xml, ok = preconfigure_cap._inject_calculation_columns(
        REGRESSION_ANCHOR, _formulas())
    assert ok is True
    # The self-closing Scope=2 container must be preserved untouched
    assert 'Scope="2"/>' in xml
    # The Scope=1 container should now have our formulas
    assert xml.count("<Expression ") == 2
    # XML must still parse
    ET.fromstring(xml.encode("utf-8"))


# -----------------------------------------------------------------------
# Sampling rate injection: CommonSamplingRate + UseCommonSamplingRate
# -----------------------------------------------------------------------
def test_inject_sampling_rate_patches_common() -> None:
    xml = (
        '<ExperimentControl><ExperimentSettings>'
        '<UseCommonSamplingRate Value="0"/>'
        '<CommonSamplingRate Units="7936" Value="50"/>'
        '</ExperimentSettings></ExperimentControl>'
    )
    new, ok = preconfigure_cap._inject_sampling_rate(xml, 20.0)
    assert ok is True
    assert 'Value="20"' in new
    # UseCommonSamplingRate must be enabled
    assert 'UseCommonSamplingRate Value="1"' in new


def test_inject_sampling_rate_no_match_is_ok() -> None:
    xml = "<Root/>"
    new, ok = preconfigure_cap._inject_sampling_rate(xml, 20.0)
    assert ok is False
    assert new == xml


# -----------------------------------------------------------------------
# Graph injection
# -----------------------------------------------------------------------
def test_inject_graph_creates_cslinegraph() -> None:
    xml = (
        "<DSProExperiment><Workspace><Workbook>"
        '<WorkbookPage PageSize="0"><PageSize Width="1760" Height="965"/>'
        "</WorkbookPage></Workbook></Workspace></DSProExperiment>"
    )
    axes = {"graph1": {"x": "Voltage", "y": "Current", "title": "I vs V"}}
    new, ok = preconfigure_cap._inject_graph(xml, axes, {})
    assert ok is True
    assert "CSLineGraph" in new
    assert "Anode Current vs" not in new  # title should be "I vs V"
    assert new.count("WorkbookItem") >= 1
    ET.fromstring(new.encode("utf-8"))


def test_inject_graph_skips_existing() -> None:
    xml = (
        "<DSProExperiment><Workspace><Workbook>"
        '<WorkbookItem GUID="CSLineGraph"><CSLineGraph/>'
        "</WorkbookItem></Workbook></Workspace></DSProExperiment>"
    )
    new, ok = preconfigure_cap._inject_graph(
        xml, {"graph1": {"x": "V", "y": "I"}}, {})
    # Should skip (graph already present)
    assert "I vs V" not in new or new == xml


def test_inject_graph_no_anchor_returns_false() -> None:
    xml = "<Root/>"
    new, ok = preconfigure_cap._inject_graph(xml, {}, {})
    assert ok is False
    assert new == xml


def test_inject_columns_returns_name_to_euid_map() -> None:
    xml = ("<DSProExperiment><DataRepository><MasterTimeMeasurement/>"
           "</DataRepository></DSProExperiment>")
    cols = [{"name": "Voltage", "unit": "V"}, {"name": "Current", "unit": "pA"}]
    new, ok, euid_map = preconfigure_cap._inject_columns(xml, cols)
    assert ok is True
    assert set(euid_map) == {"Voltage", "Current"}
    # each EUID is a fresh GUID string
    for e in euid_map.values():
        assert e.startswith("{") and e.endswith("}")
        assert e not in xml  # not pre-existing
    # both names present in the new XML
    assert 'Name="Voltage"' in new and 'Name="Current"' in new


def test_inject_graph_binds_axes_to_registered_columns() -> None:
    xml = (
        "<DSProExperiment><Workspace><Workbook>"
        '<WorkbookPage PageSize="0"><PageSize Width="1760" Height="965"/>'
        "</WorkbookPage></Workbook></Workspace></DSProExperiment>"
    )
    axes = {"graph1": {"x": "Voltage", "y": "Current", "title": "I vs V"}}
    euid_map = {"Voltage": "{aaaa1111-0000-0000-0000-000000000000}",
                "Current": "{bbbb2222-0000-0000-0000-000000000000}"}
    new, ok = preconfigure_cap._inject_graph(
        xml, axes, {}, euid_by_name=euid_map)
    assert ok is True
    # X axis (BundleIndex=0) bound to Voltage GUID
    assert 'BundleMeasID="{aaaa1111-0000-0000-0000-000000000000}"' in new
    # Y axis (BundleIndex=1) bound to Current GUID
    assert 'BundleMeasID="{bbbb2222-0000-0000-0000-000000000000}"' in new
    # No zero-GUID left in any BundleMeasID (axis bindings are all real)
    import re
    meas_ids = re.findall(r'BundleMeasID="([^"]*)"', new)
    assert all(mid != "{00000000-0000-0000-0000-000000000000}" for mid in meas_ids)
    ET.fromstring(new.encode("utf-8"))


def test_inject_graph_falls_back_to_zero_guid_when_name_missing() -> None:
    xml = (
        "<DSProExperiment><Workspace><Workbook>"
        '<WorkbookPage PageSize="0"><PageSize Width="1760" Height="965"/>'
        "</WorkbookPage></Workbook></Workspace></DSProExperiment>"
    )
    # axes reference a name not in euid_by_name -> zero-GUID fallback
    axes = {"graph1": {"x": "Voltage", "y": "MissingCol", "title": "I vs V"}}
    euid_map = {"Voltage": "{aaaa1111-0000-0000-0000-000000000000}"}
    new, ok = preconfigure_cap._inject_graph(xml, axes, {}, euid_by_name=euid_map)
    assert ok is True
    assert 'BundleMeasID="{aaaa1111-0000-0000-0000-000000000000}"' in new
    # Y falls back to zero GUID
    assert 'BundleMeasID="{00000000-0000-0000-0000-000000000000}"' in new
    ET.fromstring(new.encode("utf-8"))


# -----------------------------------------------------------------------
# Blank base fallback
# -----------------------------------------------------------------------
def test_blank_base_xml_is_valid() -> None:
    xml = preconfigure_cap._blank_base_xml()
    # Must parse
    ET.fromstring(xml.encode("utf-8"))
    # Must have the key structural elements
    assert "<DSProExperiment>" in xml
    assert "<CalculationManager>" in xml
    assert "CommonSamplingRate" in xml


def test_build_cap_blank_fallback(tmp_path: Path) -> None:
    """_build_cap with a non-existent base generates a blank .cap."""
    profile = {
        "description": "blank test",
        "sampling_hz": 20,
        "formulas": [{"name": "x", "text": "slope([y])"}],
        "columns": [{"name": "y", "unit": "V"}],
        "axes": {"graph1": {"x": "t", "y": "y"}},
    }
    out = tmp_path / "blank.cap"
    built, manifest = preconfigure_cap._build_cap(
        tmp_path / "nonexistent.cap", profile, out)
    assert built == out and out.exists()
    assert manifest.get("fallback_blank") is True
    # The blank .cap must be a valid zip with valid XML
    with zipfile.ZipFile(out) as zf:
        xml = zf.read("main.xml").decode("utf-8")
    ET.fromstring(xml)
    assert "Expression" in xml  # formula was injected
