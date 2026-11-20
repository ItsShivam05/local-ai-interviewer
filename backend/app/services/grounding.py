"""Evidence grounding and consistency checks for one evaluation. Pure functions, no model calls.

The model's analysis is useful but untrusted. This module checks it against the candidate's actual answer:

* every quote the grader cites must really occur in the answer (after normalising case, punctuation and spacing);
* a misconception counts as an error only if it is grounded (a verified "incorrect" quote supports it, or text it quotes is in
  the answer). Ungrounded ones are kept, clearly labelled as unverified, and never drive the classification;
* contradictions between the analysis and the scores are detected and resolved by small, documented, deterministic rules;
* the answer is classified (correct / correct but incomplete / partially correct / incorrect / no attempt / uncertain) so an
  incomplete explanation is never reported as a wrong one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..schemas import DimensionScores, EvidenceItem, LLMEvaluation

_WORD = re.compile(r"[a-z0-9]+")
_QUOTED = re.compile(r"[\"“'‘]([^\"”'’]{6,200})[\"”'’]")


_NON_ATTEMPT = re.compile(
    r"\b(i\s*)?(do\s*n[o']?t|don't|dont|cannot|can't|cant)\s+(really\s+)?(know|remember|recall|say)\b|\bno\s+(idea|clue)\b|"
    r"\bnot\s+(sure|certain)\b|\bi\s+have\s+no\s+(idea|experience)\b|^\s*(pass|skip|nothing|idk)\W*$", re.I)
_PURE_NON_ATTEMPT = re.compile(
    r"(i\s+)?(really\s+|honestly\s+)?(do\s*not|don'?t|dont|cannot|can'?t|cant)\s+(really\s+)?(know|remember|recall|say)(\s+(this|that|it|the\s+answer|sorry))?|"
    r"(i\s+have\s+)?no\s+(idea|clue)|(i\s*(am|'m)\s+)?not\s+(sure|certain)|idk|pass|skip|nothing|n\s*/?\s*a|next(\s+question)?", re.I)


def is_non_attempt(answer: str) -> bool:
    """A short reply that CONTAINS an "I don't know"-style phrase. It may still say something real ("Not sure, I think it uses a
    B-tree"), so on its own this only means: look closer."""
    text = (answer or "").strip()
    return len(text.split()) <= 12 and bool(_NON_ATTEMPT.search(text))


def is_pure_non_attempt(answer: str) -> bool:
    """The reply is NOTHING BUT such a phrase ("I don't know.", "idk", "pass"): there is no content a grader could credit."""
    text = re.sub(r"[\s.,!?;:…'\"-]+$", "", (answer or "").strip())
    text = re.sub(r"^(sorry|hmm+|um+|uh+|well|honestly)[\s,.]+", "", text, flags=re.I)
    return bool(text) and bool(_PURE_NON_ATTEMPT.fullmatch(text)) or not (answer or "").strip()


_PARTS = re.compile(r"[,;\n•·|]+|\s[-–]\s")
_EXPLAINS = re.compile(r"\b(is|are|was|were|be|means?|meant|use[sd]?|using|when|because|since|so|if|then|which|that|lets?|makes?|"
                       r"allows?|keeps?|returns?|stores?|gives?|has|have|can|cannot|should|would|will|prevents?|avoids?|ensures?|"
                       r"needs?|happens?|causes?|reduces?|increases?|works?|runs?|sends?|reads?|writes?)\b", re.I)
_ASKS_FOR_LIST = re.compile(r"^\W*(please\s+)?(list|name|enumerate|give)\b|\b(can|could) you (list|name)\b|"
                            r"\b(list|name) (the|all|some|a few|two|three|four|five|six|seven|\d+)\b|\bwhat are the\b|\bwhich of the\b", re.I)


def is_term_list(answer: str) -> bool:
    """An answer that is only a run of terms ("Mutable, immutable, hashable, memory, slicing, ...") with nothing explained.

    Review round 1 found such lists scored ~4.9: the grader credited the right words although no idea was explained. At least six
    comma/line-separated parts, none longer than four words, and no part that explains anything (no verb like "is", "means",
    "uses", "because"). Deliberately narrow: a terse answer that says what to do ("Use upserts, overwrite partitions, ...") is not
    capped; the grader judges it."""
    parts = [p.strip(" .:;*-\t") for p in _PARTS.split(answer or "")]
    parts = [p for p in parts if p]
    if len(parts) < 6 or any(len(p.split()) > 4 for p in parts):
        return False
    return not any(_EXPLAINS.search(p) for p in parts)


def asks_for_list(question: Optional[str]) -> bool:
    """"Name the HTTP methods" / "What are the SOLID principles?": a list of terms IS the answer, so it is never capped."""
    return bool(question and _ASKS_FOR_LIST.search(question))


def _norm(text: str) -> str:
    return " ".join(_WORD.findall((text or "").lower()))


def quote_in_answer(quote: str, answers: list[str], min_words: int = 2) -> bool:
    """True when `quote` (normalised) occurs in one of the answers. Very short quotes prove nothing and are not accepted.
    A quote may elide words with "..." - each fragment must then appear, in order."""
    fragments = [f for f in (_norm(x) for x in re.split(r"\.\.\.|…", quote or "")) if f]
    if not fragments or sum(len(f.split()) for f in fragments) < min_words:
        return False
    for ans in answers:
        hay = f" {_norm(ans)} "
        pos, ok = 0, True
        for f in fragments:
            i = hay.find(f" {f} ", pos)
            if i < 0:
                ok = False
                break
            pos = i + len(f)
        if ok:
            return True
    return False


_STOP = {"the", "and", "that", "this", "candidate", "said", "says", "states", "stated", "claims", "claimed", "thinks", "believes", "answer",
         "with", "for", "are", "was", "were", "not", "which", "what", "from", "they", "their", "there", "into", "than", "then", "when",
         "always", "never", "only", "also", "about", "incorrectly", "wrongly", "mentions", "mentioned", "suggests", "implies"}


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall((text or "").lower()) if len(t) > 2 and t not in _STOP}


