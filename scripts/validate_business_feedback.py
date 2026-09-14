"""Validate optional, evidenced causal feedback separately from transaction graphs."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from validate_research_process import ProcessIssue


def canonical_feedback_mechanism_sha256(loop: Mapping[str, Any]) -> str:
    """The review binds all mechanism content, excluding the review itself."""
    content = {key: value for key, value in loop.items() if key != "review"}
    encoded = json.dumps(
        content, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_business_model_feedback(
    feedback: Any,
    graph: Any,
    source_ids: set[str],
    passes: Any,
    *,
    declared: bool = True,
) -> list[ProcessIssue]:
    """Absence is valid; an asserted supported mechanism must be complete.

    A graph cycle establishes neither causation nor a reinforcing business effect.
    Those judgments remain the responsibility of the independent evidence review.
    """
    issues: list[ProcessIssue] = []
    root = "evidence-ledger.json.business_model_feedback"

    def fail(code: str, path: str, message: str) -> None:
        issues.append(ProcessIssue("error", "business-model-feedback-" + code, root + path, message))

    def nonblank(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def identifier(value: Any) -> bool:
        return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9-]{0,63}", value) is not None

    if not declared:
        return issues
    if not isinstance(feedback, dict):
        fail("shape", "", "declared feedback must be an object")
        return issues
    if feedback.get("version") != "1.0":
        fail("version", ".version", "must equal 1.0")
    if not nonblank(feedback.get("reason")):
        fail("reason", ".reason", "must explain the evidence assessment, including when no mechanism is established")
    loops = feedback.get("loops")
    if not isinstance(loops, list):
        fail("loops", ".loops", "must be an array")
        return issues
    if feedback.get("status") == "not_established":
        if loops:
            fail("not-established-loops", ".loops", "not_established must have no displayable mechanisms")
        return issues
    if feedback.get("status") != "supported":
        fail("status", ".status", "must be supported or not_established")
        return issues
    if not loops:
        fail("loops", ".loops", "supported feedback must contain at least one complete mechanism")
        return issues

    def graph_ids(key: str) -> set[str]:
        values = graph.get(key) if isinstance(graph, dict) else None
        return {item["id"] for item in values if isinstance(item, dict) and identifier(item.get("id"))} if isinstance(values, list) else set()

    actor_ids, flow_ids = graph_ids("actors"), graph_ids("flows")
    pass_values = [item for item in passes if isinstance(item, dict)] if isinstance(passes, (list, tuple)) else []
    primary_actors = {item.get("actor_id") for item in pass_values
                      if item.get("role") == "primary_research" and nonblank(item.get("actor_id"))}
    loop_ids: set[str] = set()

    def optional_refs(item: dict[str, Any], key: str, known: set[str], path: str) -> None:
        if key not in item:
            return
        value = item[key]
        if (not isinstance(value, list) or not all(isinstance(ref, str) for ref in value)
                or len(value) != len(set(value)) or any(ref not in known for ref in value)):
            fail("references", path + "." + key, "must contain unique valid IDs from the original participant graph")

    for loop_index, loop in enumerate(loops):
        loop_path = f".loops[{loop_index}]"
        if not isinstance(loop, dict):
            fail("loop", loop_path, "must be an object")
            continue
        loop_id = loop.get("id")
        if not identifier(loop_id) or loop_id in loop_ids:
            fail("loop-id", loop_path + ".id", "must be a unique lowercase mechanism ID")
        else:
            loop_ids.add(loop_id)
        if not nonblank(loop.get("title")):
            fail("title", loop_path + ".title", "must describe this company's causal mechanism")

        states = loop.get("states")
        state_ids: set[str] = set()
        if not isinstance(states, list) or len(states) < 2:
            fail("states", loop_path + ".states", "must contain at least two defined operating states")
            states = []
        for index, state in enumerate(states):
            path = f"{loop_path}.states[{index}]"
            if not isinstance(state, dict):
                fail("state", path, "must be an object")
                continue
            state_id = state.get("id")
            if not identifier(state_id) or state_id in state_ids:
                fail("state-id", path + ".id", "must be a unique lowercase causal-state ID")
            else:
                state_ids.add(state_id)
            for key in ("label", "definition"):
                if not nonblank(state.get(key)):
                    fail("state-text", path + "." + key, "must define a changing business condition, not merely a participant")
            optional_refs(state, "actor_ids", actor_ids, path)

        links = loop.get("links")
        if not isinstance(links, list) or not links:
            fail("links", loop_path + ".links", "must contain the ordered causal links, including the return to the first state")
            links = []
        link_ids: set[str] = set()
        outgoing = {state_id: [] for state_id in state_ids}
        incoming = {state_id: [] for state_id in state_ids}
        ordered_pairs: list[tuple[str, str]] = []
        loop_sources: set[str] = set()
        for index, link in enumerate(links):
            path = f"{loop_path}.links[{index}]"
            if not isinstance(link, dict):
                fail("link", path, "must be an object")
                continue
            link_id = link.get("id")
            if not identifier(link_id) or link_id in link_ids:
                fail("link-id", path + ".id", "must be a unique lowercase causal-link ID")
            else:
                link_ids.add(link_id)
            source, target = link.get("source"), link.get("target")
            if (not isinstance(source, str) or not isinstance(target, str)
                    or source not in state_ids or target not in state_ids or source == target):
                fail("endpoints", path, "source and target must name two different states in this mechanism")
            else:
                outgoing[source].append(target)
                incoming[target].append(source)
                ordered_pairs.append((source, target))
            if not nonblank(link.get("mechanism")):
                fail("mechanism", path + ".mechanism", "must explain why this state change influences the next")
            evidence_type = link.get("evidence_type")
            if evidence_type not in ("fact", "management_claim", "inference"):
                fail("evidence-type", path + ".evidence_type", "must distinguish fact, management_claim or inference")
            for key in ("conditions", "break_conditions"):
                values = link.get(key)
                if not isinstance(values, list) or not all(nonblank(value) for value in values):
                    fail("conditions", path + "." + key, "must be an array of nonblank statements")
                elif evidence_type == "inference" and not values:
                    fail("inference-conditions", path + "." + key, "inferred causation requires both applicability and falsifying conditions")
            refs = link.get("source_ids")
            refs_valid = isinstance(refs, list) and bool(refs) and all(isinstance(ref, str) for ref in refs)
            if not refs_valid or len(refs) != len(set(refs)) or any(ref not in source_ids for ref in refs):
                fail("sources", path + ".source_ids", "must contain nonempty unique sources from this company package")
            else:
                loop_sources.update(refs)
            locations = link.get("source_locations")
            if (not isinstance(locations, dict) or not refs_valid or set(locations) != set(refs)
                    or not all(nonblank(location) for location in locations.values())):
                fail("source-locations", path + ".source_locations", "must map exactly every source ID to a precise page or section")
            optional_refs(link, "flow_ids", flow_ids, path)

        if (len(links) != len(state_ids) or len(state_ids) < 2
                or any(len(outgoing[state_id]) != 1 or len(incoming[state_id]) != 1 for state_id in state_ids)):
            fail("cycle", loop_path + ".links", "each state must have exactly one incoming and one outgoing causal link")
        reached: set[str] = set()
        pending = [ordered_pairs[0][0]] if ordered_pairs else []
        while pending:
            current = pending.pop()
            if current in reached:
                continue
            reached.add(current)
            pending.extend(outgoing[current])
        if reached != state_ids:
            fail("cycle-connected", loop_path + ".links", "all states must belong to one connected directed cycle")
        if ordered_pairs and any(
            target != ordered_pairs[(index + 1) % len(ordered_pairs)][0]
            for index, (_, target) in enumerate(ordered_pairs)
        ):
            fail("cycle-order", loop_path + ".links", "links must follow the cycle in order and the final link must return to the starting state")

        review = loop.get("review")
        if not isinstance(review, dict):
            fail("review", loop_path + ".review", "must bind an independent review to the mechanism")
            continue
        if review.get("verdict") != "accepted":
            fail("review-verdict", loop_path + ".review.verdict", "supported feedback requires an accepted verdict; completed review alone does not accept the mechanism")
        if not nonblank(review.get("conclusion")):
            fail("review-conclusion", loop_path + ".review.conclusion", "must record the causal assessment and its limits")
        try:
            expected_hash = canonical_feedback_mechanism_sha256(loop)
        except (TypeError, ValueError, OverflowError):
            fail("hash", loop_path + ".review.mechanism_sha256", "mechanism must be finite canonical JSON")
        else:
            if review.get("mechanism_sha256") != expected_hash:
                fail("hash", loop_path + ".review.mechanism_sha256", "must match the entire mechanism excluding review")
        pass_id = review.get("pass_id")
        matches = [item for item in pass_values if isinstance(pass_id, str) and item.get("id") == pass_id]
        if len(matches) != 1:
            fail("review-pass", loop_path + ".review.pass_id", "must identify one existing independent review pass")
            continue
        reviewer = matches[0]
        reviewer_actor = reviewer.get("actor_id")
        if (reviewer.get("role") not in ("adversarial_review", "source_audit")
                or reviewer.get("execution") not in ("isolated_agent", "isolated_context")
                or reviewer.get("status") != "completed" or not nonblank(reviewer_actor)
                or reviewer_actor in primary_actors):
            fail("review-pass", loop_path + ".review.pass_id", "review must be completed and isolated from primary research")
        accessed = reviewer.get("source_ids_accessed")
        if (not isinstance(accessed, list) or not all(isinstance(ref, str) for ref in accessed)
                or not loop_sources.issubset(set(accessed))):
            fail("review-sources", loop_path + ".review.pass_id", "reviewer must declare access to every source used by this mechanism")
    return issues
