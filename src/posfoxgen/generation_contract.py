"""Check explicit generation instructions, never infer scientific truth from them.

The Harness supplies source-grounded content and three independently authored
debate positions. Passing checks their completeness, not their correctness.
No word-count or small-print convention is introduced by this module.
"""

import re
import math

from .logic import read_object


STORY_TOPICS = ("problem", "input", "output", "model", "innovation", "key_metrics", "source_figures")
DEBATE_ROLES = {"content_advocate", "science_reviewer", "visual_planner"}
CONTENT_ROLES = {"background", "method", "evidence", "limitations"}
AUXILIARY_ROLES = {"tiny_gray_footnote", "auxiliary_footnote", "ai_explanatory_note", "footnote", "microtext"}


def _placeholder_instructions(text):
    """Catch explicit positive reservation instructions, not prohibitions.

    This small bilingual lint is supplementary to the structured render_mode.
    It cannot determine what an image model actually draws.
    """
    for clause in re.split(r"[.!?。！？；;,，\n]", text):
        if re.search(r"\b(?:do not|don't|never|no|without)\b|(?:不要|不允许|禁止|不得|无需)", clause, re.I):
            continue
        if re.search(r"\b(?:leave|keep|reserve)\b.{0,45}\b(?:blank|empty|placeholder|space|box|slot)s?\b|\b(?:use|insert|draw|show|add|include)\b.{0,20}\b(?:placeholder|dummy|blank box)s?\b|\b(?:replace|fill)\b.{0,35}\blater\b|留白|占位|预留.{0,12}(?:图|表|位|空)|(?:之后|后续).{0,10}替换", clause, re.I):
            yield clause.strip()


def _source_checker(asset_table, blockers):
    assets = asset_table if isinstance(asset_table, list) else asset_table.get("assets", asset_table.get("items", []))
    ids = {a.get("id") for a in assets}

    def check(record, context):
        sources = record.get("source_ids")
        if not isinstance(sources, list) or not sources:
            blockers.append({"code": "missing_source", "message": f"{context} needs paper source IDs"})
            return set()
        for source in sources:
            if source not in ids:
                blockers.append({"code": "unknown_source", "message": f"{context} references unknown source {source}"})
        return set(sources)
    return check


def validate_content_debate(asset_table, technical_story, debate):
    """Require rich source-backed components and three explicit debate records.

technical_story maps each STORY_TOPICS key to {text, source_ids}. The debate
has participants [{role, reviewer, independent, positions, blockers}], decisions
[{topic, resolution, source_ids}], and a top-level blockers list. Resolved
participant blockers may remain as history. No API or scientific grader runs.
"""
    asset_table, technical_story, debate = map(read_object, (asset_table, technical_story, debate))
    blockers = []
    source_check = _source_checker(asset_table, blockers)
    technical_story = technical_story if isinstance(technical_story, dict) else {}
    debate = debate if isinstance(debate, dict) else {}
    for topic in STORY_TOPICS:
        record = technical_story.get(topic)
        if not isinstance(record, dict) or not str(record.get("text", "")).strip():
            blockers.append({"code": "missing_technical_story", "message": f"Explain {topic} from this paper; explicitly state non-applicability if needed", "topic": topic})
        else:
            source_check(record, topic)
    participants = debate.get("participants", [])
    roles = {p.get("role") for p in participants}
    if roles != DEBATE_ROLES or len(participants) != len(DEBATE_ROLES):
        blockers.append({"code": "missing_debate_role", "message": "Exactly one content advocate, science reviewer and visual planner is required"})
    names = [p.get("reviewer") for p in participants]
    if any(not n for n in names) or len(set(names)) != len(names) or any(p.get("independent") is not True for p in participants):
        blockers.append({"code": "independent_debate_required", "message": "Three distinct named participants must independently author their positions"})
    positions = set()
    for participant in participants:
        if not participant.get("positions"):
            blockers.append({"code": "missing_debate_position", "message": "Every participant needs source-grounded opinions"})
        for position in participant.get("positions", []):
            if position.get("assessment") and position.get("topic"):
                positions.add(position["topic"])
                source_check(position, f"{participant.get('role')} position")
            else:
                blockers.append({"code": "missing_debate_position", "message": "Opinions require a topic and assessment"})
        issues = participant.get("blockers")
        if not isinstance(issues, list) or any(not isinstance(i, dict) or i.get("resolved") is not True for i in issues):
            blockers.append({"code": "unresolved_debate_blocker", "message": f"{participant.get('role')} has unclosed blockers"})
    decisions = set()
    for decision in debate.get("decisions", []):
        if decision.get("topic") and decision.get("resolution"):
            decisions.add(decision["topic"])
            source_check(decision, "debate decision")
    required_topics = set(STORY_TOPICS) | {"logic"}
    if not required_topics <= positions or not required_topics <= decisions:
        blockers.append({"code": "debate_coverage", "message": "Opinions and explicit resolutions must cover logic and all technical story components"})
    if debate.get("blockers") != []:
        blockers.append({"code": "unresolved_debate_blocker", "message": "Debate must declare no unresolved blockers"})
    return {"pass": not blockers, "blockers": blockers, "semantic_fidelity_pass": None}


