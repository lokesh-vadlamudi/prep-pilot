"""Curated per-category algorithm cheatsheets.

Inspired by the Tech Interview Handbook's study cheatsheets: for each pattern,
the key techniques, the corner cases interviewers expect you to check, and the
target complexity. Hand-authored (reference material must be correct). Keyed by
the NeetCode-150 category names used in neetcode150.py.
"""
from __future__ import annotations

CHEATSHEETS: dict[str, dict] = {
    "Arrays & Hashing": {
        "techniques": [
            "Hash map/set for O(1) membership and complement lookups (two-sum style).",
            "Frequency counting with a dict/Counter for anagrams, top-K, dedup.",
            "Prefix sums for range-sum / subarray-sum queries in O(1) after O(n) setup.",
            "Encode composite keys (sorted string, tuple of counts) to group items.",
        ],
        "corner_cases": [
            "Empty array / single element.",
            "Duplicates present (does the answer allow them?).",
            "Negative numbers and zero.",
            "Very large arrays — is O(n^2) fast enough? Usually not.",
        ],
        "complexity": "Aim for O(n) time, O(n) space. Hashing trades space for time.",
    },
    "Two Pointers": {
        "techniques": [
            "Opposite ends moving inward on a SORTED array (two-sum II, container).",
            "Fast/slow pointers for cycle detection and finding the middle.",
            "Write pointer for in-place filtering / dedup.",
        ],
        "corner_cases": [
            "Empty / single element / all duplicates.",
            "Pointers crossing — loop while lo < hi, not <=.",
            "Skipping duplicates to avoid repeated answers (3Sum).",
        ],
        "complexity": "Usually O(n) time, O(1) space — often replaces a nested loop. Requires sorted input or a monotonic invariant.",
    },
    "Sliding Window": {
        "techniques": [
            "Grow the window with a right pointer; shrink from the left to restore an invariant.",
            "Maintain window state in a hash map / counter (chars, need/have counts).",
            "Fixed-size window: slide by one, add new / remove old element.",
        ],
        "corner_cases": [
            "Window of size 0 or larger than the input.",
            "When to update the answer — inside vs. after shrinking.",
            "Duplicate characters resetting the window start correctly.",
        ],
        "complexity": "O(n) — each element enters and leaves the window at most once.",
    },
    "Stack": {
        "techniques": [
            "Match/balance problems: push openers, pop on closers.",
            "Monotonic stack (increasing/decreasing) for next-greater / histogram spans.",
            "Store indices, not just values, when you need distances.",
        ],
        "corner_cases": [
            "Empty stack pop — check before popping.",
            "Leftover items on the stack at the end (unmatched openers).",
            "Equal elements — decide < vs <= for the monotonic invariant.",
        ],
        "complexity": "O(n) time, O(n) space; each element pushed/popped once.",
    },
    "Binary Search": {
        "techniques": [
            "Search a sorted array — halve the range each step.",
            "Binary search on the ANSWER (min/max feasible value) when the check is monotonic.",
            "Find leftmost/rightmost boundary with lower/upper-bound variants.",
        ],
        "corner_cases": [
            "Off-by-one: lo <= hi vs lo < hi; mid = lo + (hi-lo)//2 to avoid overflow.",
            "Target absent / array empty.",
            "Duplicates when finding first/last position.",
        ],
        "complexity": "O(log n) per search. Infinite loop if the range doesn't shrink — verify pointer moves.",
    },
    "Linked List": {
        "techniques": [
            "Dummy/sentinel head to simplify insertion/deletion at the front.",
            "Fast/slow pointers for middle, cycle, and nth-from-end.",
            "Reverse in place with prev/cur/next; reconnect carefully.",
        ],
        "corner_cases": [
            "Empty list / single node.",
            "Operations at head or tail.",
            "Cycles — don't loop forever; losing the rest of the list when rewiring.",
        ],
        "complexity": "Most are O(n) time, O(1) space. Draw the pointers before coding.",
    },
    "Trees": {
        "techniques": [
            "DFS (recursion) for depth/path/validation; return info up from children.",
            "BFS (queue) for level-order and shortest-depth problems.",
            "BST property: in-order traversal is sorted; use min/max bounds to validate.",
        ],
        "corner_cases": [
            "Empty tree (null root) / single node.",
            "Skewed tree → recursion depth O(n) (stack overflow risk).",
            "Duplicate values; negative node values in path sums.",
        ],
        "complexity": "O(n) time; space O(h) for recursion (h = height), O(w) for BFS (w = width).",
    },
    "Tries": {
        "techniques": [
            "Node = map of children + isEnd flag; insert/search char by char.",
            "DFS the trie for wildcard/prefix matching.",
            "Combine a trie with grid backtracking to match many words at once.",
        ],
        "corner_cases": [
            "Empty string / prefix that is also a full word.",
            "Searching a word that's a prefix of an inserted word (isEnd matters).",
            "Case sensitivity and character set size.",
        ],
        "complexity": "Insert/search O(L) for word length L; space O(total chars).",
    },
    "Heap / Priority Queue": {
        "techniques": [
            "Min-heap of size k for the k largest (and vice versa).",
            "Two heaps (max-heap low half, min-heap high half) for a running median.",
            "Push (cost, node) tuples for Dijkstra / merge-k-lists.",
        ],
        "corner_cases": [
            "k larger than the input size.",
            "Ties — decide the tie-break ordering.",
            "Empty heap access; heap of size 0/1.",
        ],
        "complexity": "push/pop O(log n); building a heap O(n). Top-k in O(n log k).",
    },
    "Backtracking": {
        "techniques": [
            "Choose → recurse → un-choose; pass a start index to avoid reusing/reordering.",
            "Sort first, then skip duplicates at the same tree level.",
            "Prune branches early (bounds, used[] array, constraints).",
        ],
        "corner_cases": [
            "Empty input → the single empty solution.",
            "Duplicate elements producing duplicate subsets/permutations.",
            "Deep-copy the partial result when recording it (don't store a reference).",
        ],
        "complexity": "Exponential by nature — O(2^n), O(n!), etc. Pruning is what makes it pass.",
    },
    "Graphs": {
        "techniques": [
            "Build an adjacency list; track a visited set to avoid revisiting.",
            "DFS/BFS for connectivity, flood fill, and grid traversal.",
            "Topological sort (Kahn's / DFS) for ordering with prerequisites; detects cycles.",
            "Union-Find for connected components and cycle detection.",
        ],
        "corner_cases": [
            "Disconnected graph — loop over all nodes as start points.",
            "Cycles / self-loops / duplicate edges.",
            "Grid bounds and marking visited to avoid infinite loops.",
        ],
        "complexity": "O(V + E) for BFS/DFS; multi-source BFS for shortest unweighted distances.",
    },
    "Advanced Graphs": {
        "techniques": [
            "Dijkstra (min-heap) for shortest paths with non-negative weights.",
            "Prim's / Kruskal's for minimum spanning tree.",
            "Bellman-Ford for ≤k-edge / negative-weight paths.",
            "Hierholzer's algorithm for Eulerian paths (itinerary).",
        ],
        "corner_cases": [
            "Unreachable nodes (infinite distance).",
            "Negative weights (Dijkstra invalid) vs. non-negative.",
            "Disconnected components; duplicate/parallel edges.",
        ],
        "complexity": "Dijkstra O(E log V); MST O(E log E); Bellman-Ford O(V·E).",
    },
    "1-D DP": {
        "techniques": [
            "Define dp[i] = best answer ending at / using up to i; find the recurrence.",
            "Roll two variables when only dp[i-1], dp[i-2] are needed (O(1) space).",
            "Decide direction (forward/backward) and base cases explicitly.",
        ],
        "corner_cases": [
            "n = 0 or 1 (base cases).",
            "Negative numbers (max-subarray, products flip signs).",
            "Unreachable states — initialize with a sentinel (inf / -1).",
        ],
        "complexity": "Usually O(n) time; O(1) or O(n) space. State out the recurrence out loud.",
    },
    "2-D DP": {
        "techniques": [
            "dp[i][j] over two sequences / a grid; fill by rows or diagonals.",
            "Interval DP (burst balloons) — iterate by increasing interval length.",
            "Reduce to 1-D when each row depends only on the previous row.",
        ],
        "corner_cases": [
            "Empty string/grid; first row/column base cases.",
            "Index bounds when referencing dp[i-1][j-1].",
            "Off-by-one between string index and dp index.",
        ],
        "complexity": "Typically O(m·n) time and space (often reducible to O(min(m,n)) space).",
    },
    "Greedy": {
        "techniques": [
            "Sort by the right key (end time, ratio) then make a locally optimal choice.",
            "Track a running best/furthest-reach (jump game, max subarray).",
            "Prove the greedy choice is safe — or fall back to DP if it isn't.",
        ],
        "corner_cases": [
            "Ties in the sort key.",
            "Empty input / single element.",
            "Cases where greedy FAILS — confirm optimal substructure holds.",
        ],
        "complexity": "Often O(n log n) (dominated by the sort). Greedy ≠ always correct — justify it.",
    },
    "Intervals": {
        "techniques": [
            "Sort by start (merging) or by end (max non-overlapping / scheduling).",
            "Sweep line / min-heap of end times for room-count problems.",
            "Two intervals overlap iff a.start <= b.end AND b.start <= a.end.",
        ],
        "corner_cases": [
            "Touching intervals ([1,2],[2,3]) — do they count as overlapping?",
            "Single interval / empty list.",
            "Unsorted input; fully-nested intervals.",
        ],
        "complexity": "O(n log n) from the sort, then O(n) sweep.",
    },
    "Math & Geometry": {
        "techniques": [
            "In-place matrix ops via transpose + reverse (rotate) or boundary shrinking (spiral).",
            "Digit manipulation with %/// and carry handling.",
            "Fast exponentiation by squaring; watch integer overflow.",
        ],
        "corner_cases": [
            "Overflow / negative numbers / zero.",
            "Empty matrix, non-square dimensions, single row or column.",
            "Off-by-one on boundary indices.",
        ],
        "complexity": "Matrix ops O(m·n); pow(x,n) O(log n). Prefer O(1) extra space in-place.",
    },
    "Bit Manipulation": {
        "techniques": [
            "XOR: a^a=0, a^0=a — cancels pairs (single number, missing number).",
            "n & (n-1) clears the lowest set bit (count bits).",
            "Masks and shifts to read/set individual bits.",
        ],
        "corner_cases": [
            "Negative numbers / two's-complement and sign bits.",
            "32-bit vs 64-bit overflow bounds.",
            "Shifting by >= width is undefined in some languages.",
        ],
        "complexity": "O(1) or O(#bits) — usually O(32). Constant space.",
    },
}


def cheatsheet_for(category: str) -> dict | None:
    return CHEATSHEETS.get(category)
