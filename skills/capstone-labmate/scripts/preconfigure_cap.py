#!/usr/bin/env python
"""Stage A — generate a preconfigured .cap template from an experiment doc.

Given an instructor document (PDF/.docx) + a sampling profile (from
config/sampling_profiles.json) + a known-good base .cap of the same
instrument family, this stage:

  1. extracts the document text and scans it for the profile's signature
     keywords (sensor names, formula symbols, axis quantities) to confirm
     the profile matches the document;
  2. copies the base .cap and surgically patches main.xml:
       - sets the sampling rate (sensor Channel SamplerRate),
       - registers the blank data columns the profile declares,
       - injects the preset formulas as Calculator <Expression> roots,
       - wires the graph X/Y axis variables and initial display ranges;
  3. writes a plain-text `cap_inject.json` manifest so a human can always
     hand-paste anything the structural injection could not verify.

Safety (R-02/R-04): this stage only prepares an *empty* experiment scaffold.
It never fabricates measurement data. If the XML injection fails validation, 
it rolls back and outputs an error manifest.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _capx  # noqa: E402
import formula_ast  # noqa: E402

# ---------------------------------------------------------------------------
# Document -> profile match (stage A step 1)
# ---------------------------------------------------------------------------
def _profile_signature(profile: Dict[str, Any]) -> List[str]:
    """Collect the profile's sensor/formula/axis tokens to look for in the doc."""
    toks: List[str] = []
    for col in profile.get("columns", []):
        if col.get("sensor"):
            toks.append(col["sensor"])
        toks.append(col.get("name", ""))
    for f in profile.get("formulas", []):
        toks.append(f.get("name", ""))
    for ax in profile.get("axes", {}).values():
        toks.append(ax.get("y", ""))
        toks.append(ax.get("title", ""))
    return [t for t in (t.lower() for t in toks) if t]


def _doc_matches(doc_text: str, profile: Dict[str, Any], need_hits: int = 1) -> Tuple[int, List[str]]:
    """Return (n_hits, hit_tokens). Non-blocking: even 0 hits is allowed."""
    sig = _profile_signature(profile)
    low = doc_text.lower()
    hits = [t for t in sig if t in low]
    return (len(hits), hits)


# ---------------------------------------------------------------------------
# XML injection helpers (stage A step 2)
# ---------------------------------------------------------------------------
def _euid() -> str:
    return "{" + str(uuid.uuid4()) + "}"


def _is_valid_xml(xml_str: str) -> bool:
    """R-04 Safety net: ensure the patched XML is still structurally valid."""
    try:
        ET.fromstring(xml_str.encode("utf-8"))
        return True
    except ET.ParseError as e:
        print(f"Critical Error: XML corruption detected during injection: {e}", file=sys.stderr)
        return False


def _inject_sampling_rate(xml: str, hz: float) -> Tuple[str, bool]:
    """Patch the sampling rate. Two forms exist in Capstone:

    1. <CommonSamplingRate Units="..." Value="N"/>  — 850 DAQ / interface families
       (hz is expressed as Value in Hz). UseCommonSamplingRate=1 when common rate is used.
    2. Channel SamplerRate="N" attribute — older / per-channel sensor families.

    We try both and succeed if at least one matched.
    """
    ok = False
    # Form 1: CommonSamplingRate Value attribute (most modern 850 templates)
    new = re.sub(
        r'(<CommonSamplingRate\b[^>]*\bValue=")[^"]*(")', rf'\g<1>{hz:.0f}\2', xml
    )
    if new != xml:
        xml = new
        ok = True
    # Ensure UseCommonSamplingRate is enabled (1) when the common rate is used.
    xml = re.sub(
        r'(<UseCommonSamplingRate\b[^>]*\bValue=")[^"]*(")',
        r'\g<1>1\2',
        xml,
    )
    # Form 2: per-channel SamplerRate attribute (legacy)
    new2 = re.sub(
        r'(SamplerRate\s*=\s*")[^"]*(")', rf'\g<1>{hz:.0f}\2', xml
    )
    if new2 != xml:
        xml = new2
        ok = True
    return xml, ok


