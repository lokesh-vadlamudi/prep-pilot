"""Prompts that turn the DGX model into a senior-SWE interview tutor."""
from __future__ import annotations

import json

from .llm import chat, chat_json
from .executor import USER_CODE_MARKER
from .models import Card, Concept, User

_PLAIN_MATH = (
    "Write complexities and math in plain text (e.g. O(n log n), 2^n), "
    "never LaTeX or $...$ delimiters."
)

USER_CONTEXT = (
    "The learner is a senior software engineer targeting senior/staff roles. "
    "Their stack: Go, Python, TypeScript/React, and cloud (AWS, GCP, Azure, Terraform). "
    "Prefer examples and trade-offs relevant to that background. " + _PLAIN_MATH
)

NEWGRAD_CONTEXT = (
    "The learner is a recent CS graduate preparing for entry-level SDE-1 interviews. "
    "They are still building fundamentals: explain from first principles, define jargon "
    "the first time you use it, prefer simple concrete examples over architecture "
    "war stories, and calibrate the bar to a strong junior candidate — do not expect "
    "senior-level depth, but do teach the right habits. {lang}" + _PLAIN_MATH
)


def learner_context(user: User | None) -> str:
    """Per-user context injected into every non-cached AI interaction."""
    if user is not None and user.level == "newgrad":
        lang = (user.lang or "python").strip()
        return NEWGRAD_CONTEXT.format(
            lang=f"Their preferred language is {lang.title()} — use it for all code examples. ")
    return USER_CONTEXT


async def diagnose_learning_plan(plan: dict, evidence: list[dict], learner: str = "") -> dict:
    """Use DGX to interpret learning evidence without letting it reschedule cards."""
    system = (
        "You are the diagnostic layer in an adaptive interview-learning system. "
        + (learner or USER_CONTEXT)
        + " The deterministic scheduler has already chosen the next action. Do not replace it. "
        "Select one recent missed concept. Describe it as an observed signal ('a recent miss "
        "suggests...'), not a fundamental deficiency. Never claim that misses on unrelated topics "
        "cause one another. Ground the diagnosis and one short retrieval question in the supplied "
        "question, feedback, and reference key points; check the technical premise of the question. "
        "If evidence is sparse, say so rather than inventing a weakness. Respond ONLY with JSON: "
        '{"diagnosis":"<1-2 sentences>","teaching_focus":"<one concrete focus>",'
        '"check_question":"<one question>"}'
    )
    payload = json.dumps({"recommendation": plan, "recent_evidence": evidence}, default=str)
    try:
        data = await chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": payload}],
            temperature=0.2,
            num_predict=700,
        )
        return {
            "available": True,
            "diagnosis": str(data.get("diagnosis", "")).strip(),
            "teaching_focus": str(data.get("teaching_focus", "")).strip(),
            "check_question": str(data.get("check_question", "")).strip(),
        }
    except Exception:  # noqa: BLE001 — the deterministic plan remains fully usable
        return {
            "available": False,
            "diagnosis": "DGX diagnosis is temporarily unavailable. Your adaptive plan is still active.",
            "teaching_focus": "",
            "check_question": "",
        }

# The app renders Mermaid; tell the model to draw when a picture helps.
DIAGRAM_HINT = (
    " When a diagram would make the explanation clearer (linked lists, trees, graphs, a "
    "traversal, control/data flow, or system-design components), include ONE simple, VALID "
    "Mermaid diagram in a ```mermaid fenced code block (e.g. `graph LR` or `flowchart TD` or "
    "`sequenceDiagram`). CRITICAL Mermaid syntax rules so it renders: wrap ANY node label that "
    "contains spaces, parentheses, punctuation, or symbols in double quotes — e.g. "
    'N5["Node 5 (unreachable)"], not N5[Node 5 (unreachable)]. Do NOT use <br/> or any HTML in '
    "labels. Keep labels short and alphanumeric where possible. Prefer a diagram over ASCII art. "
    "Only include one when it genuinely helps."
)


