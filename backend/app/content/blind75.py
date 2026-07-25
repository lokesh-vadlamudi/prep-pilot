"""Blind 75 — the canonical curated coding-interview problem list.

We store only factual, public metadata (title, category, difficulty, official
LeetCode URL) plus a SHORT pattern hint written in our own words. The full worked
approach is generated on demand by the DGX model and cached — we never reproduce
LeetCode's problem statements.

Tuple shape: (slug, title, category, difficulty, blurb, pattern)
"""
from __future__ import annotations

_B75: list[tuple[str, str, str, str, str, str]] = [
    # ---------- Array ----------
    ("two-sum", "Two Sum", "Array", "Easy", "Return indices of two numbers that add to a target.", "Hash map: store complements for O(n) lookup."),
    ("best-time-to-buy-and-sell-stock", "Best Time to Buy and Sell Stock", "Array", "Easy", "Max profit from one buy/sell over a price series.", "One pass tracking min price seen so far."),
    ("contains-duplicate", "Contains Duplicate", "Array", "Easy", "Detect if any value repeats.", "Hash set membership."),
    ("product-of-array-except-self", "Product of Array Except Self", "Array", "Medium", "Product of all elements except self, no division.", "Prefix products then suffix products."),
    ("maximum-subarray", "Maximum Subarray", "Array", "Medium", "Largest sum of a contiguous subarray.", "Kadane's algorithm."),
    ("maximum-product-subarray", "Maximum Product Subarray", "Array", "Medium", "Largest product of a contiguous subarray.", "Track running max AND min (negatives flip)."),
    ("find-minimum-in-rotated-sorted-array", "Find Minimum in Rotated Sorted Array", "Array", "Medium", "Find the min in a rotated sorted array.", "Binary search on the rotation point."),
    ("search-in-rotated-sorted-array", "Search in Rotated Sorted Array", "Array", "Medium", "Search a target in a rotated sorted array.", "Modified binary search: one half is always sorted."),
    ("3sum", "3Sum", "Array", "Medium", "All unique triplets summing to zero.", "Sort, then two pointers per anchor."),
    ("container-with-most-water", "Container With Most Water", "Array", "Medium", "Max water between two lines.", "Two pointers from the ends, move the shorter."),

    # ---------- Binary ----------
    ("sum-of-two-integers", "Sum of Two Integers", "Binary", "Medium", "Add two ints without + or -.", "XOR for sum, AND<<1 for carry, loop."),
    ("number-of-1-bits", "Number of 1 Bits", "Binary", "Easy", "Count set bits (Hamming weight).", "n &= n-1 clears lowest set bit each step."),
    ("counting-bits", "Counting Bits", "Binary", "Easy", "Count set bits for 0..n.", "DP: bits[i] = bits[i>>1] + (i&1)."),
    ("missing-number", "Missing Number", "Binary", "Easy", "Find the missing number in 0..n.", "XOR all indices+values, or sum formula."),
    ("reverse-bits", "Reverse Bits", "Binary", "Easy", "Reverse the bits of a 32-bit int.", "Shift out/in bit by bit."),

    # ---------- Dynamic Programming ----------
    ("climbing-stairs", "Climbing Stairs", "Dynamic Programming", "Easy", "Ways to climb n stairs taking 1 or 2 steps.", "Fibonacci DP."),
    ("coin-change", "Coin Change", "Dynamic Programming", "Medium", "Fewest coins to make an amount.", "Unbounded knapsack DP over amounts."),
    ("longest-increasing-subsequence", "Longest Increasing Subsequence", "Dynamic Programming", "Medium", "Length of the longest increasing subsequence.", "O(n log n) with patience/tails + binary search."),
    ("longest-common-subsequence", "Longest Common Subsequence", "Dynamic Programming", "Medium", "LCS length of two strings.", "2D DP grid on prefixes."),
    ("word-break", "Word Break", "Dynamic Programming", "Medium", "Can a string be segmented into dict words?", "DP over prefixes: dp[i] reachable from dp[j]+word."),
    ("combination-sum", "Combination Sum", "Dynamic Programming", "Medium", "All combinations summing to a target (reuse allowed).", "Backtracking with a start index."),
    ("house-robber", "House Robber", "Dynamic Programming", "Medium", "Max non-adjacent sum.", "DP: rob = max(skip, prev2 + cur)."),
    ("house-robber-ii", "House Robber II", "Dynamic Programming", "Medium", "House Robber on a circular street.", "Run linear DP twice, excluding first or last."),
    ("decode-ways", "Decode Ways", "Dynamic Programming", "Medium", "Count decodings of a digit string (1=A..26=Z).", "DP over positions, check 1- and 2-digit validity."),
    ("unique-paths", "Unique Paths", "Dynamic Programming", "Medium", "Paths from top-left to bottom-right of a grid.", "Grid DP or combinatorics C(m+n-2, m-1)."),
    ("jump-game", "Jump Game", "Dynamic Programming", "Medium", "Can you reach the last index?", "Greedy: track furthest reachable index."),

    # ---------- Graph ----------
    ("clone-graph", "Clone Graph", "Graph", "Medium", "Deep-copy an undirected graph.", "DFS/BFS with an old→new node map."),
    ("course-schedule", "Course Schedule", "Graph", "Medium", "Can all courses be finished given prereqs?", "Topological sort / cycle detection (Kahn's)."),
    ("pacific-atlantic-water-flow", "Pacific Atlantic Water Flow", "Graph", "Medium", "Cells that can drain to both oceans.", "DFS inward from each ocean's borders, intersect."),
    ("number-of-islands", "Number of Islands", "Graph", "Medium", "Count connected land regions in a grid.", "Flood fill DFS/BFS, mark visited."),
    ("longest-consecutive-sequence", "Longest Consecutive Sequence", "Graph", "Medium", "Longest run of consecutive integers.", "Hash set; start counting only at sequence heads."),
    ("alien-dictionary", "Alien Dictionary", "Graph", "Hard", "Infer letter order from sorted words. (LeetCode Premium)", "Build precedence graph, topological sort."),
    ("graph-valid-tree", "Graph Valid Tree", "Graph", "Medium", "Is the graph a valid tree? (LeetCode Premium)", "Connected AND edges == n-1 (union-find)."),
    ("number-of-connected-components-in-an-undirected-graph", "Number of Connected Components", "Graph", "Medium", "Count connected components. (LeetCode Premium)", "Union-find or DFS component count."),

    # ---------- Interval ----------
    ("insert-interval", "Insert Interval", "Interval", "Medium", "Insert & merge into sorted non-overlapping intervals.", "Scan: before, merge overlaps, after."),
    ("merge-intervals", "Merge Intervals", "Interval", "Medium", "Merge all overlapping intervals.", "Sort by start, extend current end."),
    ("non-overlapping-intervals", "Non-overlapping Intervals", "Interval", "Medium", "Min removals so none overlap.", "Greedy: sort by end, keep earliest finishers."),
    ("meeting-rooms", "Meeting Rooms", "Interval", "Easy", "Can one person attend all meetings? (Premium)", "Sort by start, check adjacent overlap."),
    ("meeting-rooms-ii", "Meeting Rooms II", "Interval", "Medium", "Min rooms for all meetings. (Premium)", "Min-heap of end times, or start/end sweep."),

    # ---------- Linked List ----------
    ("reverse-linked-list", "Reverse Linked List", "Linked List", "Easy", "Reverse a singly linked list.", "Iterative prev/cur/next pointer flip."),
    ("linked-list-cycle", "Linked List Cycle", "Linked List", "Easy", "Detect a cycle.", "Floyd's tortoise & hare."),
    ("merge-two-sorted-lists", "Merge Two Sorted Lists", "Linked List", "Easy", "Merge two sorted lists.", "Dummy head + two-pointer splice."),
    ("merge-k-sorted-lists", "Merge k Sorted Lists", "Linked List", "Hard", "Merge k sorted lists.", "Min-heap of heads, or divide & conquer."),
    ("remove-nth-node-from-end-of-list", "Remove Nth Node From End of List", "Linked List", "Medium", "Remove the nth node from the end.", "Two pointers spaced n apart."),
    ("reorder-list", "Reorder List", "Linked List", "Medium", "Reorder L0→Ln→L1→Ln-1…", "Find mid, reverse second half, merge."),

    # ---------- Matrix ----------
    ("set-matrix-zeroes", "Set Matrix Zeroes", "Matrix", "Medium", "Zero out rows/cols containing a zero, in place.", "Use first row/col as zero markers."),
    ("spiral-matrix", "Spiral Matrix", "Matrix", "Medium", "Return elements in spiral order.", "Shrink top/bottom/left/right boundaries."),
    ("rotate-image", "Rotate Image", "Matrix", "Medium", "Rotate an n×n matrix 90° in place.", "Transpose then reverse each row."),
    ("word-search", "Word Search", "Matrix", "Medium", "Does a word exist along adjacent cells?", "Backtracking DFS with visited marking."),

    # ---------- String ----------
    ("longest-substring-without-repeating-characters", "Longest Substring Without Repeating Characters", "String", "Medium", "Longest substring with all unique chars.", "Sliding window + last-seen index map."),
    ("longest-repeating-character-replacement", "Longest Repeating Character Replacement", "String", "Medium", "Longest same-char run allowing k replacements.", "Sliding window: window - maxCount ≤ k."),
    ("minimum-window-substring", "Minimum Window Substring", "String", "Hard", "Smallest window containing all target chars.", "Sliding window with need/have counts."),
    ("valid-anagram", "Valid Anagram", "String", "Easy", "Are two strings anagrams?", "Compare character counts."),
    ("group-anagrams", "Group Anagrams", "String", "Medium", "Group words that are anagrams.", "Key by sorted string or char-count tuple."),
    ("valid-parentheses", "Valid Parentheses", "String", "Easy", "Are brackets balanced & correctly nested?", "Stack of expected closers."),
    ("valid-palindrome", "Valid Palindrome", "String", "Easy", "Is it a palindrome (alphanumerics only)?", "Two pointers inward, skip non-alnum."),
    ("longest-palindromic-substring", "Longest Palindromic Substring", "String", "Medium", "Longest palindromic substring.", "Expand around each center (2n-1 centers)."),
    ("palindromic-substrings", "Palindromic Substrings", "String", "Medium", "Count palindromic substrings.", "Expand around center, count each."),
    ("encode-and-decode-strings", "Encode and Decode Strings", "String", "Medium", "Serialize/deserialize a list of strings. (Premium)", "Length-prefix each: '<len>#<str>'."),

    # ---------- Tree ----------
    ("maximum-depth-of-binary-tree", "Maximum Depth of Binary Tree", "Tree", "Easy", "Height of a binary tree.", "DFS: 1 + max(left, right)."),
    ("same-tree", "Same Tree", "Tree", "Easy", "Are two trees identical?", "Parallel DFS comparing nodes."),
    ("invert-binary-tree", "Invert Binary Tree", "Tree", "Easy", "Mirror a binary tree.", "Swap children recursively."),
    ("binary-tree-maximum-path-sum", "Binary Tree Maximum Path Sum", "Tree", "Hard", "Max path sum between any two nodes.", "DFS returns best downward branch; track global."),
    ("binary-tree-level-order-traversal", "Binary Tree Level Order Traversal", "Tree", "Medium", "Return nodes level by level.", "BFS with a queue, one level per iteration."),
    ("serialize-and-deserialize-binary-tree", "Serialize and Deserialize Binary Tree", "Tree", "Hard", "Encode a tree to a string and back.", "Preorder DFS with null markers."),
    ("subtree-of-another-tree", "Subtree of Another Tree", "Tree", "Easy", "Is t a subtree of s?", "DFS each node + same-tree check."),
    ("construct-binary-tree-from-preorder-and-inorder-traversal", "Construct Tree from Preorder & Inorder", "Tree", "Medium", "Rebuild a tree from its traversals.", "Preorder gives roots; inorder index map splits."),
    ("validate-binary-search-tree", "Validate Binary Search Tree", "Tree", "Medium", "Is it a valid BST?", "DFS carrying (min, max) bounds."),
    ("kth-smallest-element-in-a-bst", "Kth Smallest Element in a BST", "Tree", "Medium", "Find the kth smallest value.", "In-order traversal stops at k."),
    ("lowest-common-ancestor-of-a-binary-search-tree", "Lowest Common Ancestor of a BST", "Tree", "Easy", "LCA of two BST nodes.", "Walk down using BST ordering."),
    ("implement-trie-prefix-tree", "Implement Trie (Prefix Tree)", "Tree", "Medium", "Build a trie with insert/search/startsWith.", "Nodes with children map + isEnd flag."),
    ("design-add-and-search-words-data-structure", "Design Add and Search Words", "Tree", "Medium", "Word dictionary supporting '.' wildcard.", "Trie + DFS branching on '.'."),
    ("word-search-ii", "Word Search II", "Tree", "Hard", "Find all dictionary words in a grid.", "Build a trie of words, backtracking DFS."),

    # ---------- Heap ----------
    ("top-k-frequent-elements", "Top K Frequent Elements", "Heap", "Medium", "The k most frequent values.", "Count + bucket sort by frequency (or heap)."),
    ("find-median-from-data-stream", "Find Median from Data Stream", "Heap", "Hard", "Running median of a stream.", "Two heaps: max-heap low half, min-heap high half."),
]

CATEGORY_ORDER = [
    "Array", "Binary", "Dynamic Programming", "Graph", "Interval",
    "Linked List", "Matrix", "String", "Tree", "Heap",
]


def problems() -> list[dict]:
    out = []
    for i, (slug, title, cat, diff, blurb, pattern) in enumerate(_B75):
        out.append({
            "slug": slug, "title": title, "category": cat, "difficulty": diff,
            "blurb": blurb, "pattern": pattern, "order_idx": i,
            "url": f"https://leetcode.com/problems/{slug}/",
        })
    return out
