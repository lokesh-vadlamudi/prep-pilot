"""Curated fundamentals for new-grad (SDE-1) accounts. Hand-authored, Python-flavored.

audience="newgrad" — synced only to accounts with level == "newgrad".
Low `sequence` values put these FIRST in a new grad's daily plan; the shared
seed concepts (sequence 0) follow after the fundamentals are introduced.
"""
from __future__ import annotations

FOUNDATIONS = [
    dict(
        slug="big-o-basics", track="DSA", title="Big-O: reading and comparing complexity",
        difficulty="intro", tags="python,complexity", audience="newgrad", sequence=10,
        summary="What Big-O measures and how to eyeball it from code.",
        lesson_md=(
            "Big-O describes how running time (or memory) **grows with input size n** — not how fast "
            "code is in seconds. Drop constants and lower-order terms: `3n + 10` is O(n); `n^2 + n` is O(n^2).\n\n"
            "Rules of thumb:\n"
            "- A single loop over the input → **O(n)**\n"
            "- A loop inside a loop over the same input → **O(n^2)**\n"
            "- Halving the search space each step (binary search) → **O(log n)**\n"
            "- Sorting with a good algorithm → **O(n log n)**\n"
            "- Dict/set lookup in Python → **O(1)** average\n\n"
            "```python\nfor x in nums:          # O(n)\n    if x in seen_set:   # O(1) average\n        ...\n```\n"
            "Growth order: O(1) < O(log n) < O(n) < O(n log n) < O(n^2) < O(2^n). "
            "In interviews, always state time AND space complexity after solving."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="What is the time complexity of a nested loop where both loops iterate over the same list of n items?",
                 choices=["O(n)", "O(n log n)", "O(n^2)", "O(2n)"],
                 answer="O(n^2)",
                 explanation="The inner loop runs n times for each of the n outer iterations: n*n = n^2. O(2n) isn't a standard class — constants are dropped."),
            dict(kind="free",
                 prompt="Your function sorts a list and then does one pass over it. What's the overall time complexity, and why?",
                 answer="O(n log n). Sorting costs O(n log n), the pass costs O(n), and the larger term dominates: O(n log n + n) = O(n log n).",
                 explanation="Key points: add sequential steps, keep only the dominant term, name the sort's cost."),
        ],
    ),
    dict(
        slug="py-list-dict-set", track="CS Fundamentals", title="Python's list, dict, and set under the hood",
        difficulty="intro", tags="python,data-structures", audience="newgrad", sequence=20,
        summary="What the core containers cost and when to reach for each.",
        lesson_md=(
            "**list** — a dynamic array. Index/append: O(1) (append is amortized); insert/delete at the front: "
            "O(n) (everything shifts); `x in mylist`: O(n) scan.\n\n"
            "**dict** — a hash table mapping keys to values. Insert/lookup/delete: O(1) average. Keys must be "
            "hashable (immutable types like str, int, tuple).\n\n"
            "**set** — a hash table of just keys. Membership `x in myset`: O(1) average — the go-to for "
            "\"have I seen this before?\"\n\n"
            "```python\nseen = set()\nfor x in nums:\n    if x in seen:      # O(1) — with a list this is O(n)!\n        return True\n    seen.add(x)\n```\n"
            "Classic interview upgrade: replacing `in list` (O(n)) with `in set` (O(1)) turns an O(n^2) "
            "solution into O(n)."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="What is the average time complexity of checking `x in d` where d is a Python dict?",
                 choices=["O(1)", "O(log n)", "O(n)", "O(n log n)"],
                 answer="O(1)",
                 explanation="Dicts are hash tables: the key is hashed straight to a bucket. Average O(1), no scanning."),
            dict(kind="free",
                 prompt="You need to find duplicates in a list of a million usernames. Which container do you use and why? Compare with the naive approach.",
                 answer="A set. One pass adding names and checking membership is O(n) total since set lookups are O(1) average. The naive nested-loop comparison is O(n^2) — a trillion operations at this size.",
                 explanation="Key points: set = hash table, O(1) membership, one pass, contrast with O(n^2)."),
        ],
    ),
    dict(
        slug="strings-immutability", track="CS Fundamentals", title="Strings: immutability and building them efficiently",
        difficulty="intro", tags="python,strings", audience="newgrad", sequence=30,
        summary="Why += in a loop is a trap and what to do instead.",
        lesson_md=(
            "Python strings are **immutable** — every \"modification\" creates a brand-new string. "
            "That makes `s += piece` inside a loop O(n^2) overall: each += copies everything built so far.\n\n"
            "The idiomatic fix: collect parts in a list and join once at the end.\n\n"
            "```python\nparts = []\nfor word in words:\n    parts.append(word.upper())\nresult = \" \".join(parts)   # one O(n) pass\n```\n"
            "Other essentials: slicing `s[i:j]` copies (O(k)); `s.split()`, `s.strip()`, `s.lower()` return new "
            "strings; compare content with `==` (never `is`). Immutability is also why strings can be dict keys."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="Why is building a string with `s += chunk` inside a loop slow in Python?",
                 choices=[
                     "Strings are immutable, so each += copies the whole string — O(n^2) total",
                     "The += operator is not supported for strings",
                     "Python re-hashes the string on every +=",
                     "It's actually O(n) and perfectly fine",
                 ],
                 answer="Strings are immutable, so each += copies the whole string — O(n^2) total",
                 explanation="Each concatenation allocates a new string and copies all previous characters. Use ''.join(parts) instead."),
            dict(kind="free",
                 prompt="What does it mean that Python strings are immutable, and name two practical consequences.",
                 answer="Once created, a string's contents can never change — operations return new strings. Consequences: (1) building strings with += in a loop is O(n^2), so use ''.join; (2) strings are hashable and can be dict keys / set members; also s[0] = 'x' raises TypeError.",
                 explanation="Any two sensible consequences count: join idiom, hashability, safe sharing, TypeError on item assignment."),
        ],
    ),
    dict(
        slug="hashmap-patterns", track="DSA", title="The hashmap pattern: counting and complements",
        difficulty="intro", tags="python,hashmap,patterns", audience="newgrad", sequence=40,
        summary="Frequency counting and the two-sum complement trick.",
        lesson_md=(
            "Two hashmap patterns solve a huge share of easy/medium interview problems:\n\n"
            "**1. Frequency counting** — tally occurrences, then reason about the tallies.\n"
            "```python\nfrom collections import Counter\ncounts = Counter(s)          # {'a': 3, 'b': 1, ...}\n```\n"
            "Anagrams? `Counter(s1) == Counter(s2)`. Most common element? `counts.most_common(1)`.\n\n"
            "**2. Complement lookup (two-sum)** — while scanning, ask \"have I already seen the value that "
            "completes this one?\"\n"
            "```python\nseen = {}                      # value -> index\nfor i, x in enumerate(nums):\n    if target - x in seen:\n        return [seen[target - x], i]\n    seen[x] = i\n```\n"
            "Both are one pass, O(n) time, O(n) space — trading memory for speed. When you hear "
            "\"find a pair / count things / check for duplicates\", think hashmap first."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="In the classic two-sum solution, what do you store in the dict while scanning the array?",
                 choices=[
                     "Each value seen so far, mapped to its index",
                     "Every possible pair of values",
                     "The sorted copy of the array",
                     "The running sum of all elements",
                 ],
                 answer="Each value seen so far, mapped to its index",
                 explanation="At each element x you check whether target - x was already seen; storing value→index makes that an O(1) lookup."),
            dict(kind="free",
                 prompt="Explain how you'd check whether two strings are anagrams of each other, with complexity.",
                 answer="Count character frequencies of both (e.g. Counter(s1) == Counter(s2)) and compare — O(n) time, O(1)/O(k) space for a fixed alphabet. Sorting both and comparing also works but costs O(n log n).",
                 explanation="Key points: frequency counting beats sorting; state both complexities."),
        ],
    ),
    dict(
        slug="recursion-basics", track="DSA", title="Recursion: base case, progress, and the call stack",
        difficulty="intro", tags="python,recursion", audience="newgrad", sequence=50,
        summary="The two rules every recursive function must obey.",
        lesson_md=(
            "A recursive function calls itself on a **smaller** version of the problem. It needs exactly two things:\n\n"
            "1. **Base case** — the smallest input, answered directly, no recursion.\n"
            "2. **Progress** — every call must move toward the base case.\n\n"
            "```python\ndef factorial(n):\n    if n <= 1:            # base case\n        return 1\n    return n * factorial(n - 1)   # progress: n shrinks\n```\n"
            "Each call sits on the **call stack** until its sub-call returns — so factorial(n) uses O(n) stack "
            "space, and missing the base case gives `RecursionError: maximum recursion depth exceeded` "
            "(Python's default limit is ~1000).\n\n"
            "Reading recursion: trust that the recursive call returns the right answer for the smaller input, "
            "then check the combining step. That's also how you'll design tree traversals later."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="What happens in Python if a recursive function has no reachable base case?",
                 choices=[
                     "RecursionError once the recursion depth limit (~1000) is hit",
                     "It loops forever silently",
                     "Python automatically converts it to a loop",
                     "A syntax error at definition time",
                 ],
                 answer="RecursionError once the recursion depth limit (~1000) is hit",
                 explanation="Each call adds a stack frame; Python caps the depth and raises RecursionError rather than overflowing the C stack."),
            dict(kind="free",
                 prompt="Write (or describe) a recursive function to sum a list, then explain what the iterative version gains.",
                 answer="def total(nums): return 0 if not nums else nums[0] + total(nums[1:]). Base case: empty list → 0; progress: shorter list. Iterative (a loop with an accumulator) gains O(1) stack space instead of O(n) frames and avoids the recursion depth limit; nums[1:] slicing also makes the recursive one O(n^2) unless an index is passed.",
                 explanation="Look for: correct base case, progress, stack-space comparison."),
        ],
    ),
    dict(
        slug="two-pointers-intro", track="DSA", title="Two pointers: meeting in the middle",
        difficulty="intro", tags="python,two-pointers,patterns", audience="newgrad", sequence=60,
        summary="Using paired indices to replace nested loops on ordered data.",
        lesson_md=(
            "The two-pointer pattern keeps two indices and moves them by a rule, cutting O(n^2) scans to O(n). "
            "Two common shapes:\n\n"
            "**Opposite ends** (needs sorted/ordered data): check palindromes, find a pair summing to a target.\n"
            "```python\nlo, hi = 0, len(nums) - 1\nwhile lo < hi:\n    s = nums[lo] + nums[hi]\n    if s == target: return True\n    if s < target: lo += 1     # need a bigger sum\n    else: hi -= 1              # need a smaller sum\n```\n"
            "**Slow/fast (same direction)**: de-duplicate in place, find a linked-list cycle, or the middle node.\n\n"
            "The interview tell: \"sorted array\", \"palindrome\", \"remove in place\", or \"pair with property X\" "
            "→ try two pointers before reaching for nested loops. Time O(n), space O(1)."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="For a SORTED array, two pointers at both ends find whether any pair sums to a target in:",
                 choices=["O(n) time, O(1) space", "O(n^2) time, O(1) space", "O(n log n) time, O(n) space", "O(log n) time"],
                 answer="O(n) time, O(1) space",
                 explanation="Each step moves one pointer inward, so at most n steps; only two indices are stored. Sortedness makes the move direction decidable."),
            dict(kind="free",
                 prompt="How would you check if a string is a palindrome using two pointers? What's the complexity?",
                 answer="Start lo at 0 and hi at the end; while lo < hi compare s[lo] and s[hi], return False on mismatch, else move both inward. O(n) time, O(1) extra space.",
                 explanation="Key points: opposite-end pointers, single pass, constant space (vs s == s[::-1] which copies)."),
        ],
    ),
    dict(
        slug="oop-python-basics", track="CS Fundamentals", title="OOP in Python: classes, instances, and composition",
        difficulty="intro", tags="python,oop", audience="newgrad", sequence=70,
        summary="The vocabulary interviewers expect: class vs instance, inheritance vs composition.",
        lesson_md=(
            "A **class** is the blueprint; an **instance** is one object built from it. `__init__` initializes "
            "instance attributes; `self` is the instance being operated on.\n\n"
            "```python\nclass Account:\n    bank = \"Acme\"            # class attribute (shared)\n    def __init__(self, owner):\n        self.owner = owner      # instance attribute (per object)\n    def describe(self):\n        return f\"{self.owner} @ {self.bank}\"\n```\n"
            "**Inheritance** (\"is-a\"): `class Savings(Account)` reuses and overrides behavior. "
            "**Composition** (\"has-a\"): an `Account` holds a `TransactionLog` object. Modern guidance: "
            "**prefer composition** — it stays flexible as requirements change, while deep inheritance trees "
            "get brittle.\n\n"
            "Also know: dunder methods (`__repr__`, `__eq__`, `__len__`) let your objects work with built-ins, "
            "and *duck typing* means Python cares about behavior, not declared types."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="In Python, what's the difference between a class attribute and an instance attribute?",
                 choices=[
                     "Class attributes are shared by all instances; instance attributes belong to one object",
                     "Class attributes are private; instance attributes are public",
                     "Instance attributes are faster to access",
                     "There is no difference",
                 ],
                 answer="Class attributes are shared by all instances; instance attributes belong to one object",
                 explanation="Class attributes live on the class object (one copy); instance attributes are set per object, usually in __init__."),
            dict(kind="free",
                 prompt="When would you choose composition over inheritance? Give a concrete example.",
                 answer="When the relationship is 'has-a' rather than 'is-a', or when you want to swap behavior without touching a hierarchy. Example: a ReportGenerator HAS a Formatter (pdf/html) passed in, instead of PdfReportGenerator/HtmlReportGenerator subclasses — new formats need no new subclasses.",
                 explanation="Look for: has-a vs is-a, flexibility/testability, any sensible example."),
        ],
    ),
    dict(
        slug="http-rest-basics", track="System Design", title="HTTP and REST: verbs, status codes, idempotency",
        difficulty="intro", tags="http,rest,api", audience="newgrad", sequence=80,
        summary="The request/response vocabulary every SDE-1 needs.",
        lesson_md=(
            "HTTP is a request/response protocol. A REST API maps **verbs** onto resources:\n\n"
            "- **GET** /users/42 — read (never changes data)\n- **POST** /users — create\n"
            "- **PUT** /users/42 — replace\n- **PATCH** /users/42 — partial update\n- **DELETE** /users/42 — remove\n\n"
            "**Status codes** you must know cold: 200 OK, 201 Created, 400 Bad Request (client sent garbage), "
            "401 Unauthorized (who are you?), 403 Forbidden (you can't do that), 404 Not Found, "
            "500 Internal Server Error (server bug), 503 Service Unavailable.\n\n"
            "**Idempotency**: an operation is idempotent if doing it twice has the same effect as once. "
            "GET, PUT, DELETE are idempotent; POST is not (two POSTs = two records). This matters for "
            "retries — clients can safely retry idempotent calls after a timeout.\n\n"
            "4xx = the client's fault; 5xx = the server's fault. That one line resolves many debugging debates."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="A client retries a request after a timeout. Which method is UNSAFE to blindly retry?",
                 choices=["POST", "GET", "PUT", "DELETE"],
                 answer="POST",
                 explanation="POST is not idempotent — the first request may have succeeded, so retrying can create a duplicate. GET/PUT/DELETE are idempotent."),
            dict(kind="free",
                 prompt="Your API returns 500 to some users and 400 to others for the same endpoint. Explain to a teammate what each code implies about where the bug is.",
                 answer="400 means the server judged the CLIENT's request malformed (bad params/body) — fix the caller or tighten docs. 500 means the SERVER threw an unhandled error on a request it accepted — that's our bug: check logs/stack traces. Same endpoint giving both suggests some inputs pass validation and then crash the handler.",
                 explanation="Key points: 4xx client-side vs 5xx server-side, and the combined-signal interpretation."),
        ],
    ),
    dict(
        slug="sql-basics", track="System Design", title="SQL: joins, WHERE vs HAVING, and why indexes help",
        difficulty="intro", tags="sql,database", audience="newgrad", sequence=90,
        summary="Enough SQL to survive the screening round.",
        lesson_md=(
            "**JOINs** combine tables by a key:\n"
            "- `INNER JOIN` — only rows that match in both tables\n"
            "- `LEFT JOIN` — every row from the left table, matches from the right (NULLs when absent)\n\n"
            "```sql\nSELECT u.name, COUNT(o.id) AS orders\nFROM users u\nLEFT JOIN orders o ON o.user_id = u.id\nGROUP BY u.name\nHAVING COUNT(o.id) > 5;\n```\n"
            "**WHERE vs HAVING**: WHERE filters rows *before* grouping; HAVING filters groups *after* "
            "aggregation. You can't put `COUNT(*)` in WHERE.\n\n"
            "**Indexes** are sorted lookup structures (usually B-trees) that turn full-table scans (O(n)) into "
            "O(log n) seeks on the indexed column. They cost extra writes and storage — index the columns you "
            "filter/join on, not everything.\n\n"
            "Know your keys: PRIMARY KEY uniquely identifies a row; FOREIGN KEY references another table's key."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="You want every user, including those with zero orders, plus their order counts. Which join?",
                 choices=["LEFT JOIN from users to orders", "INNER JOIN", "RIGHT JOIN from users to orders", "CROSS JOIN"],
                 answer="LEFT JOIN from users to orders",
                 explanation="LEFT JOIN keeps all rows from users; users without orders appear with NULL/0 counts. INNER JOIN would drop them."),
            dict(kind="free",
                 prompt="A query filtering on email is slow on a 10M-row table. What do you do, and what's the trade-off?",
                 answer="Add an index on the email column: the query goes from a full scan (O(n)) to a B-tree seek (O(log n)). Trade-offs: the index consumes storage and slows every INSERT/UPDATE slightly since it must be maintained; only worth it for columns used in lookups/joins.",
                 explanation="Key points: index, B-tree/O(log n) vs scan, write/storage cost."),
        ],
    ),
    dict(
        slug="process-vs-thread", track="CS Fundamentals", title="Processes vs threads (and Python's GIL)",
        difficulty="intro", tags="os,concurrency,python", audience="newgrad", sequence=100,
        summary="The OS concurrency vocabulary interviewers probe first.",
        lesson_md=(
            "A **process** is a running program with its own private memory. A **thread** is an execution "
            "stream *inside* a process — threads of one process share its memory.\n\n"
            "Consequences:\n"
            "- Threads are cheap to create and share data easily — but shared data needs locks, and bugs "
            "(race conditions) are nasty.\n"
            "- Processes are isolated (one crash doesn't kill the other) but talk via slower IPC (pipes, sockets).\n\n"
            "**Python twist — the GIL**: CPython's Global Interpreter Lock lets only one thread execute Python "
            "bytecode at a time. So threads DON'T speed up CPU-bound Python code — use `multiprocessing` for "
            "that. Threads still shine for **I/O-bound** work (network calls, file reads) because the GIL is "
            "released while waiting.\n\n"
            "Rule of thumb: CPU-bound → processes; I/O-bound → threads or asyncio."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="Why don't Python threads speed up a CPU-heavy computation in CPython?",
                 choices=[
                     "The GIL allows only one thread to run Python bytecode at a time",
                     "Python threads are simulated and never run in parallel for anything",
                     "Threads can't access the CPU in Python",
                     "They do — threads always give a linear speedup",
                 ],
                 answer="The GIL allows only one thread to run Python bytecode at a time",
                 explanation="The Global Interpreter Lock serializes bytecode execution. multiprocessing sidesteps it with separate processes; threads still help I/O-bound work."),
            dict(kind="free",
                 prompt="Your script downloads 200 web pages. A colleague suggests multiprocessing. What do you recommend and why?",
                 answer="Threads (or asyncio): downloading is I/O-bound — threads wait on the network, and the GIL is released during I/O, so concurrency works fine and is lighter than 200 processes. Multiprocessing pays process-creation and IPC overhead for CPU parallelism we don't need.",
                 explanation="Key points: I/O-bound vs CPU-bound, GIL released on I/O, process overhead."),
        ],
    ),
    dict(
        slug="git-basics", track="CS Fundamentals", title="Git: the working-tree → staging → commit pipeline",
        difficulty="intro", tags="git,tooling", audience="newgrad", sequence=110,
        summary="The mental model plus the team workflow (branches and PRs).",
        lesson_md=(
            "Git tracks snapshots in three zones: your **working tree** (files on disk) → the **staging area** "
            "(`git add` picks what goes in) → the **repository** (`git commit` saves a snapshot).\n\n"
            "Team workflow you'll use daily:\n"
            "```\ngit checkout -b fix-login    # branch off main\n# edit files\ngit add -p                   # stage the relevant changes\ngit commit -m \"Fix login redirect\"\ngit push -u origin fix-login # open a Pull Request for review\n```\n"
            "**merge vs rebase**: merge ties two histories together with a merge commit (safe, default); "
            "rebase replays your commits on top of the latest main for a linear history (never rebase commits "
            "already pushed and shared).\n\n"
            "Getting unstuck: `git status` explains the current state; `git log --oneline` shows history; "
            "`git diff` shows unstaged changes. When in doubt, commit or stash before experimenting."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="What does `git add` actually do?",
                 choices=[
                     "Moves changes into the staging area so the next commit includes them",
                     "Uploads your changes to GitHub",
                     "Creates a new commit immediately",
                     "Adds a new branch",
                 ],
                 answer="Moves changes into the staging area so the next commit includes them",
                 explanation="add stages; commit snapshots what's staged; push publishes commits to the remote. Three separate steps."),
            dict(kind="free",
                 prompt="Walk through how you'd ship a small bug fix on a team project, from getting the latest code to the fix landing in main.",
                 answer="git pull on main → git checkout -b fix-xyz → edit, test → git add / git commit → git push -u origin fix-xyz → open a PR, address review comments with more commits → PR is approved and merged into main (merge commit or squash), branch deleted.",
                 explanation="Look for: branch-per-change, commits, push, PR + review, merge into main."),
        ],
    ),
    dict(
        slug="testing-basics", track="CS Fundamentals", title="Testing: unit vs integration, and what makes a good test",
        difficulty="intro", tags="testing,python", audience="newgrad", sequence=120,
        summary="Why interviewers ask 'how would you test this?' and how to answer.",
        lesson_md=(
            "**Unit tests** check one function/class in isolation — fast, precise, run on every save. "
            "**Integration tests** check pieces working together (API + DB) — slower, catch wiring bugs. "
            "**End-to-end tests** drive the whole system like a user — fewest, most brittle. "
            "The classic *test pyramid*: many unit, some integration, few E2E.\n\n"
            "A good unit test is **FIRST**: Fast, Independent (no ordering), Repeatable (no flaky network/clock), "
            "Self-checking (asserts, no eyeballing), Timely.\n\n"
            "```python\ndef test_two_sum_finds_pair():\n    assert two_sum([2, 7, 11], 9) == [0, 1]\n\ndef test_two_sum_no_pair():\n    assert two_sum([1, 2], 100) is None   # edge case!\n```\n"
            "In interviews, after coding always volunteer test cases: the happy path, edge cases (empty input, "
            "one element, duplicates, negatives), and the failure mode."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="Which is a UNIT test rather than an integration test?",
                 choices=[
                     "Calling parse_date('2026-01-01') and asserting the returned object's fields",
                     "Hitting the /signup endpoint and checking a row appears in the database",
                     "Driving the UI with a headless browser through checkout",
                     "Deploying to staging and running smoke checks",
                 ],
                 answer="Calling parse_date('2026-01-01') and asserting the returned object's fields",
                 explanation="It exercises one function in isolation with no external systems. The others cross component or system boundaries."),
            dict(kind="free",
                 prompt="You just wrote a function that returns the k largest numbers in a list. List the test cases you'd write.",
                 answer="Happy path (k < len, mixed values); k == len (whole list); k == 0 (empty result); k > len (define: error or whole list); empty input list; duplicates (ties kept correctly); negative numbers; already-sorted and reverse-sorted inputs; result order requirement (sorted or not).",
                 explanation="Credit breadth: happy path + boundary ks + empty + duplicates/negatives; bonus for pinning down ambiguous spec (k > len)."),
        ],
    ),
    dict(
        slug="newgrad-behavioral-star", track="Behavioral", title="STAR answers for new grads: projects over jobs",
        difficulty="intro", tags="behavioral,star", audience="newgrad", sequence=130,
        summary="Turning class projects and internships into strong interview stories.",
        lesson_md=(
            "Behavioral answers follow **STAR**: Situation (one sentence of context), Task (what YOU had to "
            "achieve), Action (the steps YOU took — the meat), Result (what happened, with a number if possible).\n\n"
            "As a new grad, class projects, hackathons, internships, and personal projects are all fair game — "
            "interviewers care about your behavior, not the company name.\n\n"
            "Weak: \"We built a course-registration app and it went well.\"\n"
            "Strong: \"In a 4-person class project (S), I owned the backend after our DB design kept failing "
            "under load (T). I profiled the queries, added two indexes, and rewrote the N+1 loop into one join "
            "(A). Page loads went from 8s to under 1s and we scored 95% (R).\"\n\n"
            "Say **I**, not only *we* — interviewers must see YOUR contribution. Prepare 4-5 stories covering: "
            "a technical challenge, a teammate conflict or disagreement, a failure and what you learned, and "
            "learning something fast. One good story can flex to answer many questions."
        ),
        cards=[
            dict(kind="mcq",
                 prompt="What is the most common weakness in new-grad behavioral answers?",
                 choices=[
                     "Saying 'we' throughout, so the interviewer can't tell what the candidate personally did",
                     "Using class projects instead of jobs",
                     "Giving a measurable result",
                     "Keeping the situation to one sentence",
                 ],
                 answer="Saying 'we' throughout, so the interviewer can't tell what the candidate personally did",
                 explanation="Team credit is fine, but the interviewer is hiring YOU — the Action part must be first-person and specific. Class projects are perfectly valid material."),
            dict(kind="free",
                 prompt="Tell me about a time you had to learn something quickly. (Answer in STAR form — any real project counts.)",
                 answer="A strong answer names the situation and deadline, the specific thing YOU had to learn, concrete learning actions (docs, building a toy example, asking a mentor a targeted question), and a measurable or verifiable result, ending with what you'd reuse next time.",
                 explanation="Grade on STAR structure, first-person actions, specificity, and a concrete result — not on how impressive the tech was."),
        ],
    ),
]