def _inject_calculation_columns(xml: str, formulas: List[Dict[str, str]],
                                units: Optional[Dict[str, str]] = None) -> Tuple[str, bool]:
    """Replace the Calculator container body with the profile's formula roots.

    Each formula is parsed into a *legal* nested Capstone AST via the
    ``formula_ast`` module (variable refs Type=3 with bracketed Name + a fresh
    decoupled EUID + BaseUnit dimension; operators Type=8; named functions
    Type=21; numeric constants Type=1). Per the pre-config design the variable
    references keep their bracketed *text* (``[Angle]``) — Capstone resolves
    them by column name, not EUID — and each node carries a fresh EUID so the
    formula is decoupled from any sensor/measurement EUID.

    If a single formula cannot be parsed, that column degrades to a legal 0/1
    constant so the .cap still opens cleanly — never a bare-leaf AST.
    """
    # BUGFIX: The old regex (<Container\s+[^>]*>) matched self-closing
    # <Container ... Count="0"/> elements (the Scope="2" sibling), causing
    # XML corruption. The trailing [^/] in group 1 excludes self-closing tags.
    m = re.search(
        r'(<Container\s[^>]*?[^/]>)(.*?)(</Container>\s*</CalculationManager>)',
        xml, re.S,
    )
    if m is None:
        return xml, False

    prefix = re.sub(
        r'Count\s*=\s*"\d+"', lambda _x: f'Count="{len(formulas)}"', m.group(1)
    )
    units = units or {}
    body = []
    for i, f in enumerate(formulas):
        euid = _euid()
        name = re.sub(r'[^\w]', "_", f.get("name", "col"))
        # Fresh EUID per variable node, decoupled from any measurement EUID.
        expr_xml = formula_ast.render_expression(
            name, str(f.get("text", "")), units, i, euid,
            euid_factory=_euid)
        body.append(expr_xml)

    new_xml = xml[: m.start(1)] + prefix + "".join(body) + xml[m.end(2):]
    return new_xml, True


def _inject_columns(xml: str, columns: List[Dict[str, Any]]) -> Tuple[str, bool, Dict[str, str]]:
    """Register blank user data columns (no live data, just the table headers).

    Returns (new_xml, ok, euid_by_name) where euid_by_name maps each column's
    *name* to the EUID just injected. The graph stage uses this to bind the
    X/Y axis BundleMeasID to real columns instead of zero-GUID placeholders.
    """
    anchor = "</DataRepository>"
    if anchor not in xml:
        return xml, False, {}

    # Idempotency guard: skip columns the base template already registered so a
    # second pass over an already-patched .cap never duplicates <Column> nodes.
    existing = set(re.findall(r'<Column\b[^>]*\bName="([^"]*)"', xml))

    blocks = []
    euid_by_name: Dict[str, str] = {}
    for c in columns:
        nm = c.get("name", "")
        if nm and nm in existing:
            # Reuse the already-registered column's EUID for axis binding.
            # Attribute order in a <Column> is not guaranteed, so pull the
            # whole tag then read its EUID from within it.
            tag_m = re.search(r'<Column\b[^>]*Name="' + re.escape(nm) + r'"[^>]*>', xml)
            if tag_m:
                e_m = re.search(r'EUID="([^"]*)"', tag_m.group(0))
                if e_m:
                    euid_by_name[nm] = e_m.group(1)
            continue
        euid = _euid()
        if nm:
            euid_by_name[nm] = euid
        blocks.append(
            f'<Column EUID="{euid}" Name="{nm}" '
            f'Unit="{c.get("unit", "")}" DataHasBeenDeleted="FALSE"/>'
        )
    i = xml.find(anchor)
    new_xml = xml[:i] + "".join(blocks) + xml[i:]
    return new_xml, True, euid_by_name