def validate_generation_handoff(asset_table, panel_plan, handoff, requirements=None, *, require_source_geometry=False):
    """Validate a full-paper, full-source-drawing handoff before image generation.

Existing panel_plan.panels[].image_slots {id,asset_id} is supported directly.
Each handoff slot must say render_mode='draw_full_source', with its source IDs
and instruction. content_plan retains background/method/evidence/limitations;
requirements can add content_requirements, essential_qualifiers and word_limits.
The checker cannot verify that the eventual generated pixels depict those data.
"""
    asset_table, panel_plan, handoff = map(read_object, (asset_table, panel_plan, handoff))
    requirements = read_object(requirements) if requirements is not None else {}
    blockers = []
    source_check = _source_checker(asset_table, blockers)
    source = asset_table.get("source", {}) if isinstance(asset_table, dict) else {}
    supplied = handoff.get("paper_source", {})
    if not source.get("path") or not source.get("paper_sha256") or supplied != source:
        blockers.append({"code": "paper_source_mismatch", "message": "Handoff must name the exact source paper and its SHA256 from asset_table.source"})
    if not handoff.get("user_requirements") or not str(handoff.get("prompt", "")).strip():
        blockers.append({"code": "missing_generation_brief", "message": "User requirements and a generation prompt must be explicit"})
    panels = {p["id"]: p for p in panel_plan.get("panels", [])}
    planned = {(p["id"], slot["id"]): slot for p in panels.values() for slot in p.get("image_slots", [])}
    supplied_slots = {}
    for slot in handoff.get("image_slots", []):
        key = (slot.get("panel_id"), slot.get("id"))
        if key in supplied_slots:
            blockers.append({"code": "duplicate_image_slot", "message": f"Duplicate generated slot {key}"})
        supplied_slots[key] = slot
        sources = source_check(slot, f"image slot {key}")
        expected = planned.get(key)
        if expected is None:
            blockers.append({"code": "unknown_image_slot", "message": f"Unplanned generated slot {key}"})
        elif not set(expected.get("source_ids", expected.get("asset_ids", [expected.get("asset_id")]))).issubset(sources):
            blockers.append({"code": "slot_source_mismatch", "message": f"Slot {key} must draw its assigned paper source"})
        if slot.get("render_mode") != "draw_full_source" or not str(slot.get("instruction", "")).strip() or slot.get("placeholder") is True or slot.get("reserve_only") is True:
            blockers.append({"code": "source_not_drawn", "message": f"Slot {key} must draw the complete source figure/table, not reserve a box for later"})
        for instruction in _placeholder_instructions(slot.get("instruction", "")):
            blockers.append({"code": "placeholder_instruction", "message": "Source slot instruction contradicts full source drawing", "instruction": instruction})
    for key in planned.keys() - supplied_slots.keys():
        blockers.append({"code": "missing_image_slot", "message": f"Planned source image slot {key} is absent"})
    if require_source_geometry:
        blockers.extend(validate_source_geometry(asset_table, handoff))
    content = handoff.get("content_plan", [])
    roles = {item.get("role") for item in content if str(item.get("text", "")).strip()}
    for role in sorted(CONTENT_ROLES - roles):
        blockers.append({"code": "missing_content_role", "message": f"Retain source-backed {role}, rather than a slogan alone"})
    for item in content:
        source_check(item, f"content {item.get('id')}")
        if item.get("panel_id") not in panels:
            blockers.append({"code": "unknown_content_panel", "message": "Every content component must be placed in a planned panel"})
        if item.get("typography_role") in AUXILIARY_ROLES:
            blockers.append({"code": "auxiliary_text_forbidden", "message": "Tiny gray auxiliary footnotes and AI explanatory notes are disabled by default"})
    for requirement in requirements.get("content_requirements", []):
        matches = [item for item in content if requirement.get("id") in item.get("requirement_ids", []) and item.get("text")]
        if not matches or requirement.get("role") and not any(i.get("role") == requirement["role"] for i in matches):
            blockers.append({"code": "missing_user_content", "message": f"User requirement {requirement.get('id')} needs planned scientific content"})
    for qualifier in requirements.get("essential_qualifiers", []):
        matches = [i for i in content if qualifier.get("id") in i.get("requirement_ids", []) and i.get("text") and i.get("typography_role") in {"body", "scientific_qualifier"} and set(qualifier.get("source_ids", [])) <= set(i.get("source_ids", []))]
        if not matches:
            blockers.append({"code": "qualifier_not_in_body", "message": f"Essential qualifier {qualifier.get('id')} must remain in source-backed main body text"})
    approved_limits = requirements.get("word_limits", [])
    if any(limit not in approved_limits for limit in handoff.get("word_limits", [])):
        blockers.append({"code": "unauthorized_word_limit", "message": "Handoff word limits must be explicitly requested by the user"})
    approved_numbers = {str(item.get(key)) for item in approved_limits for key in ("max_words", "max_characters") if item.get(key) is not None}
    # Narrow, disclosed audit for common uniform-length instructions; this is
    # not a semantic classifier and does not reject scientific numeric prose.
    for sentence in re.split(r"[.!?。！？\n]", handoff.get("prompt", "")):
        uniform = re.search(r"\b(?:panel|section|block)s?\b|(?:每|所有|各).*(?:区块|模块|段|部分|海报)", sentence, re.I)
        if not uniform:
            continue
        counts = re.findall(r"(\d+)\s*(?:words?\b|字)", sentence, re.I)
        if any(count not in approved_numbers for count in counts):
            blockers.append({"code": "unauthorized_word_limit", "message": "Prompt contains an unrequested uniform word-count instruction", "instruction": sentence.strip()})
    for instruction in _placeholder_instructions(handoff.get("prompt", "")):
        blockers.append({"code": "placeholder_instruction", "message": "Generation prompt may not reserve source figures/tables as placeholders", "instruction": instruction})
    debate = validate_content_debate(asset_table, handoff.get("technical_story", {}), handoff.get("debate", {}))
    blockers.extend(debate["blockers"])
    return {"pass": not blockers, "blockers": blockers, "warnings": [], "semantic_fidelity_pass": None}


