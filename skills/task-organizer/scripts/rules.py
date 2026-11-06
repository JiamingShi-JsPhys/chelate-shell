"""rules.py -- optional placement-rule configuration (profiles).



By default the tool uses a built-in, hard-coded placement table (see

``BUILTIN_PLACEMENT``). A user may override it with a YAML file named

``.task-organizer.yml`` placed either at the project root or in their home

directory.



The YAML is intentionally parsed by a small, dependency-free reader tailored

to the documented schema:



    placement:

      - priority: 1

        keywords: [draft, intermediate, temp, tmp]

        target: process

      - priority: 2

        keywords: [final, deliverable]

        target: results

    defaults:

      target: process



Domain profiles

------------------------

A single file can carry **several named rule sets** so that one data pack

covers several disciplines. ``default_profile`` picks the active one; the

CLI's ``--profile`` overrides it:



    default_profile: pharma



    profiles:

      general:

        placement:

          - priority: 1

            keywords: [final, deliverable]

            target: results

        defaults:

          target: process



      pharma:

        placement:

          - priority: 1

            keywords: [原始数据, raw, 实验数据, lab]

            target: material/initial

          - priority: 2

            keywords: [最终版, 定稿, final]

            target: results

          - priority: 3

            keywords: [临床报告, 病例, clinical]

            target: results

        defaults:

          target: process



A flat document (``placement`` / ``defaults`` at the top level, no

``profiles``) keeps working exactly as before.



Where files actually land

-------------------------

Rules only classify files whose provenance is *not* already known. The

authoritative mapping is:



- registered as user material   -> ``material/initial/``  (verbatim, never renamed)

- registered as AI-downloaded   -> ``material/downloaded/``

- matched by these rules        -> the rule's target

- otherwise                     -> ``defaults.target`` (built-in: ``process``)



``material/initial/`` is deliberately **not** the fallback: it is reserved

for the user's own material so the tool can never collide with it.



If the file is absent, the built-in rules are used. If the file is present

but cannot be parsed, a warning is emitted and the built-in rules are used --

the tool never crashes on a malformed config.

"""

from __future__ import annotations



import os

from dataclasses import dataclass, field

from pathlib import Path

from typing import Dict, List, Optional, Tuple



from scripts.utils import logger



#: Filename searched for in the project root and the user's home directory.

CONFIG_FILENAME = ".task-organizer.yml"



#: Built-in placement table, used when no config is found or parsing fails.

#: Each entry: (priority, keywords, target). First match wins when sorted by

#: priority ascending; the tool also stops at the first keyword match in list

#: order (priority is the documented tie-breaker).

#:

#: The old ``download / reference`` keyword rule was **removed**.

#: "Downloaded" is a *provenance* (the assistant fetched it), not something

#: a filename can express -- see :mod:`scripts.sources`. ``process`` is now

#: the fallback so unclassified assistant output never lands in the

#: user-reserved ``material/initial/``.

#:

#: The keyword table is the *fallback* for files with no declared

#: provenance, so it now also understands Chinese deliverable / draft words.

#: A live test showed ``综述_xxx.txt`` / ``报告_xxx.docx`` falling through to

#: ``process/`` because only English ``final``/``deliverable`` were recognised

#: -- the finished article never reached ``results/``.

BUILTIN_PLACEMENT: List[Tuple[int, List[str], str]] = [

    (1, ["final", "deliverable", "定稿", "最终版", "综述", "报告",
         "终稿", "总结", "小结"], "results"),

    (2, ["draft", "intermediate", "temp", "tmp", "raw", "草稿", "临时"], "process"),

]



#: Fallback target when no keyword matches and provenance is unknown.

#: ``process`` (was ``material/initial``) -- see module docstring.

BUILTIN_DEFAULT_TARGET = "process"





@dataclass

