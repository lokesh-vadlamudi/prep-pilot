"""Curated senior-SWE curriculum seed.

This is the verified backbone. The nightly AI job grows it from here, but these
concepts are hand-checked so your fundamentals never depend on model accuracy.
Each concept has a lesson + spaced-repetition cards (mcq / free-text).
"""
from __future__ import annotations

SEED: list[dict] = [
    # ================= DSA & Algorithms =================
    {
        "slug": "two-pointers",
        "track": "DSA",
        "title": "Two-Pointer Technique",
        "difficulty": "core",
        "tags": "arrays,strings,python,go",
        "summary": "Coordinate two indices to turn O(n^2) scans into O(n).",
        "lesson_md": (
            "The **two-pointer** pattern walks two indices through a sequence to avoid a nested loop.\n\n"
            "Common forms:\n"
            "- **Opposite ends** (sorted array): move `lo`/`hi` inward — e.g. two-sum on a sorted array, container-with-most-water.\n"
            "- **Fast/slow** (linked lists): cycle detection, finding the middle.\n"
            "- **Sliding window**: a right pointer expands, a left pointer contracts to maintain an invariant.\n\n"
            "Key insight: it works when the input is **sorted** or when the invariant is **monotonic** as a pointer moves, "
            "so you never need to re-examine positions. Typical result: O(n) time, O(1) space."
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "For 'find two numbers that sum to target' on a **sorted** array, why does the opposite-ends two-pointer approach work?",
             "choices": [
                 "Because moving a pointer changes the sum monotonically, so you can discard half the space each step",
                 "Because the array is hashed for O(1) lookup",
                 "Because recursion memoizes subproblems",
                 "Because it uses a balanced BST internally"],
             "answer": "Because moving a pointer changes the sum monotonically, so you can discard half the space each step",
             "explanation": "Sorted order makes the running sum monotonic w.r.t. pointer moves, so a too-small sum means move lo right, too-large means move hi left."},
            {"kind": "free",
             "prompt": "Explain how you'd detect a cycle in a singly linked list in O(1) space, and how you'd find the cycle's start.",
             "answer": "Floyd's tortoise-and-hare: slow moves 1, fast moves 2; if they meet there's a cycle. To find the start, reset one pointer to head and advance both by 1 — they meet at the cycle entry.",
             "explanation": "The meeting-point math: distance from head to cycle start equals distance from meeting point to cycle start (mod cycle length)."},
        ],
    },
    {
        "slug": "dynamic-programming-basics",
        "track": "DSA",
        "title": "Dynamic Programming: State & Transitions",
        "difficulty": "core",
        "tags": "dp,recursion",
        "summary": "Define a state, a transition, and a base case; memoize or tabulate.",
        "lesson_md": (
            "**DP** solves problems with *optimal substructure* and *overlapping subproblems*.\n\n"
            "The recipe:\n"
            "1. **State** — what parameters uniquely describe a subproblem? (`dp[i]`, `dp[i][j]`).\n"
            "2. **Transition** — how does a state build from smaller states?\n"
            "3. **Base case** — the smallest solvable state.\n"
            "4. **Order** — top-down (memoized recursion) or bottom-up (tabulation).\n\n"
            "Example — coin change (min coins for amount `a`): `dp[a] = 1 + min(dp[a-c] for c in coins if c<=a)`, `dp[0]=0`.\n\n"
            "Interview tip: always state the recurrence and complexity out loud (states × transition cost) before coding."
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "What two properties must a problem have for DP to apply?",
             "choices": [
                 "Optimal substructure and overlapping subproblems",
                 "Sorted input and a greedy choice",
                 "A balanced tree and O(1) lookups",
                 "Randomized pivots and tail recursion"],
             "answer": "Optimal substructure and overlapping subproblems",
             "explanation": "Optimal substructure = optimal solution builds from optimal sub-solutions; overlapping = the same subproblems recur (so caching helps)."},
            {"kind": "free",
             "prompt": "Give the state, transition, and complexity for the classic 0/1 knapsack problem.",
             "answer": "State dp[i][w] = max value using first i items within capacity w. Transition: dp[i][w] = max(dp[i-1][w], value[i] + dp[i-1][w-weight[i]]) when weight[i]<=w. Complexity O(n*W) time and space (reducible to O(W)).",
             "explanation": "The two choices are skip item i or take it; W is pseudo-polynomial so it's not truly polynomial in input size."},
        ],
    },
    {
        "slug": "big-o-analysis",
        "track": "DSA",
        "title": "Complexity Analysis & Amortization",
        "difficulty": "intro",
        "tags": "complexity",
        "summary": "Reason about time/space growth, including amortized costs.",
        "lesson_md": (
            "Big-O bounds **growth rate**, ignoring constants. Know the ladder: O(1) < O(log n) < O(n) < O(n log n) < O(n^2) < O(2^n) < O(n!).\n\n"
            "**Amortized** analysis averages cost over a sequence. Example: a dynamic array's `append` is O(n) on the rare resize but O(1) amortized because doubling spreads the copy cost across n cheap appends.\n\n"
            "Watch for hidden costs: string concatenation in a loop (O(n^2)), `list.insert(0, x)` (O(n)), or Python `in` on a list (O(n) vs set O(1))."
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "Why is appending to a dynamic array O(1) amortized despite O(n) resizes?",
             "choices": [
                 "Doubling capacity makes total copy work across n appends O(n), so O(1) each on average",
                 "Because resizes never actually happen",
                 "Because the OS pre-allocates infinite memory",
                 "Because append uses a linked list internally"],
             "answer": "Doubling capacity makes total copy work across n appends O(n), so O(1) each on average",
             "explanation": "Geometric growth: copies sum to n + n/2 + n/4 + ... < 2n total, i.e. O(1) amortized per append."},
        ],
    },

    # ================= System Design =================
    {
        "slug": "caching-strategies",
        "track": "System Design",
        "title": "Caching Strategies & Invalidation",
        "difficulty": "core",
        "tags": "caching,redis,scaling,aws",
        "summary": "Cache-aside vs write-through vs write-back, TTLs, and stampedes.",
        "lesson_md": (
            "Caching trades staleness for latency/throughput. Patterns:\n\n"
            "- **Cache-aside (lazy)**: app checks cache, on miss reads DB and populates. Simple, but first request is slow and cache can go stale.\n"
            "- **Write-through**: writes go to cache + DB synchronously. Fresh reads, slower writes.\n"
            "- **Write-back**: write to cache, flush to DB async. Fast writes, risk of data loss.\n\n"
            "**Invalidation** is the hard part. Use TTLs plus explicit invalidation on writes. Guard against:\n"
            "- **Thundering herd / stampede**: many misses hit the DB at once — mitigate with request coalescing, a mutex/lock on rebuild, or early recompute.\n"
            "- **Hot keys**: replicate or add a small local (L1) cache in front of Redis.\n\n"
            "On AWS this is ElastiCache (Redis/Memcached); pair with a CDN (CloudFront) for edge caching of static/semistatic content."
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "A single popular key expires and thousands of requests hit the DB simultaneously to rebuild it. What is this and a fix?",
             "choices": [
                 "Cache stampede — coalesce requests or hold a rebuild lock so only one recomputes",
                 "Write amplification — switch to write-back",
                 "Split brain — add a quorum",
                 "Head-of-line blocking — add more partitions"],
             "answer": "Cache stampede — coalesce requests or hold a rebuild lock so only one recomputes",
             "explanation": "Also called dogpiling. Fixes: per-key mutex on rebuild, probabilistic early expiration, or serving stale-while-revalidate."},
            {"kind": "free",
             "prompt": "Design the caching layer for a read-heavy product-detail page seeing 50k RPS. Discuss layers, invalidation, and consistency.",
             "answer": "Multi-layer: CDN/edge for anonymous full pages, an app-tier Redis (cache-aside) for product objects keyed by id with a TTL (e.g. 60s), and a small in-process LRU for hot keys to cut Redis round-trips. Invalidate on write by publishing an event that evicts the key; accept short bounded staleness. Protect against stampede with per-key locks and stale-while-revalidate.",
             "explanation": "Key trade-off: pick a consistency budget (how stale is OK) explicitly; read-heavy pages tolerate seconds of staleness for huge latency wins."},
        ],
    },
    {
        "slug": "load-balancing",
        "track": "System Design",
        "title": "Load Balancing & Health Checking",
        "difficulty": "core",
        "tags": "scaling,networking,aws,gcp",
        "summary": "Distribute traffic across instances; L4 vs L7, algorithms, health.",
        "lesson_md": (
            "A load balancer spreads requests across backends for scale + availability.\n\n"
            "- **L4 (transport)**: routes by IP/port, fast, protocol-agnostic (AWS NLB).\n"
            "- **L7 (application)**: routes by HTTP path/host/headers, enables canary + sticky sessions (AWS ALB, Envoy, nginx).\n\n"
            "Algorithms: round-robin, least-connections, weighted, consistent-hash (for cache affinity).\n\n"
            "**Health checks** remove unhealthy backends; use shallow (is-up) + deep (can-serve) checks. Beware retry storms — pair with circuit breakers, timeouts, and jittered backoff. For statefulness, prefer stateless backends + shared session store over sticky sessions."
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "When would you choose an L7 load balancer over L4?",
             "choices": [
                 "When you need routing by HTTP path/host/header, TLS termination, or canary/blue-green",
                 "When you need the absolute lowest latency and protocol-agnostic forwarding",
                 "When you must load-balance raw UDP game traffic",
                 "When you want to avoid inspecting requests at all"],
             "answer": "When you need routing by HTTP path/host/header, TLS termination, or canary/blue-green",
             "explanation": "L7 understands HTTP so it can do content-based routing and traffic shaping; L4 is faster/agnostic but blind to app semantics."},
        ],
    },
    {
        "slug": "cap-consistency",
        "track": "System Design",
        "title": "CAP, Consistency Models & Replication",
        "difficulty": "advanced",
        "tags": "distributed,databases,consistency",
        "summary": "Trade-offs under partition; strong vs eventual consistency.",
        "lesson_md": (
            "**CAP**: under a network **P**artition you must choose **C**onsistency or **A**vailability. Since partitions happen, real systems pick CP or AP behavior *during* partitions.\n\n"
            "Consistency models (strongest → weakest): **linearizable** → **sequential** → **causal** → **eventual**.\n\n"
            "Replication:\n"
            "- **Single-leader** (Postgres, MySQL): writes to leader, replicas follow. Simple; read replicas can be stale.\n"
            "- **Multi-leader / leaderless** (Dynamo, Cassandra): higher availability, needs conflict resolution (LWW, vector clocks, CRDTs).\n\n"
            "Quorums: with N replicas, `W + R > N` gives read-your-writes on the overlapping node. Understand the trade: stronger consistency costs latency + availability."
        ),
        "cards": [
            {"kind": "free",
             "prompt": "A checkout service must never double-charge but can tolerate brief unavailability. What consistency stance do you pick and how do you enforce it?",
             "answer": "Choose CP for the payment path: prefer a strongly-consistent store (single-leader with synchronous commit or a consensus-backed DB) and enforce idempotency with a unique idempotency key per charge so retries don't double-charge. Accept short unavailability during a partition rather than risk conflicting writes.",
             "explanation": "Correctness of money > availability here. Idempotency keys + exactly-once semantics at the app layer are the practical enforcement, not just DB config."},
            {"kind": "mcq",
             "prompt": "With N=3 replicas, which quorum setting guarantees a read sees the latest write?",
             "choices": ["W + R > N (e.g. W=2, R=2)", "W=1, R=1", "W=1, R=2", "Any setting; quorums don't affect this"],
             "answer": "W + R > N (e.g. W=2, R=2)",
             "explanation": "Overlap of the write and read sets guarantees at least one node in the read has the latest write."},
        ],
    },

    # ================= CS Fundamentals =================
    {
        "slug": "acid-transactions",
        "track": "CS Fundamentals",
        "title": "ACID & Isolation Levels",
        "difficulty": "core",
        "tags": "databases,sql,postgres",
        "summary": "What ACID guarantees, and the anomalies each isolation level allows.",
        "lesson_md": (
            "**ACID**: Atomicity (all-or-nothing), Consistency (invariants hold), Isolation (concurrent txns don't corrupt each other), Durability (committed = survives crash).\n\n"
            "Isolation levels trade correctness for concurrency:\n"
            "- **Read Uncommitted** — dirty reads possible.\n"
            "- **Read Committed** (Postgres default) — no dirty reads, but non-repeatable reads.\n"
            "- **Repeatable Read** — no non-repeatable reads; phantoms possible (Postgres RR actually prevents them via snapshot).\n"
            "- **Serializable** — behaves as if txns ran one at a time.\n\n"
            "Know the anomalies: dirty read, non-repeatable read, phantom, write skew (only prevented at serializable)."
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "Which anomaly is ONLY prevented at the Serializable isolation level?",
             "choices": ["Write skew", "Dirty read", "Non-repeatable read", "Lost update"],
             "answer": "Write skew",
             "explanation": "Write skew (two txns each read a shared invariant then write, breaking it) needs true serializability; lower levels can allow it."},
        ],
    },
    {
        "slug": "concurrency-primitives",
        "track": "CS Fundamentals",
        "title": "Concurrency: Locks, Channels & Races",
        "difficulty": "core",
        "tags": "concurrency,go,python",
        "summary": "Mutexes vs channels, deadlock, and data races.",
        "lesson_md": (
            "Concurrency bugs come from **shared mutable state** accessed without coordination.\n\n"
            "- **Mutex**: mutual exclusion around a critical section. Risk: deadlock (lock ordering), contention.\n"
            "- **Channels (Go)**: 'share memory by communicating' — pass ownership of data via a channel instead of locking it.\n"
            "- **Atomic ops**: lock-free counters/flags via CPU primitives.\n\n"
            "**Deadlock** needs all four Coffman conditions (mutual exclusion, hold-and-wait, no preemption, circular wait) — break any one (e.g. global lock ordering).\n\n"
            "In Go, `go test -race` catches data races. In Python, the GIL serializes bytecode but does NOT make `+=` atomic across threads, and it doesn't help CPU-bound parallelism (use multiprocessing)."
        ),
        "cards": [
            {"kind": "free",
             "prompt": "In Go, when would you prefer a channel over a sync.Mutex, and vice versa?",
             "answer": "Use a channel to transfer ownership of data or coordinate pipelines/worker pools — it expresses handoff and makes concurrency structure explicit. Use a Mutex to protect a small piece of shared state accessed in place (e.g. a map or counter) where passing ownership would be awkward or slower. Rule of thumb: channels for communication/flow, mutexes for guarding shared state.",
             "explanation": "The Go proverb: 'Don't communicate by sharing memory; share memory by communicating' — but mutexes are simpler and faster for plain shared-state protection."},
            {"kind": "mcq",
             "prompt": "Does Python's GIL make `counter += 1` thread-safe across threads?",
             "choices": [
                 "No — it's read-modify-write across multiple bytecodes and can interleave; use a Lock or atomic",
                 "Yes — the GIL makes all operations atomic",
                 "Yes — but only for integers",
                 "No — but only on multiprocessing"],
             "answer": "No — it's read-modify-write across multiple bytecodes and can interleave; use a Lock or atomic",
             "explanation": "The GIL serializes bytecode execution but a thread switch can occur between the load and store, losing updates."},
        ],
    },
    {
        "slug": "http-tls-basics",
        "track": "CS Fundamentals",
        "title": "HTTP, TLS & Connection Lifecycle",
        "difficulty": "intro",
        "tags": "networking,security",
        "summary": "How a request travels: DNS, TCP, TLS handshake, HTTP semantics.",
        "lesson_md": (
            "A browser request: **DNS** resolve → **TCP** 3-way handshake → **TLS** handshake → **HTTP** request/response.\n\n"
            "- **TLS 1.3** cut the handshake to one round trip and dropped legacy ciphers. It gives confidentiality, integrity, and server authentication (via the cert chain to a trusted CA).\n"
            "- **HTTP/1.1** = one request in flight per connection (head-of-line blocking); **HTTP/2** multiplexes streams over one TCP connection (but TCP-level HOL remains); **HTTP/3** runs over QUIC/UDP to remove that.\n"
            "- Idempotent methods (GET, PUT, DELETE) are safe to retry; POST is not without an idempotency key.\n\n"
            "Know status classes: 2xx ok, 3xx redirect, 4xx client error, 5xx server error; and caching headers (ETag, Cache-Control)."
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "Why does HTTP/3 use QUIC over UDP instead of TCP?",
             "choices": [
                 "To eliminate TCP head-of-line blocking by giving each stream independent loss recovery",
                 "Because UDP is encrypted by default",
                 "Because TCP cannot be used on the internet",
                 "To avoid needing TLS"],
             "answer": "To eliminate TCP head-of-line blocking by giving each stream independent loss recovery",
             "explanation": "In HTTP/2 a lost TCP segment stalls all multiplexed streams; QUIC's per-stream delivery removes that transport-level HOL blocking."},
        ],
    },

    # ================= Behavioral & Leadership =================
    {
        "slug": "star-method",
        "track": "Behavioral",
        "title": "STAR Stories with Senior Scope",
        "difficulty": "core",
        "tags": "behavioral,leadership",
        "summary": "Structure impact stories; show scope, ownership, and measurable results.",
        "lesson_md": (
            "**STAR** = Situation, Task, Action, Result. For senior/staff levels the bar is *scope and impact*, not just competence.\n\n"
            "- **Situation/Task**: 1-2 sentences of context — what was at stake and why it was hard.\n"
            "- **Action**: focus on *your* decisions and trade-offs; use 'I' not 'we'. Show technical judgment and how you drove others.\n"
            "- **Result**: quantify (latency ↓, revenue ↑, incident rate ↓) and reflect on what you learned.\n\n"
            "Senior signals: influencing without authority, making a reversible-vs-irreversible call, mentoring, handling ambiguity, and owning a failure honestly.\n\n"
            "Prep 6-8 stories mapped to themes: conflict, failure, leadership, ambiguity, tight deadline, disagreement with a decision, biggest technical win."
        ),
        "cards": [
            {"kind": "free",
             "prompt": "Tell me about a time you disagreed with a technical decision made by your team or manager.",
             "answer": "A strong answer: state the decision and your concern with data, describe how you raised it respectfully and proposed an alternative or an experiment, then how you committed to the outcome (disagree-and-commit) and what the result taught you. Show you can influence with evidence AND back a decision you lost gracefully.",
             "explanation": "Interviewers look for: you use data not ego, you escalate appropriately, and you don't sabotage a decision you disagreed with. Quantify the impact."},
            {"kind": "mcq",
             "prompt": "What most distinguishes a senior-level STAR answer from a mid-level one?",
             "choices": [
                 "Demonstrated scope/impact and influence beyond your own code",
                 "Using more technical jargon",
                 "Longer situation descriptions",
                 "Avoiding any mention of failure"],
             "answer": "Demonstrated scope/impact and influence beyond your own code",
             "explanation": "Seniority is measured by blast radius: cross-team influence, measurable business/technical impact, and sound judgment under ambiguity."},
        ],
    },
    {
        "slug": "coding-interview-umpire",
        "track": "DSA",
        "title": "The UMPIRE Coding-Interview Method",
        "difficulty": "intro",
        "tags": "process,communication,interview",
        "summary": "A repeatable framework for structuring any coding interview out loud.",
        "lesson_md": (
            "Top companies grade coding rounds on four axes: **communication, problem-solving, "
            "technical competency, and testing** — not just a passing solution. UMPIRE is a script "
            "that shows all four:\n\n"
            "- **U — Understand**: restate the problem, ask about input size, ranges, duplicates, empties. Write 1-2 examples.\n"
            "- **M — Match**: which known patterns fit? (two pointers, sliding window, BFS/DFS, DP, heap, binary search…)\n"
            "- **P — Plan**: sketch the approach in plain steps / pseudocode before coding. State target complexity.\n"
            "- **I — Implement**: code it cleanly, narrating decisions. Keep functions small.\n"
            "- **R — Review**: walk your code with an example, check off-by-one and edge cases.\n"
            "- **E — Evaluate**: state time/space complexity and possible optimizations.\n\n"
            "The single biggest senior signal: think out loud and drive the conversation — silence reads as being stuck."
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "You immediately see a brute-force solution. What should you do first in an interview?",
             "choices": [
                 "State the brute force + its complexity, then discuss whether a better approach exists before coding",
                 "Start coding the brute force silently to have something working",
                 "Ask the interviewer for the optimal answer",
                 "Skip to the optimal solution without explaining"],
             "answer": "State the brute force + its complexity, then discuss whether a better approach exists before coding",
             "explanation": "Verbalizing the brute force shows problem-solving and communication; you then optimize deliberately — exactly what UMPIRE's Match/Plan steps reward."},
            {"kind": "free",
             "prompt": "Interviewer gives you a problem. Walk me through your first 90 seconds before writing any code.",
             "answer": "Restate the problem in my words; ask clarifying questions (input size, value ranges, duplicates/negatives, empty input, expected output format); write one or two concrete examples including an edge case; state a brute-force idea and its complexity; then propose the pattern I'll actually use and its target complexity — only then start coding.",
             "explanation": "This is UMPIRE's Understand→Match→Plan. It prevents solving the wrong problem and demonstrates communication + structured thinking."},
        ],
    },
    {
        "slug": "system-design-framework",
        "track": "System Design",
        "title": "A System-Design Interview Framework",
        "difficulty": "core",
        "tags": "system-design,process,scaling",
        "summary": "The step order that keeps a 45-minute design round on track.",
        "lesson_md": (
            "Senior design rounds reward a **structured, requirements-driven** approach. A reliable order:\n\n"
            "1. **Clarify requirements** — functional (what it must do) and non-functional (scale, latency, availability, consistency). Nail the scope; don't boil the ocean.\n"
            "2. **Back-of-envelope estimates** — QPS, storage, bandwidth. Drives later choices (e.g. read:write ratio → caching).\n"
            "3. **API design** — a few core endpoints define the contract.\n"
            "4. **Data model** — entities, access patterns; pick SQL vs NoSQL from those patterns, not fashion.\n"
            "5. **High-level design** — draw boxes: clients, LB, services, datastores, cache, queue. Trace a request.\n"
            "6. **Scale & bottlenecks** — replicate, shard, cache, add async queues, CDNs. Name the bottleneck you're solving.\n"
            "7. **Trade-offs & failures** — consistency vs availability, hot spots, single points of failure, and how you'd monitor.\n\n"
            "Golden rule: state assumptions out loud and justify every component by a requirement — unmotivated tech name-drops hurt you."
        ),
        "cards": [
            {"kind": "free",
             "prompt": "Design a rate limiter for a public API. Walk me through it using a design framework.",
             "answer": "Clarify: per-user or per-IP? limits (e.g. 100 req/min)? distributed across many API servers? Estimate QPS. Approach: token-bucket or sliding-window-counter stored in a shared fast store (Redis) keyed by client id; each request atomically increments/consumes (Lua/INCR+EXPIRE) and is allowed if under limit, else 429 with Retry-After. Discuss: sliding window vs fixed window burst issues, Redis as a bottleneck/SPOF (replication, local pre-check), and clock/consistency trade-offs.",
             "explanation": "Strong answers pick an algorithm (token bucket / sliding window) AND address the distributed-state problem (shared store, atomicity) plus failure modes — following clarify→approach→scale→trade-offs."},
            {"kind": "mcq",
             "prompt": "In a design round, when should you do back-of-the-envelope capacity estimates?",
             "choices": [
                 "Early — they justify later architecture choices like caching and sharding",
                 "Never — they waste time",
                 "Only at the very end as a formality",
                 "Only if the interviewer asks explicitly"],
             "answer": "Early — they justify later architecture choices like caching and sharding",
             "explanation": "Estimates (QPS, storage, read:write ratio) turn architecture decisions from guesses into justified choices — a key senior signal."},
        ],
    },
    {
        "slug": "incident-ownership",
        "track": "Behavioral",
        "title": "Ownership: Incidents & Postmortems",
        "difficulty": "core",
        "tags": "behavioral,leadership,reliability",
        "summary": "Blameless postmortems and demonstrating operational ownership.",
        "lesson_md": (
            "Senior engineers own outcomes, including outages. A strong incident story shows:\n\n"
            "1. **Detection & triage** — how you found it, stopped the bleeding (rollback, feature flag), and communicated status.\n"
            "2. **Root cause** — the real cause, not the trigger. Use '5 whys'.\n"
            "3. **Blameless postmortem** — focus on systemic gaps (missing alert, no rollback path), not individuals.\n"
            "4. **Follow-through** — concrete action items you drove to prevent recurrence.\n\n"
            "Signal: you optimize for MTTR and learning, treat reliability as a feature, and build guardrails so the same class of bug can't recur."
        ),
        "cards": [
            {"kind": "free",
             "prompt": "Walk me through an outage you were responsible for and what you changed afterward.",
             "answer": "Cover: impact + how fast you mitigated (rollback/flag), the true root cause via 5-whys, a blameless framing, and the specific systemic fixes you drove (alerts, automated rollback, tests, capacity). End with the measurable improvement (e.g. MTTR down, no recurrence).",
             "explanation": "They're testing ownership and systems thinking. Owning your mistake honestly + preventing the whole class of failure is the senior signal."},
        ],
    },
    # ============ Saved-reels batch (2026-07-26): senior-track topics ============
    {
        "slug": "replication-and-sharding",
        "track": "System Design",
        "title": "Database Replication & Sharding",
        "difficulty": "core",
        "tags": "databases,scaling,replication,sharding",
        "summary": "Scale reads with replicas, scale writes with shards; know the failure modes of each.",
        "audience": "senior",
        "lesson_md": (
            "Two orthogonal scaling moves, usually applied in this order:\n\n"
            "**Replication** (copies of the same data) scales *reads* and buys availability.\n"
            "- **Leader-follower**: writes hit the leader, reads fan out to followers. *Async* replication is fast but "
            "can lose acked writes on failover and serves stale reads; *sync* is durable but adds write latency.\n"
            "- Watch for: replication lag (read-your-own-writes violations — pin a user to the leader briefly after a write), "
            "and failover split-brain (two leaders) — needs fencing/consensus.\n\n"
            "**Sharding** (partitioning data across nodes) scales *writes* and total storage.\n"
            "- **Hash sharding** spreads load evenly but kills range queries; **range sharding** keeps ranges cheap but risks hot shards.\n"
            "- **Consistent hashing** limits data movement when nodes join/leave.\n"
            "- Costs: cross-shard joins/transactions get hard, rebalancing is operationally risky, and a bad shard key is nearly "
            "irreversible — pick the key that matches your dominant access pattern (e.g. user_id for a user-centric app).\n\n"
            "Interview shape: state read:write ratio first — it decides whether you reach for replicas, shards, or just a cache."
                    "\n\n**Go deeper (HelloInterview):** [Sharding](https://www.hellointerview.com/learn/system-design/core-concepts/sharding) · [Consistent Hashing](https://www.hellointerview.com/learn/system-design/core-concepts/consistent-hashing) · [Scaling Writes pattern](https://www.hellointerview.com/learn/system-design/patterns/scaling-writes)"
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "Your service is write-heavy and a single primary DB is saturated on writes. What actually helps?",
             "choices": [
                 "Sharding — partition writes across nodes by a well-chosen key",
                 "Adding read replicas",
                 "Raising the connection pool size",
                 "Adding a CDN"],
             "answer": "Sharding — partition writes across nodes by a well-chosen key",
             "explanation": "Replicas only scale reads — every replica still applies every write. Partitioning the write stream is the move; the shard key choice is the real design decision."},
            {"kind": "free",
             "prompt": "A user updates their profile, then immediately sees the old value. Why, and how do you fix it?",
             "answer": "Replication lag: the write went to the leader, the follow-up read hit a stale follower. Fixes: read-your-own-writes consistency — route the user's reads to the leader for a short window after a write (or track a session LSN/timestamp and only serve from replicas that have caught up), or serve that page from the leader.",
             "explanation": "Classic async-replication symptom. Naming 'read-your-own-writes' and giving a concrete routing fix is the senior answer."},
        ],
    },
    {
        "slug": "auth-jwt-oauth",
        "track": "CS Fundamentals",
        "title": "Authentication: Sessions, JWT & OAuth 2.0",
        "difficulty": "core",
        "tags": "auth,security,jwt,oauth,backend",
        "summary": "What actually happens after 'Login': sessions vs tokens, refresh flows, OAuth roles, PKCE.",
        "audience": "senior",
        "lesson_md": (
            "**Authentication** proves who you are; **authorization** decides what you may do.\n\n"
            "**Session-based**: server stores session state, browser holds an opaque cookie. Easy to revoke (delete the session); "
            "needs sticky sessions or a shared session store to scale.\n\n"
            "**JWT (stateless tokens)**: the server signs a claims payload; any instance can verify without a lookup. "
            "Trade-off: you can't revoke a stolen JWT before it expires — so keep **access tokens short-lived** (minutes) and pair with a "
            "**refresh token** (long-lived, stored server-side, revocable, ideally rotated on each use). "
            "JWTs are signed, not encrypted — never put secrets in the payload; always validate `alg`, `exp`, `aud`, `iss`.\n\n"
            "**OAuth 2.0** is *delegated authorization* (let app X act on my data at Y) — with OIDC layered on top for login. "
            "Know the roles (resource owner, client, authorization server, resource server) and the **authorization-code flow**; "
            "public clients (SPAs, mobile) must add **PKCE** because they can't hold a client secret.\n\n"
            "Cookie hygiene: `HttpOnly` (no JS access → XSS-resistant), `Secure`, `SameSite` (CSRF mitigation)."
                    "\n\n**Go deeper (HelloInterview):** [API Design](https://www.hellointerview.com/learn/system-design/core-concepts/api-design)"
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "Why pair a short-lived JWT access token with a refresh token instead of one long-lived JWT?",
             "choices": [
                 "Stateless JWTs can't be revoked, so the short expiry bounds the damage of a stolen token while the revocable refresh token preserves the session",
                 "Two tokens are harder to guess than one",
                 "JWTs expire on their own and refresh tokens don't",
                 "It reduces the size of each HTTP request"],
             "answer": "Stateless JWTs can't be revoked, so the short expiry bounds the damage of a stolen token while the revocable refresh token preserves the session",
             "explanation": "The refresh token lives server-side (revocable, rotatable); the access token stays stateless and fast to verify. This split is the standard answer to 'how do you log someone out with JWTs'."},
            {"kind": "free",
             "prompt": "Walk through the OAuth 2.0 authorization-code flow with PKCE for a mobile app. Why is PKCE needed?",
             "answer": "App generates a random code_verifier and sends its hash (code_challenge) with the auth request; user authenticates at the authorization server, which redirects back with an authorization code; app exchanges code + code_verifier for tokens, and the server checks the verifier hashes to the original challenge. PKCE is needed because a mobile/SPA client can't keep a client secret and the redirect can be intercepted — the verifier proves the token requester is the same party that started the flow.",
             "explanation": "The interviewer is checking you know why the code exchange exists at all (tokens never transit the browser) and what attack PKCE kills (authorization-code interception)."},
        ],
    },
    {
        "slug": "database-indexing",
        "track": "CS Fundamentals",
        "title": "Indexing & Query Optimization",
        "difficulty": "core",
        "tags": "databases,sql,indexes,performance,backend",
        "summary": "B-tree mechanics, composite-index rules, and why writes pay for every index.",
        "audience": "senior",
        "lesson_md": (
            "An index trades write cost and space for read speed. Most are **B+ trees**: sorted keys, O(log n) lookups, great for "
            "equality *and* range scans; leaves point at rows (or contain them, in a clustered index).\n\n"
            "Rules that answer 90% of interview questions:\n"
            "- **Leftmost prefix**: an index on `(a, b, c)` serves filters on `a`, `a,b`, `a,b,c` — but not `b` or `c` alone.\n"
            "- **Range stops the chain**: after a range condition on one column, later index columns can't be used for filtering.\n"
            "- **Covering index**: if the index contains every column the query needs, the table lookup is skipped entirely.\n"
            "- **Functions kill index use**: `WHERE lower(email) = ...` can't use a plain index on `email` (needs a functional index).\n"
            "- **Selectivity matters**: indexing a 2-value column rarely helps; the planner will scan anyway.\n\n"
            "Every index slows every INSERT/UPDATE/DELETE (each one must be maintained) — 'index everything' is a write-amplification bug.\n\n"
            "Debugging tool #1: `EXPLAIN (ANALYZE)` — check for seq scans on hot paths, misestimated row counts, and sorts that an index could absorb."
                    "\n\n**Go deeper (HelloInterview):** [Database Indexing](https://www.hellointerview.com/learn/system-design/core-concepts/db-indexing) · [PostgreSQL deep-dive](https://www.hellointerview.com/learn/system-design/deep-dives/postgres)"
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "With an index on (last_name, first_name), which query CANNOT use it effectively?",
             "choices": [
                 "WHERE first_name = 'Ada'",
                 "WHERE last_name = 'Lovelace'",
                 "WHERE last_name = 'Lovelace' AND first_name = 'Ada'",
                 "WHERE last_name LIKE 'Love%'"],
             "answer": "WHERE first_name = 'Ada'",
             "explanation": "Leftmost-prefix rule: the index is sorted by last_name first, so a filter on first_name alone can't navigate the tree."},
            {"kind": "free",
             "prompt": "A production query got slow. Walk me through how you'd diagnose and fix it.",
             "answer": "Reproduce with EXPLAIN ANALYZE; look for sequential scans on large tables, row-estimate vs actual mismatches (stale statistics → ANALYZE), and expensive sorts/joins. Fix options in order: add/adjust an index matching the filter+sort (mind leftmost-prefix), make it covering if the query is hot, rewrite the query (avoid functions on indexed columns, avoid SELECT *), or restructure (denormalize/cache) if the access pattern fundamentally doesn't fit. Verify with EXPLAIN again and check write-path cost of the new index.",
             "explanation": "Senior signal: a measurement-first loop (EXPLAIN → hypothesis → fix → re-measure) plus awareness that each index taxes writes."},
        ],
    },
    {
        "slug": "ticket-booking-design",
        "track": "System Design",
        "title": "Design a Ticket-Booking System (BookMyShow)",
        "difficulty": "advanced",
        "tags": "system-design,concurrency,transactions,case-study",
        "summary": "The classic contention problem: sell each seat exactly once, at scale, with payments in the loop.",
        "audience": "senior",
        "lesson_md": (
            "Booking systems are interview favorites because the hard part is **contention**: thousands of users racing for the same seats.\n\n"
            "**Core flow**: browse (heavy reads, cacheable) → select seats → *hold* → pay → confirm.\n\n"
            "**The seat-hold pattern** is the crux:\n"
            "- On selection, place a **short TTL lock** on the seats (e.g. 5–10 min) so the user can pay without losing them.\n"
            "- Implement with a row status (`AVAILABLE → HELD(expiry) → BOOKED`) updated under a transaction, or a Redis lock keyed by seat. "
            "Expired holds are reaped (or checked lazily on read).\n"
            "- The transition must be atomic and guarded: `UPDATE seats SET status='HELD' WHERE id IN (...) AND status='AVAILABLE'` — "
            "check affected-row count == seats requested, else roll back (someone beat you).\n\n"
            "**Payments** are slow and external → do them *outside* the DB transaction; the hold TTL covers the gap. Handle payment-success-after-"
            "hold-expiry (refund or re-check) and use **idempotency keys** so retries don't double-book.\n\n"
            "**Scale notes**: browse traffic ≫ booking traffic — cache screenings/availability aggressively with short TTLs; shard by city or venue; "
            "the seat map for one show is small, so per-show contention is the bottleneck, not data volume. Popular-show on-sale spikes → queue admission (virtual waiting room)."
                    "\n\n**Go deeper (HelloInterview):** [Ticketmaster breakdown](https://www.hellointerview.com/learn/system-design/problem-breakdowns/ticketmaster) · [BookMyShow LLD](https://www.hellointerview.com/learn/low-level-design/problem-breakdowns/bookmyshow) · [Dealing with Contention](https://www.hellointerview.com/learn/system-design/patterns/dealing-with-contention)"
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "Two users click the same seat at the same moment. What prevents a double sale?",
             "choices": [
                 "An atomic conditional transition (AVAILABLE→HELD) that only one request can win, verified by affected-row count",
                 "Optimistically letting both pay and refunding the slower one",
                 "Caching the seat map so both see it as taken",
                 "Making the frontend grey out the seat faster"],
             "answer": "An atomic conditional transition (AVAILABLE→HELD) that only one request can win, verified by affected-row count",
             "explanation": "Correctness lives in the storage layer's atomicity, not the UI. The conditional UPDATE (or equivalent lock) is the exactly-once gate; everything else is UX."},
            {"kind": "free",
             "prompt": "Why should the payment call live outside the database transaction that holds the seats, and what new problems does that create?",
             "answer": "A DB transaction held open across an external payment call (seconds, can hang) would pin locks/connections and collapse throughput. Instead: commit the HELD state with a TTL, call the payment provider, then confirm. New problems: payment succeeds after the hold expired (detect and refund or re-acquire), payment retries double-charging (idempotency keys), and reconciliation for crashes between payment and confirm (a sweeper comparing provider records to bookings).",
             "explanation": "This is the distributed-transaction trap: never wrap an external call in a lock. The TTL-hold + idempotency + reconciliation trio is the senior-level answer."},
        ],
    },
    {
        "slug": "debugging-interviews",
        "track": "DSA",
        "title": "The Debugging Interview (Post-LeetCode Formats)",
        "difficulty": "core",
        "tags": "debugging,testing,interview-format,meta",
        "summary": "Interviews are shifting toward debugging broken systems, testing strategy, and real PR workflows.",
        "audience": "senior",
        "lesson_md": (
            "Platforms (HackerRank among them) are rebuilding interview formats away from pure algorithms toward what seniors do daily: "
            "**fix broken code, reason about tests, and ship reviewable PRs** — partly because AI made puzzle-solving cheap to fake.\n\n"
            "**Debugging rounds**: you get a failing service/test and limited time. Approach like an incident:\n"
            "1. Reproduce reliably; read the actual error, not what you assume it says.\n"
            "2. Bisect the search space — logs, recent diffs, binary-search the pipeline (is the bug before or after this point?).\n"
            "3. Form one hypothesis at a time and design the *cheapest observation* that falsifies it.\n"
            "4. Fix the cause, not the symptom; add the regression test; say out loud how you'd prevent the class of bug.\n\n"
            "**Testing-pyramid questions**: many fast unit tests at the base, fewer integration tests, few E2E — know *why* (speed, flakiness, "
            "localization of failures) and when to break the rule.\n\n"
            "**PR rounds**: small diffs, clear description of intent and risk, tests included, responsive to review comments.\n\n"
            "Practice: sadservers.com (broken-server scenarios), fixing failing tests in open-source repos, and narrating your debugging out loud — the narration *is* the signal."
                    "\n\n**Go deeper (HelloInterview):** [AI-Coding track](https://www.hellointerview.com/learn/ai-coding/overview/introduction) — the adjacent new format: drive an AI in a real codebase, verify and test its output"
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "In a timed debugging round, what should you do FIRST with a failing system?",
             "choices": [
                 "Reproduce the failure and read the actual error output carefully",
                 "Start adding print statements everywhere",
                 "Rewrite the suspicious-looking module",
                 "Check the code style for issues"],
             "answer": "Reproduce the failure and read the actual error output carefully",
             "explanation": "Reproduction turns guessing into measurement, and most candidates lose minutes acting on a misread error message. Observation before mutation."},
            {"kind": "free",
             "prompt": "Why does the testing pyramid put most tests at the unit level, and when is it right to violate that?",
             "answer": "Unit tests are fast, deterministic, and localize failures to a function — so you can afford thousands and run them on every change. Integration/E2E tests are slower, flakier, and a failure implicates the whole stack. Violate it when the risk lives in the seams: heavy integration layers (ORMs, network protocols), config-driven systems, or thin-logic services where mocked unit tests would only test the mocks.",
             "explanation": "Knowing the why (feedback speed + failure localization) and the legitimate exceptions separates a memorized pyramid from an understood one."},
        ],
    },
    {
        "slug": "agentic-ai-concepts",
        "track": "System Design",
        "title": "Agentic AI Systems: Core Concepts",
        "difficulty": "advanced",
        "tags": "genai,agents,llm,inference,ml-system-design",
        "summary": "The vocabulary of production agent systems: harness, loop, context, tools, evals.",
        "audience": "senior",
        "lesson_md": (
            "GenAI system-design rounds increasingly assume this vocabulary:\n\n"
            "- **Harness engineering** — the environment the agent acts in: sandbox, filesystem/runtime surface, permissions. "
            "The harness bounds the blast radius of a wrong action.\n"
            "- **Loop engineering** — when the agent iterates vs stops: max steps, budgets, convergence checks, human-approval gates for "
            "irreversible actions.\n"
            "- **Context engineering** — getting the right information into the window and keeping the wrong stuff out: retrieval, "
            "summarization/compaction of history, structured state instead of raw transcripts. Context is the scarce resource.\n"
            "- **Tool design** — few, well-named tools with typed inputs and crisp failure messages beat many overlapping ones; "
            "the model can only be as reliable as the tool contract is clear.\n"
            "- **Evals & guardrails** — regression suites of real tasks (not vibes), output validation, and rate/permission limits. "
            "Without evals, every prompt change is a blind deploy.\n\n"
            "Design-round framing: an agent system is a *state machine where an LLM chooses transitions* — so the classic questions "
            "(idempotency, retries, observability, failure isolation) all still apply, plus one new one: how do you bound and evaluate "
            "a non-deterministic component?"
                    "\n\n**Go deeper (HelloInterview):** [ChatGPT system design](https://www.hellointerview.com/learn/system-design/problem-breakdowns/chatgpt) · [Vector Databases](https://www.hellointerview.com/learn/system-design/deep-dives/vector-databases) · [ML System Design in a Hurry](https://www.hellointerview.com/learn/ml-system-design/in-a-hurry/introduction)"
        ),
        "cards": [
            {"kind": "mcq",
             "prompt": "An LLM agent occasionally issues a destructive action (e.g. deleting records). What's the *systems* fix?",
             "choices": [
                 "Constrain the harness: sandbox/permissions that make the action impossible, plus approval gates for irreversible steps",
                 "Add 'please be careful' to the prompt",
                 "Use a larger model",
                 "Lower the temperature to 0"],
             "answer": "Constrain the harness: sandbox/permissions that make the action impossible, plus approval gates for irreversible steps",
             "explanation": "Prompting reduces probability; the harness sets it to zero. Treat the model as an untrusted component and enforce safety at the boundary — same instinct as input validation."},
            {"kind": "free",
             "prompt": "Your agent's context window fills up during long tasks and quality degrades. What are your options?",
             "answer": "Context engineering: summarize/compact older turns into structured state; store working data in files or a scratchpad and retrieve on demand instead of carrying it in-window; split the task across sub-agents that each get a focused context and return only conclusions; and rank/filter retrievals so only task-relevant content enters the window. Measure with evals that specifically include long-horizon tasks.",
             "explanation": "The interviewer wants 'context is a budget to manage' — compaction, externalized state, and decomposition are the standard levers."},
        ],
    },
]