async def grade_free_answer(card: Card, concept: Concept, user_answer: str,
                            learner: str = "") -> dict:
    """Grade a free-text / coding answer. Returns {grade, correct, feedback}."""
    sys = (
        "You are a rigorous but encouraging engineering interviewer. "
        + (learner or USER_CONTEXT)
        + " Grade the candidate's answer against the reference. Be specific about "
        "what was missing or wrong, and name the strongest follow-up you'd ask next. "
        "Respond ONLY with JSON: "
        '{"grade": <0-5 SM-2 quality>, "correct": <bool>, "feedback": "<2-4 sentences>"}'
    )
    user = (
        f"QUESTION:\n{card.prompt}\n\n"
        f"REFERENCE ANSWER:\n{card.answer}\n\n"
        f"KEY POINTS / EXPLANATION:\n{card.explanation}\n\n"
        f"CANDIDATE ANSWER:\n{user_answer}"
    )
    try:
        data = await chat_json(
            [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        return {
            "grade": int(data.get("grade", 0)),
            "correct": bool(data.get("correct", False)),
            "feedback": str(data.get("feedback", "")).strip(),
        }
    except Exception as e:  # noqa: BLE001 — grading must never hard-fail the review
        return {"grade": 0, "correct": False, "feedback": f"(Auto-grade unavailable: {e})"}


async def answer_question(question: str, context: str = "", history: list[dict] | None = None,
                          learner: str = "") -> str:
    sys = (
        "You are an experienced engineer mentoring someone for interviews. "
        + (learner or USER_CONTEXT)
        + " Answer precisely and concisely with concrete examples and trade-offs. "
        "Use markdown. If the question is a system-design prompt, structure the answer "
        "(requirements, high-level design, data model, scaling, trade-offs). "
        "This is a running conversation — treat questions as follow-ups building on earlier turns."
        + DIAGRAM_HINT
    )
    ctx = f"\n\nRelevant topic the learner is studying:\n{context}" if context else ""
    messages = [{"role": "system", "content": sys}]
    messages += (history or [])[-8:]  # recent turns for follow-up context
    messages.append({"role": "user", "content": question + ctx})
    return await chat(
        messages,
        temperature=0.4, num_predict=1800,
    )


async def generate_harness(title: str, category: str, difficulty: str, pattern: str, language: str) -> dict:
    """Generate starter code + a self-contained test driver for a problem.

    The driver is appended AFTER the user's solution and must print exactly one
    line `PREPPILOT_RESULT:<json>` with {passed,total,cases:[{name,ok,expected,got}]}.
    """
    common = (
        "The judge grades by comparing the user's outputs to a known-correct reference's outputs, "
        "so you must NOT hardcode expected answers. The driver defines 6-9 varied test INPUTS "
        "(include edge cases), a normalizer that canonicalizes an output for comparison (sort when "
        "answer order is irrelevant), calls the entry function per input (recording an error marker "
        "on a throw), and prints exactly one final line "
        "'PREPPILOT_OUTPUTS:' + <json of {\"labels\":[...], \"outputs\":[...]}>. For linked-list/tree "
        "problems, build the structure from a plain array and serialize results back to arrays. The "
        "SAME driver runs against both the reference and the user code, so it must be deterministic."
    )
    if language == "go":
        sys = (
            "You are building a RELIABLE automated judge for a coding-interview trainer. "
            + USER_CONTEXT + " Language: Go (stdlib only). " + common + "\n"
            "GO STRUCTURE (important): driver_code is a COMPLETE compilable program: `package main`, "
            "an import block, any helpers, a line containing EXACTLY `" + USER_CODE_MARKER + "` on its "
            "own (the user's function is substituted there), and `func main()`. main() builds the "
            "inputs, calls the entry function, normalizes, and prints the PREPPILOT_OUTPUTS line using "
            "encoding/json (Marshal the payload, prepend the prefix). Error marker per case: a value "
            "like map[string]string{\"__error__\": \"...\"} (recover from panics). The program MUST "
            "compile with NO unused imports — if you import a package the user may need but you don't "
            "use, add `var _ = pkg.Symbol`. entry_name and reference_code must NOT include package or "
            "imports (just the function). starter_code is just the function stub.\n"
            "Respond ONLY with JSON: {\n"
            '  "entry_name": "TheFunction",\n'
            '  "starter_code": "func TheFunction(...) ... { // TODO\\n\\treturn ... }",\n'
            '  "reference_code": "a CORRECT func TheFunction(...) ... { ... } (no package/imports)",\n'
            "  \"driver_code\": \"complete package main program containing " + USER_CODE_MARKER + " and func main()\"\n"
            "}"
        )
    else:
        lang_note = {
            "python": "Language: Python 3, stdlib only. Driver is appended AFTER the user's function "
                      "(shared module). Print via print('PREPPILOT_OUTPUTS:' + json.dumps(payload)).",
            "javascript": "Language: JavaScript (Node), no packages. Driver is appended AFTER the "
                          "user's function. Print via console.log('PREPPILOT_OUTPUTS:' + JSON.stringify(payload)).",
        }[language]
        sys = (
            "You are building a RELIABLE automated judge for a coding-interview trainer. "
            + USER_CONTEXT + " " + lang_note + " " + common + "\n"
            "Respond ONLY with JSON: {\n"
            '  "entry_name": "the function the user implements",\n'
            '  "starter_code": "minimal stub defining that function w/ correct signature + TODO body",\n'
            '  "reference_code": "a CORRECT standalone implementation of entry_name (same signature)",\n'
            '  "driver_code": "the input+normalize+print harness; assumes entry_name is defined above it"\n'
            "}"
        )
    user = f"Problem: {title}\nCategory: {category}\nDifficulty: {difficulty}\nIntended pattern: {pattern}"
    data = await chat_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        temperature=0.2, num_predict=2600,
    )
    return {
        "entry_name": str(data.get("entry_name", "solve")),
        "starter_code": str(data.get("starter_code", "")),
        "reference_code": str(data.get("reference_code", "")),
        "driver_code": str(data.get("driver_code", "")),
    }


async def review_code(title: str, language: str, code: str, test_summary: str, mode: str,
                      history: list[dict], learner: str = "") -> str:
    """Mentor chat: review / explain-line-by-line / free chat, with code in context."""
    base = (
        "You are a patient senior engineer pair-programming with the candidate on a coding "
        "problem. " + (learner or USER_CONTEXT)
        + " Be concrete and encouraging; use markdown and short code snippets."
        + DIAGRAM_HINT
    )
    mode_instr = {
        "review": (
            "Review their CURRENT code for correctness, edge cases, complexity, and style. "
            "Give 2-5 specific, prioritized suggestions. If a test is failing, focus on the likely cause. "
            "Do NOT just paste a full solution unless they're totally stuck — nudge them."
        ),
        "explain": (
            "Explain their code clearly, line by line (or block by block), in plain language a "
            "developer can follow. Note the purpose of each part, the complexity, and any bug you see."
        ),
        "chat": "Answer their question about this problem or their code helpfully and concisely.",
    }.get(mode, "Help them with this problem.")

    sys = base + " " + mode_instr
    ctx = (
        f"PROBLEM: {title}\nLANGUAGE: {language}\n"
        f"TEST RESULT: {test_summary or 'not run yet'}\n\n"
        f"CANDIDATE'S CURRENT CODE:\n```{language}\n{code}\n```"
    )
    messages = [{"role": "system", "content": sys}, {"role": "user", "content": ctx}]
    messages += history[-8:]  # recent turns
    return await chat(messages, temperature=0.4, num_predict=1500)


async def generate_hint_ladder(title: str, category: str, difficulty: str, pattern: str) -> list[str]:
    """A 4-rung escalating hint ladder (nudge → structure → steps → pseudocode)."""
    sys = (
        "You are a coding-interview coach who gives the SMALLEST useful nudge first. "
        + USER_CONTEXT + " For the named problem, produce a 4-rung hint ladder that escalates: "
        "rung 1 = a gentle nudge naming the key observation or which pattern to consider (NO approach); "
        "rung 2 = the data structure / high-level approach; "
        "rung 3 = concrete step-by-step of the algorithm; "
        "rung 4 = detailed pseudocode (language-agnostic) plus the time/space complexity. "
        "Each rung reveals a bit more without giving working code before rung 4. "
        'Respond ONLY with JSON: {"hints": ["rung1", "rung2", "rung3", "rung4"]}'
    )
    user = f"Problem: {title}\nCategory: {category}\nDifficulty: {difficulty}\nPattern: {pattern}"
    data = await chat_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        temperature=0.3, num_predict=1500,
    )
    hints = data.get("hints", [])
    return [str(h).strip() for h in hints if str(h).strip()][:4]