class Rules:

    """Resolved placement rules.



    Attributes

    ----------

    placement:

        List of ``(priority, keywords, target)`` triples.

    default_target:

        Fallback target when no keyword matches.

    name:

        Profile name these rules came from (``"builtin"`` or the YAML

        profile key). Informational only.

    source:

        Path of the config the rules were loaded from, if any.

    """



    placement: List[Tuple[int, List[str], str]] = field(default_factory=list)

    default_target: str = BUILTIN_DEFAULT_TARGET

    name: str = "builtin"

    source: Optional[Path] = None



    def target_for(self, name: str) -> str:

        """Return the standard sub-dir for a file *name* (priority then order)."""

        lower = name.lower()

        ordered = sorted(self.placement, key=lambda r: r[0])

        for _priority, keywords, target in ordered:

            for kw in keywords:

                if kw.lower() in lower:

                    return target

        return self.default_target





def builtin_rules() -> Rules:

    """Return a fresh copy of the hard-coded rules."""

    return Rules(

        placement=[(p, list(k), t) for p, k, t in BUILTIN_PLACEMENT],

        default_target=BUILTIN_DEFAULT_TARGET,

        name="builtin",

    )





def _strip_comment(line: str) -> str:

    """Remove a trailing ``# ...`` comment that is not inside quotes."""

    out = []

    in_single = False

    in_double = False

    for ch in line:

        if ch == "'" and not in_double:

            in_single = not in_single

        elif ch == '"' and not in_single:

            in_double = not in_double

        elif ch == "#" and not in_single and not in_double:

            break

        out.append(ch)

    return "".join(out).rstrip()





def _parse_inline_list(token: str) -> List[str]:

    """Parse an inline flow list ``[a, b, c]`` into a list of scalars."""

    token = token.strip()

    if not (token.startswith("[") and token.endswith("]")):

        return [_parse_scalar(token)]

    inner = token[1:-1].strip()

    if not inner:

        return []

    parts = []

    buf = []

    in_single = False

    in_double = False

    for ch in inner:

        if ch == "'" and not in_double:

            in_single = not in_single

            buf.append(ch)

        elif ch == '"' and not in_single:

            in_double = not in_double

            buf.append(ch)

        elif ch == "," and not in_single and not in_double:

            parts.append("".join(buf))

            buf = []

        else:

            buf.append(ch)

    if buf:

        parts.append("".join(buf))

    return [_parse_scalar(p) for p in parts if p.strip() != ""]





def _parse_scalar(token: str) -> str:

    """Parse a scalar value, stripping surrounding quotes."""

    token = token.strip()

    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):

        return token[1:-1]

    return token





def _parse_scalar_value(body: str):

    """Parse a scalar / inline-list body that sits after a ``key:``."""

    body = body.strip()

    if body.startswith("[") or body.startswith("{"):

        return _parse_inline_list(body)

    return _parse_scalar(body)





def _parse_mapping(indent: int, lines: List[Tuple[int, str]], idx: int):

    """Parse a mapping at the given *indent*. Returns ``(dict, next_index)``."""

    result: Dict = {}

    while idx < len(lines):

        cur_indent, cur_text = lines[idx]

        if cur_indent < indent or cur_text.startswith("- "):

            break

        if ":" not in cur_text:

            idx += 1

            continue

        key, _, body = cur_text.partition(":")

        key = _parse_scalar(key)

        body = body.strip()

        if body == "":

            # A nested block may follow on deeper-indented lines.

            if idx + 1 < len(lines) and lines[idx + 1][0] > indent:

                child_indent = lines[idx + 1][0]

                value, idx = _parse_block(child_indent, lines, idx + 1)

                result[key] = value

            else:

                result[key] = None

                idx += 1

            continue

        result[key] = _parse_scalar_value(body)

        idx += 1

    return result, idx





