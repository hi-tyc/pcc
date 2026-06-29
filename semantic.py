"""Semantic analyzer: symbol resolution + whole-program type inference.

Python is dynamically typed, but compiling to native LLVM code requires
static types. We perform monomorphic whole-program inference:

  * Each expression is annotated with a concrete `.type` in
    {int, float, str, bool, none}.
  * Function parameter and return types are inferred from call sites and
    function bodies via a fixpoint iteration that handles forward
    references and recursion.
  * The top-level program is treated as the body of an implicit `main`.

Inference is monomorphic: a function must be called with consistent
argument types throughout the program.
"""

import ast_nodes as A


class SemanticError(Exception):
    def __init__(self, msg, line=0):
        super().__init__(f"SemanticError at line {line}: {msg}")
        self.line = line


# Type constants
INT, FLOAT, STR, BOOL, NONE, VOID = "int", "float", "str", "bool", "none", "void"
SET = "set"
PYOBJECT = "pyobject"  # Hybrid A+B mode: handled by libpython fallback

EXCEPTION_TYPES = {
    "Exception", "ValueError", "TypeError", "KeyError",
    "IndexError", "ZeroDivisionError", "StopIteration",
    "FileNotFoundError", "RuntimeError", "NotImplementedError",
    "ArithmeticError", "OverflowError", "FloatingPointError",
    "AttributeError", "NameError", "UnboundLocalError",
    "ImportError", "ModuleNotFoundError", "OSError",
    "IOError", "PermissionError", "TimeoutError",
    "RecursionError", "AssertionError", "KeyboardInterrupt",
    "SystemExit", "GeneratorExit", "StopAsyncIteration",
    "Warning", "UserWarning", "DeprecationWarning",
    "PendingDeprecationWarning", "SyntaxWarning",
    "RuntimeWarning", "FutureWarning", "ImportWarning",
    "UnicodeWarning", "BytesWarning", "ResourceWarning",
    "LookupError", "EnvironmentError", "EOFError",
    "MemoryError", "ReferenceError",
}

BUILTINS = {
    "print": None,        # returns none
    "len": INT,
    "abs": None,          # returns type of arg
    "int": INT,
    "float": FLOAT,
    "str": STR,
    "bool": BOOL,
    "input": STR,
    "range": "range",     # only valid as for-iterable
    "min": None,
    "max": None,
    "enumerate": "enumerate",  # special: handled in _for_var_type
    "sum": None,
    "sorted": None,
    "map": None,
    "filter": None,
    "isinstance": BOOL,
    "set": None,
    "dict": None,
    "tuple": None,
    "list": None,         # convert iterable to list
    "deque": None,        # from collections; returns ("obj", "deque")
    "Counter": None,      # from collections; returns ("obj", "Counter")
    "hex": STR,
    "oct": STR,
    "bin": STR,
    "chr": STR,
    "ord": INT,
    "round": None,      # returns int or float depending on args
    "divmod": None,     # returns tuple
    "iter": None,       # iterator
    "next": None,       # next value
    "repr": STR,
    "ascii": STR,
    "format": STR,
    "reversed": None,
    "any": BOOL,
    "all": BOOL,
    "zip": None,
    "hasattr": BOOL,
    "getattr": None,
    "setattr": NONE,
    "callable": BOOL,
    "type": STR,        # simplified: returns type name string
    "id": INT,
    "hash": INT,
    "open": ("obj", "File"),
    "math": None,       # module reference
    "string": None,     # module reference
    "__lambda__": STR,    # desugared lambda; opaque to analysis
}


def numeric_base(t):
    """Map bool->int so arithmetic can treat booleans as integers."""
    if t == BOOL:
        return INT
    if t in (INT, FLOAT):
        return t
    return None


def _collect_locals(body):
    """Pre-scan a function body for names that are assigned (and thus local).
    Also collects `global` declarations so they can be excluded from locals.
    Returns (local_names, global_decls).
    """
    local_names = set()
    global_decls = set()

    def add_for_var(var_target):
        """Flatten a for-loop target (str or nested list) into local names."""
        if isinstance(var_target, str):
            local_names.add(var_target)
        elif isinstance(var_target, list):
            for v in var_target:
                add_for_var(v)

    def add_assign_target(target):
        if isinstance(target, A.Name):
            local_names.add(target.name)
        elif isinstance(target, A.TupleLit):
            for el in target.elements:
                add_assign_target(el)
        # Subscript / Attribute targets don't create new locals.

    def visit_stmt(s):
        if isinstance(s, A.Assign):
            add_assign_target(s.target)
        elif isinstance(s, A.AugAssign):
            if isinstance(s.target, A.Name):
                local_names.add(s.target.name)
        elif isinstance(s, A.For):
            # s.var is now a list of targets (strings or nested lists).
            add_for_var(s.var)
            for x in s.body:
                visit_stmt(x)
            for x in s.orelse:
                visit_stmt(x)
        elif isinstance(s, A.If):
            for _, body in s.branches:
                for x in body:
                    visit_stmt(x)
            for x in s.orelse:
                visit_stmt(x)
        elif isinstance(s, A.While):
            for x in s.body:
                visit_stmt(x)
            for x in s.orelse:
                visit_stmt(x)
        elif isinstance(s, A.Global):
            for n in s.names:
                global_decls.add(n)
        elif isinstance(s, A.With):
            for ctx, var in s.items:
                if var is not None:
                    local_names.add(var)
            for x in s.body:
                visit_stmt(x)
        elif isinstance(s, A.Try):
            for x in s.body:
                visit_stmt(x)
            for _, name, hb in s.handlers:
                if name is not None:
                    local_names.add(name)
                for x in hb:
                    visit_stmt(x)
        # FuncDef nesting is hoisted to top-level; skip here.

    for s in body:
        visit_stmt(s)
    return local_names - global_decls, global_decls


class FuncInfo:
    def __init__(self, defn):
        self.defn = defn
        self.name = defn.name
        self.params = defn.params
        self.param_types = [None] * len(defn.params)
        self.return_type = None
        self.analyzed = False
        self.local_types = {}  # var name -> type (filled during final pass)
        self.local_names = set()
        self.global_decls = set()
        self.enclosing_func = None  # name of enclosing function (for hoisted nested funcs)
        self.defaults = getattr(defn, "defaults", {}) or {}