async def author_approach(title: str, category: str, difficulty: str, pattern: str) -> str:
    """Author a worked approach for a coding problem (cached after first call)."""
    sys = (
        "You are a top competitive-programming coach preparing a senior engineer. "
        + USER_CONTEXT
        + " For the named LeetCode problem, write a concise worked approach in markdown. "
        "Do NOT paste the full problem statement. Structure it as:\n"
        "**Idea** (the key insight), **Steps** (numbered), **Complexity** (time & space), "
        "**Pitfalls** (1-3 common mistakes), and a short **Pseudocode** block. "
        "Keep it tight — an experienced engineer's cheat-sheet, ~200-300 words."
    )
    user = f"Problem: {title}\nCategory: {category}\nDifficulty: {difficulty}\nIntended pattern: {pattern}"
    return await chat(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        temperature=0.3, num_predict=1400,
    )


async def coach_problem(title: str, pattern: str, user_plan: str, learner: str = "") -> dict:
    """Grade a candidate's proposed approach to a coding problem."""
    sys = (
        "You are a senior interviewer running a coding round. "
        + (learner or USER_CONTEXT)
        + " The candidate describes how they'd solve the problem (approach, not full code). "
        "Judge whether their plan is correct and optimal, name the single most important gap or "
        "the follow-up you'd ask, and rate recall for spaced repetition. "
        'Respond ONLY with JSON: {"grade": <0-5>, "on_track": <bool>, "feedback": "<2-4 sentences>"}'
    )
    user = f"PROBLEM: {title}\nOPTIMAL PATTERN: {pattern}\n\nCANDIDATE'S PLAN:\n{user_plan}"
    try:
        data = await chat_json(
            [{"role": "system", "content": sys}, {"role": "user", "content": user}],
            temperature=0.2,
        )
        return {
            "grade": int(data.get("grade", 0)),
            "on_track": bool(data.get("on_track", False)),
            "feedback": str(data.get("feedback", "")).strip(),
        }
    except Exception as e:  # noqa: BLE001
        return {"grade": 0, "on_track": False, "feedback": f"(Coach unavailable: {e})"}


