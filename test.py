import random
from collections import deque

class BPlusNode:
    __slots__ = ('keys', 'children', 'is_leaf', 'next', 'parent')
    def __init__(self, is_leaf=True):
        self.keys = []
        self.children = []
        self.is_leaf = is_leaf
        self.next = None
        self.parent = None

class BPlusTree:
    def __init__(self, order=4):
        self.order = order
        self.min_keys = (order - 1) // 2
        self.root = BPlusNode()
        self.size = 0

    def insert(self, key, value=None):
        if value is None: value = key
        leaf = self._find_leaf(key)
        idx = self._find_index(leaf.keys, key)
        if idx < len(leaf.keys) and leaf.keys[idx] == key:
            leaf.children[idx] = value
            return
        leaf.keys.insert(idx, key)
        leaf.children.insert(idx, value)
        self.size += 1
        if len(leaf.keys) >= self.order:
            self._split_leaf(leaf)

    def _find_leaf(self, key):
        node = self.root
        while not node.is_leaf:
            idx = self._find_index(node.keys, key)
            node = node.children[idx]
        return node

    def _find_index(self, keys, key):
        lo, hi = 0, len(keys)
        while lo < hi:
            mid = (lo + hi) // 2
            if keys[mid] < key: lo = mid + 1
            else: hi = mid
        return lo

    def _split_leaf(self, leaf):
        mid = (len(leaf.keys) + 1) // 2
        new_leaf = BPlusNode(is_leaf=True)
        new_leaf.keys = leaf.keys[mid:]
        new_leaf.children = leaf.children[mid:]
        leaf.keys = leaf.keys[:mid]
        leaf.children = leaf.children[:mid]
        new_leaf.next = leaf.next
        leaf.next = new_leaf
        self._insert_in_parent(leaf, new_leaf.keys[0], new_leaf)

    def _split_internal(self, node):
        mid = len(node.keys) // 2
        promote_key = node.keys[mid]
        new_node = BPlusNode(is_leaf=False)
        new_node.keys = node.keys[mid+1:]
        new_node.children = node.children[mid+1:]
        node.keys = node.keys[:mid]
        node.children = node.children[:mid+1]
        for child in new_node.children:
            child.parent = new_node
        self._insert_in_parent(node, promote_key, new_node)

    def _insert_in_parent(self, left, key, right):
        parent = left.parent
        if parent is None:
            new_root = BPlusNode(is_leaf=False)
            new_root.keys = [key]
            new_root.children = [left, right]
            left.parent = new_root
            right.parent = new_root
            self.root = new_root
            return
        idx = parent.children.index(left) + 1
        parent.keys.insert(idx - 1, key)
        parent.children.insert(idx, right)
        right.parent = parent
        if len(parent.keys) >= self.order:
            self._split_internal(parent)

    def search(self, key):
        leaf = self._find_leaf(key)
        idx = self._find_index(leaf.keys, key)
        if idx < len(leaf.keys) and leaf.keys[idx] == key:
            return leaf.children[idx]
        return None

    def range_search(self, start, end):
        result = []
        leaf = self._find_leaf(start)
        while leaf:
            for i, k in enumerate(leaf.keys):
                if k > end: return result
                if start <= k <= end:
                    result.append((k, leaf.children[i]))
            leaf = leaf.next
        return result

    def delete(self, key):
        leaf = self._find_leaf(key)
        idx = self._find_index(leaf.keys, key)
        if idx >= len(leaf.keys) or leaf.keys[idx] != key:
            return False
        leaf.keys.pop(idx)
        leaf.children.pop(idx)
        self.size -= 1
        if leaf is self.root and leaf.is_leaf:
            return True
        if len(leaf.keys) < self.min_keys and leaf.parent:
            self._merge_or_redistribute_leaf(leaf)
        return True

    def _merge_or_redistribute_leaf(self, leaf):
        parent = leaf.parent
        idx = parent.children.index(leaf)
        if idx > 0:
            left = parent.children[idx - 1]
            if len(left.keys) > self.min_keys:
                leaf.keys.insert(0, left.keys.pop())
                leaf.children.insert(0, left.children.pop())
                parent.keys[idx - 1] = leaf.keys[0]
                return
        if idx < len(parent.children) - 1:
            right = parent.children[idx + 1]
            if len(right.keys) > self.min_keys:
                leaf.keys.append(right.keys.pop(0))
                leaf.children.append(right.children.pop(0))
                parent.keys[idx] = right.keys[0]
                return
        if idx > 0:
            left = parent.children[idx - 1]
            left.keys.extend(leaf.keys)
            left.children.extend(leaf.children)
            left.next = leaf.next
            parent.keys.pop(idx - 1)
            parent.children.pop(idx)
        else:
            right = parent.children[idx + 1]
            leaf.keys.extend(right.keys)
            leaf.children.extend(right.children)
            leaf.next = right.next
            parent.keys.pop(idx)
            parent.children.pop(idx + 1)
        if len(parent.keys) < self.min_keys and parent.parent:
            self._merge_or_redistribute_internal(parent)
        elif len(parent.keys) == 0 and parent is self.root:
            self.root = parent.children[0]
            self.root.parent = None

    def _merge_or_redistribute_internal(self, node):
        parent = node.parent
        if parent is None: return
        idx = parent.children.index(node)
        if idx > 0:
            left = parent.children[idx - 1]
            if len(left.keys) > self.min_keys:
                node.keys.insert(0, parent.keys[idx - 1])
                node.children.insert(0, left.children.pop())
                parent.keys[idx - 1] = left.keys.pop()
                return
        if idx < len(parent.children) - 1:
            right = parent.children[idx + 1]
            if len(right.keys) > self.min_keys:
                node.keys.append(parent.keys[idx])
                node.children.append(right.children.pop(0))
                parent.keys[idx] = right.keys.pop(0)
                return
        if idx > 0:
            left = parent.children[idx - 1]
            left.keys.append(parent.keys.pop(idx - 1))
            left.keys.extend(node.keys)
            left.children.extend(node.children)
            parent.children.pop(idx)
        else:
            right = parent.children[idx + 1]
            node.keys.append(parent.keys.pop(idx))
            node.keys.extend(right.keys)
            node.children.extend(right.children)
            parent.children.pop(idx + 1)
        if len(parent.keys) < self.min_keys and parent.parent:
            self._merge_or_redistribute_internal(parent)
        elif len(parent.keys) == 0 and parent is self.root:
            self.root = parent.children[0]
            self.root.parent = None

    def traverse(self):
        result = []
        def _inorder(node):
            if node.is_leaf:
                result.extend(node.keys)
                return
            for i, child in enumerate(node.children):
                _inorder(child)
                if i < len(node.keys):
                    result.append(node.keys[i])
        _inorder(self.root)
        return result

    def get_height(self):
        height = 0
        node = self.root
        while node:
            height += 1
            if node.is_leaf: break
            node = node.children[0]
        return height

    def validate(self):
        errors = []
        def _check(node, depth=0, min_key=None, max_key=None):
            if not node.is_leaf:
                if node is not self.root and len(node.keys) < self.min_keys:
                    errors.append(f"Internal node underflow at depth {depth}")
                if len(node.children) != len(node.keys) + 1:
                    errors.append(f"Children count mismatch at depth {depth}")
                for i, child in enumerate(node.children):
                    child_min = node.keys[i-1] if i > 0 else min_key
                    child_max = node.keys[i] if i < len(node.keys) else max_key
                    _check(child, depth+1, child_min, child_max)
            else:
                if node is not self.root and len(node.keys) < self.min_keys and self.size > 0:
                    errors.append(f"Leaf underflow")
                for i in range(1, len(node.keys)):
                    if node.keys[i-1] > node.keys[i]:
                        errors.append(f"Leaf keys not sorted")
                if min_key is not None and node.keys and node.keys[0] < min_key:
                    errors.append(f"Key below min")
                if max_key is not None and node.keys and node.keys[-1] >= max_key:
                    errors.append(f"Key above max")
        _check(self.root)
        depths = set()
        def _leaf_depth(node, d=0):
            if node.is_leaf: depths.add(d); return
            for c in node.children: _leaf_depth(c, d+1)
        _leaf_depth(self.root)
        if len(depths) > 1:
            errors.append(f"Leaves at different depths: {depths}")
        return len(errors) == 0, errors

    def visualize(self):
        lines = []
        def _draw(node, prefix="", is_last=True):
            connector = "└── " if is_last else "├── "
            if node.is_leaf:
                lines.append(f"{prefix}{connector}Leaf: {node.keys}")
            else:
                lines.append(f"{prefix}{connector}Internal: {node.keys}")
                for i, child in enumerate(node.children):
                    _draw(child, prefix + ("    " if is_last else "│   "), i == len(node.children) - 1)
        _draw(self.root, "", True)
        return '\n'.join(lines)