class Analyzer:
    def __init__(self, program, embed_mode=False):
        self.program = program
        self.embed_mode = embed_mode
        self.funcs = {}
        self.top_stmts = []
        self.changed = False
        self.global_types = {}
        self.cur_fn = None  # FuncInfo currently being analyzed, or None for top-level
        self.classes = {}   # class_name -> {"methods": {short: mangled}, "attrs": {name: type}}
        self.dict_key_types = {}  # var_name -> {key_str: type} for per-key dict value tracking

    def analyze(self):
        # Separate function definitions, class definitions, imports, and top-level code.
        for s in self.program:
            if isinstance(s, A.FuncDef):
                if s.name in self.funcs or s.name in BUILTINS:
                    raise SemanticError(f"duplicate function '{s.name}'", s.line)
                self.funcs[s.name] = FuncInfo(s)
            elif isinstance(s, A.ClassDef):
                self._collect_class(s)
            elif isinstance(s, (A.Import, A.ImportFrom)):
                # Register imports as no-op statements that just record names.
                self.top_stmts.append(s)
            else:
                self.top_stmts.append(s)

        # Pre-scan each function for the set of names that are local to it
        # (assigned anywhere in its body). Per Python rules, any name assigned
        # in a function is local; other names resolve to module globals.
        for fn in self.funcs.values():
            locals_, globals_ = _collect_locals(fn.defn.body)
            fn.local_names = set(fn.params) | locals_
            fn.global_decls = globals_

        # Fill in unresolved param types from default values, then fall back to
        # NONE (unknown) for params that are never called with concrete types
        # (e.g. methods in a class that is defined but never instantiated/called).
        # Done before the fixpoint so return types of such functions propagate.
        self._apply_defaults()

        # Scan method bodies for `self.attr = value` to infer attribute types.
        # Run inside the fixpoint so attribute types propagate across iterations.
        # Fixpoint inference.
        for _ in range(100):
            self.changed = False
            self.global_types = {}
            self._collect_class_attrs()
            for s in self.top_stmts:
                self._stmt(s, self.global_types, is_global_scope=True)
            for fn in self.funcs.values():
                self._analyze_func(fn)
            if not self.changed:
                break

        # Final pass: ensure everything resolved; recompute types with strict checks.
        self.global_types = {}
        self._collect_class_attrs()
        for s in self.top_stmts:
            self._stmt(s, self.global_types, is_global_scope=True, strict=True)
        for fn in self.funcs.values():
            self._analyze_func(fn, strict=True)

        # Any function still with unresolved return type returns None.
        for fn in self.funcs.values():
            if fn.return_type is None:
                # Function with no return -> returns None
                fn.return_type = NONE

        return {
            "funcs": self.funcs,
            "top_stmts": self.top_stmts,
            "globals": self.global_types,
            "classes": self.classes,
        }

    # ---------- class collection ----------
    def _collect_class(self, cls_def):
        """Register a class and its methods (with mangled names) in self.funcs."""
        name = cls_def.name
        if name in self.classes:
            return  # already collected (fixpoint may re-run)
        self.classes[name] = {"methods": {}, "attrs": {}}
        for method in cls_def.methods:
            mangled = name + "__" + method.name
            if mangled in self.funcs:
                continue
            fn = FuncInfo(method)
            fn.name = mangled
            fn.enclosing_func = None
            # First param is "self" with type ("obj", ClassName)
            if fn.params and fn.params[0] == "self":
                fn.param_types[0] = ("obj", name)
            self.funcs[mangled] = fn
            self.classes[name]["methods"][method.name] = mangled
            # Hoist nested function definitions inside this method.
            self._hoist_nested_funcs(method.body, mangled)

    def _hoist_nested_funcs(self, body, prefix):
        """Find FuncDef nodes in a statement list and register them with mangled names.
        Recurses into nested control flow."""
        for s in body:
            self._scan_for_nested(s, prefix)

    def _scan_for_nested(self, s, prefix):
        if isinstance(s, A.FuncDef):
            mangled = prefix + "__" + s.name
            if mangled not in self.funcs:
                fn = FuncInfo(s)
                fn.name = mangled
                fn.enclosing_func = prefix
                self.funcs[mangled] = fn
                self._hoist_nested_funcs(s.body, mangled)
            return
        if isinstance(s, A.If):
            for _, body in s.branches:
                self._hoist_nested_funcs(body, prefix)
            self._hoist_nested_funcs(s.orelse, prefix)
        elif isinstance(s, A.While):
            self._hoist_nested_funcs(s.body, prefix)
            self._hoist_nested_funcs(s.orelse, prefix)
        elif isinstance(s, A.For):
            self._hoist_nested_funcs(s.body, prefix)
            self._hoist_nested_funcs(s.orelse, prefix)
        elif isinstance(s, A.With):
            self._hoist_nested_funcs(s.body, prefix)
        elif isinstance(s, A.Try):
            self._hoist_nested_funcs(s.body, prefix)
            for _, _, hb in s.handlers:
                self._hoist_nested_funcs(hb, prefix)

    def _collect_class_attrs(self):
        """Scan all method bodies for `self.attr = value` to infer attribute types."""
        for cls_name, cls_info in self.classes.items():
            for short, mangled in cls_info["methods"].items():
                fn = self.funcs.get(mangled)
                if fn is None:
                    continue
                self._scan_self_attrs(fn.defn.body, cls_name, cls_info)

    def _scan_self_attrs(self, body, cls_name, cls_info):
        for s in body:
            if isinstance(s, A.Assign):
                if isinstance(s.target, A.Attribute) and isinstance(s.target.obj, A.Name) \
                        and s.target.obj.name == "self":
                    # Use a temporary scope with self typed as the class to evaluate value.
                    scope = {"self": ("obj", cls_name)}
                    vt = self._expr(s.value, scope, strict=False)
                    if vt is not None and vt != NONE:
                        prev = cls_info["attrs"].get(s.target.attr)
                        if prev is None:
                            cls_info["attrs"][s.target.attr] = vt
                            self.changed = True
                        elif prev != vt:
                            if prev == NONE:
                                cls_info["attrs"][s.target.attr] = vt
                                self.changed = True
                            elif (isinstance(prev, tuple) and isinstance(vt, tuple)
                                  and prev[0] == "list" and vt[0] == "list" and prev[1] == NONE):
                                cls_info["attrs"][s.target.attr] = vt
                                self.changed = True
            elif isinstance(s, A.If):
                for _, b in s.branches:
                    self._scan_self_attrs(b, cls_name, cls_info)
                self._scan_self_attrs(s.orelse, cls_name, cls_info)
            elif isinstance(s, A.While):
                self._scan_self_attrs(s.body, cls_name, cls_info)
                self._scan_self_attrs(s.orelse, cls_name, cls_info)
            elif isinstance(s, A.For):
                self._scan_self_attrs(s.body, cls_name, cls_info)
                self._scan_self_attrs(s.orelse, cls_name, cls_info)
            elif isinstance(s, A.With):
                self._scan_self_attrs(s.body, cls_name, cls_info)
            elif isinstance(s, A.Try):
                self._scan_self_attrs(s.body, cls_name, cls_info)
                for _, _, hb in s.handlers:
                    self._scan_self_attrs(hb, cls_name, cls_info)

    # ---------- function ----------
    def _analyze_func(self, fn, strict=False):
        if any(t is None for t in fn.param_types):
            if strict:
                # will be reported later
                pass
            return
        scope = {p: t for p, t in zip(fn.params, fn.param_types)}
        # Initialise known locals to None so resolution treats them as locals.
        for n in fn.local_names:
            if n not in scope:
                scope[n] = None
        # Closure support: copy enclosing function's inferred local types into scope
        # (only for names not already defined locally).
        if fn.enclosing_func and fn.enclosing_func in self.funcs:
            enc = self.funcs[fn.enclosing_func]
            for n, t in enc.local_types.items():
                if n not in scope and n not in fn.params:
                    scope[n] = t
        prev_fn = self.cur_fn
        self.cur_fn = fn
        rt = self._block_return(fn.defn.body, scope, strict=strict)
        self.cur_fn = prev_fn
        # Always record local_types so closure variable types propagate across iterations.
        fn.local_types = dict(scope)
        if fn.return_type is None:
            if rt is not None:
                fn.return_type = rt
                self.changed = True
        else:
            if rt is not None and not self._type_compatible(fn.return_type, rt):
                raise SemanticError(
                    f"inconsistent return types in '{fn.name}': "
                    f"{fn.return_type} vs {rt}", fn.defn.line)
            elif rt is not None:
                new_rt = self._more_specific(fn.return_type, rt)
                if new_rt != fn.return_type:
                    fn.return_type = new_rt
                    self.changed = True

    def _apply_defaults(self):
        """Fill unresolved param types from default values; fall back to NONE."""
        for fn in self.funcs.values():
            for i, p in enumerate(fn.params):
                if fn.param_types[i] is not None:
                    continue
                if p in fn.defaults:
                    dt = self._expr_type(fn.defaults[p], {}, strict=False)
                    if dt is None:
                        dt = NONE
                    fn.param_types[i] = dt
                else:
                    # Never called with a concrete type and no default: treat as
                    # unknown (NONE) so the body can still be analyzed.
                    fn.param_types[i] = NONE

    def _type_compatible(self, t1, t2):
        """Check if two types are compatible, treating NONE as 'unknown'."""
        if t1 == t2:
            return True
        if t1 is None or t2 is None or t1 == NONE or t2 == NONE:
            return True
        if isinstance(t1, tuple) and isinstance(t2, tuple):
            if t1[0] != t2[0]:
                return False
            if t1[0] == "list":
                return self._type_compatible(t1[1], t2[1])
            if t1[0] == "tuple":
                if len(t1[1]) != len(t2[1]):
                    return False
                return all(self._type_compatible(a, b) for a, b in zip(t1[1], t2[1]))
            if t1[0] == "dict":
                return self._type_compatible(t1[1], t2[1]) and self._type_compatible(t1[2], t2[2])
            return t1 == t2
        return False

    def _more_specific(self, t1, t2):
        """Return the more specific of two compatible types (non-NONE preferred)."""
        if t1 is None or t1 == NONE:
            return t2
        if t2 is None or t2 == NONE:
            return t1
        if isinstance(t1, tuple) and isinstance(t2, tuple) and t1[0] == t2[0]:
            if t1[0] == "list":
                return ("list", self._more_specific(t1[1], t2[1]))
            if t1[0] == "tuple":
                return ("tuple", [self._more_specific(a, b) for a, b in zip(t1[1], t2[1])])
            if t1[0] == "dict":
                return ("dict", self._more_specific(t1[1], t2[1]),
                        self._more_specific(t1[2], t2[2]))
        return t1

    def _block_return(self, body, scope, strict=False):
        """Compute the inferred return type of a statement block."""
        rt = None
        for s in body:
            r = self._stmt(s, scope, strict=strict)
            if r is not None:
                if rt is None:
                    rt = r
                elif not self._type_compatible(rt, r):
                    raise SemanticError(f"inconsistent return types: {rt} vs {r}", s.line)
                else:
                    rt = self._more_specific(rt, r)
        return rt

    # ---------- statements ----------
    def _stmt(self, s, scope, strict=False, is_global_scope=False):
        """Returns the return type contributed by this statement, or None."""
        if isinstance(s, A.ExprStmt):
            self._expr(s.expr, scope, strict)
            return None
        if isinstance(s, A.Assign):
            return self._handle_assign(s, scope, strict, is_global_scope)
        if isinstance(s, A.AugAssign):
            tt = self._expr(s.target, scope, strict)
            vt = self._expr(s.value, scope, strict)
            rt = self._binop_type(s.op, tt, vt, s.line)
            # augmented assignment requires target to keep a consistent type
            if tt is not None and rt is not None and tt != rt:
                if isinstance(s.target, A.Name):
                    raise SemanticError(
                        f"augmented assignment changes type of '{s.target.name}' "
                        f"from {tt} to {rt}", s.line)
            # If target is an attribute, update the class attr type.
            if isinstance(s.target, A.Attribute):
                self._maybe_update_attr_type(s.target, rt, scope, strict)
            return None
        if isinstance(s, A.Return):
            if s.value is None:
                return NONE
            return self._expr(s.value, scope, strict)
        if isinstance(s, (A.Break, A.Continue, A.Pass)):
            return None
        if isinstance(s, A.Global):
            # Names are collected in _collect_locals -> fn.global_decls.
            # Do NOT add them to local scope; they resolve via global_types.
            return None
        if isinstance(s, A.If):
            rts = []
            for cond, body in s.branches:
                self._expr(cond, scope, strict)
                r = self._block_return(body, scope, strict)
                if r is not None:
                    rts.append(r)
            if s.orelse:
                r = self._block_return(s.orelse, scope, strict)
                if r is not None:
                    rts.append(r)
            if rts:
                # all branches must agree
                first = rts[0]
                for r in rts[1:]:
                    if r != first and r != NONE:
                        raise SemanticError(f"inconsistent return types across branches: {first} vs {r}", s.line)
                return first
            return None
        if isinstance(s, A.While):
            self._expr(s.cond, scope, strict)
            r1 = self._block_return(s.body, scope, strict)
            r2 = None
            if s.orelse:
                r2 = self._block_return(s.orelse, scope, strict)
            return r1 or r2
        if isinstance(s, A.For):
            self._expr(s.iterable, scope, strict)
            # The loop variable type is derived from the iterable.
            vt = self._for_var_type(s.iterable, scope, strict)
            # s.var is a list of targets (strings or nested lists).
            self._define_for_var(s.var, vt, scope, s.line, is_global_scope)
            r1 = self._block_return(s.body, scope, strict)
            r2 = None
            if s.orelse:
                r2 = self._block_return(s.orelse, scope, strict)
            return r1 or r2
        if isinstance(s, (A.With,)):
            for ctx, var in s.items:
                self._expr(ctx, scope, strict)
                if var is not None:
                    # `with ctx as var`: var gets the context manager type (opaque).
                    ct = self._expr(ctx, scope, strict)
                    self._define(var, ct, scope, s.line, is_global_scope)
            return self._block_return(s.body, scope, strict)
        if isinstance(s, A.Try):
            rts = []
            r = self._block_return(s.body, scope, strict)
            if r is not None:
                rts.append(r)
            for exc_type, name, hb in s.handlers:
                if exc_type is not None:
                    self._expr(exc_type, scope, strict)
                if name is not None:
                    self._define(name, ("obj", "Exception"), scope, s.line, is_global_scope)
                r = self._block_return(hb, scope, strict)
                if r is not None:
                    rts.append(r)
            if rts:
                first = rts[0]
                for r in rts[1:]:
                    if r != first and r != NONE:
                        raise SemanticError(
                            f"inconsistent return types in try/except: {first} vs {r}", s.line)
                return first
            return None
        if isinstance(s, A.Raise):
            if s.exc is not None:
                self._expr(s.exc, scope, strict)
            return NONE
        if isinstance(s, A.ClassDef):
            # Handled in analyze(); skip if encountered here.
            return None
        if isinstance(s, (A.Import, A.ImportFrom)):
            # Register names in global scope (no-op for code generation).
            self._handle_import(s, scope, is_global_scope)
            return None
        if isinstance(s, A.FuncDef):
            # Nested function definitions are hoisted to top-level in analyze().
            # Skip when encountered in a body.
            return None
        raise SemanticError(f"unhandled statement {type(s).__name__}", s.line)

    def _handle_assign(self, s, scope, strict, is_global_scope):
        vt = self._expr(s.value, scope, strict)
        target = s.target
        if isinstance(target, A.Name):
            self._define(target.name, vt, scope, s.line, is_global_scope)
            # Track per-key dict types when assigning a DictLit to a variable.
            if isinstance(s.value, A.DictLit):
                if target.name not in self.dict_key_types:
                    self.dict_key_types[target.name] = {}
                for k, v in s.value.pairs:
                    if isinstance(k, A.StringLit):
                        new_t = self._expr(v, scope, strict)
                        existing = self.dict_key_types[target.name].get(k.value)
                        # Don't overwrite a refined type with an unrefined one.
                        if existing is None or existing == NONE:
                            self.dict_key_types[target.name][k.value] = new_t
                        elif isinstance(existing, tuple) and isinstance(new_t, tuple) \
                                and existing[0] == "list" and new_t[0] == "list" \
                                and existing[1] != NONE and new_t[1] == NONE:
                            pass  # keep refined type
                        else:
                            self.dict_key_types[target.name][k.value] = new_t
        elif isinstance(target, A.Subscript):
            # Type-check the subscript target to set .type on obj
            self._expr(target, scope, strict)
            # Track per-key dict types for `dict["key"] = value` assignments.
            if isinstance(target.obj, A.Name) and isinstance(target.index, A.StringLit):
                var_name = target.obj.name
                if var_name not in self.dict_key_types:
                    self.dict_key_types[var_name] = {}
                prev = self.dict_key_types[var_name].get(target.index.value)
                if prev is None or prev == NONE:
                    if vt is not None and vt != NONE:
                        self.dict_key_types[var_name][target.index.value] = vt
                        self.changed = True
                elif isinstance(prev, tuple) and isinstance(vt, tuple) \
                        and prev[0] == "list" and vt[0] == "list" and prev[1] == NONE and vt[1] != NONE:
                    self.dict_key_types[var_name][target.index.value] = vt
                    self.changed = True
        elif isinstance(target, A.Attribute):
            # Attribute assignment: update the class attr type if obj is a class instance.
            self._maybe_update_attr_type(target, vt, scope, strict)
        elif isinstance(target, A.TupleLit):
            # Tuple unpacking: a, b = value
            self._handle_tuple_unpack(target, s.value, vt, scope, s.line, is_global_scope)
        return None

    def _handle_tuple_unpack(self, target, value, vt, scope, line, is_global_scope):
        """Handle `a, b = value` where target is a TupleLit."""
        targets = target.elements
        # If the value is also a TupleLit, evaluate each element directly.
        if isinstance(value, A.TupleLit):
            value_types = [self._expr(el, scope, False) for el in value.elements]
            for t, tt in zip(targets, value_types):
                if isinstance(t, A.Name):
                    self._define(t.name, tt, scope, line, is_global_scope)
            return
        # Otherwise, use the inferred type of the value.
        if isinstance(vt, tuple) and vt[0] == "tuple" and len(vt[1]) == len(targets):
            for t, tt in zip(targets, vt[1]):
                if isinstance(t, A.Name):
                    self._define(t.name, tt, scope, line, is_global_scope)
        elif isinstance(vt, tuple) and vt[0] == "list":
            # All targets get the list element type.
            for t in targets:
                if isinstance(t, A.Name):
                    self._define(t.name, vt[1], scope, line, is_global_scope)
        else:
            # Unknown value type; define targets as None (unknown).
            for t in targets:
                if isinstance(t, A.Name):
                    self._define(t.name, None, scope, line, is_global_scope)

    def _maybe_update_attr_type(self, attr_node, vt, scope, strict):
        """If attr_node is `obj.attr` where obj is a class instance, update the class attr type."""
        if vt is None:
            return
        # NONE is "unknown"; don't let it overwrite a more specific attr type.
        if vt == NONE:
            return
        obj = attr_node.obj
        ot = self._expr(obj, scope, strict)
        if isinstance(ot, tuple) and ot[0] == "obj":
            class_name = ot[1]
            if class_name in self.classes:
                attrs = self.classes[class_name]["attrs"]
                prev = attrs.get(attr_node.attr)
                if prev is None:
                    attrs[attr_node.attr] = vt
                    self.changed = True
                elif prev != vt:
                    # Refine NONE -> T.
                    if prev == NONE:
                        attrs[attr_node.attr] = vt
                        self.changed = True
                    # Refine ("list", NONE) -> ("list", T).
                    elif (isinstance(prev, tuple) and isinstance(vt, tuple)
                          and prev[0] == "list" and vt[0] == "list" and prev[1] == NONE):
                        attrs[attr_node.attr] = vt
                        self.changed = True

    def _handle_import(self, s, scope, is_global_scope):
        """Register imported names in scope so they resolve to module types."""
        # Stdlib module names (those the compiler knows natively).
        KNOWN_STDLIB = {
            "random", "time", "re", "threading", "queue", "collections",
            "concurrent", "concurrent.futures", "math", "os", "sys", "json",
            "itertools", "functools", "string", "datetime", "struct",
            "io", "pathlib", "copy", "textwrap", "bisect", "heapq",
            "operator", "enum", "abc", "contextlib", "csv", "base64",
            "pprint", "unicodedata", "codecs", "hashlib", "hmac",
            "secrets", "decimal", "fractions", "statistics", "array",
            "weakref", "dataclasses", "typing", "argparse", "configparser",
            "shutil", "tempfile", "glob", "fnmatch", "subprocess", "signal",
            "mmap", "ctypes", "platform", "errno", "stat", "socket",
            "ssl", "http", "urllib", "email", "xml", "html",
            "logging", "warnings", "traceback", "inspect", "types",
        }
        if isinstance(s, A.Import):
            name = s.alias if s.alias else s.module
            top = s.module.split(".")[0]
            # In embed mode, non-stdlib modules are PyObject* (route A).
            if self.embed_mode and top not in KNOWN_STDLIB:
                self._define(name, PYOBJECT, scope, s.line, is_global_scope)
            else:
                # Use just the top-level module name for the type.
                self._define(name, ("module", top), scope, s.line, is_global_scope)
        elif isinstance(s, A.ImportFrom):
            top = s.module.split(".")[0]
            # In embed mode, names from `from X import Y` are individual
            # Python objects (functions, classes, constants). Register them
            # as PYOBJECT so attribute access and calls route through
            # libpython — this works for stdlib too because the value is
            # already a fully-resolved Python object after the import.
            if self.embed_mode:
                for n in s.names:
                    self._define(n, PYOBJECT, scope, s.line, is_global_scope)
            else:
                for n in s.names:
                    self._define(n, ("module", s.module + "." + n), scope, s.line, is_global_scope)

    @staticmethod
    def _type_has_none(t):
        """True if the type contains NONE anywhere (recursive)."""
        if t is None or t == NONE:
            return True
        if isinstance(t, tuple):
            if t[0] == "tuple":
                return any(Analyzer._type_has_none(x) for x in t[1])
            if t[0] == "list":
                return Analyzer._type_has_none(t[1])
        return False

    @staticmethod
    def _merge_types(old, new):
        """Merge two types, preferring the non-NONE side at every position.
        Returns the merged type, or old if incompatible."""
        if old is None or old == NONE:
            return new
        if new is None or new == NONE:
            return old
        if old == new:
            return old
        if isinstance(old, tuple) and isinstance(new, tuple) and old[0] == new[0]:
            if old[0] == "tuple" and len(old[1]) == len(new[1]):
                return ("tuple", [Analyzer._merge_types(o, n) for o, n in zip(old[1], new[1])])
            if old[0] == "list":
                return ("list", Analyzer._merge_types(old[1], new[1]))
        return old

    def _define(self, name, t, scope, line, is_global_scope):
        if t is None:
            return
        # NONE (the "none" type) is treated as "unknown"; don't let it overwrite a
        # more specific existing type, and don't error on it.
        if t == NONE:
            # Only set if the name is entirely unknown.
            target_dict = self.global_types if (self.cur_fn is not None and name in self.cur_fn.global_decls) else scope
            if name not in target_dict or target_dict.get(name) is None:
                target_dict[name] = t
                self.changed = True
            return
        # A `global`-declared name inside a function writes to the module scope.
        if self.cur_fn is not None and name in self.cur_fn.global_decls:
            target = self.global_types
        else:
            target = scope
        prev = target.get(name)
        if prev is None:
            target[name] = t
            self.changed = True
        elif prev != t:
            # Allow refining ("list", "none") -> ("list", T) and vice versa
            if (isinstance(prev, tuple) and isinstance(t, tuple)
                    and prev[0] == "list" and t[0] == "list"):
                if prev[1] == NONE:
                    target[name] = t
                    self.changed = True
                    return
                if t[1] == NONE:
                    return  # keep the more specific type
            # Allow refining NONE (the "none" type) to a more concrete type.
            if prev == NONE and t != NONE:
                target[name] = t
                self.changed = True
                return
            # Allow promoting a native int/float/bool to PYOBJECT when a
            # program mixes native code with C-extension calls (e.g.
            # `total = 0; total = sqrt(total + 1)` in a numpy-using program).
            # Python variables are dynamically typed; in our hybrid mode this
            # is a legal re-typing.
            if t == PYOBJECT and prev in (INT, FLOAT, BOOL):
                target[name] = t
                self.changed = True
                return
            raise SemanticError(
                f"variable '{name}' reassigned with inconsistent type {prev} -> {t}", line)

    def _for_var_type(self, iterable, scope, strict):
        # Handle enumerate(): yields (index, element) tuples.
        if isinstance(iterable, A.Call) and isinstance(iterable.func, A.Name) \
                and iterable.func.name == "enumerate":
            if iterable.args:
                inner_t = self._expr(iterable.args[0], scope, strict)
                if isinstance(inner_t, tuple) and inner_t[0] == "list":
                    return ("tuple", [INT, inner_t[1]])
                if inner_t == STR:
                    return ("tuple", [INT, STR])
                if inner_t == "range":
                    return ("tuple", [INT, INT])
                # Unknown inner type; return tuple with None elements.
                return ("tuple", [INT, None])
            return ("tuple", [INT, None])
        t = self._expr(iterable, scope, strict)
        if t == "range":
            return INT
        if t == STR:
            return STR
        if isinstance(t, tuple) and t[0] == "list":
            return t[1]  # element type
        if isinstance(t, tuple) and t[0] == "tuple":
            return t  # iterating over a tuple yields its elements (the tuple itself when unpacking)
        if isinstance(t, tuple) and t[0] == "dict":
            return t[1]  # iterating over a dict yields keys
        if isinstance(t, tuple) and t[0] == "set":
            return t[1]  # element type
        if t is None or t == NONE:
            # Unknown iterable type; yield unknown elements.
            return NONE
        if strict:
            raise SemanticError(f"cannot iterate over value of type {t}", iterable.line)
        return None

    def _define_for_var(self, var_target, value_type, scope, line, is_global_scope):
        """Recursively define for-loop variables from a target spec.
        var_target is a string or a list (possibly nested).
        value_type is the type yielded by the iterable."""
        if isinstance(var_target, str):
            self._define(var_target, value_type, scope, line, is_global_scope)
            return
        if isinstance(var_target, list):
            # Tuple unpacking: value_type should be ("tuple", [elem_types]).
            if isinstance(value_type, tuple) and value_type[0] == "tuple":
                elems = value_type[1]
                for i, vt in enumerate(var_target):
                    et = elems[i] if i < len(elems) else None
                    self._define_for_var(vt, et, scope, line, is_global_scope)
            else:
                # Non-tuple value type (e.g. ("list", T), NONE, INT, STR) applied
                # to each target as-is.
                for vt in var_target:
                    self._define_for_var(vt, value_type, scope, line, is_global_scope)

    # ---------- expressions ----------
    def _expr(self, e, scope, strict=False):
        t = self._expr_type(e, scope, strict)
        e.type = t
        return t

    def _expr_type(self, e, scope, strict):
        if isinstance(e, A.NumberLit):
            return INT if isinstance(e.value, int) else FLOAT
        if isinstance(e, A.StringLit):
            return STR
        if isinstance(e, A.BoolLit):
            return BOOL
        if isinstance(e, A.NoneLit):
            return NONE
        if isinstance(e, A.Name):
            if e.name in scope:
                t = scope[e.name]
                if t is None and strict:
                    raise SemanticError(f"variable '{e.name}' used before assignment with known type", e.line)
                return t
            # Fall back to module globals (read-only access from functions).
            if e.name in self.global_types:
                return self.global_types[e.name]
            if e.name in self.funcs:
                return ("func", e.name)
            # Check for hoisted nested function references.
            resolved = self._resolve_call_name(e.name)
            if resolved != e.name and resolved in self.funcs:
                return ("func", resolved)
            if e.name in self.classes:
                return ("class", e.name)
            if e.name in BUILTINS:
                return ("builtin", e.name)
            if e.name in EXCEPTION_TYPES:
                return ("obj", e.name)
            if strict:
                raise SemanticError(f"undefined name '{e.name}'", e.line)
            return None
        if isinstance(e, A.BinOp):
            lt = self._expr(e.left, scope, strict)
            rt = self._expr(e.right, scope, strict)
            # Hybrid mode: any pyobject operand → pyobject result.
            if lt == PYOBJECT or rt == PYOBJECT:
                return PYOBJECT
            return self._binop_type(e.op, lt, rt, e.line)
        if isinstance(e, A.UnaryOp):
            ot = self._expr(e.operand, scope, strict)
            # Hybrid mode: pyobject operand → pyobject (except for `not` which is bool).
            if ot == PYOBJECT:
                return BOOL if e.op == "not" else PYOBJECT
            if e.op == "not":
                return BOOL
            if e.op in ("+", "-"):
                if ot is None:
                    return None
                if numeric_base(ot) is not None:
                    return INT if numeric_base(ot) == INT else FLOAT
                if ot == NONE or isinstance(ot, tuple):
                    return None
                raise SemanticError(f"unary {e.op} not defined for type {ot}", e.line)
            raise SemanticError(f"unknown unary op {e.op}", e.line)
        if isinstance(e, A.BoolOp):
            self._expr(e.left, scope, strict)
            self._expr(e.right, scope, strict)
            return BOOL
        if isinstance(e, A.IfExp):
            self._expr(e.cond, scope, strict)
            tt = self._expr(e.then, scope, strict)
            et = self._expr(e.else_, scope, strict)
            if tt is None or et is None:
                return None
            if tt != et:
                # Allow NONE vs T (None is a polymorphic fallback).
                if tt == NONE:
                    return et
                if et == NONE:
                    return tt
                # Allow int/float mixing (promote to float).
                if {numeric_base(tt), numeric_base(et)} <= {INT, FLOAT}:
                    return FLOAT if FLOAT in (tt, et) else INT
                raise SemanticError(f"ternary branches have different types {tt} vs {et}", e.line)
            return tt
        # Exception construction: Exception("msg"), ValueError("msg"), etc.
        if isinstance(e, A.Call) and isinstance(e.func, A.Name):
            exc_types = {"Exception", "ValueError", "TypeError", "KeyError",
                         "IndexError", "ZeroDivisionError", "StopIteration",
                         "FileNotFoundError", "RuntimeError", "NotImplementedError",
                         "ArithmeticError", "OverflowError", "FloatingPointError",
                         "AttributeError", "NameError", "UnboundLocalError",
                         "ImportError", "ModuleNotFoundError", "OSError",
                         "IOError", "PermissionError", "TimeoutError",
                         "RecursionError", "AssertionError", "KeyboardInterrupt",
                         "SystemExit", "GeneratorExit", "StopAsyncIteration",
                         "Warning", "UserWarning", "DeprecationWarning",
                         "PendingDeprecationWarning", "SyntaxWarning",
                         "RuntimeWarning", "FutureWarning", "ImportWarning",
                         "UnicodeWarning", "BytesWarning", "ResourceWarning"}
            if e.func.name in exc_types:
                return ("obj", e.func.name)
        if isinstance(e, A.Call) and isinstance(e.func, A.Name) and e.func.name == "__lambda__":
            # Lambda: return type of body
            if e.args:
                return self._expr(e.args[0], scope, strict)
            return NONE
        # Type conversion builtins are exact — they always return their target
        # type even if the argument is a pyobject. This lets users write
        # `int(numpy_value)` to convert a hybrid value into a native int.
        if isinstance(e, A.Call) and isinstance(e.func, A.Name) \
                and e.func.name in ("int", "float", "str", "bool"):
            return self._builtin_type(e.func.name, e, [], strict)
        if isinstance(e, A.Call):
            # For direct calls to a Name (user function or built-in), always
            # go through _call_type so we can refine param types and return
            # type via fixpoint iteration. This is critical in hybrid mode:
            # a function that takes a numpy array and returns a numpy array
            # needs to be typed correctly so calls to it from the top level
            # propagate the PYOBJECT type.
            if isinstance(e.func, A.Name) and e.func.name in self.funcs:
                return self._call_type(e, scope, strict)
            # Hybrid mode: if any arg or func is pyobject, return pyobject.
            ft = self._expr(e.func, scope, strict=False)
            if ft == PYOBJECT or any(self._expr(a, scope, strict=False) == PYOBJECT for a in e.args):
                return PYOBJECT
            return self._call_type(e, scope, strict)
        if isinstance(e, A.ListLit):
            elem_types = [self._expr(el, scope, strict) for el in e.elements]
            if not elem_types:
                return ("list", NONE)  # empty list; will be refined by usage
            et0 = elem_types[0]
            for et in elem_types[1:]:
                if et is None or et == NONE:
                    continue  # NONE/None elements are "unknown", don't constrain
                if et0 is None or et0 == NONE:
                    et0 = et
                elif et != et0:
                    # Allow int/bool mixing (bool is int)
                    if numeric_base(et0) == INT and numeric_base(et) == INT:
                        et0 = INT
                    else:
                        raise SemanticError(f"list elements have inconsistent types {et0} vs {et}", e.line)
            return ("list", et0 if et0 is not None else NONE)
        if isinstance(e, A.TupleLit):
            elem_types = [self._expr(el, scope, strict) for el in e.elements]
            return ("tuple", elem_types)
        if isinstance(e, A.DictLit):
            key_t = None
            val_t = None
            for k, v in e.pairs:
                kt = self._expr(k, scope, strict)
                vt = self._expr(v, scope, strict)
                if kt is not None:
                    key_t = kt if key_t is None else key_t
                if vt is not None:
                    if val_t is None:
                        val_t = vt
                    elif val_t != vt:
                        # Mixed value types -> use NONE as the common type.
                        val_t = NONE
            return ("dict", key_t if key_t is not None else NONE, val_t if val_t is not None else None)
        if isinstance(e, A.Subscript):
            ot = self._expr(e.obj, scope, strict)
            it = self._expr(e.index, scope, strict)
            # Hybrid mode: pyobject subscript returns pyobject.
            if ot == PYOBJECT or it == PYOBJECT:
                return PYOBJECT
            if ot is None:
                return None
            if isinstance(ot, tuple) and ot[0] == "list":
                if strict and it is not None and numeric_base(it) != INT:
                    raise SemanticError(f"list index must be int, got {it}", e.line)
                return ot[1]
            if isinstance(ot, tuple) and ot[0] == "dict":
                # Check per-key type tracking for string-literal keys.
                if isinstance(e.obj, A.Name) and isinstance(e.index, A.StringLit):
                    key_types = self.dict_key_types.get(e.obj.name)
                    if key_types and e.index.value in key_types:
                        return key_types[e.index.value]
                # Dict subscript returns the value type (may be None if mixed).
                return ot[2]
            if isinstance(ot, tuple) and ot[0] == "tuple":
                # Tuple subscript: if index is a constant literal, return the
                # specific element type; otherwise fall back to the first.
                elems = ot[1]
                if isinstance(e.index, A.NumberLit) and 0 <= e.index.value < len(elems):
                    return elems[e.index.value]
                return elems[0] if elems else None
            if ot == STR:
                if strict and it is not None and numeric_base(it) != INT:
                    raise SemanticError(f"string index must be int, got {it}", e.line)
                return STR
            if strict:
                raise SemanticError(f"cannot subscript value of type {ot}", e.line)
            return None
        if isinstance(e, A.Slice):
            ot = self._expr(e.obj, scope, strict)
            if e.start is not None:
                self._expr(e.start, scope, strict)
            if e.stop is not None:
                self._expr(e.stop, scope, strict)
            if e.step is not None:
                self._expr(e.step, scope, strict)
            if ot is None:
                return None
            if isinstance(ot, tuple) and ot[0] == "list":
                return ot  # slicing a list returns a list of the same type
            if ot == STR:
                return STR
            if strict:
                raise SemanticError(f"cannot slice value of type {ot}", e.line)
            return None
        if isinstance(e, A.Attribute):
            # Hybrid mode: if obj is pyobject, attribute access returns pyobject.
            ot = self._expr(e.obj, scope, strict=False)
            if ot == PYOBJECT:
                return PYOBJECT
            return self._attr_type(e, scope, strict)
        if isinstance(e, A.MethodCall):
            # Hybrid mode: if obj is pyobject, method call returns pyobject.
            ot = self._expr(e.obj, scope, strict=False)
            if ot == PYOBJECT:
                return PYOBJECT
            return self._method_call_type(e, scope, strict)
        if isinstance(e, A.FString):
            # Evaluate all expression parts for side effects; result is always STR.
            for part, info in e.parts:
                if info is not False:  # True (expr) or a format-spec string -> expression
                    self._expr(part, scope, strict)
            return STR
        if isinstance(e, A.Compare):
            # Chained comparison: evaluate all operands, return BOOL.
            for operand in e.operands:
                self._expr(operand, scope, strict)
            return BOOL
        if isinstance(e, A.IsOp):
            self._expr(e.left, scope, strict)
            self._expr(e.right, scope, strict)
            return BOOL
        if isinstance(e, A.Starred):
            return self._expr(e.value, scope, strict)
        if isinstance(e, A.ListComp):
            return self._listcomp_type(e, scope, strict)
        if isinstance(e, A.DictComp):
            return self._dictcomp_type(e, scope, strict)
        raise SemanticError(f"unhandled expression {type(e).__name__}", e.line)

    def _attr_type(self, e, scope, strict):
        """Handle attribute access: obj.attr"""
        ot = self._expr(e.obj, scope, strict)
        if ot is None:
            return None
        if isinstance(ot, tuple) and ot[0] == "obj":
            class_name = ot[1]
            if class_name in self.classes:
                attrs = self.classes[class_name]["attrs"]
                if e.attr in attrs:
                    return attrs[e.attr]
                # Unknown attr on a known class; return None (will be inferred later).
                return None
            # Runtime classes (Counter, Thread, Lock, Event, Queue, deque).
            # Attribute access on these returns None (opaque).
            return None
        if isinstance(ot, tuple) and ot[0] == "module":
            return ("module_attr", ot[1], e.attr)
        if ot == STR:
            # String attribute access (e.g., str.join) -> method type.
            return ("method", "str", e.attr)
        if isinstance(ot, tuple) and ot[0] == "list":
            return ("method", "list", e.attr)
        if ot == NONE:
            return None
        if strict:
            raise SemanticError(f"cannot access attribute '{e.attr}' on value of type {ot}", e.line)
        return None

    def _listcomp_type(self, e, scope, strict):
        """Handle [expr for var in iterable (if cond)*]."""
        # Evaluate the iterable in the current scope.
        iter_t = self._for_var_type(e.iterable, scope, strict)
        # Create a child scope with the loop variable(s) defined.
        child_scope = dict(scope)
        self._define_for_var(e.var, iter_t, child_scope, e.line, is_global_scope=False)
        # Evaluate conditions (for side effects).
        for cond in e.conditions:
            self._expr(cond, child_scope, strict)
        # Evaluate the element expression to get the list's element type.
        et = self._expr(e.element, child_scope, strict)
        return ("list", et if et is not None else NONE)

    def _dictcomp_type(self, e, scope, strict):
        """Handle {k_expr: v_expr for var in iterable (if cond)*}."""
        iter_t = self._for_var_type(e.iterable, scope, strict)
        child_scope = dict(scope)
        self._define_for_var(e.var, iter_t, child_scope, e.line, is_global_scope=False)
        for cond in e.conditions:
            self._expr(cond, child_scope, strict)
        # Key and value types
        kt = self._expr(e.key_expr, child_scope, strict)
        vt = self._expr(e.val_expr, child_scope, strict)
        # Dict type: ("dict", key_t, val_t) - 3-tuple
        return ("dict", kt if kt is not None else STR, vt if vt is not None else NONE)

    def _method_call_type(self, e, scope, strict):
        ot = self._expr(e.obj, scope, strict)
        # Evaluate args, expanding Starred args (tuples/lists) into individual types.
        arg_types = []
        for a in e.args:
            if isinstance(a, A.Starred):
                st = self._expr(a.value, scope, strict)
                if isinstance(st, tuple) and st[0] == "tuple":
                    arg_types.extend(st[1])
                elif isinstance(st, tuple) and st[0] == "list":
                    arg_types.append(st[1])
                else:
                    arg_types.append(st)
            else:
                arg_types.append(self._expr(a, scope, strict))
        # Evaluate kwargs for side effects.
        for k, v in (e.kwargs or {}).items():
            self._expr(v, scope, strict)
        if ot is None:
            return None
        # Refine per-key dict type when appending to a dict subscript list.
        # e.g., stats["producer_times"].append((pid, elapsed)) refines the key type.
        if isinstance(ot, tuple) and ot[0] == "list":
            if isinstance(e.obj, A.Subscript) and isinstance(e.obj.obj, A.Name) \
               and isinstance(e.obj.index, A.StringLit) and e.method in ("append", "add"):
                if arg_types and arg_types[0] is not None and arg_types[0] != NONE:
                    var_name = e.obj.obj.name
                    if var_name in self.dict_key_types:
                        prev = self.dict_key_types[var_name].get(e.obj.index.value)
                        new_t = ("list", arg_types[0])
                        merged = self._merge_types(prev, new_t) if prev is not None else new_t
                        if merged != prev:
                            self.dict_key_types[var_name][e.obj.index.value] = merged
                            self.changed = True
        # Methods on user-defined class instances (and runtime objects).
        if isinstance(ot, tuple) and ot[0] == "obj":
            return self._obj_method_call_type(ot, e, arg_types, scope, strict)
        # Methods on runtime modules (random.randint, re.sub, etc.).
        if isinstance(ot, tuple) and ot[0] == "module":
            return self._module_method_call_type(ot[1], e, arg_types, scope, strict)
        # Methods on strings.
        if ot == STR:
            return self._str_method_type(e.method, arg_types, strict, e.line)
        # Methods on lists.
        if isinstance(ot, tuple) and ot[0] == "list":
            return self._list_method_type(ot, e, arg_types, scope, strict)
        if isinstance(ot, tuple) and ot[0] == "set":
            return self._runtime_obj_method_type("set", e, arg_types, strict)
        if isinstance(ot, tuple) and ot[0] == "dict":
            return self._runtime_obj_method_type("dict", e, arg_types, strict, dict_type=ot)
        if ot == NONE:
            return None
        if strict:
            raise SemanticError(f"method call on unsupported type {ot}", e.line)
        return None

    def _obj_method_call_type(self, ot, e, arg_types, scope, strict):
        """Method call on a user-defined class instance."""
        class_name = ot[1]
        m = e.method
        if class_name in self.classes:
            methods = self.classes[class_name]["methods"]
            if m in methods:
                mangled = methods[m]
                fn = self.funcs.get(mangled)
                if fn is not None:
                    # Set param types from this call (first param is self).
                    call_arg_types = [ot] + arg_types
                    for i, (p, at) in enumerate(zip(fn.params, call_arg_types)):
                        if i >= len(call_arg_types):
                            break
                        if at is None:
                            continue
                        if fn.param_types[i] is None:
                            fn.param_types[i] = at
                            self.changed = True
                        elif fn.param_types[i] != at:
                            # Allow NONE -> T refinement for params.
                            if fn.param_types[i] == NONE:
                                fn.param_types[i] = at
                                self.changed = True
                    return fn.return_type
            # Unknown method on known class; return None.
            return None
        # Runtime class.
        return self._runtime_obj_method_type(class_name, e, arg_types, strict)

    def _runtime_obj_method_type(self, class_name, e, arg_types, strict, dict_type=None):
        """Method call on a runtime object (Counter, Thread, Lock, Event, Queue, deque)."""
        m = e.method
        if class_name == "Counter":
            if m == "update":
                return NONE
            if m == "most_common":
                return ("list", ("tuple", [STR, INT]))
            if m == "values":
                return ("list", INT)
            if m == "keys":
                return ("list", STR)
            if m == "items":
                return ("list", ("tuple", [STR, INT]))
            if m in ("get",):
                return INT
            return None
        if class_name in ("Thread",):
            if m in ("start", "join"):
                return NONE
            return None
        if class_name == "Lock":
            if m in ("acquire", "release"):
                return NONE
            return None
        if class_name == "Event":
            if m in ("set", "clear", "wait"):
                return NONE
            if m in ("is_set",):
                return BOOL
            return None
        if class_name == "Queue":
            if m in ("put", "task_done", "join"):
                return NONE
            if m == "get":
                # Return a generic "any" type that the semantic analyzer
                # will refine based on usage. Defaults to STR for backward
                # compatibility.
                return STR
            if m in ("empty",):
                return BOOL
            if m in ("qsize",):
                return INT
            return None
        if class_name == "deque":
            if m in ("append", "appendleft", "extend", "extendleft", "clear"):
                return NONE
            if m in ("pop", "popleft"):
                return arg_types[0] if arg_types else None
            return None
        if class_name == "set":
            if m in ("add", "remove", "discard", "clear", "update"):
                return NONE
            if m in ("contains", "issubset", "issuperset", "isdisjoint"):
                return BOOL
            if m in ("union", "intersection", "difference", "symmetric_difference", "copy"):
                return ("obj", "set")
            if m == "pop":
                return NONE
            return None
        if class_name == "dict":
            if m == "keys":
                return ("list", STR)
            if m == "values":
                return ("list", NONE)
            if m == "items":
                return ("list", ("tuple", [STR, NONE]))
            if m in ("get", "setdefault"):
                # Return the dict's value type (ot[2])
                if dict_type is not None and len(dict_type) >= 3:
                    return dict_type[2]
                return NONE
            if m in ("update", "clear", "pop"):
                return NONE
            if m == "copy":
                return ("dict", STR, NONE)
            return None
        return None

    def _module_method_call_type(self, mod_name, e, arg_types, scope, strict):
        """Method call on a module: random.randint, re.sub, time.perf_counter, etc."""
        m = e.method
        if mod_name == "random":
            if m == "randint":
                return INT
            if m == "random":
                return FLOAT
            if m == "seed":
                return NONE
            if m == "choice":
                # Returns the element type of the first arg (a list).
                if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "list":
                    return arg_types[0][1]
                return None
            if m in ("uniform", "gauss", "normalvariate"):
                return FLOAT
            return None
        if mod_name == "time":
            if m in ("perf_counter", "time", "monotonic", "process_time"):
                return FLOAT
            if m == "sleep":
                return NONE
            return None
        if mod_name == "re":
            if m == "sub":
                return STR
            if m == "findall":
                return ("list", STR)
            if m == "search" or m == "match":
                return ("obj", "Match")
            if m == "split":
                return ("list", STR)
            return None
        if mod_name == "threading":
            if m == "Thread":
                # Set param types of the target function from args tuple.
                target = e.kwargs.get("target")
                args_expr = e.kwargs.get("args")
                if target is not None and isinstance(target, A.Name) and args_expr is not None:
                    fn_name = self._resolve_call_name(target.name)
                    if fn_name not in self.funcs:
                        fn_name = target.name
                    if fn_name in self.funcs:
                        fn = self.funcs[fn_name]
                        # Evaluate args tuple to get element types.
                        at = self._expr(args_expr, scope, strict)
                        elem_types = None
                        if isinstance(at, tuple) and at[0] == "tuple":
                            elem_types = at[1]
                        elif isinstance(at, tuple) and at[0] == "list":
                            elem_types = [at[1]]
                        if elem_types:
                            for i, (p, et) in enumerate(zip(fn.params, elem_types)):
                                if et is None or et == NONE:
                                    continue
                                if fn.param_types[i] is None or fn.param_types[i] == NONE:
                                    if fn.param_types[i] != et:
                                        fn.param_types[i] = et
                                        self.changed = True
                return ("obj", "Thread")
            if m == "Lock":
                return ("obj", "Lock")
            if m == "Event":
                return ("obj", "Event")
            return None
        if mod_name == "queue":
            if m == "Queue":
                return ("obj", "Queue")
            if m == "Empty":
                return ("obj", "Exception")
            return None
        if mod_name == "collections":
            if m == "deque":
                return ("obj", "deque")
            if m == "Counter":
                return ("obj", "Counter")
            return None
        if mod_name in ("concurrent.futures",):
            if m == "ThreadPoolExecutor":
                return ("obj", "ThreadPoolExecutor")
            if m == "as_completed":
                return ("list", NONE)
            return None
        if mod_name == "math":
            if m in ("sqrt", "log", "log2", "log10", "sin", "cos", "tan",
                     "asin", "acos", "atan", "atan2", "sinh", "cosh", "tanh",
                     "exp", "floor", "ceil", "fabs", "copysign", "fmod",
                     "pow", "hypot", "degrees", "radians", "gamma", "lgamma",
                     "erf", "erfc", "expm1", "log1p", "trunc"):
                return FLOAT
            if m in ("gcd", "lcm", "factorial", "isclose", "isfinite",
                     "isinf", "isnan"):
                if m in ("isfinite", "isinf", "isnan", "isclose"):
                    return BOOL
                return INT
            if m in ("pi", "e", "tau", "inf", "nan"):
                return FLOAT
            return None
        if mod_name == "string":
            if m in ("ascii_letters", "ascii_lowercase", "ascii_uppercase",
                     "digits", "hexdigits", "octdigits", "punctuation",
                     "whitespace", "printable"):
                return STR
            return None
        if mod_name == "os":
            if m in ("getcwd", "listdir", "getenv", "path"):
                return STR
            if m in ("mkdir", "rmdir", "remove", "rename", "chmod", "chdir", "system"):
                return NONE
            return None
        if mod_name == "sys":
            if m in ("argv", "path", "platform", "version", "maxsize"):
                return STR
            if m in ("exit",):
                return NONE
            return None
        if mod_name == "json":
            if m in ("dumps", "dump"):
                return STR
            if m in ("loads", "load"):
                return NONE
            return None
        if mod_name == "itertools":
            if m in ("chain", "cycle", "islice", "count", "repeat",
                     "starmap", "takewhile", "dropwhile", "filterfalse",
                     "groupby", "accumulate", "product", "permutations",
                     "combinations", "combinations_with_replacement"):
                return ("list", NONE)
            return None
        if mod_name == "functools":
            if m in ("reduce", "lru_cache", "partial", "wraps", "cache"):
                return NONE
            return None
        # Imported name like "collections.deque" stored as ("module", "collections.deque").
        if "." in mod_name:
            top = mod_name.split(".")[-1]
            return self._module_method_call_type(top, e, arg_types, scope, strict)
        # User module: check if the method name exists as a function
        fn_name = e.method
        if fn_name in self.funcs:
            fn = self.funcs[fn_name]
            for i, (p, at) in enumerate(zip(fn.params, arg_types)):
                if i < len(fn.param_types):
                    if fn.param_types[i] is None or fn.param_types[i] == NONE:
                        if at and at != NONE:
                            fn.param_types[i] = at
                            self.changed = True
            return fn.return_type
        return None

    def _str_method_type(self, m, arg_types, strict, line):
        """Method call on a string."""
        if m in ("lower", "upper", "strip", "lstrip", "rstrip", "title", "capitalize",
                 "swapcase", "replace", "join", "format", "removeprefix", "removesuffix",
                 "expandtabs", "center", "ljust", "rjust", "zfill"):
            return STR
        if m in ("split", "splitlines"):
            return ("list", STR)
        if m in ("find", "index", "count", "rfind", "rindex"):
            return INT
        if m in ("startswith", "endswith", "isalpha", "isdigit", "isalnum",
                 "isspace", "islower", "isupper", "isnumeric", "isdecimal",
                 "isidentifier", "isprintable", "istitle"):
            return BOOL
        if m == "encode":
            return STR
        if m in ("partition", "rpartition"):
            return ("tuple", [STR, STR, STR])
        if m == "maketrans":
            return NONE
        if m == "translate":
            return STR
        if strict:
            raise SemanticError(f"unknown string method '{m}'", line)
        return None

    def _list_method_type(self, ot, e, arg_types, scope, strict):
        """Method call on a list."""
        m = e.method
        if m in ("append", "add"):
            if strict and len(arg_types) != 1:
                raise SemanticError("append() expects 1 argument", e.line)
            # Refine list type if it was ("list", "none") (from empty list)
            if ot[1] == NONE and arg_types and arg_types[0] is not None:
                new_type = ("list", arg_types[0])
                self._refine_list_obj(e.obj, ot, new_type, scope)
                ot = new_type
            elif strict and arg_types and arg_types[0] is not None and arg_types[0] != ot[1]:
                # Allow refinement of tuple element types from NONE to specific.
                if isinstance(ot[1], tuple) and isinstance(arg_types[0], tuple) \
                        and ot[1][0] == "tuple" and arg_types[0][0] == "tuple" \
                        and len(ot[1][1]) == len(arg_types[0][1]):
                    refined = [a if (o == NONE or o is None) else o
                               for o, a in zip(ot[1][1], arg_types[0][1])]
                    if refined != list(ot[1][1]):
                        new_type = ("list", ("tuple", refined))
                        self._refine_list_obj(e.obj, ot, new_type, scope)
                        ot = new_type
                # Allow int/bool mixing
                elif not (numeric_base(arg_types[0]) == INT and numeric_base(ot[1]) == INT):
                    raise SemanticError(
                        f"append() argument type {arg_types[0]} doesn't match list type {ot[1]}", e.line)
            return NONE
        if m in ("pop",):
            return ot[1]
        if m in ("insert", "extend", "remove", "clear", "sort", "reverse", "copy"):
            # extend: refine list type if element type was NONE.
            if m == "extend" and ot[1] == NONE and arg_types and arg_types[0] is not None:
                if isinstance(arg_types[0], tuple) and arg_types[0][0] == "list":
                    new_type = ("list", arg_types[0][1])
                    self._refine_list_obj(e.obj, ot, new_type, scope)
                elif isinstance(arg_types[0], tuple) and arg_types[0][0] == "tuple":
                    # extend with a tuple: use first element type.
                    if arg_types[0][1]:
                        new_type = ("list", arg_types[0][1][0])
                        self._refine_list_obj(e.obj, ot, new_type, scope)
            return NONE
        if m in ("index", "count"):
            return INT
        if strict:
            raise SemanticError(f"unknown list method '{m}'", e.line)
        return None

    def _refine_list_obj(self, obj_node, old_type, new_type, scope):
        """Refine the type of a list object (Name, Attribute, or Subscript) from old_type to new_type."""
        if isinstance(obj_node, A.Name):
            name = obj_node.name
            if name in scope and scope[name] == old_type:
                scope[name] = new_type
                self.changed = True
            elif name in self.global_types and self.global_types[name] == old_type:
                self.global_types[name] = new_type
                self.changed = True
            obj_node.type = new_type
        elif isinstance(obj_node, A.Subscript) and isinstance(obj_node.obj, A.Name) \
                and isinstance(obj_node.index, A.StringLit):
            # Refine per-key dict type: stats["key"] type updated.
            var_name = obj_node.obj.name
            if var_name in self.dict_key_types:
                prev = self.dict_key_types[var_name].get(obj_node.index.value)
                merged = self._merge_types(prev, new_type) if prev is not None else new_type
                if merged != prev:
                    self.dict_key_types[var_name][obj_node.index.value] = merged
                    self.changed = True
            obj_node.type = new_type
        elif isinstance(obj_node, A.Attribute):
            # Refine the attribute type on the class.
            ot = self._expr(obj_node.obj, scope, strict=False)
            if isinstance(ot, tuple) and ot[0] == "obj":
                class_name = ot[1]
                if class_name in self.classes:
                    attrs = self.classes[class_name]["attrs"]
                    prev = attrs.get(obj_node.attr)
                    if prev == old_type:
                        attrs[obj_node.attr] = new_type
                        self.changed = True
            obj_node.type = new_type

    def _binop_type(self, op, lt, rt, line):
        if lt is None or rt is None:
            return None
        # Treat NONE as an unknown type that yields to the other operand.
        if lt == NONE and rt == NONE:
            return NONE
        if lt == NONE:
            lt = rt  # assume NONE takes on the other operand's type
        if rt == NONE:
            rt = lt
        # String operations
        if op == "+":
            if lt == STR and rt == STR:
                return STR
            # List concatenation
            if isinstance(lt, tuple) and lt[0] == "list" and isinstance(rt, tuple) and rt[0] == "list":
                if lt[1] != rt[1] and not (numeric_base(lt[1]) == INT and numeric_base(rt[1]) == INT):
                    raise SemanticError(f"cannot concatenate lists of {lt[1]} and {rt[1]}", line)
                return ("list", lt[1])
            # Tuple concatenation
            if isinstance(lt, tuple) and lt[0] == "tuple" and isinstance(rt, tuple) and rt[0] == "tuple":
                return ("tuple", list(lt[1]) + list(rt[1]))
        if op == "*":
            if lt == STR and numeric_base(rt) == INT:
                return STR
            if rt == STR and numeric_base(lt) == INT:
                return STR
            # List repetition: list * int or int * list
            if isinstance(lt, tuple) and lt[0] == "list" and numeric_base(rt) == INT:
                return lt
            if isinstance(rt, tuple) and rt[0] == "list" and numeric_base(lt) == INT:
                return rt
            # Tuple repetition
            if isinstance(lt, tuple) and lt[0] == "tuple" and numeric_base(rt) == INT:
                return lt
            if isinstance(rt, tuple) and rt[0] == "tuple" and numeric_base(lt) == INT:
                return rt
        # Comparisons -> bool
        if op in ("==", "!=", "<", ">", "<=", ">=", "in", "not in"):
            return BOOL
        # Arithmetic
        if op in ("+", "-", "*", "/", "//", "%", "**"):
            b1 = numeric_base(lt)
            b2 = numeric_base(rt)
            if b1 is None or b2 is None:
                # Operands aren't numeric; be lenient (return None rather than erroring).
                return None
            if op == "/":
                return FLOAT
            if op == "//":
                return FLOAT if (b1 == FLOAT or b2 == FLOAT) else INT
            if op == "**":
                # int ** int with non-negative constant exponent -> int, else float
                return INT if (b1 == INT and b2 == INT) else FLOAT
            # +, -, *, %
            if b1 == FLOAT or b2 == FLOAT:
                return FLOAT
            return INT
        raise SemanticError(f"unknown operator '{op}'", line)

    def _resolve_call_name(self, name):
        """Resolve a function name, accounting for hoisted nested functions.
        When inside a method/nested function, a call to a short name may refer to
        a hoisted nested function with a mangled name like Enclosing__name."""
        if name in self.funcs:
            return name
        if self.cur_fn is not None:
            enc = self.cur_fn.name
            while enc is not None:
                candidate = enc + "__" + name
                if candidate in self.funcs:
                    return candidate
                enc_fn = self.funcs.get(enc)
                enc = enc_fn.enclosing_func if enc_fn else None
        return name

    def _call_type(self, e, scope, strict):
        # Resolve callable
        if isinstance(e.func, A.Attribute):
            # e.g., module.func(...) — treat as a method call on the module.
            return self._method_call_type(
                A.MethodCall(e.func.obj, e.func.attr, e.args, e.line, kwargs=e.kwargs),
                scope, strict)
        if not isinstance(e.func, A.Name):
            raise SemanticError("only direct function calls are supported", e.line)
        name = self._resolve_call_name(e.func.name)
        # __lambda__ is opaque: avoid evaluating its body (may have undefined names).
        if name == "__lambda__" or e.func.name == "__lambda__":
            return STR
        # Evaluate arg types, expanding Starred args.
        arg_types = []
        for a in e.args:
            if isinstance(a, A.Starred):
                st = self._expr(a.value, scope, strict)
                if isinstance(st, tuple) and st[0] == "tuple":
                    arg_types.extend(st[1])
                elif isinstance(st, tuple) and st[0] == "list":
                    arg_types.append(st[1])
                else:
                    arg_types.append(st)
            else:
                arg_types.append(self._expr(a, scope, strict))
        # Evaluate kwargs for side effects; also collect their types for constructors.
        kwarg_types = {}
        for k, v in (e.kwargs or {}).items():
            kwarg_types[k] = self._expr(v, scope, strict)

        # Constructor call: name is a user-defined class.
        if name in self.classes:
            self._set_init_param_types(name, arg_types, kwarg_types)
            return ("obj", name)
        # Constructor call for runtime classes referenced via imported name.
        if name == "Counter" or name == "deque":
            return ("obj", name)

        if name in self.funcs:
            fn = self.funcs[name]
            # Allow default arguments: missing trailing params are OK if they have defaults.
            has_starred = any(isinstance(a, A.Starred) for a in e.args)
            if not has_starred and len(arg_types) > len(fn.params):
                if strict:
                    raise SemanticError(
                        f"function '{name}' expects {len(fn.params)} args, got {len(arg_types)}", e.line)
            # Set param types from this call (monomorphic).
            for i, (p, at) in enumerate(zip(fn.params, arg_types)):
                if at is None or at == NONE:
                    # NONE/None args are "unknown" — don't constrain param type.
                    continue
                if fn.param_types[i] is None:
                    fn.param_types[i] = at
                    self.changed = True
                elif fn.param_types[i] != at:
                    # Allow NONE -> T refinement.
                    if fn.param_types[i] == NONE:
                        fn.param_types[i] = at
                        self.changed = True
                    elif strict:
                        raise SemanticError(
                            f"function '{name}' called with inconsistent type for "
                            f"parameter '{p}': {fn.param_types[i]} vs {at}", e.line)
            return fn.return_type
        if name in BUILTINS:
            return self._builtin_type(name, e, arg_types, strict)
        # Check if it's a variable holding a function reference (e.g., lambda)
        var_t = scope.get(name)
        if var_t is None:
            var_t = self.global_types.get(name)
        if isinstance(var_t, tuple) and var_t[0] == "func":
            fn_name = var_t[1]
            if fn_name in self.funcs:
                fn = self.funcs[fn_name]
                for i, (p, at) in enumerate(zip(fn.params, arg_types)):
                    if at is None or at == NONE:
                        continue
                    if i < len(fn.param_types):
                        if fn.param_types[i] is None or fn.param_types[i] == NONE:
                            fn.param_types[i] = at
                            self.changed = True
                return fn.return_type
        if strict:
            raise SemanticError(f"call to undefined function '{name}'", e.line)
        return None

    def _set_init_param_types(self, class_name, arg_types, kwarg_types):
        """Set __init__'s param types from a constructor call."""
        mangled = self.classes[class_name]["methods"].get("__init__")
        if mangled is None:
            return
        fn = self.funcs.get(mangled)
        if fn is None:
            return
        # First param is self (already set). Map positional args to params[1:].
        for i, at in enumerate(arg_types, start=1):
            if i >= len(fn.params):
                break
            if at is None:
                continue
            if fn.param_types[i] is None:
                fn.param_types[i] = at
                self.changed = True
            elif fn.param_types[i] != at and fn.param_types[i] == NONE:
                fn.param_types[i] = at
                self.changed = True
        # Map kwargs to params.
        for k, kt in kwarg_types.items():
            if k in fn.params:
                idx = fn.params.index(k)
                if kt is None:
                    continue
                if fn.param_types[idx] is None:
                    fn.param_types[idx] = kt
                    self.changed = True
                elif fn.param_types[idx] != kt and fn.param_types[idx] == NONE:
                    fn.param_types[idx] = kt
                    self.changed = True

    def _builtin_type(self, name, e, arg_types, strict):
        if name == "print":
            return NONE
        if name == "len":
            if strict and len(arg_types) != 1:
                raise SemanticError("len() expects a single argument", e.line)
            if strict and arg_types and arg_types[0] is not None and \
                    arg_types[0] != STR and not (isinstance(arg_types[0], tuple) and arg_types[0][0] in ("list", "tuple", "dict", "set", "obj")):
                raise SemanticError("len() expects a string, list, tuple, or dict argument", e.line)
            return INT
        if name == "abs":
            if strict and (len(arg_types) != 1 or arg_types[0] is None or numeric_base(arg_types[0]) is None):
                raise SemanticError("abs() expects a numeric argument", e.line)
            if arg_types and arg_types[0] is not None:
                b = numeric_base(arg_types[0])
                return INT if b == INT else FLOAT
            return None
        if name == "int":
            return INT
        if name == "float":
            return FLOAT
        if name == "str":
            return STR
        if name == "bool":
            return BOOL
        if name == "input":
            return STR
        if name == "range":
            return "range"
        if name in ("min", "max"):
            if arg_types:
                b = arg_types[0]
                return b
            return None
        if name == "sum":
            # sum of a list of ints -> int; list of floats -> float; default int.
            if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "list":
                et = arg_types[0][1]
                if et == FLOAT:
                    return FLOAT
                if et == INT or numeric_base(et) == INT:
                    return INT
                if et == NONE:
                    return INT
            return INT
        if name == "sorted":
            # sorted(list) -> list of same element type.
            if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "list":
                return arg_types[0]
            if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "dict":
                return ("list", arg_types[0][1])
            return ("list", NONE)
        if name == "enumerate":
            return "enumerate"
        if name in ("map", "filter"):
            # Basic support: return a list of the iterable's element type.
            if len(arg_types) >= 2 and isinstance(arg_types[1], tuple) and arg_types[1][0] == "list":
                return arg_types[1]
            return ("list", NONE)
        if name == "isinstance":
            return BOOL
        if name == "set":
            return ("obj", "set")
        if name == "dict":
            if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "dict":
                return arg_types[0]
            return ("dict", NONE, None)
        if name == "tuple":
            if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "list":
                return ("tuple", [arg_types[0][1]])
            if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "tuple":
                return arg_types[0]
            return ("tuple", [])
        if name == "list":
            # list(iterable) -> list of iterable's element type. We use NONE
            # for the element type to let the runtime determine it from the
            # actual values (which is what happens when we convert a pyobject
            # such as a numpy array to a native list).
            if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "list":
                return arg_types[0]
            if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "tuple":
                return ("list", arg_types[0][1][0] if arg_types[0][1] else NONE)
            if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "set":
                return ("list", arg_types[0][1])
            if arg_types and arg_types[0] == STR:
                return ("list", STR)
            return ("list", NONE)
        if name in ("deque", "Counter"):
            return ("obj", name)
        if name == "__lambda__":
            return STR
        if name == "hex" or name == "oct" or name == "bin" or name == "chr":
            return STR
        if name == "ord":
            return INT
        if name == "round":
            if arg_types:
                if arg_types[0] == FLOAT:
                    if len(arg_types) > 1 and arg_types[1] == INT:
                        return FLOAT
                    return INT
                return arg_types[0]
            return FLOAT
        if name == "divmod":
            return ("tuple", [INT, INT])
        if name == "repr" or name == "ascii" or name == "format":
            return STR
        if name == "any" or name == "all":
            return BOOL
        if name == "reversed":
            if arg_types and isinstance(arg_types[0], tuple) and arg_types[0][0] == "list":
                return arg_types[0]
            return ("list", NONE)
        if name == "zip":
            return ("list", ("tuple", [NONE]))
        if name == "id" or name == "hash":
            return INT
        if name == "callable" or name == "hasattr":
            return BOOL
        if name == "type":
            return STR
        if name == "open":
            return ("obj", "File")
        return None


def analyze(program, embed_mode=False):
    return Analyzer(program, embed_mode=embed_mode).analyze()
