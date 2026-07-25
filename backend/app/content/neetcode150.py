"""NeetCode 150 — the expanded curated coding-interview set (superset of Blind 75).

Same policy as blind75.py: only factual public metadata (title, category,
difficulty, official LeetCode slug) plus a SHORT pattern hint in our own words.
Full worked approaches are generated on demand by the DGX model and cached.

Tuple shape: (slug, title, category, difficulty, in_blind75, blurb, pattern)
Categories follow NeetCode's roadmap taxonomy. Order is the roadmap order.
"""
from __future__ import annotations

_NC: list[tuple[str, str, str, str, bool, str, str]] = [
    # ---------- Arrays & Hashing ----------
    ("contains-duplicate", "Contains Duplicate", "Arrays & Hashing", "Easy", True, "Detect if any value repeats.", "Hash set membership."),
    ("valid-anagram", "Valid Anagram", "Arrays & Hashing", "Easy", True, "Are two strings anagrams?", "Compare character counts."),
    ("two-sum", "Two Sum", "Arrays & Hashing", "Easy", True, "Indices of two numbers adding to target.", "Hash map of complements, O(n)."),
    ("group-anagrams", "Group Anagrams", "Arrays & Hashing", "Medium", True, "Group words that are anagrams.", "Key by sorted string or char-count tuple."),
    ("top-k-frequent-elements", "Top K Frequent Elements", "Arrays & Hashing", "Medium", True, "The k most frequent values.", "Count + bucket sort by frequency."),
    ("product-of-array-except-self", "Product of Array Except Self", "Arrays & Hashing", "Medium", True, "Product except self, no division.", "Prefix then suffix products."),
    ("valid-sudoku", "Valid Sudoku", "Arrays & Hashing", "Medium", False, "Is a 9×9 board valid so far?", "Hash sets per row/col/3×3 box."),
    ("encode-and-decode-strings", "Encode and Decode Strings", "Arrays & Hashing", "Medium", True, "Serialize a list of strings. (Premium)", "Length-prefix: '<len>#<str>'."),
    ("longest-consecutive-sequence", "Longest Consecutive Sequence", "Arrays & Hashing", "Medium", True, "Longest run of consecutive ints.", "Hash set; count only from sequence heads."),

    # ---------- Two Pointers ----------
    ("valid-palindrome", "Valid Palindrome", "Two Pointers", "Easy", True, "Palindrome ignoring non-alnum.", "Two pointers inward, skip non-alnum."),
    ("two-sum-ii-input-array-is-sorted", "Two Sum II", "Two Pointers", "Medium", False, "Two-sum on a sorted array.", "Two pointers from the ends."),
    ("3sum", "3Sum", "Two Pointers", "Medium", True, "Unique triplets summing to zero.", "Sort, then two pointers per anchor."),
    ("container-with-most-water", "Container With Most Water", "Two Pointers", "Medium", True, "Max water between two lines.", "Two pointers, move the shorter side."),
    ("trapping-rain-water", "Trapping Rain Water", "Two Pointers", "Hard", False, "Total trapped rainwater.", "Two pointers tracking left/right max."),

    # ---------- Sliding Window ----------
    ("best-time-to-buy-and-sell-stock", "Best Time to Buy and Sell Stock", "Sliding Window", "Easy", True, "Max profit from one buy/sell.", "Track min price seen so far."),
    ("longest-substring-without-repeating-characters", "Longest Substring Without Repeating Characters", "Sliding Window", "Medium", True, "Longest all-unique substring.", "Window + last-seen index map."),
    ("longest-repeating-character-replacement", "Longest Repeating Character Replacement", "Sliding Window", "Medium", True, "Longest run allowing k replacements.", "Window valid while len - maxCount ≤ k."),
    ("permutation-in-string", "Permutation in String", "Sliding Window", "Medium", False, "Does s2 contain a permutation of s1?", "Fixed-size window of char counts."),
    ("minimum-window-substring", "Minimum Window Substring", "Sliding Window", "Hard", True, "Smallest window covering all target chars.", "Window with need/have counts."),
    ("sliding-window-maximum", "Sliding Window Maximum", "Sliding Window", "Hard", False, "Max of each window of size k.", "Monotonic decreasing deque of indices."),

    # ---------- Stack ----------
    ("valid-parentheses", "Valid Parentheses", "Stack", "Easy", True, "Balanced/nested brackets?", "Stack of expected closers."),
    ("min-stack", "Min Stack", "Stack", "Medium", False, "Stack with O(1) getMin.", "Auxiliary stack of running minimums."),
    ("evaluate-reverse-polish-notation", "Evaluate Reverse Polish Notation", "Stack", "Medium", False, "Evaluate an RPN expression.", "Stack: pop two operands per operator."),
    ("generate-parentheses", "Generate Parentheses", "Stack", "Medium", False, "All valid parenthesis combinations.", "Backtracking with open/close counts."),
    ("daily-temperatures", "Daily Temperatures", "Stack", "Medium", False, "Days until a warmer temperature.", "Monotonic decreasing stack of indices."),
    ("car-fleet", "Car Fleet", "Stack", "Medium", False, "Count car fleets reaching the target.", "Sort by position; stack of arrival times."),
    ("largest-rectangle-in-histogram", "Largest Rectangle in Histogram", "Stack", "Hard", False, "Largest rectangle area in a histogram.", "Monotonic increasing stack of (index,height)."),

    # ---------- Binary Search ----------
    ("binary-search", "Binary Search", "Binary Search", "Easy", False, "Classic search in a sorted array.", "Halve the range each step."),
    ("search-a-2d-matrix", "Search a 2D Matrix", "Binary Search", "Medium", False, "Search a row/col-sorted matrix.", "Treat as flattened sorted array."),
    ("koko-eating-bananas", "Koko Eating Bananas", "Binary Search", "Medium", False, "Min eating speed to finish in h hours.", "Binary search on the answer (speed)."),
    ("find-minimum-in-rotated-sorted-array", "Find Minimum in Rotated Sorted Array", "Binary Search", "Medium", True, "Min of a rotated sorted array.", "Binary search on the rotation point."),
    ("search-in-rotated-sorted-array", "Search in Rotated Sorted Array", "Binary Search", "Medium", True, "Search in a rotated sorted array.", "One half is always sorted."),
    ("time-based-key-value-store", "Time Based Key-Value Store", "Binary Search", "Medium", False, "get(key, timestamp) ≤ time.", "Per-key sorted list + binary search on time."),
    ("median-of-two-sorted-arrays", "Median of Two Sorted Arrays", "Binary Search", "Hard", False, "Median of two sorted arrays in log time.", "Binary search partition of the smaller array."),

    # ---------- Linked List ----------
    ("reverse-linked-list", "Reverse Linked List", "Linked List", "Easy", True, "Reverse a singly linked list.", "Iterative prev/cur/next flip."),
    ("merge-two-sorted-lists", "Merge Two Sorted Lists", "Linked List", "Easy", True, "Merge two sorted lists.", "Dummy head + two-pointer splice."),
    ("reorder-list", "Reorder List", "Linked List", "Medium", True, "Reorder L0→Ln→L1→…", "Find mid, reverse half, merge."),
    ("remove-nth-node-from-end-of-list", "Remove Nth Node From End of List", "Linked List", "Medium", True, "Remove nth-from-end node.", "Two pointers spaced n apart."),
    ("copy-list-with-random-pointer", "Copy List With Random Pointer", "Linked List", "Medium", False, "Deep-copy a list with random pointers.", "Hash old→new, or interleave clones."),
    ("add-two-numbers", "Add Two Numbers", "Linked List", "Medium", False, "Add two digit-lists.", "Walk both with a carry."),
    ("linked-list-cycle", "Linked List Cycle", "Linked List", "Easy", True, "Detect a cycle.", "Floyd's fast/slow pointers."),
    ("find-the-duplicate-number", "Find the Duplicate Number", "Linked List", "Medium", False, "Find the one duplicate, O(1) space.", "Floyd's cycle detection on values-as-links."),
    ("lru-cache", "LRU Cache", "Linked List", "Medium", False, "O(1) get/put least-recently-used cache.", "Hash map + doubly linked list."),
    ("merge-k-sorted-lists", "Merge k Sorted Lists", "Linked List", "Hard", True, "Merge k sorted lists.", "Min-heap or divide & conquer."),
    ("reverse-nodes-in-k-group", "Reverse Nodes in k-Group", "Linked List", "Hard", False, "Reverse every k nodes.", "Reverse each group with careful relinking."),

    # ---------- Trees ----------
    ("invert-binary-tree", "Invert Binary Tree", "Trees", "Easy", True, "Mirror a binary tree.", "Swap children recursively."),
    ("maximum-depth-of-binary-tree", "Maximum Depth of Binary Tree", "Trees", "Easy", True, "Tree height.", "DFS: 1 + max(left, right)."),
    ("diameter-of-binary-tree", "Diameter of Binary Tree", "Trees", "Easy", False, "Longest path between any two nodes.", "DFS returns height, track left+right max."),
    ("balanced-binary-tree", "Balanced Binary Tree", "Trees", "Easy", False, "Is every subtree height-balanced?", "DFS returns height or -1 if unbalanced."),
    ("same-tree", "Same Tree", "Trees", "Easy", True, "Are two trees identical?", "Parallel DFS."),
    ("subtree-of-another-tree", "Subtree of Another Tree", "Trees", "Easy", True, "Is t a subtree of s?", "DFS + same-tree check."),
    ("lowest-common-ancestor-of-a-binary-search-tree", "Lowest Common Ancestor of a BST", "Trees", "Medium", True, "LCA of two BST nodes.", "Walk using BST ordering."),
    ("binary-tree-level-order-traversal", "Binary Tree Level Order Traversal", "Trees", "Medium", True, "Nodes level by level.", "BFS one level per iteration."),
    ("binary-tree-right-side-view", "Binary Tree Right Side View", "Trees", "Medium", False, "Values visible from the right.", "BFS, take the last node per level."),
    ("count-good-nodes-in-binary-tree", "Count Good Nodes in Binary Tree", "Trees", "Medium", False, "Nodes ≥ all ancestors on their path.", "DFS carrying the running max."),
    ("validate-binary-search-tree", "Validate Binary Search Tree", "Trees", "Medium", True, "Is it a valid BST?", "DFS with (min, max) bounds."),
    ("kth-smallest-element-in-a-bst", "Kth Smallest Element in a BST", "Trees", "Medium", True, "kth smallest value.", "In-order traversal stops at k."),
    ("construct-binary-tree-from-preorder-and-inorder-traversal", "Construct Tree from Preorder & Inorder", "Trees", "Medium", True, "Rebuild tree from traversals.", "Preorder roots; inorder index splits."),
    ("binary-tree-maximum-path-sum", "Binary Tree Maximum Path Sum", "Trees", "Hard", True, "Max path sum between any nodes.", "DFS returns best branch; track global."),
    ("serialize-and-deserialize-binary-tree", "Serialize and Deserialize Binary Tree", "Trees", "Hard", True, "Encode a tree to string and back.", "Preorder DFS with null markers."),

    # ---------- Tries ----------
    ("implement-trie-prefix-tree", "Implement Trie (Prefix Tree)", "Tries", "Medium", True, "insert/search/startsWith.", "Nodes with children map + isEnd."),
    ("design-add-and-search-words-data-structure", "Design Add and Search Words", "Tries", "Medium", True, "Dictionary with '.' wildcard.", "Trie + DFS branching on '.'."),
    ("word-search-ii", "Word Search II", "Tries", "Hard", True, "Find all dict words in a grid.", "Trie of words + backtracking DFS."),

    # ---------- Heap / Priority Queue ----------
    ("kth-largest-element-in-a-stream", "Kth Largest Element in a Stream", "Heap / Priority Queue", "Easy", False, "kth largest as values stream in.", "Min-heap of size k."),
    ("last-stone-weight", "Last Stone Weight", "Heap / Priority Queue", "Easy", False, "Smash the two heaviest repeatedly.", "Max-heap, pop two each round."),
    ("k-closest-points-to-origin", "K Closest Points to Origin", "Heap / Priority Queue", "Medium", False, "k points nearest the origin.", "Max-heap of size k by distance²."),
    ("kth-largest-element-in-an-array", "Kth Largest Element in an Array", "Heap / Priority Queue", "Medium", False, "kth largest value.", "Quickselect O(n) avg, or heap."),
    ("task-scheduler", "Task Scheduler", "Heap / Priority Queue", "Medium", False, "Min intervals with cooldown n.", "Max-heap of counts + cooldown queue (or math)."),
    ("design-twitter", "Design Twitter", "Heap / Priority Queue", "Medium", False, "Feed of recent tweets from followees.", "Per-user tweet lists + merge via heap."),
    ("find-median-from-data-stream", "Find Median from Data Stream", "Heap / Priority Queue", "Hard", True, "Running median of a stream.", "Two heaps: max-heap low, min-heap high."),

    # ---------- Backtracking ----------
    ("subsets", "Subsets", "Backtracking", "Medium", False, "All subsets (power set).", "Backtrack include/exclude each element."),
    ("combination-sum", "Combination Sum", "Backtracking", "Medium", True, "Combinations summing to target (reuse).", "Backtracking with a start index."),
    ("combination-sum-ii", "Combination Sum II", "Backtracking", "Medium", False, "Combinations, each number once.", "Sort + skip duplicates at each level."),
    ("permutations", "Permutations", "Backtracking", "Medium", False, "All permutations.", "Backtrack swapping / used array."),
    ("subsets-ii", "Subsets II", "Backtracking", "Medium", False, "Subsets with duplicates.", "Sort + skip duplicate branches."),
    ("word-search", "Word Search", "Backtracking", "Medium", True, "Does a word exist along adjacent cells?", "DFS backtracking with visited marks."),
    ("palindrome-partitioning", "Palindrome Partitioning", "Backtracking", "Medium", False, "All partitions into palindromes.", "Backtrack cut points; check palindrome."),
    ("letter-combinations-of-a-phone-number", "Letter Combinations of a Phone Number", "Backtracking", "Medium", False, "All letter combos for digit string.", "Backtrack over per-digit letters."),
    ("n-queens", "N-Queens", "Backtracking", "Hard", False, "Place n non-attacking queens.", "Backtrack rows; track cols & diagonals."),

    # ---------- Graphs ----------
    ("number-of-islands", "Number of Islands", "Graphs", "Medium", True, "Count connected land regions.", "Flood fill DFS/BFS."),
    ("max-area-of-island", "Max Area of Island", "Graphs", "Medium", False, "Largest island area.", "DFS returning area, track max."),
    ("clone-graph", "Clone Graph", "Graphs", "Medium", True, "Deep-copy an undirected graph.", "DFS/BFS with old→new map."),
    ("walls-and-gates", "Walls and Gates", "Graphs", "Medium", False, "Distance to nearest gate. (Premium)", "Multi-source BFS from all gates."),
    ("rotting-oranges", "Rotting Oranges", "Graphs", "Medium", False, "Minutes until all oranges rot.", "Multi-source BFS by minute."),
    ("pacific-atlantic-water-flow", "Pacific Atlantic Water Flow", "Graphs", "Medium", True, "Cells draining to both oceans.", "DFS inward from each ocean, intersect."),
    ("surrounded-regions", "Surrounded Regions", "Graphs", "Medium", False, "Capture regions not touching the border.", "Mark border-connected O's, flip rest."),
    ("course-schedule", "Course Schedule", "Graphs", "Medium", True, "Can all courses finish?", "Topological sort / cycle detection."),
    ("course-schedule-ii", "Course Schedule II", "Graphs", "Medium", False, "A valid course order.", "Kahn's topological sort order."),
    ("graph-valid-tree", "Graph Valid Tree", "Graphs", "Medium", True, "Is it a valid tree? (Premium)", "Connected AND edges == n-1 (union-find)."),
    ("number-of-connected-components-in-an-undirected-graph", "Number of Connected Components", "Graphs", "Medium", True, "Count components. (Premium)", "Union-find or DFS."),
    ("redundant-connection", "Redundant Connection", "Graphs", "Medium", False, "Edge that creates a cycle.", "Union-find; first edge that unions same set."),
    ("word-ladder", "Word Ladder", "Graphs", "Hard", False, "Shortest transform sequence length.", "BFS over one-letter-change neighbors."),

    # ---------- Advanced Graphs ----------
    ("reconstruct-itinerary", "Reconstruct Itinerary", "Advanced Graphs", "Hard", False, "Use all tickets, lexicographically first.", "Hierholzer's Eulerian path (postorder DFS)."),
    ("min-cost-to-connect-all-points", "Min Cost to Connect All Points", "Advanced Graphs", "Medium", False, "MST over Manhattan distances.", "Prim's/Kruskal's minimum spanning tree."),
    ("network-delay-time", "Network Delay Time", "Advanced Graphs", "Medium", False, "Time for signal to reach all nodes.", "Dijkstra shortest paths, take the max."),
    ("swim-in-rising-water", "Swim in Rising Water", "Advanced Graphs", "Hard", False, "Min time to cross a rising grid.", "Dijkstra/heap minimizing the path's max cell."),
    ("alien-dictionary", "Alien Dictionary", "Advanced Graphs", "Hard", True, "Infer letter order. (Premium)", "Build precedence graph, topological sort."),
    ("cheapest-flights-within-k-stops", "Cheapest Flights Within K Stops", "Advanced Graphs", "Medium", False, "Cheapest price with ≤ k stops.", "Bellman-Ford relaxed k+1 times."),

    # ---------- 1-D Dynamic Programming ----------
    ("climbing-stairs", "Climbing Stairs", "1-D DP", "Easy", True, "Ways to climb n stairs (1 or 2).", "Fibonacci DP."),
    ("min-cost-climbing-stairs", "Min Cost Climbing Stairs", "1-D DP", "Easy", False, "Min cost to reach the top.", "dp[i] = cost[i] + min(dp[i-1], dp[i-2])."),
    ("house-robber", "House Robber", "1-D DP", "Medium", True, "Max non-adjacent sum.", "rob = max(skip, prev2 + cur)."),
    ("house-robber-ii", "House Robber II", "1-D DP", "Medium", True, "House Robber on a circle.", "Linear DP twice, drop first or last."),
    ("longest-palindromic-substring", "Longest Palindromic Substring", "1-D DP", "Medium", True, "Longest palindromic substring.", "Expand around each center."),
    ("palindromic-substrings", "Palindromic Substrings", "1-D DP", "Medium", True, "Count palindromic substrings.", "Expand around center, count."),
    ("decode-ways", "Decode Ways", "1-D DP", "Medium", True, "Count decodings of a digit string.", "DP over positions, 1- and 2-digit checks."),
    ("coin-change", "Coin Change", "1-D DP", "Medium", True, "Fewest coins for an amount.", "Unbounded knapsack DP."),
    ("maximum-product-subarray", "Maximum Product Subarray", "1-D DP", "Medium", True, "Largest product subarray.", "Track running max AND min."),
    ("word-break", "Word Break", "1-D DP", "Medium", True, "Segmentable into dict words?", "dp[i] reachable from dp[j]+word."),
    ("longest-increasing-subsequence", "Longest Increasing Subsequence", "1-D DP", "Medium", True, "Length of longest increasing subseq.", "Tails array + binary search, O(n log n)."),
    ("partition-equal-subset-sum", "Partition Equal Subset Sum", "1-D DP", "Medium", False, "Split into two equal-sum subsets.", "Subset-sum DP to total/2 (bitset)."),

    # ---------- 2-D Dynamic Programming ----------
    ("unique-paths", "Unique Paths", "2-D DP", "Medium", True, "Paths across a grid.", "Grid DP or C(m+n-2, m-1)."),
    ("longest-common-subsequence", "Longest Common Subsequence", "2-D DP", "Medium", True, "LCS length of two strings.", "2D DP on prefixes."),
    ("best-time-to-buy-and-sell-stock-with-cooldown", "Best Time to Buy/Sell Stock With Cooldown", "2-D DP", "Medium", False, "Max profit with a 1-day cooldown.", "State machine DP: hold/sold/rest."),
    ("coin-change-ii", "Coin Change II", "2-D DP", "Medium", False, "Number of ways to make an amount.", "Unbounded knapsack counting DP."),
    ("target-sum", "Target Sum", "2-D DP", "Medium", False, "Ways to reach target with ±.", "Subset-sum DP on transformed target."),
    ("interleaving-string", "Interleaving String", "2-D DP", "Medium", False, "Is s3 an interleaving of s1, s2?", "2D DP over the two prefixes."),
    ("longest-increasing-path-in-a-matrix", "Longest Increasing Path in a Matrix", "2-D DP", "Hard", False, "Longest strictly increasing path.", "DFS + memoization on cells."),
    ("distinct-subsequences", "Distinct Subsequences", "2-D DP", "Hard", False, "Count subsequences of s equal to t.", "2D DP on prefixes."),
    ("edit-distance", "Edit Distance", "2-D DP", "Hard", False, "Min edits to convert s→t.", "2D DP: insert/delete/replace."),
    ("burst-balloons", "Burst Balloons", "2-D DP", "Hard", False, "Max coins bursting balloons.", "Interval DP on last-to-burst."),
    ("regular-expression-matching", "Regular Expression Matching", "2-D DP", "Hard", False, "Match with '.' and '*'.", "2D DP handling '*' zero-or-more."),

    # ---------- Greedy ----------
    ("maximum-subarray", "Maximum Subarray", "Greedy", "Medium", True, "Largest contiguous sum.", "Kadane's algorithm."),
    ("jump-game", "Jump Game", "Greedy", "Medium", True, "Can you reach the last index?", "Track furthest reachable index."),
    ("jump-game-ii", "Jump Game II", "Greedy", "Medium", False, "Min jumps to the end.", "Greedy BFS-by-levels over reach."),
    ("gas-station", "Gas Station", "Greedy", "Medium", False, "Start index to complete the circuit.", "If total ≥ 0, restart after any deficit."),
    ("hand-of-straights", "Hand of Straights", "Greedy", "Medium", False, "Split into consecutive groups of k.", "Count map; greedily start at smallest."),
    ("merge-triplets-to-form-target-triplet", "Merge Triplets to Form Target", "Greedy", "Medium", False, "Can triplets merge to the target?", "Keep triplets ≤ target; union of maxes."),
    ("partition-labels", "Partition Labels", "Greedy", "Medium", False, "Partition so each letter is in one part.", "Last-index map; extend window to max last."),
    ("valid-parenthesis-string", "Valid Parenthesis String", "Greedy", "Medium", False, "Validity with '*' wildcards.", "Track min/max possible open count."),

    # ---------- Intervals ----------
    ("insert-interval", "Insert Interval", "Intervals", "Medium", True, "Insert & merge into sorted intervals.", "Scan: before, merge, after."),
    ("merge-intervals", "Merge Intervals", "Intervals", "Medium", True, "Merge overlapping intervals.", "Sort by start, extend end."),
    ("non-overlapping-intervals", "Non-overlapping Intervals", "Intervals", "Medium", True, "Min removals so none overlap.", "Greedy by earliest end time."),
    ("meeting-rooms", "Meeting Rooms", "Intervals", "Easy", True, "Attend all meetings? (Premium)", "Sort by start, check overlaps."),
    ("meeting-rooms-ii", "Meeting Rooms II", "Intervals", "Medium", True, "Min rooms needed. (Premium)", "Min-heap of end times / sweep line."),
    ("minimum-interval-to-include-each-query", "Minimum Interval to Include Each Query", "Intervals", "Hard", False, "Smallest interval covering each query.", "Sort queries + intervals; min-heap by size."),

    # ---------- Math & Geometry ----------
    ("rotate-image", "Rotate Image", "Math & Geometry", "Medium", True, "Rotate n×n matrix 90° in place.", "Transpose then reverse rows."),
    ("spiral-matrix", "Spiral Matrix", "Math & Geometry", "Medium", True, "Elements in spiral order.", "Shrink four boundaries."),
    ("set-matrix-zeroes", "Set Matrix Zeroes", "Math & Geometry", "Medium", True, "Zero rows/cols in place.", "First row/col as markers."),
    ("happy-number", "Happy Number", "Math & Geometry", "Easy", False, "Does digit-square sum reach 1?", "Cycle detection (set or fast/slow)."),
    ("plus-one", "Plus One", "Math & Geometry", "Easy", False, "Increment a digit array.", "Handle carry right-to-left."),
    ("powx-n", "Pow(x, n)", "Math & Geometry", "Medium", False, "Compute x^n.", "Fast exponentiation by squaring."),
    ("multiply-strings", "Multiply Strings", "Math & Geometry", "Medium", False, "Multiply big numbers as strings.", "Grade-school multiply into a digit array."),
    ("detect-squares", "Detect Squares", "Math & Geometry", "Medium", False, "Count axis-aligned squares.", "Count points; pick diagonal pairs."),

    # ---------- Bit Manipulation ----------
    ("single-number", "Single Number", "Bit Manipulation", "Easy", False, "The one non-duplicated number.", "XOR all values."),
    ("number-of-1-bits", "Number of 1 Bits", "Bit Manipulation", "Easy", True, "Count set bits.", "n &= n-1 clears lowest set bit."),
    ("counting-bits", "Counting Bits", "Bit Manipulation", "Easy", True, "Set-bit count for 0..n.", "dp[i] = dp[i>>1] + (i&1)."),
    ("reverse-bits", "Reverse Bits", "Bit Manipulation", "Easy", True, "Reverse a 32-bit int.", "Shift out/in bit by bit."),
    ("missing-number", "Missing Number", "Bit Manipulation", "Easy", True, "Missing number in 0..n.", "XOR indices+values, or sum formula."),
    ("sum-of-two-integers", "Sum of Two Integers", "Bit Manipulation", "Medium", True, "Add without + or -.", "XOR sum, AND<<1 carry, loop."),
    ("reverse-integer", "Reverse Integer", "Bit Manipulation", "Medium", False, "Reverse digits with overflow check.", "Pop/push digits, guard 32-bit bounds."),
]

CATEGORY_ORDER = [
    "Arrays & Hashing", "Two Pointers", "Sliding Window", "Stack", "Binary Search",
    "Linked List", "Trees", "Tries", "Heap / Priority Queue", "Backtracking",
    "Graphs", "Advanced Graphs", "1-D DP", "2-D DP", "Greedy", "Intervals",
    "Math & Geometry", "Bit Manipulation",
]


def problems() -> list[dict]:
    out = []
    for i, (slug, title, cat, diff, in_b75, blurb, pattern) in enumerate(_NC):
        collections = "neetcode150" + (",blind75" if in_b75 else "")
        out.append({
            "slug": slug, "title": title, "category": cat, "difficulty": diff,
            "blurb": blurb, "pattern": pattern, "order_idx": i,
            "in_blind75": in_b75, "collections": collections,
            "url": f"https://leetcode.com/problems/{slug}/",
        })
    return out