def _inject_graph(xml: str, axes: Dict[str, Any], range_dict: Dict[str, Any],
                  euid_by_name: Optional[Dict[str, str]] = None) -> Tuple[str, bool]:
    """Inject a CSLineGraph into the Workbook.

    Capstone graphs live inside <WorkbookPage> > <WorkbookItem GUID="CSLineGraph">.
    If the base .cap has no graph, we build a minimal one.

    Axis binding: when *euid_by_name* is supplied (from _inject_columns), the
    X/Y axis BundleMeasID are bound to the matching column EUIDs so the graph
    opens with Voltage on X and Current on Y already wired. Falls back to
    zero-GUID auto-select when the named column is not registered.
    """
    # --- Find the first axes entry (graph1) and its x/y variables ---
    graph_cfg = None
    for key, val in axes.items():
        if key.startswith("graph"):
            graph_cfg = val
            break
    if graph_cfg is None:
        return xml, False

    x_var = graph_cfg.get("x", "")
    y_var = graph_cfg.get("y", "")
    title = graph_cfg.get("title", "Graph")

    # --- Resolve X/Y BundleMeasID: prefer the injected column EUIDs ---
    zero_euid = "{00000000-0000-0000-0000-000000000000}"
    lookup = (euid_by_name or {})
    x_meas = lookup.get(x_var, zero_euid)
    y_meas = lookup.get(y_var, zero_euid)

    # --- Build a minimal CSLineGraph block ---
    graph_euid = _euid()
    euid = _euid()
    graph_block = f'''
    <WorkbookItem GUID="CSLineGraph" ShowFrame="FALSE" ToolBarHiddenWhenLocked="FALSE" ZValue="0.001" ToolBarPinned="FALSE" TitleVisible="FALSE">
     <BackgroundColor B="255" A="255" R="255" G="255"/>
     <FrameColor B="192" A="255" R="192" G="192"/>
     <Position X="0.01644736842105263" Y="0.05389221556886228"/>
     <Size Height="0.9281437125748503" Width="0.9736842105263158"/>
     <DataOptions AddNewDataSetsFromPriorPages="FALSE" AddNewDataSets="TRUE"/>
     <DisplayTitle ReadOnly="FALSE" DisplayTitleText="{title}" Font="DejaVu Sans,-1,14,5,50,0,0,0,0,0">
      <Alignment Index="0"/>
     </DisplayTitle>
     <CSLineGraph LineGraphShowMirroredIndependentAxes="0" LineGraphShowAreaUnderCurve="0" LineGraphAddDataSets="0" LineGraphAllowAxisAndPlotAreaMovement="0" LineGraphSavedCurveFitTypeNotMenuIndex="1">
      <LineGraphAutoScaleFromZero NumberOfNames="1" Enabled="0">
       <CheckedItem Index="0" IsChecked="0" Name="Auto scale from zero"/>
      </LineGraphAutoScaleFromZero>
      <LineGraphAutoScalingBehavior Index="0" Enabled="1"/>
      <LineGraphStatisticsSelections NumberOfNames="4" Enabled="0">
       <CheckedItem Index="0" IsChecked="0" Name="Minimum"/>
       <CheckedItem Index="1" IsChecked="0" Name="Maximum"/>
       <CheckedItem Index="2" IsChecked="1" Name="Mean"/>
       <CheckedItem Index="3" IsChecked="0" Name="Standard Deviation"/>
      </LineGraphStatisticsSelections>
      <LineGraphCurveFitSelections LineGraphCurveFitState="TRUE"/>
      <LineGraphPlotAreaElement>
       <ZPlotArea ZPABehaviorWhenNewDataSetAdded="1" ShowMeasurementSymbol="0" ShowUnits="1" CustomName="Custom Name" ZPAOriginLockedForMultiAxis="FALSE" ZPAAutoScalingBehaviorWhenNewDataSetAdded="3" NamingConvention="2" ZPASavedCurveFitTypeNotMenuIndex="1" ZPAScalesLockedForMultiAxis="FALSE" ZPALeftSideDependentAxisCount="1" ZPAAutoScalingBehaviorWhenDataPointChanges="3" ZPARightSideDependentAxisCount="0">
        <ZDataAreaAppearanceSettings ZDAASShowHorizontalOriginLine="1" ZDAASUseOpacity="1" ZDAASShowMinorDivisions="1" ZDAASShowMajorDivisions="1" ZDAASShowBorder="0">
         <ZDAASMajorGridColor B="192" A="166" R="192" G="192"/>
         <ZDAASMinorGridColor B="240" A="166" R="240" G="240"/>
         <ZDAASOriginColor B="0" A="166" R="0" G="0"/>
         <ZDAASBorderColor B="255" A="180" R="188" G="202"/>
        </ZDataAreaAppearanceSettings>
        <ZLinearAxis BundleGenericTokenMode="0" AllInputTrackingMode="3" ZLAScalingLocked="0" BundleBurstMode="0" ZLAShowScaleValues="TRUE" ZLATranslationLocked="FALSE" BundleAlignmentMode="3" ZLAShowCustomName="FALSE" ZLAShowMinorDivisions="1" ZLAShowMajorDivisions="1">
         <BundleInput UsingGlobalDefaultAccuracy="TRUE" BundleMeasID="{x_meas}" InputDataSetTrackingMode="0" BundleIndex="0" BundleDataSetID="{zero_euid}" AccuracyType="0" InputUsingDefaultNumberFormat="TRUE" MaxAccuracy="0" MinAccuracy="0">
          <InputNumberFormatter SNUpperExponent="7" ZLLowerValue="-0" SNThresholdAllowed="1" EngineeringNotation="3" OutputFormatMode="1" FixedDecimals="2" ScientificNotation="3" RangeLower="-1.797693134862316e+307" SignificantFigures="3" SNLowerExponent="-4" ZLThresholdAllowed="0" RangeUpper="1.797693134862316e+307" Resolution="0" ZLUpperValue="0"/>
         </BundleInput>
         <BundleInput UsingGlobalDefaultAccuracy="TRUE" BundleMeasID="{y_meas}" InputDataSetTrackingMode="0" BundleIndex="1" BundleDataSetID="{zero_euid}" AccuracyType="0" InputUsingDefaultNumberFormat="TRUE" MaxAccuracy="0" MinAccuracy="0">
          <InputNumberFormatter SNUpperExponent="7" ZLLowerValue="-0" SNThresholdAllowed="1" EngineeringNotation="3" OutputFormatMode="1" FixedDecimals="2" ScientificNotation="3" RangeLower="-1.797693134862316e+307" SignificantFigures="3" SNLowerExponent="-4" ZLThresholdAllowed="0" RangeUpper="1.797693134862316e+307" Resolution="0" ZLUpperValue="0"/>
         </BundleInput>
         <ZLAMajorGridColor B="192" A="255" R="192" G="192"/>
         <ZLAMinorGridColor B="240" A="255" R="240" G="240"/>
         <ZLAScaleValueColor B="0" A="255" R="0" G="0"/>
        </ZLinearAxis>
        <ZPACurveFitSelections ZPACurveFitState="TRUE"/>
        <ZTwoDimensionDataRenderBasicProperties ZTDDRBPDataPointAppearance="0" ZTDDRBPSmoothingPointCount="0" ZTDDRBPDependentOffset="0" ZTDDRBPApplyMasterOpacity="0" ZTDDRBPLineThicknessSetting="1" ZTDDRBPUseSolidLine="1" ZTDDRBPShowDependentUncertainty="0" ZTDDRBPColorChoiceStrategy="2" ZTDDRBPShowConnectingLines="1" ZTDDRBPShowStandardDeviationStatistic="0" ZTDDRBPStatisticsOpacity="1" ZTDDRBPShowDataSymbol="0" ZTDDRBPShowSelectedStatistics="0" ZTDDRBPShowMaximumStatistic="0" ZTDDRBPShowStandardDeviationStatisticGradient="1" ZTDDRBPShowDataPoints="1" ZTDDRBPLockRenderer="0" ZTDDRBPConnectingLineStyle="0" ZTDDRBPShowMinimumStatistic="0" ZTDDRBPShowUncertainty="1" ZTDDRBPShowAreaUnderCurve="0" ZTDDRBPUsageName="" ZTDDRBPShowRenderer="1" ZTDDRBPIndependentOffset="0" ZTDDRBPAntialiasedDrawing="1" ZTDDRBPShowMedianStatistic="0" ZTDDRBPMasterOpacity="25" ZTDDRBPShowCurveFits="1" ZTDDRBPLineStyle="1" ZTDDRBPActive="1" ZTDDRBPFillDescenderOrRectangle="FALSE" ZTDDRBPShowIndependentUncertainty="0" ZTDDRBPShowMeanStatistic="1" ZTDDRBPDataPointSize="4" ZTDDRBPDataSymbolSize="10" ZTDDRBPShowModeStatistic="0" ZTDDRBPUseBlackForConnectingLine="FALSE">
         <ZTDDRBPBaseColor B="0" A="255" R="0" G="0"/>
        </ZTwoDimensionDataRenderBasicProperties>
       </ZPlotArea>
      </LineGraphPlotAreaElement>
     </CSLineGraph>
    </WorkbookItem>
'''
    # --- Find insertion point: inside <WorkbookPage>...</WorkbookPage>, before </WorkbookPage> ---
    # Search for the closing </WorkbookPage> tag; insert the graph just before it.
    anchor = "</WorkbookPage>"
    idx = xml.rfind(anchor)
    if idx < 0:
        return xml, False

    # If a CSLineGraph already exists in this WorkbookPage, skip (don't double-inject).
    page_start = xml.rfind("<WorkbookPage", 0, idx)
    if page_start >= 0:
        page_block = xml[page_start:idx]
        if "CSLineGraph" in page_block:
            return xml, False  # graph already present, leave as-is

    new_xml = xml[:idx] + graph_block + xml[idx:]
    return new_xml, True


