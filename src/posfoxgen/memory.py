"""Development-only experience records; model weights are never modified here."""

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random

from .quality import reward as quality_reward

HELDOUT_SPLITS = {"heldout", "held-out", "test", "dev", "validation", "independent"}


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def append_experience(path, entry):
    if entry.get("split") in HELDOUT_SPLITS:
        raise ValueError("heldout evidence must never enter optimizer memory")
    if entry.get("split") not in {"development", "train", "training"}:
        raise ValueError("An explicit development or train split is required")
    required = {"run_id", "issues", "plan", "trajectory", "score_before", "score_after", "valid_after", "applicability"}
    if required - entry.keys():
        raise ValueError("Missing experience fields: " + ", ".join(sorted(required - entry.keys())))
    if not all(entry[k] for k in ("issues", "plan", "trajectory", "applicability")):
        raise ValueError("Experience requires issues, plan, actual trajectory and applicability")
    if not _number(entry["score_before"]) or not _number(entry["score_after"]):
        raise ValueError("Scores must be finite numbers")
    if not isinstance(entry["valid_after"], bool):
        raise ValueError("valid_after must explicitly state whether hard gates passed")
    record = dict(entry)
    outcome = quality_reward({"score": entry["score_before"]}, {"score": entry["score_after"], "valid": entry["valid_after"]})
    record["score_change"] = outcome["score_change"]
    record["reward"] = outcome["reward"]
    record["recorded_at"] = datetime.now(timezone.utc).isoformat()
    record["experience_id"] = hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def retrieve_experience(path, issues, limit=5):
    destination = Path(path)
    if not destination.exists():
        return []
    query = {str(x).casefold() for x in issues}
    matches = []
    for line in destination.read_text().splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        if record.get("split") not in {"development", "train", "training"}:
            continue
        terms = {str(x).casefold() for x in record.get("applicability", [])}
        terms |= {str(x.get("type", "")).casefold() for x in record.get("issues", [])}
        overlap = len(query & terms)
        if overlap:
            # Recompute old records too: a historical positive scalar must not
            # reward an invalid artifact after validity policy changes.
            if _number(record.get("score_before")) and _number(record.get("score_after")):
                outcome = quality_reward({"score": record["score_before"]}, {"score": record["score_after"], "valid": record.get("valid_after") is True})
                record["reward"] = outcome["reward"]
                record["score_change"] = outcome["score_change"]
            matches.append((overlap, record.get("recorded_at", ""), record))
    matches.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [x[2] for x in matches[:limit]]


def select_best_valid(candidates):
    valid = [c for c in candidates if c.get("valid") is True and not c.get("blockers") and _number(c.get("score"))]
    return max(valid, key=lambda c: c["score"], default=None)


def strategy_statistics(path, issues):
    """Summarize relevant development evidence by named repair strategy.

    Rewards are whole-poster score changes for valid repairs and the quality
    module's hard validity penalty otherwise. Raw score changes remain visible
    separately, so a failure cannot become a positive learning example.
    """
    groups = {}
    for record in retrieve_experience(path, issues, limit=None):
        plan = record.get("plan")
        name = record.get("strategy") or (plan.get("strategy") if isinstance(plan, dict) else None)
        if not isinstance(name, str) or not name.strip():
            name = "unspecified"
        name = name.strip()
        stats = groups.setdefault(name, {"count": 0, "valid_count": 0, "reward_sum": 0.0, "score_change_sum": 0.0})
        if not _number(record.get("reward")):
            continue
        stats["count"] += 1
        stats["valid_count"] += record.get("valid_after") is True
        stats["reward_sum"] += record["reward"]
        stats["score_change_sum"] += record.get("score_change", 0.0)
    result = {}
    for name, stats in sorted(groups.items()):
        n = stats["count"]
        if n:
            average = round(stats["reward_sum"] / n, 6)
            result[name] = {"count": n, "valid_count": stats["valid_count"], "valid_rate": round(stats["valid_count"] / n, 6), "mean_reward": average, "mean_effective_reward": average, "mean_score_change": round(stats["score_change_sum"] / n, 6)}
    return result


def choose_strategy(path, issues, candidates, exploration_rate=0.1, seed=None):
    """Use reproducible epsilon-greedy selection, with no model invocation.

    Candidates may be strategy-name strings or dictionaries containing a
    ``strategy``, ``id`` or ``name``. An exploration step prefers candidates
    without relevant history. Exploitation considers known candidates only,
    ordered by validity-adjusted mean reward, then valid rate.
    """
    if not _number(exploration_rate) or not 0 <= exploration_rate <= 1:
        raise ValueError("exploration_rate must be a finite number from 0 to 1")
    if not isinstance(candidates, (list, tuple)) or not candidates:
        raise ValueError("At least one repair strategy candidate is required")
    choices = {}
    for candidate in candidates:
        name = candidate if isinstance(candidate, str) else candidate.get("strategy", candidate.get("id", candidate.get("name"))) if isinstance(candidate, dict) else None
        if not isinstance(name, str) or not name.strip() or name.strip() in choices:
            raise ValueError("Every candidate needs a unique nonempty strategy name")
        choices[name.strip()] = candidate
    stats = strategy_statistics(path, issues)
    known = [name for name in choices if name in stats]
    untried = [name for name in choices if name not in stats]
    rng = random.Random(seed)
    explore = not known or rng.random() < exploration_rate
    if explore:
        selected = rng.choice(untried or list(choices))
        reason = "No relevant development evidence; explore an untried strategy" if not known else "Exploration draw; prefer an untried strategy when available"
        mode = "explore"
    else:
        selected = max(known, key=lambda name: (stats[name]["mean_reward"], stats[name]["valid_rate"], stats[name]["count"]))
        reason = "Highest mean whole-poster reward with invalid outcomes penalized; valid rate and sample count break ties"
        mode = "exploit"
    return {"strategy": selected, "candidate": choices[selected], "mode": mode, "reason": reason, "exploration_rate": exploration_rate, "seed": seed, "statistics": {name: stats[name] for name in choices if name in stats}}