async def author_from_text(book: str, chapter: str, section_text: str) -> dict:
    """Author a grounded lesson + cards STRICTLY from a book section's text."""
    sys = (
        "You are turning a section of a technical book the learner OWNS into study material. "
        + USER_CONTEXT + " Base everything ONLY on the provided text — do not add facts not present "
        "in it. Write a faithful lesson summarizing this section's key ideas, then cards that test "
        "understanding of THIS section. Respond ONLY with JSON:\n"
        "{\n"
        '  "title": "concise title for this section\'s main idea",\n'
        '  "summary": "one sentence",\n'
        '  "lesson_md": "150-300 word markdown summary grounded in the text (definitions, key points, examples it gives)",\n'
        '  "cards": [\n'
        '     {"kind":"mcq","prompt":"...","choices":["A","B","C","D"],"answer":"exact correct choice","explanation":"..."},\n'
        '     {"kind":"free","prompt":"an open question this section answers","answer":"model answer from the text","explanation":"key points"}\n'
        "  ]\n"
        "}\n"
        "If the text is front-matter / a table of contents / mostly non-substantive, respond with "
        '{"skip": true}.'
    )
    user = f"BOOK: {book}\nCHAPTER: {chapter}\n\nSECTION TEXT:\n\"\"\"\n{section_text[:9000]}\n\"\"\""
    data = await chat_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        temperature=0.3, num_predict=2200,
    )
    if data.get("skip"):
        return {"skip": True}
    for c in data.get("cards", []):
        if isinstance(c.get("choices"), list):
            c["choices_json"] = json.dumps(c["choices"])
    return data


