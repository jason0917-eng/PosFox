import pytest

from posfoxgen.memory import append_experience, retrieve_experience, select_best_valid


def entry(split="development"):
    return {"run_id": "r1", "split": split, "issues": [{"type": "overflow", "panel_id": "p1"}], "plan": {"action": "shorten source-grounded text"}, "trajectory": [{"operation": "text_edit", "target": "p1-text"}], "score_before": 60, "score_after": 70, "valid_after": True, "applicability": ["overflow", "dense text"]}


def test_heldout_experience_cannot_enter_optimizer_memory(tmp_path):
    with pytest.raises(ValueError, match="heldout"):
        append_experience(tmp_path / "memory.jsonl", entry("heldout"))
    assert not (tmp_path / "memory.jsonl").exists()


def test_retrieval_keeps_relevant_successes_and_failures(tmp_path):
    path = tmp_path / "memory.jsonl"
    append_experience(path, entry())
    failed = entry()
    failed.update(score_after=55, valid_after=False)
    append_experience(path, failed)
    unrelated = entry()
    unrelated["applicability"] = ["color"]
    unrelated["issues"] = [{"type": "color"}]
    append_experience(path, unrelated)
    result = retrieve_experience(path, ["overflow"])
    assert len(result) == 2
    assert {x["reward"] for x in result} == {10, -100}


def test_best_valid_is_not_invalid_high_score():
    result = select_best_valid([{"id": "invalid", "score": 99, "valid": False}, {"id": "good", "score": 75, "valid": True}])
    assert result["id"] == "good"


def test_no_valid_candidate_returns_none():
    assert select_best_valid([{"id": "bad", "score": 99, "valid": False}]) is None


def test_invalid_high_score_has_negative_reward_matching_quality(tmp_path):
    from posfoxgen.quality import reward

    item = entry()
    item.update(score_before=60, score_after=90, valid_after=False)
    stored = append_experience(tmp_path / "memory.jsonl", item)
    assert stored["reward"] < 0
    expected = reward({"score": 60, "valid": True}, {"score": 90, "valid": False})
    assert stored["reward"] == expected["reward"]


def test_statistics_aggregate_relevant_strategies_and_validity(tmp_path):
    from posfoxgen.memory import strategy_statistics

    path = tmp_path / "memory.jsonl"
    for strategy, after, valid in [("shorten", 70, True), ("shorten", 90, False), ("resize", 65, True)]:
        item = entry()
        item.update(strategy=strategy, score_after=after, valid_after=valid)
        append_experience(path, item)
    unrelated = entry()
    unrelated.update(strategy="recolor", applicability=["color"], issues=[{"type": "color"}])
    append_experience(path, unrelated)
    result = strategy_statistics(path, ["overflow"])
    assert set(result) == {"shorten", "resize"}
    assert result["shorten"]["count"] == 2
    assert result["shorten"]["valid_rate"] == 0.5
    assert result["resize"]["mean_reward"] == 5


def test_exploitation_chooses_highest_validity_adjusted_mean(tmp_path):
    from posfoxgen.memory import choose_strategy

    path = tmp_path / "memory.jsonl"
    for strategy, after in [("shorten", 70), ("resize", 65)]:
        item = entry()
        item["plan"]["strategy"] = strategy
        item["score_after"] = after
        append_experience(path, item)
    result = choose_strategy(path, ["overflow"], ["shorten", "resize"], exploration_rate=0, seed=7)
    assert result["strategy"] == "shorten"
    assert result["mode"] == "exploit"
    assert result["reason"]


def test_exploration_is_seeded_and_selects_supplied_candidate(tmp_path):
    from posfoxgen.memory import choose_strategy

    args = (tmp_path / "absent.jsonl", ["overflow"], ["shorten", "resize", "reflow"])
    first = choose_strategy(*args, exploration_rate=1, seed=42)
    second = choose_strategy(*args, exploration_rate=1, seed=42)
    assert first == second
    assert first["mode"] == "explore"
    assert first["strategy"] in args[2]


def test_selection_rejects_invalid_exploration_rate_and_no_candidates(tmp_path):
    from posfoxgen.memory import choose_strategy

    with pytest.raises(ValueError, match="exploration_rate"):
        choose_strategy(tmp_path / "none", [], ["s"], exploration_rate=1.1)
    with pytest.raises(ValueError, match="candidate"):
        choose_strategy(tmp_path / "none", [], [])


def test_statistics_do_not_trust_legacy_positive_reward_for_invalid_result(tmp_path):
    import json
    from posfoxgen.memory import strategy_statistics

    item = entry()
    item.update(strategy="unsafe", score_after=99, valid_after=False, reward=39)
    path = tmp_path / "legacy.jsonl"
    path.write_text(json.dumps(item) + "\n")
    assert strategy_statistics(path, ["overflow"])["unsafe"]["mean_reward"] == -100


def test_exploration_prefers_untried_strategy_and_preserves_candidate_payload(tmp_path):
    from posfoxgen.memory import choose_strategy

    path = tmp_path / "memory.jsonl"
    item = entry()
    item["strategy"] = "shorten"
    append_experience(path, item)
    candidate = {"strategy": "reflow", "scope": "panel"}
    result = choose_strategy(path, ["overflow"], [{"strategy": "shorten"}, candidate], exploration_rate=1, seed=0)
    assert result["strategy"] == "reflow"
    assert result["candidate"] == candidate