def _blank_base_xml() -> str:
    """Return a minimal valid DSProExperiment main.xml.

    Used as a fallback when no --base-template is supplied. The structure
    mirrors a known-good Capstone export: Header, DataRepository with time
    measurement, empty CalculationManager, ExperimentControl with
    CommonSamplingRate, and an empty WorkbookPage.
    """
    euid_time = "{" + str(uuid.uuid4()) + "}"
    euid_trial = "{" + str(uuid.uuid4()) + "}"
    return f'''<DSProExperiment>
 <Header LanguageID="409" Version="2.12.2" Language="enu" DigitCharacters="" ImportedFileName="" DecimalSeparator="." ArgumentSeparator=","/>
 <NameFactory>
  <namespace name="Run"/>
  <namespace name="WorkbookPage">
   <nameID value="1"/>
  </namespace>
 </NameFactory>
 <AVDeviceEnumerator>
  <VideoDevices/>
  <AudioDevices/>
 </AVDeviceEnumerator>
 <Hardware Version="1">
  <UnconnectedSensor/>
 </Hardware>
 <DataRepository CurrentTrialID="{euid_trial}">
  <SelectionManager/>
  <MasterTimeMeasurement NamingConvention="2" DefaultUnit="256" ShowMeasurementSymbol="FALSE" GenericType="1" MaxAccuracy="0" ShowUnits="TRUE" UsingGlobalDefaultAccuracy="0" BaseUnit="256" DefaultMinimumDisplayValue="0" MinAccuracy="9.9999999999999995e-07" LongName="Time" UsePreferredColor="FALSE" AccuracyType="0" Visible="TRUE" ShortName="time" DefaultAccuracy="9.9999999999999995e-07" MeasurementName="Time" SymbolName="t" PreferredColor="4294967295" EUID="{euid_time}" DefaultMaximumDisplayValue="10"/>
 </DataRepository>
 <CalculationManager>
  <Container RulesVersion="1.1000000000000001" Scope="2" Count="0"/>
  <Container RulesVersion="1.1000000000000001" Scope="1" Count="0">
  </Container>
 </CalculationManager>
 <ExperimentControl>
  <ExperimentSettingsCollection ActiveSettingsId="1">
   <ExperimentSettings SettingsId="1">
    <RecordingMode Value="Continuous"/>
    <UseCommonSamplingRate Value="1"/>
    <CommonSamplingRate Units="7936" Value="20"/>
    <TargetSensor Value="{{00000000-0000-0000-0000-000000000000}}"/>
    <ToolMode Value="Record"/>
    <ActiveSensorSettings SensorUid="{{00000000-0000-0000-0000-000000000000}}"/>
    <SensorSettingsCollection/>
   </ExperimentSettings>
  </ExperimentSettingsCollection>
 </ExperimentControl>
 <Workspace>
  <Workbook IsLegacyPageFormat="FALSE" WorkbookDpiX="162" CurrentPage="0" DefaultDisplayFontSize="1" WorkbookDpiY="162" PageFormat="0">
   <WorkbookPage SnapToGuides="1" Locked="0" Name="Page #1" ShowMasterPage="TRUE" EUID="{euid_time}" PageID="1" EnableMargins="1" SnapToGrid="1" ShowAllPalettesChecked="TRUE">
    <PageControlBar VisibilityConfigurable="TRUE" Closable="TRUE" Visible="TRUE">
     <RecordReplayModeSelector Visible="TRUE"/>
     <Clock Visible="TRUE"/>
     <ContinuousMode Visible="TRUE"/>
     <SampleRateSensorSelector Visible="TRUE"/>
     <SampleRateControl Visible="TRUE"/>
     <RecordingConditions Visible="TRUE"/>
     <DeleteLastRun Visible="TRUE"/>
    </PageControlBar>
    <PageDisplayPalette VisibilityConfigurable="TRUE" Closable="TRUE" Visible="TRUE">
     <ObjNameLineGraph Visible="TRUE"/>
     <ObjNameDataTable Visible="TRUE"/>
     <ObjNameDigits Visible="TRUE"/>
     <ObjNameEmpty Visible="TRUE"/>
    </PageDisplayPalette>
    <PageSize Width="1760" Height="965"/>
   </WorkbookPage>
  </Workbook>
  <Journal NextSnapshotIndex="0"/>
 </Workspace>
 <PageToolManager ActivePage="0">
  <SensorPage>
   <RunVisibilitySettings ShowChannelNameID="TRUE" ShowRunNames="TRUE" ShowRuns="TRUE" ShowMeasurementUnits="TRUE" ShowRunSymbols="TRUE"/>
  </SensorPage>
  <CalculationPage>
   <RunVisibilitySettings ShowChannelNameID="TRUE" ShowRunNames="TRUE" ShowRuns="TRUE" ShowMeasurementUnits="TRUE" ShowRunSymbols="TRUE"/>
  </CalculationPage>
  <UserEnteredDataPage>
   <RunVisibilitySettings ShowChannelNameID="TRUE" ShowRunNames="TRUE" ShowRuns="TRUE" ShowMeasurementUnits="TRUE" ShowRunSymbols="TRUE"/>
  </UserEnteredDataPage>
  <Calculator ShowSimpleButton="TRUE" ShowTimerModeButton="TRUE" ShowTableHeaders="TRUE" ShowScientificButton="TRUE" ShowFilterButton="TRUE" ShowSpecialButton="TRUE" ShowFunctionButtons="TRUE" ShowStatisticsButton="TRUE" ShowPrettyPrint="TRUE" ShowPropertyButtons="TRUE" ShowCustomButton="TRUE" ShowSymbolButtons="TRUE" ShowHintText="TRUE" ShowLogicButton="TRUE" ShowAngleModeButtons="TRUE"/>
 </PageToolManager>
</DSProExperiment>'''