def validate_source_geometry(asset_table, handoff):
    """Check measured source sizes and planned envelopes; never certify image pixels."""
    blockers = []
    assets = {a.get("id"): a for a in asset_table.get("assets", [])}
    def block(code, message): blockers.append({"code": code, "message": message})
    for slot in handoff.get("image_slots", []):
        context = str(slot.get("id"))
        measured = slot.get("source_geometry")
        if not isinstance(measured, list) or not measured:
            block("missing_source_geometry", f"{context} needs measured source geometry")
            continue
        expected = {i for i in slot.get("source_ids", []) if assets.get(i, {}).get("path")}
        if {g.get("asset_id") for g in measured if isinstance(g, dict)} != expected:
            block("source_geometry_mismatch", f"{context} must measure each assigned visual source")
        ratios = []
        for g in measured:
            if not isinstance(g, dict):
                block("source_geometry_mismatch", f"{context} geometry must be an object"); continue
            a = assets.get(g.get("asset_id"), {})
            width, height = a.get("width"), a.get("height")
            if not all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) and n > 0 for n in (width, height)):
                block("source_geometry_mismatch", f"{context} source has no real pixel dimensions"); continue
            ratio = width / height; ratios.append(ratio)
            if g.get("pixel_size") != [width, height] or g.get("sha256") != a.get("sha256") or not isinstance(g.get("aspect_ratio"), (int, float)) or not math.isclose(g["aspect_ratio"], ratio, rel_tol=1e-6):
                block("source_geometry_mismatch", f"{context} geometry differs from authoritative source")
        frame = slot.get("planned_frame", [])
        if not isinstance(frame, list) or len(frame) != 4 or not all(isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) for n in frame) or min(frame[2:]) <= 0:
            block("missing_planned_frame", f"{context} needs a finite planned x,y,width,height frame"); continue
        policy = slot.get("geometry_policy")
        if policy == "native_table" and slot.get("native_table_source_checked") is True:
            continue
        if policy == "contain":
            continue
        if policy != "preserve_source_aspect" or len(ratios) != 1 or not math.isclose(frame[2] / frame[3], ratios[0], rel_tol=.01):
            block("source_frame_distortion", f"{context} needs a source-aspect frame or explicit contain; native tables require source-checked reflow")
    return blockers