def _parse_list(indent: int, lines: List[Tuple[int, str]], idx: int):

    """Parse a list whose dash lines sit at *indent*. Returns ``(list, next)``."""

    result: List = []

    while idx < len(lines):

        cur_indent, cur_text = lines[idx]

        if cur_indent != indent or not cur_text.startswith("- "):

            break

        # Gather this item's lines: the dash line plus everything deeper.

        end = idx + 1

        while end < len(lines) and lines[end][0] > indent:

            end += 1

        item_lines = lines[idx:end]

        head = item_lines[0][1][2:].strip()  # content right after "- "

        # Re-base the dash line to the mapping indent (indent + 2) so the

        # inline first key and the following keys align.

        norm: List[Tuple[int, str]] = [(indent + 2, head)] + item_lines[1:]

        if ":" in head and not head.startswith("[") and not head.startswith("{"):

            value, _ = _parse_mapping(indent + 2, norm, 0)

        else:

            value = _parse_scalar_value(head) if head != "" else None

        result.append(value)

        idx = end

    return result, idx





def _parse_block(indent: int, lines: List[Tuple[int, str]], idx: int):

    """Dispatch to mapping/list parsing based on the first line."""

    if idx >= len(lines):

        return (None, idx)

    _cur_indent, cur_text = lines[idx]

    if cur_text.startswith("- "):

        return _parse_list(indent, lines, idx)

    return _parse_mapping(indent, lines, idx)





def _mini_yaml_load(text: str) -> dict:

    """Parse the supported YAML subset into a Python dict.



    Raises ``ValueError`` on anything it cannot represent; callers should

    catch this and fall back to built-in rules.

    """

    lines: List[Tuple[int, str]] = []

    for raw in text.splitlines():

        if "\t" in raw:

            raise ValueError("tabs are not supported; use spaces")

        cleaned = _strip_comment(raw)

        if cleaned.strip() == "":

            continue

        indent = len(raw) - len(raw.lstrip(" "))

        lines.append((indent, cleaned.strip()))



    if not lines:

        # A comment-only / blank file is a valid "no overrides" config

        # (that is exactly what `init` writes as its template). Treat it as

        # an empty mapping so callers fall back to built-in rules *silently*

        # instead of warning about an "empty document".

        return {}



    root_indent = lines[0][0]

    value, _ = _parse_block(root_indent, lines, 0)

    if not isinstance(value, dict):

        raise ValueError("top-level must be a mapping")

    return value





def _resolve_rules(data: dict, name: str = "config") -> Rules:

    """Turn a parsed dict into a :class:`Rules`."""

    placement_raw = data.get("placement") or []

    if not isinstance(placement_raw, list):

        raise ValueError("placement must be a list")



    placement: List[Tuple[int, List[str], str]] = []

    for entry in placement_raw:

        if not isinstance(entry, dict):

            raise ValueError("each placement entry must be a mapping")

        priority = entry.get("priority", 0)

        keywords = entry.get("keywords") or []

        if isinstance(keywords, str):

            keywords = [keywords]

        target = entry.get("target")

        if target is None:

            raise ValueError("placement entry missing target")

        if not isinstance(keywords, list):

            keywords = [_parse_scalar(str(keywords))]

        try:

            priority = int(priority)  # type: ignore[arg-type]

        except (TypeError, ValueError):

            priority = 0

        placement.append((priority, [str(k) for k in keywords], str(target)))



    defaults = data.get("defaults") or {}

    default_target = str(

        defaults.get("target", BUILTIN_DEFAULT_TARGET)

    )



    return Rules(

        placement=placement,

        default_target=default_target,

        name=name,

    )





def profile_names(data: dict) -> List[str]:

    """Return the profile names declared in a parsed config document."""

    profiles = data.get("profiles")

    if not isinstance(profiles, dict):

        return []

    return sorted(str(k) for k in profiles.keys())