def _build_cap(base: Path, profile: Dict[str, Any], out: Path) -> Tuple[Optional[Path], Dict[str, Any]]:
    """Copy base .cap, patch main.xml per profile, re-package. Never raises.

    If *base* does not exist, a minimal blank .cap is generated from
    `_blank_base_xml` so the tool still produces an openable file.
    """
    import shutil

    manifest: Dict[str, Any] = {
        "profile": profile.get("description", ""),
        "sampling_hz": profile.get("sampling_hz"),
        "injected": {},
    }

    # --- Resolve the source XML ---
    if base.exists():
        try:
            shutil.copy2(base, out)
        except OSError as exc:
            manifest["error"] = f"cannot copy base template: {exc}"
            return None, manifest
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            data = {n: zf.read(n) for n in names}
        original_xml = data.get("main.xml", b"").decode("utf-8", "replace")
        xml = original_xml
    else:
        # Fallback: build a blank .cap from scratch
        manifest["fallback_blank"] = True
        xml = _blank_base_xml()
        # Write the blank zip so later code can read it back
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("main.xml", xml.encode("utf-8"))
        original_xml = xml

    # --- Apply injections ---
    # Order matters:
    #   1. columns first  -> yields euid_by_name used for graph axis binding
    #   2. formulas next  -> needs the column units (BaseUnit dims) so its
    #      variable references carry the right dimension
    #   3. graph last     -> binds X/Y to the just-registered column EUIDs
    xml, ok1 = _inject_sampling_rate(xml, float(profile.get("sampling_hz", 0)))
    manifest["injected"]["sampling_rate"] = ok1

    # unit map for the formula parser (column name -> BaseUnit id string)
    col_units = {c.get("name", ""): str(c.get("unit", ""))
                 for c in profile.get("columns", [])}

    xml, ok3, col_euids = _inject_columns(xml, profile.get("columns", []))
    manifest["injected"]["columns"] = ok3

    xml, ok2 = _inject_calculation_columns(
        xml, profile.get("formulas", []), units=col_units)
    manifest["injected"]["formulas"] = ok2

    xml, ok4 = _inject_graph(xml, profile.get("axes", {}),
                             profile.get("ranges", {}), euid_by_name=col_euids)
    manifest["injected"]["graph"] = ok4
    # axes_bound reflects whether the *first* graph's X/Y resolved to real
    # column EUIDs. If the base already ships a graph we skip injection
    # (ok4 False) and flag it so the user knows to bind manually in Capstone.
    axes = profile.get("axes", {})
    first = next((v for k, v in axes.items() if k.startswith("graph")), {})
    x_bound = first.get("x", "") in col_euids
    y_bound = first.get("y", "") in col_euids
    manifest["injected"]["axes_bound"] = bool(ok4 and x_bound and y_bound)

    # R-04: Verify XML validity before repackaging!
    if xml != original_xml and not _is_valid_xml(xml):
        manifest["error"] = "XML corruption during injection. Aborted to prevent Capstone crash."
        manifest["injected"] = {"sampling_rate": False, "formulas": False, "columns": False, "graph": False}
        return out, manifest

    # Plain-text paste-ready fallback
    manifest["calc_text"] = [
        {"name": f.get("name"), "text": f.get("text", "")}
        for f in profile.get("formulas", [])
    ]

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        if base.exists():
            for n, b in data.items():
                if n == "main.xml":
                    zf.writestr(n, xml.encode("utf-8"))
                else:
                    zf.writestr(n, b)
        else:
            zf.writestr("main.xml", xml.encode("utf-8"))

    return out, manifest


