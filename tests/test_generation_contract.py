import copy

import pytest

from posfoxgen.generation_contract import validate_generation_handoff, validate_content_debate


def generation_inputs():
    assets = {"source": {"path": "paper.pdf", "paper_sha256": "a" * 64}, "assets": [{"id": "fig1"}, {"id": "table1"}, {"id": "text1"}]}
    panels = {"panels": [{"id": "method", "image_slots": [{"id": "diagram", "asset_id": "fig1"}]}, {"id": "results", "image_slots": [{"id": "table", "asset_id": "table1"}]}]}
    requirements = {"content_requirements": [{"id": "rq-method", "role": "method"}], "essential_qualifiers": [{"id": "limited-domain", "source_ids": ["text1"]}]}
    handoff = {"paper_source": copy.deepcopy(assets["source"]), "user_requirements": ["Explain the method and show the measured evidence."], "prompt": "Draw the complete paper diagram and numerical table in their panels. Include source-backed explanatory prose.", "content_plan": [
        {"id": role, "panel_id": "method" if role in {"background", "method"} else "results", "role": role, "text": text, "source_ids": ["text1"], "typography_role": "body", "requirement_ids": ["rq-method"] if role == "method" else []}
        for role, text in (("background", "Prior approaches lack verifiable design feedback."), ("method", "An agent plans, renders and revises its design."), ("evidence", "The measured comparison reports a trade-off."), ("limitations", "Evaluation is limited to the sampled domain."))], "image_slots": [
        {"id": "diagram", "panel_id": "method", "source_ids": ["fig1"], "render_mode": "draw_full_source", "instruction": "Draw all diagram components, labels and arrows from Figure 1."},
        {"id": "table", "panel_id": "results", "source_ids": ["table1"], "render_mode": "draw_full_source", "instruction": "Draw all rows, columns, headers, values and comparison direction from Table 1."}], "word_limits": []}
    handoff["content_plan"][-1]["requirement_ids"] = ["limited-domain"]
    topics = ["problem", "input", "output", "model", "innovation", "key_metrics", "source_figures"]
    handoff["technical_story"] = {topic: {"text": "Source-backed explanation of " + topic, "source_ids": ["fig1"] if topic == "source_figures" else ["text1"]} for topic in topics}
    handoff["debate"] = {"participants": [{"role": role, "reviewer": role + "-agent", "independent": True, "positions": [{"topic": topic, "assessment": "Source evidence supports retaining " + topic, "source_ids": ["text1"]} for topic in topics + ["logic"]], "blockers": []} for role in ["content_advocate", "science_reviewer", "visual_planner"]], "decisions": [{"topic": topic, "resolution": "Retain source-backed " + topic, "source_ids": ["text1"]} for topic in topics + ["logic"]], "blockers": []}
    return assets, panels, handoff, requirements


def codes(result):
    return {x["code"] for x in result["blockers"]}


def test_complete_source_drawings_and_scientific_body_plan_pass_structural_gate():
    result = validate_generation_handoff(*generation_inputs())
    assert result["pass"], result
    assert result["semantic_fidelity_pass"] is None


@pytest.mark.parametrize("mode", ["placeholder", "reserve_only", "replace_later", ""])
def test_source_slot_cannot_be_a_placeholder_or_reserved_box(mode):
    a, p, h, r = generation_inputs(); h["image_slots"][0]["render_mode"] = mode
    assert "source_not_drawn" in codes(validate_generation_handoff(a, p, h, r))


def test_every_planned_slot_requires_its_exact_source_and_panel():
    a, p, h, r = generation_inputs(); h["image_slots"][0]["source_ids"] = ["table1"]
    h["image_slots"].pop()
    result = validate_generation_handoff(a, p, h, r)
    assert {"slot_source_mismatch", "missing_image_slot"} <= codes(result)


def test_slogan_only_content_cannot_replace_paper_explanation():
    a, p, h, r = generation_inputs(); h["content_plan"] = [{"id": "slogan", "role": "slogan", "text": "Design smarter!", "source_ids": ["text1"], "panel_id": "method"}]
    assert "missing_content_role" in codes(validate_generation_handoff(a, p, h, r))