async def propose_supplements(book_a: str, titles_a: list[str], book_b: str, titles_b: list[str]) -> dict:
    """Propose foundational prereqs + cross-link topic pairs across the two books."""
    sys = (
        "You are designing a study plan across two technical books a senior engineer is learning. "
        + USER_CONTEXT + " Given their chapter/section topics, propose: (a) 4-6 FOUNDATIONAL "
        "prerequisite topics a learner should be solid on to get the most from these books, and "
        "(b) 6-8 CROSS-LINK pairs — a topic from book A that connects to a topic from book B "
        "(where understanding one deepens the other). Respond ONLY with JSON:\n"
        '{"prereqs": ["topic", ...],\n'
        ' "bridges": [{"a": "a topic from book A", "b": "a related topic from book B"}, ...]}'
    )
    user = (
        f"BOOK A ({book_a}) topics:\n- " + "\n- ".join(titles_a[:40]) +
        f"\n\nBOOK B ({book_b}) topics:\n- " + "\n- ".join(titles_b[:40])
    )
    return await chat_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        temperature=0.4, num_predict=1200,
    )


async def cross_link(book_a: str, topic_a: str, book_b: str, topic_b: str) -> dict:
    """Author a card connecting an overlapping topic across the two books."""
    sys = (
        "You are helping a senior engineer connect ideas across two books they're studying. "
        + USER_CONTEXT + " Write ONE free-response card that asks the learner to relate the two "
        'topics below. Respond ONLY with JSON: {"title":"...","summary":"...",'
        '"prompt":"...","answer":"...","explanation":"..."}'
    )
    user = f"BOOK A: {book_a} — topic: {topic_a}\nBOOK B: {book_b} — topic: {topic_b}"
    return await chat_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        temperature=0.4, num_predict=900,
    )


async def generate_concept(track: str, topic_hint: str, existing_titles: list[str],
                           audience: str = "senior") -> dict:
    """Generate a fresh concept + 2 cards as JSON. Used by the nightly job."""
    ctx = (NEWGRAD_CONTEXT.format(lang="Use Python for all code examples. ")
           if audience == "newgrad" else USER_CONTEXT)
    sys = (
        "You are a SWE interview curriculum author. "
        + ctx
        + " Create ONE new interview-worthy concept for the given track that is NOT "
        "already covered. Respond ONLY with JSON of the form:\n"
        "{\n"
        '  "slug": "kebab-case-id",\n'
        '  "title": "...",\n'
        '  "difficulty": "intro|core|advanced",\n'
        '  "tags": "comma,separated",\n'
        '  "summary": "one sentence",\n'
        '  "lesson_md": "150-300 word markdown lesson with a concrete example",\n'
        '  "cards": [\n'
        '     {"kind":"mcq","prompt":"...","choices":["A","B","C","D"],"answer":"exact correct choice text","explanation":"..."},\n'
        '     {"kind":"free","prompt":"an open interview question","answer":"model reference answer","explanation":"key points"}\n'
        "  ]\n"
        "}"
    )
    user = (
        f"TRACK: {track}\n"
        f"THEME HINT: {topic_hint}\n"
        f"ALREADY COVERED (avoid duplicates): {', '.join(existing_titles[:60])}"
    )
    data = await chat_json(
        [{"role": "system", "content": sys}, {"role": "user", "content": user}],
        temperature=0.7, num_predict=2200,
    )
    # Normalise shape.
    data.setdefault("cards", [])
    for c in data["cards"]:
        if "choices" in c and isinstance(c["choices"], list):
            c["choices_json"] = json.dumps(c["choices"])
    return data