# ---------------------------------------------------------------------------
# Stage entry point
# ---------------------------------------------------------------------------
def run(doc_path: Path, profile_name: str, base_template: Optional[Path],
        outdir: Path, exp: str) -> int:
    outdir = outdir.resolve()
    (outdir / "stage_a").mkdir(parents=True, exist_ok=True)

    profiles_path = Path(__file__).resolve().parent.parent / "config" / "sampling_profiles.json"
    try:
        profiles = json.loads(profiles_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"error: cannot load sampling profiles: {exc}", file=sys.stderr)
        return 2
        
    if profile_name not in profiles:
        print(f"error: unknown profile {profile_name!r}. Available: "
              f"{', '.join(profiles)}", file=sys.stderr)
        return 2
    profile = profiles[profile_name]

    # Step 1: confirm the document actually mentions this profile.
    try:
        # Updated to match the refactored _capx.py method name
        doc_text = _capx.extract_document_text(doc_path)
    except Exception as exc:  
        print(f"error: could not read document {doc_path}: {exc}", file=sys.stderr)
        return 1
        
    hits, hit_toks = _doc_matches(doc_text, profile)
    if hits < 1:
        print(f"warning: document mentions none of the {profile_name} "
              f"profile's signature tokens; proceeding but verify by hand.",
              file=sys.stderr)

    manifest = {
        "experiment": exp,
        "profile": profile_name,
        "doc_match_hits": hits,
        "doc_match_tokens": hit_toks,
        "cap_file": None,
    }

    # Step 2: build the preconfigured .cap
    cap_path = outdir / "stage_a" / f"{exp}.cap"
    if base_template and base_template.exists():
        built, cap_manifest = _build_cap(base_template, profile, cap_path)
    else:
        # No user-supplied base template: fall back to the bundled
        # blank.base.cap (in skill's assets dir) which is a known-good
        # empty 850 DAQ .cap. This gives a fully working .cap without
        # requiring the user to source a base template.
        skill_root = Path(__file__).resolve().parent.parent
        bundled = skill_root / "assets" / "blank.base.cap"
        if bundled.exists():
            built, cap_manifest = _build_cap(bundled, profile, cap_path)
            cap_manifest["note"] = (
                "No --base-template supplied; used bundled blank.base.cap. "
                "For instrument-specific setups (DAQ channels, sensor "
                "calibrations), provide --base-template of the same family."
            )
        else:
            # Last resort: generate a minimal skeleton from _blank_base_xml
            blank_base = outdir / "stage_a" / "_blank_base.cap"
            if not blank_base.exists():
                with zipfile.ZipFile(blank_base, "w", zipfile.ZIP_DEFLATED) as zf:
                    zf.writestr("main.xml", _blank_base_xml().encode("utf-8"))
            built, cap_manifest = _build_cap(blank_base, profile, cap_path)
            cap_manifest["note"] = (
                "Neither --base-template nor bundled blank.base.cap found; "
                "used minimal generated skeleton. Expect reduced functionality."
            )
    manifest["cap_file"] = str(built) if built else None
    manifest["cap_manifest"] = cap_manifest
    (outdir / "stage_a" / "cap_inject.json").write_text(
        json.dumps(cap_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8")

    # Always emit the paste-ready formula manifest.
    manifest["calc_text"] = [
        {"name": f.get("name"), "text": f.get("text", "")}
        for f in profile.get("formulas", [])
    ]
    (outdir / "stage_a" / "preconfig_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    status = "cap built" if manifest.get("cap_file") else "manifest only (no cap)"
    print(f"stage A: {status} ({profile_name}, {hits} doc tokens matched) "
          f"-> {outdir / 'stage_a' / 'preconfig_manifest.json'}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(prog="capstone-labmate preconfig",
                                description="Stage A: build a preconfigured .cap")
    p.add_argument("--doc", required=True, type=Path,
                   help="instructor experiment document (.pdf/.docx/.txt)")
    p.add_argument("--profile", required=True,
                   help="sampling profile key from config/sampling_profiles.json")
    p.add_argument("--base-template", type=Path, default=None,
                   help="known-good base .cap of the same instrument family")
    p.add_argument("--outdir", required=True, type=Path,
                   help="working directory for artifacts")
    p.add_argument("--exp", default="exp",
                   help="experiment tag (output .cap stem)")
    a = p.parse_args(argv)
    return run(a.doc.resolve(), a.profile,
               a.base_template, a.outdir.resolve(), a.exp)


if __name__ == "__main__":
    raise SystemExit(main())