def _related(a: str, b: str, threshold: float = 0.4) -> bool:
    """Content-word overlap (boilerplate such as "the candidate said" removed) between a misconception and a quoted error."""
    x, y = _tokens(a), _tokens(b)
    return bool(x and y) and len(x & y) >= 1 and len(x & y) / min(len(x), len(y)) >= threshold


_FIGURE = re.compile(r"\d+(?:[.,]\d+)*")
_NUMBER_WORDS = {w: str(i) for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
_NUMBER_WORDS.update({"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90",
                      "hundred": "100", "thousand": "1000", "million": "1000000"})


def _figure(text: str) -> str:
    t = text.replace(",", "")
    return t.rstrip("0").rstrip(".") if "." in t else t


def unsupported_figures(text: str, sources: list[str]) -> list[str]:
    """Figures (10 or more, or with decimals) in `text` that appear in none of the `sources`, as digits or as number words.

    Used for the suggested answer to a RESUME question: the grader does not know the candidate's project, so a number that the
    candidate, the question and the resume never mentioned is an invention. Single digits are ignored ("3 layers", "one SELECT")."""
    have: set[str] = set()
    for s in sources:
        low = (s or "").lower()
        have.update(_figure(m) for m in _FIGURE.findall(low))
        have.update(n for w, n in _NUMBER_WORDS.items() if re.search(rf"\b{w}\b", low))
    out: list[str] = []
    for m in _FIGURE.findall(text or ""):
        f = _figure(m)
        if f not in have and f not in out and (len(f.split(".")[0]) >= 2 or "." in f):
            out.append(f)
    return out


@dataclass
class Grounding:
    evidence: list[EvidenceItem]
    grounded_misconceptions: list[str]
    unverified_misconceptions: list[str]
    flags: list[dict[str, str]] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)
    dimension_scores: Optional[DimensionScores] = None
    confidence: str = "medium"
    classification: str = "partially_correct"


def verify_evidence(ev: LLMEvaluation, answers: list[str]) -> list[EvidenceItem]:
    out = []
    for item in ev.evidence:
        if not item.quote and not item.point:
            continue
        out.append(item.model_copy(update={"verified": quote_in_answer(item.quote, answers)}))
    return out


def split_misconceptions(misconceptions: list[str], evidence: list[EvidenceItem], answers: list[str]) -> tuple[list[str], list[str]]:
    """(grounded, unverified). Grounded: an 'incorrect' quote that really is in the answer supports it, or text the
    misconception itself quotes is found in the answer. Single verified 'incorrect' quote with a single misconception also counts."""
    wrong_quotes = [e for e in evidence if e.kind == "incorrect" and e.verified]
    grounded, unverified = [], []
    for m in misconceptions:
        quoted = [q for q in _QUOTED.findall(m) if quote_in_answer(q, answers)]
        support = [e for e in wrong_quotes if _related(m, e.point + " " + e.quote)]
        if quoted or support or (len(misconceptions) == 1 and len(wrong_quotes) == 1):
            grounded.append(m)
        else:
            unverified.append(m)
    return grounded, unverified


def classify(*, dims: DimensionScores, grounded_misconceptions: list[str], correct_points: list[str], confidence: str,
             non_attempt: bool, claimed_errors: int = 0) -> str:
    """Deterministic answer classification. Errors must be grounded to call an answer incorrect."""
    if non_attempt:
        return "no_attempt"
    if confidence == "low":
        return "uncertain"
    c, comp = dims.correctness, dims.completeness
    if grounded_misconceptions and c <= 4:
        return "incorrect"
    if not grounded_misconceptions and not correct_points and c <= 2:
        # nothing right and nothing provably wrong: a claimed-but-unverified error means the grader may be mistaken
        if claimed_errors:
            return "uncertain"
        return "no_attempt" if comp <= 1 else "incorrect"
    if c >= 7 and comp >= 7 and not grounded_misconceptions:
        return "correct"
    if c >= 7 and not grounded_misconceptions:
        return "correct_incomplete"
    return "partially_correct"


