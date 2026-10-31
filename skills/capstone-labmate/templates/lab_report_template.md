# Lab Report Template

> **SYSTEM INSTRUCTION TO HOST LLM:**
> This template is generalized from a real LaTeX lab report. It contains no personal or institutional information, only the formatting skeleton and writing conventions. All `<...>` are placeholders to be filled by the Host LLM based on `stage_c/summary.json`, `stage_c/csv/*.csv`, and the lab manual. 
> **DO NOT hallucinate any numerical values (R-05).** The watermark at the end is appended automatically by `draft_report.py`. Do not generate it yourself.

---

# Lab <N>: <Lab Title> — Post-Lab Report

<Course Name> | Reported by: <Name> | Date: <Date>

---

## Purpose
<One paragraph explaining the objective: Use known quantities to calibrate/instrument parameters, use the calibration results to measure <target quantity>, identify <physical conclusion>, and verify <resolution/limiting cases>.>

## Apparatus
<List of apparatus, including models: host/sensors/accessories, and data acquisition software (PASCO Capstone).>

## Theory

### <Theory Section 1: Core Formula>
\[
<Formula> \tag{1}
\]
where `<Symbol Definition>`.

### <Theory Section 2: Physical Model>
\[
<Formula> \tag{2}
\]
\[
<Formula> \tag{3}
\]

### Key Constants
\[
<Constant Table: c, h, eV, hc, etc., as needed>
\]

## Part 1 — <Calibration / Preliminary Experiment: Determine <Parameter>>

<Describe the measurement angles of the central maximum position and the calibration line, and provide the angle difference calculation:>
\[
\theta = \theta_0 - \theta_{\text{peak}} = <Value>^\circ.
\]

| <Item> | <Accepted Value> | <Order/Index> | <Measured Quantity (<Unit>)> |
| --- | --- | --- | --- |
| <Calibration Line> | <Value> | 1 | <Value> |

**Exercise Q1.** <Verbatim question from the lab manual.>
\[
<Derivation process>
\approx \boxed{<Result>}
\]

**Exercise Q2.** <Verbatim question from the lab manual.>
<Answer: Explain the universality of this parameter (depends only on the instrument, not the measured object, hence applicable to all subsequent measurements).>

## Part 2 — <Formal Measurement 1: <Sample A> Data>
<Explain the peak extraction method and calculation formula; list all observed peaks below.>

| Peak Position (<Unit>) | <Δ Position> (<Unit>) | <Order> | Measured <Quantity> | Accepted <Quantity> | Error | Note |
| --- | --- | --- | --- | --- | --- | --- |
| <Value> | <Value> | 1 | <Value> | <Value> | <±x.x%> | Hit (<Category>) |
| <Value> | <Value> | 1 | <Value> | — | — | Noise |
| ... | ... | ... | ... | ... | ... | ... |

**Exercise Q3.** <Lab manual question.>
\[
<Step-by-step calculation: Measured = d·sin(θ), etc.>
\]

**Exercise Q4.** <Lab manual question: Percentage difference.>
\[
\frac{|<meas>-<acc>|}{<acc>}\times100\% \approx <x.xx\%>
\]

**<Subsequent Discussion Question Number>.** <Conclusive answer:> 
<Which peaks are true signals (error ≤ ~1%), and which are noise/stray light (near central maximum, not corresponding to any known value). Name them one by one.>

<figure Full-range scan>
![](<Name>.png)
*Fig. <N>: Full-range <Sample A> <Spectrum> (file `<Name>.png`).*

<figure Zoomed-in scan>
![](<Name>0.png)
*Fig. <N+1>: Zoomed-in <Sample A> <Spectrum> showing the weak <features> (file `<Name>0.png`). These lines are only <x>%–<y>% of the scale maximum and are invisible in the full-range scan.*

## Part 3 — <Formal Measurement 2: <Sample B>>
<Same structure as Part 2; if energy level/transition identification is involved, add ΔE and n_i derivation columns.>

| Peak <Position> | <Δ Position> | <Order> | Measured <Quantity> | <Intermediate Quantity> | <Derived Quantity> | Accepted <Quantity> | Error | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

**Exercise Q5–Q<k>.** <Answer lab manual questions one by one, with formulas + values.>
<Summary paragraph: State whether every characteristic/observable required by the manual was measured; explicitly state if weak signals were only visible after zooming in.>

<Full-range + Zoomed-in figure pairing, same as above.>

## Part 4 — <Formal Measurement 3 / Resolution Test>
<If the experiment involves "resolving double lines/limiting cases": provide the theoretical angular resolution calculation, compare it with the measured peak width, and honestly state negative conclusions like "detected but not resolved.">

**Exercise Q<k+1>.** ...

<Full-range + Zoomed-in figure pairing.>

## Discussion — <Why are these peaks so small / hard to find?>
<The weak signal intensity is only <x>%–<y>% of the full scale, buried in baseline noise during full-range scanning. Physical reasons:>
- **<Reason 1 (Transition probability/emission intensity)>**: ...
- **<Reason 2 (Instrument efficiency, e.g., high-order diffraction/detector response)>**: ...
- **<Reason 3 (Noise and sensitivity)>**: ...
<Final sentence: After zooming into the corresponding region and expanding the vertical axis, the weak peaks are clearly visible, confirming the instrument is working properly.>

## Conclusions
1. <Calibration result: Parameter = Value (uncertainty/source).>
2. <Sample A: N true signal peaks all matched (≤ x%), M near-center peaks identified as noise.>
3. <Sample B: All characteristics/observables required by the manual were measured, derived quantity ≈ ... successfully identified.>
4. <Resolution test: Detected but not resolved (or successfully resolved), providing theoretical separation vs. measured peak width.>
5. <Weak signals are only visible after zooming in, with intensity at x%–y% of full scale.>

*Figures uploaded separately: `<Name>.png`, `<Name>0.png`, ... (list all actual figures).*

**Note on file names.** The file `<X>0.png` is the **zoomed-in scan** of the weak signal region (expanded vertical axis, narrowed horizontal range, making the weak peaks occupying <x>%–<y>% of full scale visible); `<X>.png` is the corresponding **full-range scan**.

---

## STRICT FORMATTING RULES FOR HOST LLM (Do NOT output this section in the final report)

1. **Data Fidelity**: Every value must come from `summary.json` / `csv` / manual. Percentage error is always calculated as `|measured − accepted| / accepted × 100%`. Estimated values must be labeled as "Estimated".
2. **Table Columns**: Measurement tables MUST contain `Error` (%) and `Note` columns. `Note` values must be `Hit (<Category>)`, `Noise`, or `Calibration`. Anything not matching a known value is marked as `Noise` with a brief explanation.
3. **Exercise Questions**: Answer sequentially as `Exercise Q1, Q2, ...`. Copy the question number first, then provide the formula derivation. The final answer must be enclosed in `\boxed{}` (or **bold** in Markdown).
4. **Figures**: For every measurement Part, provide a "Full-range + Zoomed-in" pair. The zoomed-in caption MUST explain what was zoomed in and why it was invisible in the original figure (intensity percentage). If nothing was observed, write "Not observed" and analyze the reason. **Do NOT provide empty figures.**
5. **Coverage Check**: After drafting, cross-check against the lab manual requirements (Content/Exercises/Tables/Figures). Add any missing parts.
6. **Honest Negative Results**: If "double lines detected but unresolved", state the theoretical separation, measured peak width, and conclusion. Do not evade the question.