def _select_profile(data: dict, profile: Optional[str]) -> Tuple[dict, str]:

    """Pick the mapping that holds the active rules.



    Returns ``(mapping, profile_name)``. Resolution order:



    1. explicit *profile* (CLI ``--profile``) -- must exist, else ValueError;

    2. ``default_profile`` from the document;

    3. the document itself (flat layout).



    A document with no ``profiles`` key is always treated as flat, so old

    configs keep working untouched.

    """

    profiles = data.get("profiles")

    if not isinstance(profiles, dict) or not profiles:

        if profile:

            raise ValueError(

                f"profile '{profile}' requested but the config declares no profiles"

            )

        return data, "config"



    if profile is None:

        profile = data.get("default_profile")

        if profile is None:

            # No default and none requested: fall back to the flat layout if

            # it carries rules, otherwise the first declared profile.

            if data.get("placement") or data.get("defaults"):

                return data, "config"

            profile = sorted(str(k) for k in profiles.keys())[0]



    key = str(profile)

    if key not in profiles:

        available = ", ".join(sorted(str(k) for k in profiles.keys()))

        raise ValueError(f"unknown profile '{key}' (available: {available})")



    body = profiles[key]

    if not isinstance(body, dict):

        raise ValueError(f"profile '{key}' must be a mapping")

    return body, key





def load_rules(

    root: Optional[Path] = None,

    extra_path: Optional[Path] = None,

    profile: Optional[str] = None,

) -> Rules:

    """Load placement rules.



    Search order

    -----------

    1. ``extra_path`` if provided (explicit --config).

    2. ``<root>/.task-organizer.yml``.

    3. ``<home>/.task-organizer.yml``.

    4. Built-in rules (always the fallback).



    Parameters

    ----------

    profile:

        Name of a profile declared under ``profiles:`` in the config. When

        omitted, ``default_profile`` is used, then the flat layout.



    A missing file yields built-in rules silently. A present-but-unparseable

    file (including an unknown profile name) yields a warning plus built-in

    rules.

    """

    candidates: List[Path] = []

    if extra_path is not None:

        candidates.append(Path(extra_path))

    if root is not None:

        candidates.append(Path(root) / CONFIG_FILENAME)

    home = Path.home() / CONFIG_FILENAME

    candidates.append(home)



    for path in candidates:

        if not path.is_file():

            continue

        try:

            text = path.read_text(encoding="utf-8")

        except OSError as exc:

            logger.warning(f"rules: cannot read {path} ({exc}); using built-in")

            return builtin_rules()

        try:

            data = _mini_yaml_load(text)

            body, profile_name = _select_profile(data, profile)

            rules = _resolve_rules(body, name=profile_name)

            if not rules.placement:

                # An empty / comment-only config (exactly what ``init`` writes

                # as its template) means "use the built-in rules" -- NOT "no

                # keywords, dump everything to process". Fall back silently so

                # ``报告`` / ``final`` still route to results.

                built = builtin_rules()

                built.source = path

                return built

            rules.source = path

            logger.info(

                f"rules: loaded {path} "

                f"(profile={profile_name}, {len(rules.placement)} placement rules)"

            )

            return rules

        except Exception as exc:  # noqa: BLE001 - parse failure must not crash

            logger.warning(

                f"rules: failed to parse {path} ({exc}); using built-in rules"

            )

            return builtin_rules()



    return builtin_rules()





def available_profiles(

    root: Optional[Path] = None, extra_path: Optional[Path] = None

) -> List[str]:

    """Return the profile names available in the first config found."""

    candidates: List[Path] = []

    if extra_path is not None:

        candidates.append(Path(extra_path))

    if root is not None:

        candidates.append(Path(root) / CONFIG_FILENAME)

    candidates.append(Path.home() / CONFIG_FILENAME)

    for path in candidates:

        if not path.is_file():

            continue

        try:

            data = _mini_yaml_load(path.read_text(encoding="utf-8"))

        except Exception:  # noqa: BLE001

            continue

        return profile_names(data)

    return []





def target_for(name: str, rules: Optional[Rules] = None) -> str:

    """Public helper: which standard sub-dir does *name* go into?"""

    return (rules or builtin_rules()).target_for(name)