CLASSIFICATION_LABELS = {
    "correct": "Correct", "correct_incomplete": "Correct but incomplete", "partially_correct": "Partially correct",
    "incorrect": "Incorrect", "no_attempt": "No real attempt", "uncertain": "Uncertain (grader unsure)",
}


def ground(ev: LLMEvaluation, *, answers: list[str], non_attempt: bool, question: Optional[str] = None) -> Grounding:
    """Check one evaluation against the answer(s) it graded (for voice answers: raw transcript and repaired text)."""
    evidence = verify_evidence(ev, answers)
    grounded, unverified = split_misconceptions(ev.misconceptions, evidence, answers)
    dims = ev.dimension_scores.model_copy()
    flags: list[dict[str, str]] = []
    adjustments: list[str] = []
    confidence = ev.confidence

    unverified_quotes = [e for e in evidence if e.quote and not e.verified]
    if unverified_quotes:
        flags.append({"code": "unverified_quote", "message": f"{len(unverified_quotes)} quoted passage(s) cited by the grader were not found in the answer; they are shown as unverified."})
    if unverified:
        flags.append({"code": "ungrounded_misconception", "message": "Some claimed errors could not be tied to anything in the answer, so they are listed as unverified and not counted as mistakes."})

    # "I don't know"-style wording in a SHORT answer is only a non-attempt if the grader also saw nothing of value in it;
    # "You don't know the length upfront, so use a generator" is a real answer.
    # A reply that is nothing but the phrase is a non-attempt whatever the grader made of it (a fooled or generous grader cannot
    # turn "I don't know" into a good score). A short reply that merely contains the phrase is one only if the grader ALSO found
    # nothing right in it and scored it low.
    pure = bool(answers) and is_pure_non_attempt(answers[0])
    non_attempt = pure or (non_attempt and not ev.correct_points and dims.correctness <= 4)
    if non_attempt:
        high = [d for d in ("correctness", "completeness", "depth", "practical_application", "clarity") if getattr(dims, d) > 2]
        if high:
            for d in type(dims).model_fields:
                v = getattr(dims, d)
                if v is not None and v > 2:
                    setattr(dims, d, 2)
            adjustments.append("The answer was not a real attempt (e.g. \"I don't know\"), so every dimension was capped at 2.")
            flags.append({"code": "non_attempt_scored_high", "message": "The grader scored a non-attempt above 2; scores were capped."})
    else:
        if grounded and dims.correctness >= 8:
            flags.append({"code": "high_correctness_with_errors", "message": "Correctness was scored high although a verified error was found; confidence lowered."})
            confidence = "low" if confidence == "low" else "medium"
        # Requires >= 2 correct points and no claimed error at all (verified or not), so a forgotten misconception is not "corrected" away.
        if not grounded and not unverified and len(ev.correct_points) >= 2 and dims.correctness <= 3 and confidence != "low":
            # Nothing said was shown to be wrong: low marks belong under completeness, not correctness.
            adjustments.append(f"Correctness raised from {dims.correctness} to 5: no incorrect statement was identified, so the gaps are scored under completeness instead.")
            flags.append({"code": "incomplete_scored_as_incorrect", "message": "The answer was incomplete rather than wrong."})
            dims.correctness = 5
        if not ev.correct_points and dims.correctness >= 7 and not any(e.kind == "correct" and e.verified for e in evidence):
            flags.append({"code": "high_score_without_evidence", "message": "A high correctness score was given without citing anything correct; confidence lowered."})
            confidence = "low" if confidence == "low" else "medium"
        # last, so no rule above can lift a capped dimension again
        if answers and is_term_list(answers[0]) and not asks_for_list(question):
            high = [d for d in type(dims).model_fields if (getattr(dims, d) or 0) > 3]
            if high:
                for d in high:
                    setattr(dims, d, 3)
                adjustments.append("The answer lists terms without explaining any of them, so every dimension was capped at 3. "
                                   "Say what each idea means or why it matters to earn more.")
                flags.append({"code": "term_list", "message": "A list of terms with nothing explained; scores were capped at 3."})

    cls = classify(dims=dims, grounded_misconceptions=grounded, correct_points=ev.correct_points, confidence=confidence, non_attempt=non_attempt,
                   claimed_errors=len(unverified))
    return Grounding(evidence=evidence, grounded_misconceptions=grounded, unverified_misconceptions=unverified, flags=flags,
                     adjustments=adjustments, dimension_scores=dims, confidence=confidence, classification=cls)