def test_paper_and_unknown_source_references_are_checked():
    a, p, h, r = generation_inputs(); h["paper_source"]["paper_sha256"] = "different"
    h["content_plan"][0]["source_ids"] = ["nonexistent"]
    assert {"paper_source_mismatch", "unknown_source"} <= codes(validate_generation_handoff(a, p, h, r))


def test_essential_qualifier_must_remain_main_body_with_source():
    a, p, h, r = generation_inputs(); h["content_plan"][-1]["typography_role"] = "tiny_gray_footnote"
    result = validate_generation_handoff(a, p, h, r)
    assert {"auxiliary_text_forbidden", "qualifier_not_in_body"} <= codes(result)


@pytest.mark.parametrize("prompt", ["Use exactly 30 words per panel.", "每个区块限制30字。", "Maximum 40 words for every section."])
def test_prompt_cannot_invent_uniform_word_limits(prompt):
    a, p, h, r = generation_inputs(); h["prompt"] += prompt
    assert "unauthorized_word_limit" in codes(validate_generation_handoff(a, p, h, r))


def test_explicit_user_word_limit_is_allowed_but_not_a_harness_default():
    a, p, h, r = generation_inputs(); r["word_limits"] = [{"scope": "panel", "max_words": 30}]
    h["word_limits"] = copy.deepcopy(r["word_limits"]); h["prompt"] += " Use at most 30 words per panel."
    assert validate_generation_handoff(a, p, h, r)["pass"]
    h["word_limits"][0]["max_words"] = 20
    assert "unauthorized_word_limit" in codes(validate_generation_handoff(a, p, h, r))


def test_scientific_semicolon_is_not_banned_as_an_ai_note_heuristic():
    a, p, h, r = generation_inputs(); h["content_plan"][-1]["text"] = "The method is evaluated on one domain; transfer remains uncertain."
    assert validate_generation_handoff(a, p, h, r)["pass"]
    h["content_plan"][-1]["typography_role"] = "ai_explanatory_note"
    assert "auxiliary_text_forbidden" in codes(validate_generation_handoff(a, p, h, r))


def test_content_debate_requires_all_three_independent_roles_and_source_decisions():
    a, p, h, r = generation_inputs()
    assert validate_content_debate(a, h["technical_story"], h["debate"])["pass"]
    h["debate"]["participants"].pop()
    assert "missing_debate_role" in codes(validate_generation_handoff(a, p, h, r))


@pytest.mark.parametrize("topic", ["problem", "input", "output", "model", "innovation", "key_metrics", "source_figures"])
def test_rich_technical_story_cannot_omit_a_component(topic):
    a, p, h, r = generation_inputs(); h["technical_story"].pop(topic)
    assert "missing_technical_story" in codes(validate_generation_handoff(a, p, h, r))


def test_unresolved_debate_blocker_cannot_advance_to_generation():
    a, p, h, r = generation_inputs(); h["debate"]["participants"][1]["blockers"] = [{"id": "wrong-data", "resolved": False}]
    assert "unresolved_debate_blocker" in codes(validate_generation_handoff(a, p, h, r))
    h["debate"]["participants"][1]["blockers"][0]["resolved"] = True
    assert validate_generation_handoff(a, p, h, r)["pass"]


@pytest.mark.parametrize("instruction", ["Reserve a blank box for Figure 1 and replace it later.", "Use a placeholder instead of the complex original table.", "这里预留图片位置，后续再替换原图。"])
def test_instructions_cannot_contradict_full_source_mode(instruction):
    a, p, h, r = generation_inputs(); h["image_slots"][0]["instruction"] = instruction
    assert "placeholder_instruction" in codes(validate_generation_handoff(a, p, h, r))


def test_negative_placeholder_prohibition_is_accepted():
    a, p, h, r = generation_inputs(); h["prompt"] += " Do not use placeholders. 不要留白，不要后续替换；完整绘制原图。"
    assert validate_generation_handoff(a, p, h, r)["pass"]


def test_explicit_placeholder_flag_cannot_hide_behind_full_source_mode():
    a, p, h, r = generation_inputs(); h["image_slots"][0]["placeholder"] = True
    assert "source_not_drawn" in codes(validate_generation_handoff(a, p, h, r))
