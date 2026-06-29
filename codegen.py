"""LLVM IR code generator.

Converts the semantically-validated AST (with inferred `.type` on every
expression) into textual LLVM IR. The IR targets LLVM with opaque
pointers (LLVM >= 15); pointer types are written as `ptr`.

Type lowering:
    int   -> i64      float -> double     str -> ptr
    bool  -> i1       none -> i64 (placeholder); void return for none functions

Module-level (top-level) variables become LLVM globals so that functions
can read them. Function-local names become `alloca` slots.
"""

import struct
import ast_nodes as A
from semantic import INT, FLOAT, STR, BOOL, NONE


class CodeGenError(Exception):
    def __init__(self, msg, line=0):
        super().__init__(f"CodeGenError at line {line}: {msg}")
        self.line = line


RUNTIME_DECLS = """\
; ---- runtime declarations ----
declare ptr @py_str_concat(ptr, ptr)
declare ptr @py_str_empty()
declare ptr @py_str_mul(ptr, i64)
declare ptr @py_int_to_str(i64)
declare ptr @py_float_to_str(double)
declare ptr @py_input()
declare i64 @py_len(ptr)
declare i64 @py_int_parse(ptr)
declare double @py_float_parse(ptr)
declare i64 @py_ipow(i64, i64)
declare double @py_fpow(double, double)
declare i64 @py_ifloordiv(i64, i64)
declare i64 @py_imod(i64, i64)
declare double @py_idiv(i64, i64)
declare void @py_print_int(i64)
declare void @py_print_float(double)
declare void @py_print_str(ptr)
declare void @py_print_bool(i1)
declare void @py_print_none()
declare i64 @strlen(ptr)
declare i32 @strcmp(ptr, ptr)
declare ptr @strstr(ptr, ptr)
declare double @llvm.fabs.f64(double)
declare double @llvm.floor.f64(double)
declare double @llvm.pow.f64(double, double)
; ---- list runtime ----
declare ptr @py_list_new()
declare void @py_list_set_kind(ptr, i32)
declare void @py_list_append_int(ptr, i64)
declare void @py_list_append_float(ptr, double)
declare void @py_list_append_str(ptr, ptr)
declare void @py_list_append_list(ptr, ptr)
declare i64 @py_list_get_int(ptr, i64)
declare double @py_list_get_float(ptr, i64)
declare ptr @py_list_get_str(ptr, i64)
declare ptr @py_list_get_list(ptr, i64)
declare void @py_list_set_int(ptr, i64, i64)
declare void @py_list_set_float(ptr, i64, double)
declare void @py_list_set_str(ptr, i64, ptr)
declare void @py_list_set_list(ptr, i64, ptr)
declare i64 @py_list_len(ptr)
declare i64 @py_list_pop_int(ptr)
declare double @py_list_pop_float(ptr)
declare ptr @py_list_pop_str(ptr)
declare ptr @py_list_pop_list(ptr)
declare void @py_list_insert_int(ptr, i64, i64)
declare void @py_list_insert_float(ptr, i64, double)
declare void @py_list_insert_str(ptr, i64, ptr)
declare void @py_list_insert_list(ptr, i64, ptr)
declare i64 @py_list_index_int(ptr, i64)
declare ptr @py_list_index_str(ptr, ptr)
declare i64 @py_list_count_int(ptr, i64)
declare i64 @py_list_count_str(ptr, ptr)
declare void @py_list_print(ptr)
declare ptr @py_list_to_str(ptr)
; ---- list slicing / extend / pop_at ----
declare ptr @py_list_slice_int(ptr, i64, i64)
declare ptr @py_list_slice_float(ptr, i64, i64)
declare ptr @py_list_slice_str(ptr, i64, i64)
declare ptr @py_list_slice_list(ptr, i64, i64)
declare void @py_list_extend_int(ptr, ptr)
declare void @py_list_extend_float(ptr, ptr)
declare void @py_list_extend_str(ptr, ptr)
declare void @py_list_extend_list(ptr, ptr)
declare i64 @py_list_pop_at_int(ptr, i64)
declare double @py_list_pop_at_float(ptr, i64)
declare ptr @py_list_pop_at_str(ptr, i64)
declare ptr @py_list_pop_at_list(ptr, i64)
; ---- object operations ----
declare ptr @py_object_new(i32)
declare i64 @py_object_get_int(ptr, ptr)
declare double @py_object_get_float(ptr, ptr)
declare ptr @py_object_get_str(ptr, ptr)
declare i32 @py_object_get_bool(ptr, ptr)
declare ptr @py_object_get_list(ptr, ptr)
declare ptr @py_object_get_obj(ptr, ptr)
declare void @py_object_set_int(ptr, ptr, i64)
declare void @py_object_set_float(ptr, ptr, double)
declare void @py_object_set_str(ptr, ptr, ptr)
declare void @py_object_set_bool(ptr, ptr, i32)
declare void @py_object_set_list(ptr, ptr, ptr)
declare void @py_object_set_obj(ptr, ptr, ptr)
declare void @py_object_set_none(ptr, ptr)
declare i32 @py_object_is_none(ptr, ptr)
; ---- random / time / format ----
declare void @py_random_seed(i64)
declare i64 @py_random_randint(i64, i64)
declare i64 @py_random_choice_int(ptr)
declare ptr @py_random_choice_str(ptr)
declare double @py_random_random()
declare double @py_time_perf_counter()
declare ptr @py_format_int(i64, ptr)
declare ptr @py_format_float(double, ptr)
declare ptr @py_format_str(ptr, ptr)
declare ptr @py_str_lower(ptr)
declare ptr @py_str_upper(ptr)
declare ptr @py_str_replace(ptr, ptr, ptr)
declare i32 @py_str_startswith(ptr, ptr)
declare i32 @py_str_endswith(ptr, ptr)
declare i64 @py_str_find(ptr, ptr)
declare ptr @py_str_strip(ptr)
declare ptr @py_str_lstrip(ptr)
declare ptr @py_str_rstrip(ptr)
declare ptr @py_str_split(ptr, ptr)
declare ptr @py_str_split_ws(ptr)
declare void @py_list_sort_int(ptr)
declare void @py_list_sort_float(ptr)
declare void @py_list_sort_str(ptr)
; ---- threading / queue / regex ----
declare ptr @py_thread_new(ptr, i64)
declare void @py_thread_start(ptr)
declare void @py_thread_join(ptr)
declare ptr @py_lock_new()
declare void @py_lock_acquire(ptr)
declare void @py_lock_release(ptr)
declare ptr @py_event_new()
declare void @py_event_set(ptr)
declare i32 @py_event_is_set(ptr)
declare void @py_event_clear(ptr)
declare void @py_event_wait(ptr)
declare ptr @py_queue_new(i64)
declare void @py_queue_put(ptr, ptr)
declare ptr @py_queue_get(ptr, i64)
declare i64 @py_queue_size(ptr)
declare i32 @py_queue_empty(ptr)
declare void @py_queue_task_done(ptr)
declare void @py_queue_join(ptr)
declare ptr @py_queue_box_int(i64)
declare ptr @py_queue_box_float(double)
declare ptr @py_queue_box_str(ptr)
declare ptr @py_re_sub(ptr, ptr, ptr)
declare ptr @py_re_findall(ptr, ptr)
; ---- Counter ----
declare ptr @py_counter_new()
declare void @py_counter_update_list(ptr, ptr)
declare void @py_counter_update_counter(ptr, ptr)
declare ptr @py_counter_values(ptr)
declare i64 @py_counter_len(ptr)
declare ptr @py_counter_most_common(ptr, i64)
declare ptr @py_object_get_as_str(ptr, ptr)
; ---- set runtime ----
declare ptr @py_set_new()
declare void @py_set_add_int(ptr, i64)
declare void @py_set_add_str(ptr, ptr)
declare i32 @py_set_contains_int(ptr, i64)
declare i32 @py_set_contains_str(ptr, ptr)
declare i64 @py_set_len(ptr)
declare void @py_set_remove_int(ptr, i64)
declare void @py_set_remove_str(ptr, ptr)
declare ptr @py_set_to_list_int(ptr)
declare ptr @py_set_to_list_str(ptr)
; ---- dict methods ----
declare ptr @py_dict_keys(ptr)
declare ptr @py_dict_values(ptr)
declare ptr @py_dict_items(ptr)
declare i32 @py_dict_contains(ptr, ptr)
declare i64 @py_dict_get_int(ptr, ptr, i64)
declare double @py_dict_get_float(ptr, ptr, double)
declare ptr @py_dict_get_str(ptr, ptr, ptr)
declare ptr @py_dict_get_obj(ptr, ptr, ptr)
; ---- math module ----
declare double @py_math_sqrt(double)
declare double @py_math_pow(double, double)
declare double @py_math_log(double)
declare double @py_math_log2(double)
declare double @py_math_log10(double)
declare double @py_math_sin(double)
declare double @py_math_cos(double)
declare double @py_math_tan(double)
declare double @py_math_floor(double)
declare double @py_math_ceil(double)
declare double @py_math_fabs(double)
declare double @py_math_exp(double)
declare i64 @py_math_gcd(i64, i64)
declare i64 @py_math_lcm(i64, i64)
declare double @py_math_pi()
declare double @py_math_e()
declare double @py_math_inf()
declare double @py_math_nan()
; ---- exception handling ----
declare void @py_exc_push()
declare i32 @py_exc_catch()
declare void @py_exc_pop()
declare ptr @py_exc_msg()
declare i32 @py_exc_kind()
declare void @py_exc_raise(i32, ptr)
declare void @py_exc_raise_value(ptr)
declare void @py_exc_raise_type(ptr)
declare void @py_exc_raise_zerodiv(ptr)
declare void @py_exc_raise_key(ptr)
declare void @py_exc_raise_index(ptr)
declare void @py_exc_raise_stopiter()
; ---- more string methods ----
declare ptr @py_str_ljust(ptr, i64, ptr)
declare ptr @py_str_rjust(ptr, i64, ptr)
declare ptr @py_str_center(ptr, i64, ptr)
declare ptr @py_str_zfill(ptr, i64)
declare ptr @py_str_title(ptr)
declare ptr @py_str_capitalize(ptr)
declare ptr @py_str_swapcase(ptr)
declare ptr @py_str_removeprefix(ptr, ptr)
declare ptr @py_str_removesuffix(ptr, ptr)
declare i64 @py_str_count(ptr, ptr)
; ---- more builtins ----
declare ptr @py_hex(i64)
declare ptr @py_oct(i64)
declare ptr @py_bin(i64)
declare i64 @py_ord(ptr)
declare ptr @py_chr(i64)
declare double @py_round(double, i64)
declare i64 @py_round_int(double)
declare void @py_divmod(i64, i64, ptr, ptr)
; ---- string module constants ----
declare ptr @py_string_ascii_letters()
declare ptr @py_string_ascii_lowercase()
declare ptr @py_string_ascii_uppercase()
declare ptr @py_string_digits()
declare ptr @py_string_hexdigits()
declare ptr @py_string_octdigits()
declare ptr @py_string_punctuation()
declare ptr @py_string_whitespace()
; ---- iterator support ----
declare ptr @py_iter_list(ptr)
declare ptr @py_iter_str(ptr)
declare ptr @py_iter_range(i64, i64, i64)
declare i32 @py_iter_has_next(ptr)
declare i64 @py_iter_next_int(ptr)
declare ptr @py_iter_next_str(ptr)
"""


def is_list_type(t):
    return isinstance(t, tuple) and t[0] == "list"


def is_obj_type(t):
    return isinstance(t, tuple) and t[0] == "obj"


def is_tuple_type(t):
    return isinstance(t, tuple) and t[0] == "tuple"


def is_module_type(t):
    return isinstance(t, tuple) and t[0] in ("module", "module_attr", "class", "func", "builtin", "method")


def list_elem_type(t):
    return t[1] if is_list_type(t) else None


def list_kind_tag(elem_type):
    """Map an element type to the runtime kind tag (matches enum in runtime.c)."""
    if is_list_type(elem_type):
        return 4  # LE_LIST
    if is_obj_type(elem_type):
        return 4  # treat object elements like list ptrs
    if is_tuple_type(elem_type):
        return 4  # tuples are stored as list ptrs
    if isinstance(elem_type, tuple):
        return 4  # any other tuple type (dict, etc.) -> stored as ptr
    return {"int": 0, "bool": 3, "float": 1, "str": 2, "none": 0}.get(elem_type, 0)


def llvm_type(t):
    if isinstance(t, tuple):
        # list, obj, tuple, dict, module, etc. all lower to ptr
        return "ptr"
    return {"int": "i64", "float": "double", "str": "ptr",
            "bool": "i1", "none": "i64"}.get(t, "i64")


def ret_llvm_type(t):
    return "void" if t == NONE else llvm_type(t)


def zero_value(t):
    if isinstance(t, tuple):
        return "null"
    return {"int": "0", "float": "0.0", "bool": "false",
            "str": "null", "none": "0"}.get(t, "0")


def numeric_base(t):
    if t == BOOL:
        return INT
    if t in (INT, FLOAT):
        return t
    return None


def float_hex(value):
    """IEEE-754 double as an LLVM hex literal, e.g. 0x40091eb851eb851f."""
    if value != value:  # nan
        return "0x7ff8000000000000"
    if value == float("inf"):
        return "0x7ff0000000000000"
    if value == float("-inf"):
        return "0xfff0000000000000"
    return "0x" + struct.pack(">d", value).hex()


def escape_llvm_bytes(raw):
    """Escape a bytes object for an LLVM c"..." constant."""
    out = []
    for b in raw:
        if 32 <= b <= 126 and b not in (0x22, 0x5C):  # not " or backslash
            out.append(chr(b))
        else:
            out.append("\\%02X" % b)
    return "".join(out)


class CodeGen:
    def __init__(self, info):
        self.funcs = info["funcs"]
        self.func_names = set(info["funcs"].keys())
        self.top_stmts = info["top_stmts"]
        self.global_types = info["globals"]
        self.classes = info.get("classes", {})
        # Assign class IDs: sort class names alphabetically, assign 0,1,2,...
        self.class_ids = {}
        for idx, cname in enumerate(sorted(self.classes.keys())):
            self.class_ids[cname] = idx
        self.string_pool = {}      # content -> global name
        self.string_counter = 0
        self.global_defs = []      # global var + string constant definitions
        self.chunks = []           # finished function bodies (strings)
        self.body = []             # current function body lines
        self.counter = 0
        self.label_counter = 0
        self.locals = {}           # name -> (ptr_or_global, type, is_global)
        self.func_sigs = {}
        self.loop_stack = []       # list of (continue_label, break_label)
        self.terminated = False
        self.current_label = None
        self.current_fn_ret = None
        self.current_fn_name = None
        self.in_main = False

    # ---- emission helpers ----
    def fresh(self, prefix="t"):
        self.counter += 1
        return f"%{prefix}.{self.counter}"

    def fresh_label(self, prefix="L"):
        self.label_counter += 1
        return f"{prefix}.{self.label_counter}"

    def emit(self, line):
        if self.terminated:
            return  # dead code after a terminator
        self.body.append("  " + line)

    def emit_term(self, line):
        if self.terminated:
            return
        self.body.append("  " + line)
        self.terminated = True

    def place_block(self, label):
        self.body.append(f"{label}:")
        self.terminated = False
        self.current_label = label

    def br(self, label):
        self.emit_term(f"br label %{label}")

    def cbr(self, cond, tlabel, flabel):
        self.emit_term(f"br i1 {cond}, label %{tlabel}, label %{flabel}")

    def entry_alloca_index(self):
        for i, line in enumerate(self.body):
            if line.strip() == "entry:":
                return i + 1
        return len(self.body)

    def insert_alloca(self, line):
        self.body.insert(self.entry_alloca_index(), "  " + line)

    def void_result(self):
        """Return a void result (for statements that produce no value)."""
        return "0", NONE

    def null_ptr(self):
        return "null", NONE

    # ---- string interning ----
    def intern_string(self, content):
        if content in self.string_pool:
            return self.string_pool[content]
        name = f"@.str.{self.string_counter}"
        self.string_counter += 1
        raw = content.encode("utf-8") + b"\x00"
        self.global_defs.append(
            f'{name} = private unnamed_addr constant [{len(raw)} x i8] c"{escape_llvm_bytes(raw)}"'
        )
        self.string_pool[content] = name
        return name

    # ---- module generation ----
    def generate(self):
        # Pre-intern common strings.
        self.intern_string(" ")
        self.intern_string("\n")
        self.intern_string("True")
        self.intern_string("False")
        self.intern_string("None")

        # Emit global variable definitions (top-level vars).
        for vname, vtype in self.global_types.items():
            self.global_defs.append(f"@g_{vname} = global {llvm_type(vtype)} {zero_value(vtype)}")

        for name, fn in self.funcs.items():
            self.gen_function(fn)
        self.gen_main()

        parts = ["; Module generated by pycompiler\n", RUNTIME_DECLS,
                 "\n; ---- string constants and global variables ----\n",
                 "\n".join(self.global_defs),
                 "\n\n; ---- functions ----\n",
                 "\n\n".join(self.chunks)]
        return "\n".join(parts) + "\n"

    def _start_function(self):
        self.body = []
        self.counter = 0
        self.label_counter = 0
        self.terminated = False
        self.locals = {}

    def gen_function(self, fn):
        self._start_function()
        self.current_fn_ret = fn.return_type
        self.current_fn_name = fn.name
        self.in_main = False
        retty = ret_llvm_type(fn.return_type)
        params = [f"{llvm_type(pt)} noundef %arg_{p}" for p, pt in zip(fn.params, fn.param_types)]
        self.body.append(f"define {retty} @fn_{fn.name}({', '.join(params)}) {{")
        self.place_block("entry")
        # Module globals are visible for read access from functions; a name
        # declared `global` and assigned here also writes through the global.
        # Add globals first so params/locals shadow them.
        for vname, vtype in self.global_types.items():
            self.locals[vname] = (f"@g_{vname}", vtype, True)
        for p, pt in zip(fn.params, fn.param_types):
            slot = self.fresh(f"var_{p}")
            self.insert_alloca(f"{slot} = alloca {llvm_type(pt)}")
            self.emit(f"store {llvm_type(pt)} %arg_{p}, ptr {slot}")
            self.locals[p] = (slot, pt, False)
        for vname, vtype in fn.local_types.items():
            if vname in fn.params or vtype is None:
                continue
            slot = self.fresh(f"var_{vname}")
            self.insert_alloca(f"{slot} = alloca {llvm_type(vtype)}")
            self.locals[vname] = (slot, vtype, False)
        for s in fn.defn.body:
            self.gen_stmt(s)
        if not self.terminated:
            self.emit_default_ret()
        self.body.append("}")
        self.chunks.append("\n".join(self.body))

    def emit_default_ret(self):
        rt = self.current_fn_ret
        if rt is None or rt == NONE:
            self.emit_term("ret void")
        else:
            self.emit_term(f"ret {llvm_type(rt)} {zero_value(rt)}")

    def gen_main(self):
        self._start_function()
        self.current_fn_ret = "int"
        self.in_main = True
        self.body.append("define i32 @main() {")
        self.place_block("entry")
        for vname, vtype in self.global_types.items():
            self.locals[vname] = (f"@g_{vname}", vtype, True)
        for s in self.top_stmts:
            self.gen_stmt(s)
        if not self.terminated:
            self.emit_term("ret i32 0")
        self.body.append("}")
        self.chunks.append("\n".join(self.body))

    # ---- variable access ----
    def load_var(self, name, line=0):
        # A bare function name used as a value (e.g. target=consumer) yields
        # its function pointer. Module/builtin names are opaque.
        if name not in self.locals:
            resolved = self._resolve_call_name(name)
            if resolved in self.funcs:
                return f"@fn_{resolved}", ("func", resolved)
            if name in self.funcs:
                return f"@fn_{name}", ("func", name)
            raise CodeGenError(f"undefined variable '{name}'", line)
        slot, vtype, is_global = self.locals[name]
        if vtype is None:
            raise CodeGenError(f"variable '{name}' has no type", line)
        if vtype == NONE:
            return "0", NONE
        r = self.fresh()
        self.emit(f"{r} = load {llvm_type(vtype)}, ptr {slot}")
        return r, vtype

    def store_var(self, name, value, vtype, line=0):
        if name not in self.locals:
            raise CodeGenError(f"cannot assign to undeclared variable '{name}'", line)
        slot, slot_type, is_global = self.locals[name]
        target_type = slot_type if slot_type is not None else vtype
        val = self.coerce(value, vtype, target_type)
        self.emit(f"store {llvm_type(target_type)} {val}, ptr {slot}")

    def _ensure_local(self, name, vtype):
        """Ensure a local variable has an alloca slot (for comprehension vars
        that the semantic analyzer may not have pre-declared)."""
        if name not in self.locals:
            slot = self.fresh(f"var_{name}")
            self.insert_alloca(f"{slot} = alloca {llvm_type(vtype)}")
            self.locals[name] = (slot, vtype, False)

    # ---- statements ----
    def gen_stmt(self, s):
        if isinstance(s, A.ExprStmt):
            self.gen_expr(s.expr)
        elif isinstance(s, A.Assign):
            self.gen_assign(s)
        elif isinstance(s, A.AugAssign):
            self.gen_augassign(s)
        elif isinstance(s, A.Return):
            if self.in_main:
                self.emit_term("ret i32 0")
                return
            if self.current_fn_ret == NONE or s.value is None:
                self.emit_term("ret void")
                return
            val, vt = self.gen_expr(s.value)
            val = self.coerce(val, vt, self.current_fn_ret)
            self.emit_term(f"ret {llvm_type(self.current_fn_ret)} {val}")
        elif isinstance(s, A.Break):
            if not self.loop_stack:
                raise CodeGenError("break outside loop", s.line)
            self.br(self.loop_stack[-1][1])
        elif isinstance(s, A.Continue):
            if not self.loop_stack:
                raise CodeGenError("continue outside loop", s.line)
            self.br(self.loop_stack[-1][0])
        elif isinstance(s, (A.Pass, A.Global, A.Import, A.ImportFrom, A.ClassDef,
                            A.FuncDef)):
            # Imports are no-ops (names already resolved by semantic analyzer).
            # ClassDef/FuncDef are hoisted to top-level by the semantic analyzer.
            pass
        elif isinstance(s, A.Raise):
            self.gen_raise(s)
            return
        elif isinstance(s, A.If):
            self.gen_if(s)
        elif isinstance(s, A.While):
            self.gen_while(s)
        elif isinstance(s, A.For):
            self.gen_for(s)
        elif isinstance(s, A.With):
            self.gen_with(s)
        elif isinstance(s, A.Try):
            self.gen_try(s)
        else:
            raise CodeGenError(f"unhandled statement {type(s).__name__}", s.line)

    def gen_assign(self, s):
        target = s.target
        # Tuple unpacking: a, b = value
        if isinstance(target, A.TupleLit):
            self.gen_tuple_unpack(target, s.value, s.line)
            return
        val, vt = self.gen_expr(s.value)
        if isinstance(target, A.Subscript):
            self.gen_subscript_assign(target, val, vt, s.line)
        elif isinstance(target, A.Attribute):
            self.gen_attr_assign(target, val, vt, s.line)
        else:
            self.store_var(target.name, val, vt, s.line)
            # For list values, ensure the kind tag matches the variable's
            # declared (possibly refined) type, e.g. [] later refined to
            # list-of-list via append.
            slot, slot_type, _ = self.locals[target.name]
            if is_list_type(slot_type):
                self.emit(f"call void @py_list_set_kind(ptr {val}, i32 {list_kind_tag(list_elem_type(slot_type))})")

    def gen_augassign(self, s):
        target = s.target
        if isinstance(target, A.Subscript):
            cur, ct = self.gen_subscript(target)
            rval, rt = self.gen_expr(s.value)
            res, rest = self.gen_binop(s.op, cur, ct, rval, rt, ct, s.line)
            self.gen_subscript_assign(target, res, rest, s.line)
        elif isinstance(target, A.Attribute):
            cur, ct = self.gen_attr_get(target)
            rval, rt = self.gen_expr(s.value)
            res, rest = self.gen_binop(s.op, cur, ct, rval, rt, ct, s.line)
            self.gen_attr_assign(target, res, rest, s.line)
        else:
            cur, ct = self.load_var(target.name, s.line)
            rval, rt = self.gen_expr(s.value)
            if s.op == "**":
                if numeric_base(ct) == INT and numeric_base(rt) == INT:
                    a = self.coerce(cur, ct, INT)
                    b = self.coerce(rval, rt, INT)
                    r = self.fresh()
                    self.emit(f"{r} = call i64 @py_ipow(i64 {a}, i64 {b})")
                    self.store_var(target.name, r, INT, s.line)
                else:
                    cur_f = self.coerce(cur, ct, FLOAT)
                    val_f = self.coerce(rval, rt, FLOAT)
                    r = self.fresh()
                    self.emit(f"{r} = call double @py_fpow(double {cur_f}, double {val_f})")
                    self.store_var(target.name, r, FLOAT, s.line)
                return
            res, rest = self.gen_binop(s.op, cur, ct, rval, rt, ct, s.line)
            self.store_var(target.name, res, rest, s.line)

    def gen_tuple_unpack(self, target, value, line):
        """Handle a, b = value where target is a TupleLit."""
        targets = target.elements
        # If RHS is also a TupleLit, evaluate each element directly.
        if isinstance(value, A.TupleLit):
            vals = [self.gen_expr(el) for el in value.elements]
            for t, (v, vt) in zip(targets, vals):
                if isinstance(t, A.Name):
                    self.store_var(t.name, v, vt, line)
                elif isinstance(t, A.Subscript):
                    self.gen_subscript_assign(t, v, vt, line)
                elif isinstance(t, A.Attribute):
                    self.gen_attr_assign(t, v, vt, line)
            return
        # Otherwise, the RHS evaluates to a list/tuple ptr; index into it.
        rv, rt = self.gen_expr(value)
        # Determine the element type. For ("tuple", [t1, t2, ...]) use per-index;
        # for ("list", et) use et for all.
        elem_types = None
        if is_tuple_type(rt):
            elem_types = rt[1]
        for i, t in enumerate(targets):
            et = elem_types[i] if (elem_types and i < len(elem_types)) else \
                 (list_elem_type(rt) if is_list_type(rt) else NONE)
            ev = self._list_get_typed(rv, i, et, line)
            if isinstance(t, A.Name):
                self.store_var(t.name, ev, et, line)
            elif isinstance(t, A.Subscript):
                self.gen_subscript_assign(t, ev, et, line)
            elif isinstance(t, A.Attribute):
                self.gen_attr_assign(t, ev, et, line)

    def _list_get_typed(self, list_ptr, idx, elem_type, line):
        """Get element at idx from a list/tuple ptr with the given element type."""
        idx_lit = str(idx)
        if elem_type == INT or elem_type == BOOL:
            r = self.fresh()
            self.emit(f"{r} = call i64 @py_list_get_int(ptr {list_ptr}, i64 {idx_lit})")
            if elem_type == BOOL:
                b = self.fresh()
                self.emit(f"{b} = trunc i64 {r} to i1")
                return b
            return r
        if elem_type == FLOAT:
            r = self.fresh()
            self.emit(f"{r} = call double @py_list_get_float(ptr {list_ptr}, i64 {idx_lit})")
            return r
        if elem_type == STR:
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_list_get_str(ptr {list_ptr}, i64 {idx_lit})")
            return r
        if is_list_type(elem_type) or is_obj_type(elem_type) or is_tuple_type(elem_type):
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_list_get_list(ptr {list_ptr}, i64 {idx_lit})")
            return r
        if elem_type == NONE or elem_type is None:
            # Unknown element type: read as i64 (runtime stores all elements
            # in a 64-bit union; i64 and ptr are interchangeable via inttoptr).
            r = self.fresh()
            self.emit(f"{r} = call i64 @py_list_get_int(ptr {list_ptr}, i64 {idx_lit})")
            return r
        # Fallback: read as int ptr (object/none).
        r = self.fresh()
        self.emit(f"{r} = call ptr @py_list_get_list(ptr {list_ptr}, i64 {idx_lit})")
        return r

    def gen_with(self, s):
        """with ctx as var: body — acquire/release the context manager."""
        ctx_ptrs = []
        for ctx_expr, var in s.items:
            cv, ct = self.gen_expr(ctx_expr)
            ctx_ptrs.append((cv, ct))
            if var is not None:
                self.store_var(var, cv, ct, s.line)
            # Acquire: if it's a Lock, call py_lock_acquire; otherwise no-op.
            if is_obj_type(ct) and ct[1] == "Lock":
                self.emit(f"call void @py_lock_acquire(ptr {cv})")
        for st in s.body:
            self.gen_stmt(st)
        for cv, ct in ctx_ptrs:
            if is_obj_type(ct) and ct[1] == "Lock":
                self.emit(f"call void @py_lock_release(ptr {cv})")

    def gen_try(self, s):
        """try/except — flag-based exception handling."""
        self.emit("call void @py_exc_push()")

        end_label = self.fresh_label("tryend")
        handler_label = self.fresh_label("handler")

        # Generate try body, checking for exception after each statement
        for st in s.body:
            self.gen_stmt(st)
            if self.terminated:
                break
            # Check if an exception was raised
            caught = self.fresh()
            self.emit(f"{caught} = call i32 @py_exc_catch()")
            has_exc = self.fresh()
            self.emit(f"{has_exc} = icmp ne i32 {caught}, 0")
            no_exc = self.fresh_label("no_exc")
            self.cbr(has_exc, handler_label, no_exc)
            self.place_block(no_exc)

        if not self.terminated:
            # No exception - pop and continue
            self.emit("call void @py_exc_pop()")
            self.br(end_label)

        # Exception handler
        self.place_block(handler_label)
        for exc_type, name, hb in s.handlers:
            if name:
                msg = self.fresh()
                self.emit(f"{msg} = call ptr @py_exc_msg()")
                self.store_var(name, msg, STR, s.line)
            for st in hb:
                self.gen_stmt(st)
                if self.terminated:
                    break
            if not self.terminated:
                break

        if not self.terminated:
            self.emit("call void @py_exc_pop()")
            self.br(end_label)

        self.place_block(end_label)

    def gen_raise(self, s):
        """raise Exception("msg") — raise an exception."""
        if s.exc is None:
            # re-raise
            self.emit("call void @py_exc_raise(i32 1, ptr null)")
            return
        val, vtype = self.gen_expr(s.exc)
        # If it's a string, raise ValueError
        if vtype == STR:
            self.emit(f"call void @py_exc_raise_value(ptr {val})")
        elif is_obj_type(vtype):
            # Get the exception message - for simplicity, raise with kind 1
            self.emit(f"call void @py_exc_raise(i32 1, ptr null)")
        else:
            self.emit(f"call void @py_exc_raise(i32 1, ptr null)")

    def gen_if(self, s):
        end_label = self.fresh_label("if.end")
        n = len(s.branches)
        for i, (cond, body) in enumerate(s.branches):
            cv, ct = self.gen_expr(cond)
            cb = self.to_bool(cv, ct)
            then_label = self.fresh_label("if.then")
            if i < n - 1:
                else_label = self.fresh_label("if.next")
            elif s.orelse:
                else_label = self.fresh_label("if.else")
            else:
                else_label = end_label
            self.cbr(cb, then_label, else_label)
            self.place_block(then_label)
            for st in body:
                self.gen_stmt(st)
            if not self.terminated:
                self.br(end_label)
            if i < n - 1:
                self.place_block(else_label)  # becomes next elif's condition block
                continue
            if s.orelse:
                self.place_block(else_label)
                for st in s.orelse:
                    self.gen_stmt(st)
                if not self.terminated:
                    self.br(end_label)
        self.place_block(end_label)

    def gen_while(self, s):
        cond_label = self.fresh_label("while.cond")
        body_label = self.fresh_label("while.body")
        cont_label = self.fresh_label("while.cont")
        else_label = self.fresh_label("while.else") if s.orelse else None
        end_label = self.fresh_label("while.end")
        self.br(cond_label)
        self.place_block(cond_label)
        cv, ct = self.gen_expr(s.cond)
        cb = self.to_bool(cv, ct)
        self.cbr(cb, body_label, else_label if s.orelse else end_label)
        self.place_block(body_label)
        self.loop_stack.append((cont_label, end_label))
        for st in s.body:
            self.gen_stmt(st)
        self.loop_stack.pop()
        if not self.terminated:
            self.br(cont_label)
        self.place_block(cont_label)
        self.br(cond_label)
        if s.orelse:
            self.place_block(else_label)
            for st in s.orelse:
                self.gen_stmt(st)
            if not self.terminated:
                self.br(end_label)
        self.place_block(end_label)

    def _for_single_var(self, s):
        """Return the single loop variable name if s.var is a single-target list, else None."""
        if isinstance(s.var, list) and len(s.var) == 1 and isinstance(s.var[0], str):
            return s.var[0]
        if isinstance(s.var, str):
            return s.var
        return None

    def _store_for_target(self, var_target, value, val_type, line):
        """Store an iteration value into the for-loop target(s).
        var_target is a string, a list of strings, or a nested list."""
        if isinstance(var_target, str):
            self.store_var(var_target, value, val_type, line)
            return
        if isinstance(var_target, list):
            # Tuple unpacking: value is a list/tuple ptr; index into it.
            # Determine element types from val_type if it's a tuple.
            elem_types = None
            if is_tuple_type(val_type):
                elem_types = val_type[1]
            elif is_list_type(val_type):
                elem_types = None  # use list elem type per-index isn't known
            for i, vt in enumerate(var_target):
                et = elem_types[i] if (elem_types and i < len(elem_types)) else \
                     (list_elem_type(val_type) if is_list_type(val_type) else NONE)
                ev = self._list_get_typed(value, i, et, line)
                self._store_for_target(vt, ev, et, line)

    def gen_for(self, s):
        it = s.iterable
        # enumerate(iterable): special loop with an index counter.
        if isinstance(it, A.Call) and isinstance(it.func, A.Name) and it.func.name == "enumerate":
            self.gen_for_enumerate(s)
            return
        if isinstance(it, A.Call) and isinstance(it.func, A.Name) and it.func.name == "range":
            args = it.args
            if len(args) == 1:
                stop_val, stop_t = self.gen_expr(args[0])
                start, stop, step = "0", self.coerce(stop_val, stop_t, INT), "1"
            elif len(args) == 2:
                sv, st0 = self.gen_expr(args[0])
                ev, et0 = self.gen_expr(args[1])
                start, stop, step = self.coerce(sv, st0, INT), self.coerce(ev, et0, INT), "1"
            elif len(args) == 3:
                sv, st0 = self.gen_expr(args[0])
                ev, et0 = self.gen_expr(args[1])
                tv, tt0 = self.gen_expr(args[2])
                start = self.coerce(sv, st0, INT)
                stop = self.coerce(ev, et0, INT)
                step = self.coerce(tv, tt0, INT)
            else:
                raise CodeGenError("range() expects 1-3 arguments", s.line)
            var_name = self._for_single_var(s)
            if var_name is None:
                raise CodeGenError("range loop requires a single variable", s.line)
            self.store_var(var_name, start, INT, s.line)
            cond_label = self.fresh_label("for.cond")
            body_label = self.fresh_label("for.body")
            cont_label = self.fresh_label("for.cont")
            else_label = self.fresh_label("for.else") if s.orelse else None
            end_label = self.fresh_label("for.end")
            self.br(cond_label)
            self.place_block(cond_label)
            cur, _ = self.load_var(var_name, s.line)
            cmp_pos = self.fresh()
            self.emit(f"{cmp_pos} = icmp slt i64 {cur}, {stop}")
            cmp_neg = self.fresh()
            self.emit(f"{cmp_neg} = icmp sgt i64 {cur}, {stop}")
            pos = self.fresh()
            self.emit(f"{pos} = icmp sgt i64 {step}, 0")
            cmp = self.fresh()
            self.emit(f"{cmp} = select i1 {pos}, i1 {cmp_pos}, i1 {cmp_neg}")
            self.cbr(cmp, body_label, else_label if s.orelse else end_label)
            self.place_block(body_label)
            self.loop_stack.append((cont_label, end_label))
            for st in s.body:
                self.gen_stmt(st)
            self.loop_stack.pop()
            if not self.terminated:
                self.br(cont_label)
            self.place_block(cont_label)
            cur2, _ = self.load_var(var_name, s.line)
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {cur2}, {step}")
            self.store_var(var_name, nxt, INT, s.line)
            self.br(cond_label)
            if s.orelse:
                self.place_block(else_label)
                for st in s.orelse:
                    self.gen_stmt(st)
                if not self.terminated:
                    self.br(end_label)
            self.place_block(end_label)
            return
        # Iterate over a string: for ch in s
        if getattr(it, "type", None) == STR:
            str_val, _ = self.gen_expr(it)
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @strlen(ptr {str_val})")
            idx_slot = self.fresh()
            self.insert_alloca(f"{idx_slot} = alloca i64")
            self.emit(f"store i64 0, ptr {idx_slot}")
            cond_label = self.fresh_label("for.cond")
            body_label = self.fresh_label("for.body")
            cont_label = self.fresh_label("for.cont")
            end_label = self.fresh_label("for.end")
            self.br(cond_label)
            self.place_block(cond_label)
            ci = self.fresh()
            self.emit(f"{ci} = load i64, ptr {idx_slot}")
            cmp = self.fresh()
            self.emit(f"{cmp} = icmp slt i64 {ci}, {lenr}")
            self.cbr(cmp, body_label, end_label)
            self.place_block(body_label)
            ptr = self.fresh()
            self.emit(f"{ptr} = getelementptr inbounds i8, ptr {str_val}, i64 {ci}")
            ch = self.fresh()
            self.emit(f"{ch} = load i8, ptr {ptr}")
            buf = self.fresh()
            self.insert_alloca(f"{buf} = alloca [2 x i8]")
            self.emit(f"store i8 {ch}, ptr {buf}")
            self.emit(f"store i8 0, ptr {self._gep_byte(buf)}")
            var_name = self._for_single_var(s)
            if var_name is None:
                raise CodeGenError("string loop requires a single variable", s.line)
            self.store_var(var_name, buf, STR, s.line)
            self.loop_stack.append((cont_label, end_label))
            for st in s.body:
                self.gen_stmt(st)
            self.loop_stack.pop()
            if not self.terminated:
                self.br(cont_label)
            self.place_block(cont_label)
            ci2 = self.fresh()
            self.emit(f"{ci2} = load i64, ptr {idx_slot}")
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {ci2}, 1")
            self.emit(f"store i64 {nxt}, ptr {idx_slot}")
            self.br(cond_label)
            self.place_block(end_label)
            return
        # Iterate over a list/tuple: for x in lst (with optional tuple unpacking)
        it_type = getattr(it, "type", None)
        if is_list_type(it_type) or is_tuple_type(it_type):
            lv, _ = self.gen_expr(it)
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @py_list_len(ptr {lv})")
            idx_slot = self.fresh()
            self.insert_alloca(f"{idx_slot} = alloca i64")
            self.emit(f"store i64 0, ptr {idx_slot}")
            cond_label = self.fresh_label("for.cond")
            body_label = self.fresh_label("for.body")
            cont_label = self.fresh_label("for.cont")
            else_label = self.fresh_label("for.else") if s.orelse else None
            end_label = self.fresh_label("for.end")
            self.br(cond_label)
            self.place_block(cond_label)
            ci = self.fresh()
            self.emit(f"{ci} = load i64, ptr {idx_slot}")
            cmp = self.fresh()
            self.emit(f"{cmp} = icmp slt i64 {ci}, {lenr}")
            self.cbr(cmp, body_label, else_label if s.orelse else end_label)
            self.place_block(body_label)
            et = list_elem_type(it_type) if is_list_type(it_type) else NONE
            if is_tuple_type(it_type):
                # Iterating over a tuple of tuples: each element is itself a tuple/list.
                et = it_type  # the tuple type itself (elements are tuples)
            var_name = self._for_single_var(s)
            if var_name is not None:
                ev = self._list_get_typed(lv, ci, et, s.line)
                self.store_var(var_name, ev, et, s.line)
            else:
                # Tuple unpacking: get the element (a list/tuple ptr) and unpack.
                ev = self._list_get_typed(lv, ci, et, s.line)
                self._store_for_target(s.var, ev, et, s.line)
            self.loop_stack.append((cont_label, end_label))
            for st in s.body:
                self.gen_stmt(st)
            self.loop_stack.pop()
            if not self.terminated:
                self.br(cont_label)
            self.place_block(cont_label)
            ci2 = self.fresh()
            self.emit(f"{ci2} = load i64, ptr {idx_slot}")
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {ci2}, 1")
            self.emit(f"store i64 {nxt}, ptr {idx_slot}")
            self.br(cond_label)
            if s.orelse:
                self.place_block(else_label)
                for st in s.orelse:
                    self.gen_stmt(st)
                if not self.terminated:
                    self.br(end_label)
            self.place_block(end_label)
            return
        raise CodeGenError("for-loops only support range(), string, or list iteration", s.line)

    def gen_for_enumerate(self, s):
        """for i, x in enumerate(iterable[, start]): — index counter + element."""
        it = s.iterable
        inner = it.args[0]
        inner_type = getattr(inner, "type", None)
        # Determine the element type yielded by the inner iterable.
        elem_t = list_elem_type(inner_type) if is_list_type(inner_type) else \
                 (STR if inner_type == STR else NONE)
        # Optional start argument (default 0).
        start_val = "0"
        if len(it.args) >= 2:
            sv, st = self.gen_expr(it.args[1])
            start_val = self.coerce(sv, st, INT)
        # List index slot (always starts at 0).
        list_idx_slot = self.fresh()
        self.insert_alloca(f"{list_idx_slot} = alloca i64")
        self.emit(f"store i64 0, ptr {list_idx_slot}")
        # Enumerate value slot (starts at start_val).
        enum_slot = self.fresh()
        self.insert_alloca(f"{enum_slot} = alloca i64")
        self.emit(f"store i64 {start_val}, ptr {enum_slot}")
        if is_list_type(inner_type):
            lv, _ = self.gen_expr(inner)
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @py_list_len(ptr {lv})")
            cond_label = self.fresh_label("for.cond")
            body_label = self.fresh_label("for.body")
            cont_label = self.fresh_label("for.cont")
            end_label = self.fresh_label("for.end")
            self.br(cond_label)
            self.place_block(cond_label)
            ci = self.fresh()
            self.emit(f"{ci} = load i64, ptr {list_idx_slot}")
            cmp = self.fresh()
            self.emit(f"{cmp} = icmp slt i64 {ci}, {lenr}")
            self.cbr(cmp, body_label, end_label)
            self.place_block(body_label)
            # i = enum value, x = list[ci]
            ev_val = self.fresh()
            self.emit(f"{ev_val} = load i64, ptr {enum_slot}")
            idx_var = s.var[0] if isinstance(s.var, list) else s.var
            elem_target = s.var[1] if (isinstance(s.var, list) and len(s.var) > 1) else None
            self.store_var(idx_var, ev_val, INT, s.line)
            if elem_target is not None:
                ev = self._list_get_typed(lv, ci, elem_t, s.line)
                if isinstance(elem_target, list):
                    # Nested tuple unpacking: for i, (a, b) in enumerate(...)
                    self._store_for_target(elem_target, ev, elem_t, s.line)
                else:
                    self.store_var(elem_target, ev, elem_t, s.line)
            self.loop_stack.append((cont_label, end_label))
            for st in s.body:
                self.gen_stmt(st)
            self.loop_stack.pop()
            if not self.terminated:
                self.br(cont_label)
            self.place_block(cont_label)
            ci2 = self.fresh()
            self.emit(f"{ci2} = load i64, ptr {list_idx_slot}")
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {ci2}, 1")
            self.emit(f"store i64 {nxt}, ptr {list_idx_slot}")
            ev2 = self.fresh()
            self.emit(f"{ev2} = load i64, ptr {enum_slot}")
            env_next = self.fresh()
            self.emit(f"{env_next} = add i64 {ev2}, 1")
            self.emit(f"store i64 {env_next}, ptr {enum_slot}")
            self.br(cond_label)
            self.place_block(end_label)
            return
        raise CodeGenError("enumerate only supports list iteration", s.line)

    def _gep_byte(self, buf):
        r = self.fresh()
        self.emit(f"{r} = getelementptr inbounds [2 x i8], ptr {buf}, i64 0, i32 1")
        return r

    # ---- expressions ----
    def gen_expr(self, e):
        if isinstance(e, A.NumberLit):
            if isinstance(e.value, int):
                return str(e.value), INT
            return float_hex(e.value), FLOAT
        if isinstance(e, A.StringLit):
            return self.intern_string(e.value), STR
        if isinstance(e, A.BoolLit):
            return ("true" if e.value else "false"), BOOL
        if isinstance(e, A.NoneLit):
            return "0", NONE
        if isinstance(e, A.Name):
            return self.load_var(e.name, e.line)
        if isinstance(e, A.BinOp):
            lv, lt = self.gen_expr(e.left)
            rv, rt = self.gen_expr(e.right)
            return self.gen_binop(e.op, lv, lt, rv, rt, getattr(e, "type", None), e.line)
        if isinstance(e, A.UnaryOp):
            return self.gen_unary(e)
        if isinstance(e, A.BoolOp):
            return self.gen_boolop(e)
        if isinstance(e, A.IfExp):
            return self.gen_ifexp(e)
        if isinstance(e, A.Call):
            return self.gen_call(e)
        if isinstance(e, A.ListLit):
            return self.gen_list_lit(e)
        if isinstance(e, A.TupleLit):
            return self.gen_tuple_lit(e)
        if isinstance(e, A.Subscript):
            return self.gen_subscript(e)
        if isinstance(e, A.Slice):
            return self.gen_slice(e)
        if isinstance(e, A.Attribute):
            return self.gen_attr_get(e)
        if isinstance(e, A.MethodCall):
            return self.gen_method_call(e)
        if isinstance(e, A.FString):
            return self.gen_fstring(e)
        if isinstance(e, A.Compare):
            return self.gen_chained_compare(e)
        if isinstance(e, A.IsOp):
            return self.gen_isop(e)
        if isinstance(e, A.ListComp):
            return self.gen_listcomp(e)
        if isinstance(e, A.DictComp):
            return self.gen_dictcomp(e)
        if isinstance(e, A.DictLit):
            return self.gen_dict_lit(e)
        raise CodeGenError(f"unhandled expression {type(e).__name__}", e.line)

    def gen_dict_lit(self, e):
        """Dict literal: {k: v, ...} -> PyObject with string-keyed attributes."""
        r = self.fresh()
        self.emit(f"{r} = call ptr @py_object_new(i32 999)")
        for key_expr, val_expr in e.pairs:
            kv, kt = self.gen_expr(key_expr)
            kv = self.coerce(kv, kt, STR)
            vv, vt = self.gen_expr(val_expr)
            if vt == INT or vt == BOOL:
                v = self.coerce(vv, vt, INT)
                self.emit(f"call void @py_object_set_int(ptr {r}, ptr {kv}, i64 {v})")
            elif vt == FLOAT:
                v = self.coerce(vv, vt, FLOAT)
                self.emit(f"call void @py_object_set_float(ptr {r}, ptr {kv}, double {v})")
            elif vt == STR:
                self.emit(f"call void @py_object_set_str(ptr {r}, ptr {kv}, ptr {vv})")
            elif vt == NONE:
                self.emit(f"call void @py_object_set_none(ptr {r}, ptr {kv})")
            else:
                v = self.coerce(vv, vt, vt if isinstance(vt, tuple) else ("obj", "unknown"))
                self.emit(f"call void @py_object_set_obj(ptr {r}, ptr {kv}, ptr {v})")
        return r, getattr(e, "type", ("dict", STR, NONE))

    def gen_list_lit(self, e):
        r = self.fresh()
        self.emit(f"{r} = call ptr @py_list_new()")
        et = list_elem_type(getattr(e, "type", None))
        if et is None:
            et = NONE
        # Set the element kind tag for generic print/repr.
        self.emit(f"call void @py_list_set_kind(ptr {r}, i32 {list_kind_tag(et)})")
        for el in e.elements:
            v, t = self.gen_expr(el)
            self._list_append(r, v, t, et)
        return r, getattr(e, "type", ("list", et))

    def _list_append(self, list_ptr, value, val_type, elem_type):
        if is_list_type(elem_type) or is_obj_type(elem_type) or is_tuple_type(elem_type):
            v = self.coerce(value, val_type, elem_type if isinstance(elem_type, tuple) else ("list", NONE))
            self.emit(f"call void @py_list_append_list(ptr {list_ptr}, ptr {v})")
        elif elem_type == INT or elem_type == BOOL:
            v = self.coerce(value, val_type, INT)
            self.emit(f"call void @py_list_append_int(ptr {list_ptr}, i64 {v})")
        elif elem_type == FLOAT:
            v = self.coerce(value, val_type, FLOAT)
            self.emit(f"call void @py_list_append_float(ptr {list_ptr}, double {v})")
        elif elem_type == STR:
            v = self.coerce(value, val_type, STR)
            self.emit(f"call void @py_list_append_str(ptr {list_ptr}, ptr {v})")
        elif elem_type == NONE or elem_type is None:
            # Unknown element type: pick append function based on the value type.
            if val_type == INT or val_type == BOOL:
                v = self.coerce(value, val_type, INT)
                self.emit(f"call void @py_list_append_int(ptr {list_ptr}, i64 {v})")
            elif val_type == FLOAT:
                v = self.coerce(value, val_type, FLOAT)
                self.emit(f"call void @py_list_append_float(ptr {list_ptr}, double {v})")
            elif val_type == STR:
                v = self.coerce(value, val_type, STR)
                self.emit(f"call void @py_list_append_str(ptr {list_ptr}, ptr {v})")
            else:
                v = self.coerce(value, val_type, ("obj", "unknown"))
                self.emit(f"call void @py_list_append_list(ptr {list_ptr}, ptr {v})")
        else:
            raise CodeGenError(f"cannot append element of type {val_type} to list of {elem_type}")

    def gen_tuple_lit(self, e):
        """Tuple literal -> represented as a PyList at runtime."""
        r = self.fresh()
        self.emit(f"{r} = call ptr @py_list_new()")
        # Determine element types from the inferred tuple type.
        ttype = getattr(e, "type", None)
        elem_types = []
        if is_tuple_type(ttype):
            elem_types = ttype[1]
        # Set kind based on the first element type (or INT if mixed/empty).
        et_for_kind = elem_types[0] if elem_types else NONE
        self.emit(f"call void @py_list_set_kind(ptr {r}, i32 {list_kind_tag(et_for_kind)})")
        for i, el in enumerate(e.elements):
            v, t = self.gen_expr(el)
            et = elem_types[i] if i < len(elem_types) else t
            self._list_append(r, v, t, et if et is not None else NONE)
        return r, ttype if ttype is not None else ("tuple", elem_types)

    def gen_slice(self, e):
        """List slicing: a[start:stop:step] (step must be 1 or None)."""
        obj_type = self._obj_type_of(e.obj)
        if e.step is not None:
            # Only support constant step of 1.
            sv, st = self.gen_expr(e.step)
            # Best-effort check: if it's a literal 1 we accept; else error.
            if not (isinstance(e.step, A.NumberLit) and e.step.value == 1):
                raise CodeGenError("slice step != 1 not supported", e.line)
        if is_list_type(obj_type):
            lv, _ = self.gen_expr(e.obj)
            et = list_elem_type(obj_type)
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @py_list_len(ptr {lv})")
            # start (default 0)
            if e.start is not None:
                sv, st = self.gen_expr(e.start)
                sv = self.coerce(sv, st, INT)
                start = self._normalize_index(sv, lenr)
            else:
                start = "0"
            # stop (default length)
            if e.stop is not None:
                ev, et0 = self.gen_expr(e.stop)
                ev = self.coerce(ev, et0, INT)
                stop = self._normalize_index(ev, lenr)
            else:
                stop = lenr
            fn = {"int": "py_list_slice_int", "float": "py_list_slice_float",
                  "str": "py_list_slice_str"}.get(et)
            if fn is None:
                fn = "py_list_slice_list"
            r = self.fresh()
            self.emit(f"{r} = call ptr @{fn}(ptr {lv}, i64 {start}, i64 {stop})")
            return r, obj_type
        if obj_type == STR:
            sv, _ = self.gen_expr(e.obj)
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @strlen(ptr {sv})")
            if e.start is not None:
                stv, stt = self.gen_expr(e.start)
                stv = self.coerce(stv, stt, INT)
                start = self._normalize_index(stv, lenr)
            else:
                start = "0"
            if e.stop is not None:
                spv, spt = self.gen_expr(e.stop)
                spv = self.coerce(spv, spt, INT)
                stop = self._normalize_index(spv, lenr)
            else:
                stop = lenr
            # Clamp start/stop
            zc = self.fresh()
            self.emit(f"{zc} = icmp slt i64 {start}, 0")
            start = self.fresh()
            self.emit(f"{start} = select i1 {zc}, i64 0, i64 0")
            # Build substring via getelementptr + length
            ptr = self.fresh()
            self.emit(f"{ptr} = getelementptr inbounds i8, ptr {sv}, i64 {start}")
            sublen = self.fresh()
            self.emit(f"{sublen} = sub i64 {stop}, {start}")
            zc2 = self.fresh()
            self.emit(f"{zc2} = icmp slt i64 {sublen}, 0")
            sublen = self.fresh()
            self.emit(f"{sublen} = select i1 {zc2}, i64 0, i64 0")
            buf = self.fresh()
            self.insert_alloca(f"{buf} = alloca i8, i64 256")
            # memcpy-like loop: simplest is to call py_str_concat with empty.
            # Instead, use a byte-by-byte copy into a buffer of size sublen+1.
            dst = buf
            self.emit(f"call void @llvm.memcpy.p0.p0.i64(ptr {dst}, ptr {ptr}, i64 {sublen}, i1 false)")
            nullptr = self.fresh()
            self.emit(f"{nullptr} = getelementptr inbounds i8, ptr {dst}, i64 {sublen}")
            self.emit(f"store i8 0, ptr {nullptr}")
            return dst, STR
        raise CodeGenError(f"cannot slice value of type {obj_type}", e.line)

    def _normalize_index(self, idx, lenr):
        """If idx < 0, add lenr; return the normalized index value name."""
        neg = self.fresh()
        self.emit(f"{neg} = icmp slt i64 {idx}, 0")
        adj = self.fresh()
        self.emit(f"{adj} = add i64 {idx}, {lenr}")
        r = self.fresh()
        self.emit(f"{r} = select i1 {neg}, i64 {adj}, i64 {idx}")
        return r

    def gen_fstring(self, e):
        """f-string: concatenate literal and expression parts."""
        result = None
        for part, info in e.parts:
            if info is False:
                # Literal string part.
                lit = part.value if isinstance(part, A.StringLit) else str(part)
                s = self.intern_string(lit)
                piece = s
            elif info is True:
                # Expression without format spec.
                v, t = self.gen_expr(part)
                piece = self._value_to_str(v, t)
            else:
                # Expression with a format spec (info is the spec string).
                v, t = self.gen_expr(part)
                spec_ptr = self.intern_string(info)
                if t == INT or t == BOOL:
                    iv = self.coerce(v, t, INT)
                    r = self.fresh()
                    self.emit(f"{r} = call ptr @py_format_int(i64 {iv}, ptr {spec_ptr})")
                    piece = r
                elif t == FLOAT:
                    r = self.fresh()
                    self.emit(f"{r} = call ptr @py_format_float(double {v}, ptr {spec_ptr})")
                    piece = r
                elif t == STR:
                    r = self.fresh()
                    self.emit(f"{r} = call ptr @py_format_str(ptr {v}, ptr {spec_ptr})")
                    piece = r
                else:
                    piece = self._value_to_str(v, t)
            if result is None:
                result = piece
            else:
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_str_concat(ptr {result}, ptr {piece})")
                result = r
        if result is None:
            return self.intern_string(""), STR
        return result, STR

    def _value_to_str(self, v, t):
        """Convert a value of any type to a string pointer."""
        if t == STR:
            return v
        if t == INT:
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_int_to_str(i64 {v})")
            return r
        if t == FLOAT:
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_float_to_str(double {v})")
            return r
        if t == BOOL:
            tn = self.intern_string("True")
            fn = self.intern_string("False")
            r = self.fresh()
            self.emit(f"{r} = select i1 {v}, ptr {tn}, ptr {fn}")
            return r
        if t == NONE:
            return self.intern_string("None")
        if is_list_type(t) or is_tuple_type(t):
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_list_to_str(ptr {v})")
            return r
        if is_obj_type(t):
            return self.intern_string("<object>")
        # Fallback: treat as pointer, format as object.
        return self.intern_string("<object>")

    def gen_chained_compare(self, e):
        """Chained comparison: a < b < c -> (a<b) and (b<c) with short-circuit."""
        ops = e.ops
        operands = e.operands
        n = len(ops)
        if n == 1:
            lv, lt = self.gen_expr(operands[0])
            rv, rt = self.gen_expr(operands[1])
            return self.gen_compare(ops[0], lv, lt, rv, rt, e.line), BOOL
        # Multi-comparison with short-circuit.
        end_label = self.fresh_label("cmp.end")
        result_slot = self.fresh()
        self.insert_alloca(f"{result_slot} = alloca i1")
        prev_val, prev_t = self.gen_expr(operands[0])
        entry_label = self.current_label
        for i, op in enumerate(ops):
            cur_val, cur_t = self.gen_expr(operands[i + 1])
            cmp = self.gen_compare(op, prev_val, prev_t, cur_val, cur_t, e.line)
            if i < n - 1:
                # Short-circuit: if cmp is false, store false and jump to end.
                false_label = self.fresh_label("cmp.false")
                next_label = self.fresh_label("cmp.next")
                self.cbr(cmp, next_label, false_label)
                self.place_block(false_label)
                self.emit(f"store i1 false, ptr {result_slot}")
                self.br(end_label)
                self.place_block(next_label)
                prev_val, prev_t = cur_val, cur_t
            else:
                # Last comparison: store its result.
                self.emit(f"store i1 {cmp}, ptr {result_slot}")
                self.br(end_label)
        self.place_block(end_label)
        r = self.fresh()
        self.emit(f"{r} = load i1, ptr {result_slot}")
        return r, BOOL

    def gen_isop(self, e):
        """is / is not operator — pointer or integer equality."""
        lv, lt = self.gen_expr(e.left)
        rv, rt = self.gen_expr(e.right)
        if is_obj_type(lt) or is_obj_type(rt) or is_list_type(lt) or is_list_type(rt) \
                or is_tuple_type(lt) or is_tuple_type(rt) or lt == STR or rt == STR:
            # Coerce NONE (i64 0) to ptr so the comparison is valid.
            if lt == NONE:
                lv = self.coerce(lv, NONE, ("obj", "unknown"))
            if rt == NONE:
                rv = self.coerce(rv, NONE, ("obj", "unknown"))
            r = self.fresh()
            self.emit(f"{r} = icmp eq ptr {lv}, {rv}")
        else:
            # Numeric/none comparison.
            a = self.coerce(lv, lt, INT) if lt != NONE else lv
            b = self.coerce(rv, rt, INT) if rt != NONE else rv
            r = self.fresh()
            self.emit(f"{r} = icmp eq i64 {a}, {b}")
        if e.negate:
            n = self.fresh()
            self.emit(f"{n} = xor i1 {r}, true")
            r = n
        return r, BOOL

    def gen_listcomp(self, e):
        """List comprehension: [expr for var in iterable (if cond)*]."""
        result = self.fresh()
        self.emit(f"{result} = call ptr @py_list_new()")
        et = getattr(e.element, "type", None)
        if et is None:
            et = NONE
        self.emit(f"call void @py_list_set_kind(ptr {result}, i32 {list_kind_tag(et)})")
        # Generate a loop over the iterable, similar to gen_for but appending.
        it = e.iterable
        it_type = getattr(it, "type", None)
        # range-based comprehension
        if isinstance(it, A.Call) and isinstance(it.func, A.Name) and it.func.name == "range":
            args = it.args
            if len(args) == 1:
                stop_val, stop_t = self.gen_expr(args[0])
                start, stop, step = "0", self.coerce(stop_val, stop_t, INT), "1"
            elif len(args) == 2:
                sv, st0 = self.gen_expr(args[0])
                ev, et0 = self.gen_expr(args[1])
                start, stop, step = self.coerce(sv, st0, INT), self.coerce(ev, et0, INT), "1"
            else:
                sv, st0 = self.gen_expr(args[0])
                ev, et0 = self.gen_expr(args[1])
                tv, tt0 = self.gen_expr(args[2])
                start = self.coerce(sv, st0, INT)
                stop = self.coerce(ev, et0, INT)
                step = self.coerce(tv, tt0, INT)
            var_name = e.var[0] if isinstance(e.var, list) else e.var
            self._ensure_local(var_name, INT)
            self.store_var(var_name, start, INT, e.line)
            cond_label = self.fresh_label("lc.cond")
            body_label = self.fresh_label("lc.body")
            cont_label = self.fresh_label("lc.cont")
            end_label = self.fresh_label("lc.end")
            self.br(cond_label)
            self.place_block(cond_label)
            cur, _ = self.load_var(var_name, e.line)
            cmp_pos = self.fresh()
            self.emit(f"{cmp_pos} = icmp slt i64 {cur}, {stop}")
            cmp_neg = self.fresh()
            self.emit(f"{cmp_neg} = icmp sgt i64 {cur}, {stop}")
            pos = self.fresh()
            self.emit(f"{pos} = icmp sgt i64 {step}, 0")
            cmp = self.fresh()
            self.emit(f"{cmp} = select i1 {pos}, i1 {cmp_pos}, i1 {cmp_neg}")
            self.cbr(cmp, body_label, end_label)
            self.place_block(body_label)
            self._emit_listcomp_body(e, result)
            self.br(cont_label)
            self.place_block(cont_label)
            cur2, _ = self.load_var(var_name, e.line)
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {cur2}, {step}")
            self.store_var(var_name, nxt, INT, e.line)
            self.br(cond_label)
            self.place_block(end_label)
            return result, ("list", et)
        # list-based comprehension
        if is_list_type(it_type):
            lv, _ = self.gen_expr(it)
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @py_list_len(ptr {lv})")
            idx_slot = self.fresh()
            self.insert_alloca(f"{idx_slot} = alloca i64")
            self.emit(f"store i64 0, ptr {idx_slot}")
            cond_label = self.fresh_label("lc.cond")
            body_label = self.fresh_label("lc.body")
            cont_label = self.fresh_label("lc.cont")
            end_label = self.fresh_label("lc.end")
            self.br(cond_label)
            self.place_block(cond_label)
            ci = self.fresh()
            self.emit(f"{ci} = load i64, ptr {idx_slot}")
            cmp = self.fresh()
            self.emit(f"{cmp} = icmp slt i64 {ci}, {lenr}")
            self.cbr(cmp, body_label, end_label)
            self.place_block(body_label)
            elem_et = list_elem_type(it_type)
            ev = self._list_get_typed(lv, ci, elem_et, e.line)
            var_name = e.var[0] if isinstance(e.var, list) else e.var
            self._ensure_local(var_name, elem_et if elem_et else NONE)
            self.store_var(var_name, ev, elem_et, e.line)
            self._emit_listcomp_body(e, result)
            self.br(cont_label)
            self.place_block(cont_label)
            ci2 = self.fresh()
            self.emit(f"{ci2} = load i64, ptr {idx_slot}")
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {ci2}, 1")
            self.emit(f"store i64 {nxt}, ptr {idx_slot}")
            self.br(cond_label)
            self.place_block(end_label)
            return result, ("list", et)
        # string-based comprehension
        if it_type == STR:
            sv, _ = self.gen_expr(it)
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @strlen(ptr {sv})")
            idx_slot = self.fresh()
            self.insert_alloca(f"{idx_slot} = alloca i64")
            self.emit(f"store i64 0, ptr {idx_slot}")
            cond_label = self.fresh_label("lc.cond")
            body_label = self.fresh_label("lc.body")
            cont_label = self.fresh_label("lc.cont")
            end_label = self.fresh_label("lc.end")
            self.br(cond_label)
            self.place_block(cond_label)
            ci = self.fresh()
            self.emit(f"{ci} = load i64, ptr {idx_slot}")
            cmp = self.fresh()
            self.emit(f"{cmp} = icmp slt i64 {ci}, {lenr}")
            self.cbr(cmp, body_label, end_label)
            self.place_block(body_label)
            ptr = self.fresh()
            self.emit(f"{ptr} = getelementptr inbounds i8, ptr {sv}, i64 {ci}")
            ch = self.fresh()
            self.emit(f"{ch} = load i8, ptr {ptr}")
            buf = self.fresh()
            self.insert_alloca(f"{buf} = alloca [2 x i8]")
            self.emit(f"store i8 {ch}, ptr {buf}")
            zptr = self.fresh()
            self.emit(f"{zptr} = getelementptr inbounds [2 x i8], ptr {buf}, i64 0, i32 1")
            self.emit(f"store i8 0, ptr {zptr}")
            var_name = e.var[0] if isinstance(e.var, list) else e.var
            self._ensure_local(var_name, STR)
            self.store_var(var_name, buf, STR, e.line)
            self._emit_listcomp_body(e, result)
            self.br(cont_label)
            self.place_block(cont_label)
            ci2 = self.fresh()
            self.emit(f"{ci2} = load i64, ptr {idx_slot}")
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {ci2}, 1")
            self.emit(f"store i64 {nxt}, ptr {idx_slot}")
            self.br(cond_label)
            self.place_block(end_label)
            return result, ("list", et)
        raise CodeGenError("list comprehension only supports range/string/list iterables", e.line)

    def _emit_listcomp_body(self, e, result):
        """Emit the body of a list comprehension: evaluate conditions, then append expr."""
        skip_label = self.fresh_label("lc.skip")
        for cond in e.conditions:
            cv, ct = self.gen_expr(cond)
            cb = self.to_bool(cv, ct)
            cont_label = self.fresh_label("lc.cont")
            self.cbr(cb, cont_label, skip_label)
            self.place_block(cont_label)
        v, t = self.gen_expr(e.element)
        et = getattr(e.element, "type", None)
        if et is None:
            et = t
        self._list_append(result, v, t, et)
        self.br(skip_label)
        self.place_block(skip_label)

    def gen_dictcomp(self, e):
        """Dict comprehension: {k: v for var in iterable (if cond)*}."""
        result = self.fresh()
        self.emit(f"{result} = call ptr @py_object_new(i32 999)")
        it = e.iterable
        it_type = getattr(it, "type", None)
        # range-based
        if isinstance(it, A.Call) and isinstance(it.func, A.Name) and it.func.name == "range":
            args = it.args
            if len(args) == 1:
                stop_val, stop_t = self.gen_expr(args[0])
                start, stop, step = "0", self.coerce(stop_val, stop_t, INT), "1"
            elif len(args) == 2:
                sv, st0 = self.gen_expr(args[0])
                ev, et0 = self.gen_expr(args[1])
                start, stop, step = self.coerce(sv, st0, INT), self.coerce(ev, et0, INT), "1"
            else:
                sv, st0 = self.gen_expr(args[0])
                ev, et0 = self.gen_expr(args[1])
                tv, tt0 = self.gen_expr(args[2])
                start = self.coerce(sv, st0, INT)
                stop = self.coerce(ev, et0, INT)
                step = self.coerce(tv, tt0, INT)
            var_name = e.var[0] if isinstance(e.var, list) else e.var
            self._ensure_local(var_name, INT)
            self.store_var(var_name, start, INT, e.line)
            cond_label = self.fresh_label("dc.cond")
            body_label = self.fresh_label("dc.body")
            cont_label = self.fresh_label("dc.cont")
            end_label = self.fresh_label("dc.end")
            self.br(cond_label)
            self.place_block(cond_label)
            cur, _ = self.load_var(var_name, e.line)
            cmp_pos = self.fresh()
            self.emit(f"{cmp_pos} = icmp slt i64 {cur}, {stop}")
            cmp_neg = self.fresh()
            self.emit(f"{cmp_neg} = icmp sgt i64 {cur}, {stop}")
            pos = self.fresh()
            self.emit(f"{pos} = icmp sgt i64 {step}, 0")
            cmp = self.fresh()
            self.emit(f"{cmp} = select i1 {pos}, i1 {cmp_pos}, i1 {cmp_neg}")
            self.cbr(cmp, body_label, end_label)
            self.place_block(body_label)
            self._emit_dictcomp_body(e, result)
            self.br(cont_label)
            self.place_block(cont_label)
            cur2, _ = self.load_var(var_name, e.line)
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {cur2}, {step}")
            self.store_var(var_name, nxt, INT, e.line)
            self.br(cond_label)
            self.place_block(end_label)
            return result, ("dict", STR, NONE)
        # list-based
        if is_list_type(it_type):
            lv, _ = self.gen_expr(it)
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @py_list_len(ptr {lv})")
            idx_slot = self.fresh()
            self.insert_alloca(f"{idx_slot} = alloca i64")
            self.emit(f"store i64 0, ptr {idx_slot}")
            cond_label = self.fresh_label("dc.cond")
            body_label = self.fresh_label("dc.body")
            cont_label = self.fresh_label("dc.cont")
            end_label = self.fresh_label("dc.end")
            self.br(cond_label)
            self.place_block(cond_label)
            ci = self.fresh()
            self.emit(f"{ci} = load i64, ptr {idx_slot}")
            cmp = self.fresh()
            self.emit(f"{cmp} = icmp slt i64 {ci}, {lenr}")
            self.cbr(cmp, body_label, end_label)
            self.place_block(body_label)
            elem_et = list_elem_type(it_type)
            ev = self._list_get_typed(lv, ci, elem_et, e.line)
            var_name = e.var[0] if isinstance(e.var, list) else e.var
            self._ensure_local(var_name, elem_et if elem_et else NONE)
            self.store_var(var_name, ev, elem_et, e.line)
            self._emit_dictcomp_body(e, result)
            self.br(cont_label)
            self.place_block(cont_label)
            ci2 = self.fresh()
            self.emit(f"{ci2} = load i64, ptr {idx_slot}")
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {ci2}, 1")
            self.emit(f"store i64 {nxt}, ptr {idx_slot}")
            self.br(cond_label)
            self.place_block(end_label)
            return result, ("dict", STR, NONE)
        raise CodeGenError("dict comprehension only supports range/list iterables", e.line)

    def _emit_dictcomp_body(self, e, result):
        """Emit the body of a dict comprehension: evaluate conditions, then set k: v."""
        skip_label = self.fresh_label("dc.skip")
        for cond in e.conditions:
            cv, ct = self.gen_expr(cond)
            cb = self.to_bool(cv, ct)
            cont_label = self.fresh_label("dc.cont")
            self.cbr(cb, cont_label, skip_label)
            self.place_block(cont_label)
        kv, kt = self.gen_expr(e.key_expr)
        kv = self.coerce(kv, kt, STR)
        vv, vt = self.gen_expr(e.val_expr)
        if vt == INT or vt == BOOL:
            v = self.coerce(vv, vt, INT)
            self.emit(f"call void @py_object_set_int(ptr {result}, ptr {kv}, i64 {v})")
        elif vt == FLOAT:
            v = self.coerce(vv, vt, FLOAT)
            self.emit(f"call void @py_object_set_float(ptr {result}, ptr {kv}, double {v})")
        elif vt == STR:
            self.emit(f"call void @py_object_set_str(ptr {result}, ptr {kv}, ptr {vv})")
        elif vt == NONE:
            self.emit(f"call void @py_object_set_none(ptr {result}, ptr {kv})")
        else:
            v = self.coerce(vv, vt, vt if isinstance(vt, tuple) else ("obj", "unknown"))
            self.emit(f"call void @py_object_set_obj(ptr {result}, ptr {kv}, ptr {v})")
        self.br(skip_label)
        self.place_block(skip_label)

    def gen_subscript(self, e):
        obj_type = self._obj_type_of(e.obj)
        # String indexing: s[i] -> single-char string
        if obj_type == STR:
            sv, _ = self.gen_expr(e.obj)
            iv, it = self.gen_expr(e.index)
            iv = self.coerce(iv, it, INT)
            # Handle negative index
            neg = self.fresh()
            self.emit(f"{neg} = icmp slt i64 {iv}, 0")
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @strlen(ptr {sv})")
            adjusted = self.fresh()
            self.emit(f"{adjusted} = add i64 {iv}, {lenr}")
            idx = self.fresh()
            self.emit(f"{idx} = select i1 {neg}, i64 {adjusted}, i64 {iv}")
            ptr = self.fresh()
            self.emit(f"{ptr} = getelementptr inbounds i8, ptr {sv}, i64 {idx}")
            ch = self.fresh()
            self.emit(f"{ch} = load i8, ptr {ptr}")
            buf = self.fresh()
            self.insert_alloca(f"{buf} = alloca [2 x i8]")
            self.emit(f"store i8 {ch}, ptr {buf}")
            zero_ptr = self.fresh()
            self.emit(f"{zero_ptr} = getelementptr inbounds [2 x i8], ptr {buf}, i64 0, i32 1")
            self.emit(f"store i8 0, ptr {zero_ptr}")
            return buf, STR
        # Tuple indexing: tuples are stored as PyList at runtime.
        if is_tuple_type(obj_type):
            lv, _ = self.gen_expr(e.obj)
            iv, it = self.gen_expr(e.index)
            iv = self.coerce(iv, it, INT)
            elem_types = obj_type[1]
            # Determine the element type at this index. If the index is a
            # constant literal, use the specific element type; otherwise fall
            # back to the first element type.
            et = elem_types[0] if elem_types else NONE
            if isinstance(e.index, A.NumberLit) and 0 <= e.index.value < len(elem_types):
                et = elem_types[e.index.value]
            if et == INT:
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_get_int(ptr {lv}, i64 {iv})")
                return r, INT
            if et == FLOAT:
                r = self.fresh()
                self.emit(f"{r} = call double @py_list_get_float(ptr {lv}, i64 {iv})")
                return r, FLOAT
            if et == STR:
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_list_get_str(ptr {lv}, i64 {iv})")
                return r, STR
            if et == BOOL:
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_get_int(ptr {lv}, i64 {iv})")
                b = self.fresh()
                self.emit(f"{b} = trunc i64 {r} to i1")
                return b, BOOL
            if isinstance(et, tuple):
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_list_get_list(ptr {lv}, i64 {iv})")
                return r, et
            r = self.fresh()
            self.emit(f"{r} = call i64 @py_list_get_int(ptr {lv}, i64 {iv})")
            return r, NONE
        # List indexing
        if is_list_type(obj_type):
            lv, _ = self.gen_expr(e.obj)
            iv, it = self.gen_expr(e.index)
            iv = self.coerce(iv, it, INT)
            et = list_elem_type(obj_type)
            if et == INT:
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_get_int(ptr {lv}, i64 {iv})")
                return r, INT
            if et == FLOAT:
                r = self.fresh()
                self.emit(f"{r} = call double @py_list_get_float(ptr {lv}, i64 {iv})")
                return r, FLOAT
            if et == STR:
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_list_get_str(ptr {lv}, i64 {iv})")
                return r, STR
            if et == BOOL:
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_get_int(ptr {lv}, i64 {iv})")
                b = self.fresh()
                self.emit(f"{b} = trunc i64 {r} to i1")
                return b, BOOL
            if is_list_type(et) or is_obj_type(et) or is_tuple_type(et):
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_list_get_list(ptr {lv}, i64 {iv})")
                return r, et
            if et == NONE or et is None:
                # Unknown element type (e.g. attribute list initialized as []
                # whose element type the semantic analyzer couldn't infer).
                # Read as i64; callers can coerce to the needed type via
                # inttoptr/bitcast since both are 64 bits at runtime.
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_get_int(ptr {lv}, i64 {iv})")
                return r, NONE
            raise CodeGenError(f"cannot index list of type {obj_type}", e.line)
        # Dict indexing: treat dict as PyObject with string-keyed attributes.
        if isinstance(obj_type, tuple) and obj_type[0] == "dict":
            dv, _ = self.gen_expr(e.obj)
            kv, kt = self.gen_expr(e.index)
            kv = self.coerce(kv, kt, STR)
            # Use the inferred type (from per-key tracking) to call the right getter.
            inferred_t = getattr(e, "type", None)
            if inferred_t == INT:
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_object_get_int(ptr {dv}, ptr {kv})")
                return r, INT
            if inferred_t == FLOAT:
                r = self.fresh()
                self.emit(f"{r} = call double @py_object_get_float(ptr {dv}, ptr {kv})")
                return r, FLOAT
            if inferred_t == STR:
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_object_get_str(ptr {dv}, ptr {kv})")
                return r, STR
            if inferred_t == BOOL:
                r = self.fresh()
                self.emit(f"{r} = call i32 @py_object_get_bool(ptr {dv}, ptr {kv})")
                b = self.fresh()
                self.emit(f"{b} = trunc i32 {r} to i1")
                return b, BOOL
            if isinstance(inferred_t, tuple) and inferred_t[0] in ("list", "tuple", "obj"):
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_object_get_list(ptr {dv}, ptr {kv})")
                return r, inferred_t
            # Fallback: unknown type, read as i64.
            r = self.fresh()
            self.emit(f"{r} = call i64 @py_object_get_int(ptr {dv}, ptr {kv})")
            return r, NONE
        raise CodeGenError(f"cannot subscript value of type {obj_type}", e.line)

    def gen_subscript_assign(self, target, value, val_type, line):
        obj_type = self._obj_type_of(target.obj)
        if is_list_type(obj_type):
            lv, _ = self.gen_expr(target.obj)
            iv, it = self.gen_expr(target.index)
            iv = self.coerce(iv, it, INT)
            et = list_elem_type(obj_type)
            if et == INT or et == BOOL:
                v = self.coerce(value, val_type, INT)
                self.emit(f"call void @py_list_set_int(ptr {lv}, i64 {iv}, i64 {v})")
            elif et == FLOAT:
                v = self.coerce(value, val_type, FLOAT)
                self.emit(f"call void @py_list_set_float(ptr {lv}, i64 {iv}, double {v})")
            elif et == STR:
                v = self.coerce(value, val_type, STR)
                self.emit(f"call void @py_list_set_str(ptr {lv}, i64 {iv}, ptr {v})")
            elif is_list_type(et) or is_obj_type(et) or is_tuple_type(et):
                v = self.coerce(value, val_type, et if isinstance(et, tuple) else ("obj", "unknown"))
                self.emit(f"call void @py_list_set_list(ptr {lv}, i64 {iv}, ptr {v})")
            elif et == NONE or et is None:
                # Unknown element type: pick setter based on the value's type.
                if val_type == INT or val_type == BOOL:
                    v = self.coerce(value, val_type, INT)
                    self.emit(f"call void @py_list_set_int(ptr {lv}, i64 {iv}, i64 {v})")
                elif val_type == FLOAT:
                    v = self.coerce(value, val_type, FLOAT)
                    self.emit(f"call void @py_list_set_float(ptr {lv}, i64 {iv}, double {v})")
                elif val_type == STR:
                    v = self.coerce(value, val_type, STR)
                    self.emit(f"call void @py_list_set_str(ptr {lv}, i64 {iv}, ptr {v})")
                else:
                    v = self.coerce(value, val_type, ("obj", "unknown"))
                    self.emit(f"call void @py_list_set_list(ptr {lv}, i64 {iv}, ptr {v})")
            else:
                raise CodeGenError(f"cannot assign to list of {obj_type}", line)
        elif isinstance(obj_type, tuple) and obj_type[0] == "dict":
            dv, _ = self.gen_expr(target.obj)
            kv, kt = self.gen_expr(target.index)
            kv = self.coerce(kv, kt, STR)
            if val_type == INT or val_type == BOOL:
                v = self.coerce(value, val_type, INT)
                self.emit(f"call void @py_object_set_int(ptr {dv}, ptr {kv}, i64 {v})")
            elif val_type == FLOAT:
                v = self.coerce(value, val_type, FLOAT)
                self.emit(f"call void @py_object_set_float(ptr {dv}, ptr {kv}, double {v})")
            elif val_type == STR:
                v = self.coerce(value, val_type, STR)
                self.emit(f"call void @py_object_set_str(ptr {dv}, ptr {kv}, ptr {v})")
            elif val_type == NONE:
                self.emit(f"call void @py_object_set_none(ptr {dv}, ptr {kv})")
            else:
                v = self.coerce(value, val_type, val_type if isinstance(val_type, tuple) else ("obj", "unknown"))
                self.emit(f"call void @py_object_set_obj(ptr {dv}, ptr {kv}, ptr {v})")
        else:
            raise CodeGenError(f"cannot assign to subscript of type {obj_type}", line)

    # ---- attribute access ----
    def gen_attr_get(self, e):
        """Read obj.attr — returns (value, attr_type)."""
        attr_type = getattr(e, "type", None)
        # Evaluate obj to get both the value and its type (see gen_attr_assign
        # for why we don't rely on e.obj.type).
        ov, obj_type = self.gen_expr(e.obj)
        # Module attribute access: handle module constants
        if is_module_type(obj_type):
            mod_name = obj_type[1] if obj_type[0] == "module" else obj_type[1]
            top_mod = mod_name.split(".")[-1] if "." in mod_name else mod_name
            attr = e.attr
            # Math module constants
            if top_mod == "math" and attr in ("pi", "e", "inf", "nan"):
                fn_map = {"pi": "py_math_pi", "e": "py_math_e", "inf": "py_math_inf", "nan": "py_math_nan"}
                r = self.fresh()
                self.emit(f"{r} = call double @{fn_map[attr]}()")
                return r, FLOAT
            # String module constants
            if top_mod == "string" and attr in ("ascii_letters", "ascii_lowercase", "ascii_uppercase",
                                                  "digits", "hexdigits", "octdigits", "punctuation", "whitespace"):
                fn_map = {"ascii_letters": "py_string_ascii_letters", "ascii_lowercase": "py_string_ascii_lowercase",
                          "ascii_uppercase": "py_string_ascii_uppercase", "digits": "py_string_digits",
                          "hexdigits": "py_string_hexdigits", "octdigits": "py_string_octdigits",
                          "punctuation": "py_string_punctuation", "whitespace": "py_string_whitespace"}
                r = self.fresh()
                self.emit(f"{r} = call ptr @{fn_map[attr]}()")
                return r, STR
            # Other module attributes: return as opaque
            return ov, obj_type
        if obj_type == NONE or obj_type is None:
            # Unknown type (e.g. element read from a list with unknown element
            # type). Coerce i64 -> ptr and treat as a generic object.
            ov = self.coerce(ov, NONE, ("obj", "unknown"))
            obj_type = ("obj", "unknown")
        if not is_obj_type(obj_type):
            raise CodeGenError(f"cannot access attribute on type {obj_type}", e.line)
        # If the semantic analyzer didn't set .type on this Attribute node,
        # look up the attribute type from the class definition.
        if attr_type is None and obj_type[1] in self.classes:
            attrs = self.classes[obj_type[1]]["attrs"]
            if e.attr in attrs:
                attr_type = attrs[e.attr]
        name_ptr = self.intern_string(e.attr)
        if attr_type == INT:
            r = self.fresh()
            self.emit(f"{r} = call i64 @py_object_get_int(ptr {ov}, ptr {name_ptr})")
            return r, INT
        if attr_type == FLOAT:
            r = self.fresh()
            self.emit(f"{r} = call double @py_object_get_float(ptr {ov}, ptr {name_ptr})")
            return r, FLOAT
        if attr_type == STR:
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_object_get_str(ptr {ov}, ptr {name_ptr})")
            return r, STR
        if attr_type == BOOL:
            r = self.fresh()
            self.emit(f"{r} = call i32 @py_object_get_bool(ptr {ov}, ptr {name_ptr})")
            b = self.fresh()
            self.emit(f"{b} = trunc i32 {r} to i1")
            return b, BOOL
        if is_list_type(attr_type):
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_object_get_list(ptr {ov}, ptr {name_ptr})")
            self.emit(f"call void @py_list_set_kind(ptr {r}, i32 {list_kind_tag(list_elem_type(attr_type))})")
            return r, attr_type
        if is_obj_type(attr_type) or is_tuple_type(attr_type) or attr_type == NONE:
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_object_get_obj(ptr {ov}, ptr {name_ptr})")
            return r, attr_type if attr_type is not None else NONE
        # Unknown attr type — read as object ptr.
        r = self.fresh()
        self.emit(f"{r} = call ptr @py_object_get_obj(ptr {ov}, ptr {name_ptr})")
        return r, attr_type if attr_type is not None else NONE

    def gen_attr_assign(self, target, value, val_type, line):
        """Store value into obj.attr."""
        # Evaluate obj to get both the value and its type. We cannot rely on
        # target.obj.type being set: the semantic analyzer skips setting .type
        # on the obj node for `self.attr = None` (it returns early in
        # _maybe_update_attr_type when the value is None). Reading the type
        # from self.locals via gen_expr is always correct for `self`.
        ov, obj_type = self.gen_expr(target.obj)
        if obj_type == NONE or obj_type is None:
            # Unknown type (e.g. self.root where root was assigned from a list
            # with unknown element type). Coerce i64 -> ptr and treat as obj.
            ov = self.coerce(ov, NONE, ("obj", "unknown"))
            obj_type = ("obj", "unknown")
        if not is_obj_type(obj_type):
            raise CodeGenError(f"cannot assign attribute on type {obj_type}", line)
        name_ptr = self.intern_string(target.attr)
        if val_type == INT:
            v = self.coerce(value, val_type, INT)
            self.emit(f"call void @py_object_set_int(ptr {ov}, ptr {name_ptr}, i64 {v})")
        elif val_type == FLOAT:
            v = self.coerce(value, val_type, FLOAT)
            self.emit(f"call void @py_object_set_float(ptr {ov}, ptr {name_ptr}, double {v})")
        elif val_type == STR:
            v = self.coerce(value, val_type, STR)
            self.emit(f"call void @py_object_set_str(ptr {ov}, ptr {name_ptr}, ptr {v})")
        elif val_type == BOOL:
            v = self.coerce(value, val_type, BOOL)
            z = self.fresh()
            self.emit(f"{z} = zext i1 {v} to i32")
            self.emit(f"call void @py_object_set_bool(ptr {ov}, ptr {name_ptr}, i32 {z})")
        elif is_list_type(val_type):
            v = self.coerce(value, val_type, val_type)
            self.emit(f"call void @py_object_set_list(ptr {ov}, ptr {name_ptr}, ptr {v})")
        elif is_obj_type(val_type) or is_tuple_type(val_type):
            v = self.coerce(value, val_type, val_type)
            self.emit(f"call void @py_object_set_obj(ptr {ov}, ptr {name_ptr}, ptr {v})")
        elif val_type == NONE:
            self.emit(f"call void @py_object_set_none(ptr {ov}, ptr {name_ptr})")
        else:
            raise CodeGenError(f"cannot assign attribute of type {val_type}", line)

    def _obj_type_of(self, e):
        """Determine the type of an expression's obj without emitting code.
        Falls back to evaluating via gen_expr (which reads self.locals) when
        the semantic analyzer didn't set .type on the node (e.g. for `self`
        in bodies that assign self.attr = None)."""
        t = getattr(e, "type", None)
        if t is not None:
            return t
        if isinstance(e, A.Name) and e.name in self.locals:
            return self.locals[e.name][1]
        # Last resort: evaluate (emits a load) to discover the type.
        _, t = self.gen_expr(e)
        return t

    def gen_method_call(self, e):
        obj_type = self._obj_type_of(e.obj)
        if is_list_type(obj_type):
            return self.gen_list_method(e, obj_type)
        if is_obj_type(obj_type):
            return self.gen_obj_method_call(e, obj_type)
        if is_module_type(obj_type):
            return self.gen_module_method_call(e, obj_type)
        if obj_type == STR:
            return self.gen_str_method(e, obj_type)
        # Dict methods
        if isinstance(obj_type, tuple) and obj_type[0] == "dict":
            objval, _ = self.gen_expr(e.obj)
            if e.method == "keys":
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_dict_keys(ptr {objval})")
                return r, ("list", STR)
            if e.method == "values":
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_dict_values(ptr {objval})")
                return r, ("list", NONE)
            if e.method == "items":
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_dict_items(ptr {objval})")
                return r, ("list", NONE)
            if e.method == "get":
                # dict.get(key) or dict.get(key, default)
                kvv, kvt = self.gen_expr(e.args[0])
                kvv = self.coerce(kvv, kvt, STR)
                # Use a generic getter that handles all value types
                vt = getattr(e, "type", NONE)
                if vt == INT or vt == BOOL:
                    dval = 0
                    if len(e.args) > 1:
                        dvv, dvt = self.gen_expr(e.args[1])
                        dval = self.coerce(dvv, dvt, INT)
                    out = self.fresh()
                    self.emit(f"{out} = call i64 @py_dict_get_int(ptr {objval}, ptr {kvv}, i64 {dval})")
                    return out, INT
                elif vt == FLOAT:
                    dval = "0.0"
                    if len(e.args) > 1:
                        dvv, dvt = self.gen_expr(e.args[1])
                        dval = self.coerce(dvv, dvt, FLOAT)
                    out = self.fresh()
                    self.emit(f"{out} = call double @py_dict_get_float(ptr {objval}, ptr {kvv}, double {dval})")
                    return out, FLOAT
                elif vt == STR:
                    dval = "null"
                    if len(e.args) > 1:
                        dvv, dvt = self.gen_expr(e.args[1])
                        dval = self.coerce(dvv, dvt, STR)
                    out = self.fresh()
                    self.emit(f"{out} = call ptr @py_dict_get_str(ptr {objval}, ptr {kvv}, ptr {dval})")
                    return out, STR
                else:
                    dval = "null"
                    if len(e.args) > 1:
                        dvv, dvt = self.gen_expr(e.args[1])
                        dval = self.coerce(dvv, dvt, ("obj", "None"))
                    r = self.fresh()
                    self.emit(f"{r} = call ptr @py_dict_get_obj(ptr {objval}, ptr {kvv}, ptr {dval})")
                    return r, NONE
            if e.method in ("update", "clear", "pop"):
                return self.void_result()
        if obj_type == NONE or obj_type is None:
            # Unknown type (e.g. dict value, element from a list with unknown
            # element type). Try common list methods first, then fall back to
            # generic object.
            if e.method in ("append", "add", "extend", "pop", "insert", "index",
                            "remove", "sort", "reverse", "clear", "copy", "count"):
                return self.gen_list_method(e, ("list", NONE))
            return self.gen_obj_method_call(e, ("obj", "unknown"))
        raise CodeGenError(f"method call on unsupported type {obj_type}", e.line)

    def gen_str_method(self, e, obj_type):
        """Handle str.join(list_of_str) by looping and concatenating."""
        sv, _ = self.gen_expr(e.obj)
        m = e.method
        if m == "join":
            listv, lt = self.gen_expr(e.args[0])
            n = self.fresh()
            self.emit(f"{n} = call i64 @py_list_len(ptr {listv})")
            result_slot = self.fresh("joinres")
            self.insert_alloca(f"{result_slot} = alloca ptr")
            empty = self.intern_string("")
            self.emit(f"store ptr {empty}, ptr {result_slot}")
            i_slot = self.fresh("joini")
            self.insert_alloca(f"{i_slot} = alloca i64")
            self.emit(f"store i64 0, ptr {i_slot}")
            cond_lbl = self.fresh_label("joincond")
            body_lbl = self.fresh_label("joinbody")
            sep_lbl = self.fresh_label("joinsep")
            elem_lbl = self.fresh_label("joinelem")
            done_lbl = self.fresh_label("joindone")
            self.br(cond_lbl)
            self.place_block(cond_lbl)
            i_val = self.fresh()
            self.emit(f"{i_val} = load i64, ptr {i_slot}")
            cmp = self.fresh()
            self.emit(f"{cmp} = icmp slt i64 {i_val}, {n}")
            self.cbr(cmp, body_lbl, done_lbl)
            self.place_block(body_lbl)
            gt0 = self.fresh()
            self.emit(f"{gt0} = icmp sgt i64 {i_val}, 0")
            self.cbr(gt0, sep_lbl, elem_lbl)
            self.place_block(sep_lbl)
            cur1 = self.fresh()
            self.emit(f"{cur1} = load ptr, ptr {result_slot}")
            new1 = self.fresh()
            self.emit(f"{new1} = call ptr @py_str_concat(ptr {cur1}, ptr {sv})")
            self.emit(f"store ptr {new1}, ptr {result_slot}")
            self.br(elem_lbl)
            self.place_block(elem_lbl)
            elem = self.fresh()
            self.emit(f"{elem} = call ptr @py_list_get_str(ptr {listv}, i64 {i_val})")
            cur2 = self.fresh()
            self.emit(f"{cur2} = load ptr, ptr {result_slot}")
            new2 = self.fresh()
            self.emit(f"{new2} = call ptr @py_str_concat(ptr {cur2}, ptr {elem})")
            self.emit(f"store ptr {new2}, ptr {result_slot}")
            next_i = self.fresh()
            self.emit(f"{next_i} = add i64 {i_val}, 1")
            self.emit(f"store i64 {next_i}, ptr {i_slot}")
            self.br(cond_lbl)
            self.place_block(done_lbl)
            final = self.fresh()
            self.emit(f"{final} = load ptr, ptr {result_slot}")
            return final, STR
        if m in ("lower", "upper"):
            r = self.fresh()
            fn = "py_str_lower" if m == "lower" else "py_str_upper"
            self.emit(f"{r} = call ptr @{fn}(ptr {sv})")
            return r, STR
        if m == "replace":
            old, _ = self.gen_expr(e.args[0])
            new, _ = self.gen_expr(e.args[1])
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_str_replace(ptr {sv}, ptr {old}, ptr {new})")
            return r, STR
        if m in ("startswith", "endswith"):
            prefix, _ = self.gen_expr(e.args[0])
            r = self.fresh()
            fn = "py_str_startswith" if m == "startswith" else "py_str_endswith"
            self.emit(f"{r} = call i32 @{fn}(ptr {sv}, ptr {prefix})")
            b = self.fresh()
            self.emit(f"{b} = icmp ne i32 {r}, 0")
            return b, BOOL
        if m == "find":
            sub, _ = self.gen_expr(e.args[0])
            r = self.fresh()
            self.emit(f"{r} = call i64 @py_str_find(ptr {sv}, ptr {sub})")
            return r, INT
        if m in ("strip", "lstrip", "rstrip"):
            r = self.fresh()
            fn = {"strip": "py_str_strip", "lstrip": "py_str_lstrip", "rstrip": "py_str_rstrip"}[m]
            self.emit(f"{r} = call ptr @{fn}(ptr {sv})")
            return r, STR
        if m == "split":
            # split by delimiter; default is whitespace
            delim = None
            if e.args:
                delim, _ = self.gen_expr(e.args[0])
            r = self.fresh()
            if delim is not None:
                self.emit(f"{r} = call ptr @py_str_split(ptr {sv}, ptr {delim})")
            else:
                self.emit(f"{r} = call ptr @py_str_split_ws(ptr {sv})")
            return r, ("list", STR)
        raise CodeGenError(f"string method '{m}' not supported", e.line)

    def gen_list_method(self, e, obj_type):
        lv, _ = self.gen_expr(e.obj)
        et = list_elem_type(obj_type)
        m = e.method
        if m in ("append", "add"):
            v, t = self.gen_expr(e.args[0])
            self._list_append(lv, v, t, et)
            return "0", NONE
        if m == "extend":
            other, ot = self.gen_expr(e.args[0])
            if et == INT or et == BOOL:
                fn = "py_list_extend_int"
            elif et == FLOAT:
                fn = "py_list_extend_float"
            elif et == STR:
                fn = "py_list_extend_str"
            else:
                fn = "py_list_extend_list"
            self.emit(f"call void @{fn}(ptr {lv}, ptr {other})")
            return "0", NONE
        if m == "pop":
            # pop([idx]) — no args: pop from end; one arg: pop at index.
            if e.args:
                iv, it = self.gen_expr(e.args[0])
                iv = self.coerce(iv, it, INT)
                if et == INT or et == BOOL:
                    r = self.fresh()
                    self.emit(f"{r} = call i64 @py_list_pop_at_int(ptr {lv}, i64 {iv})")
                    if et == BOOL:
                        b = self.fresh()
                        self.emit(f"{b} = trunc i64 {r} to i1")
                        return b, BOOL
                    return r, INT
                if et == FLOAT:
                    r = self.fresh()
                    self.emit(f"{r} = call double @py_list_pop_at_float(ptr {lv}, i64 {iv})")
                    return r, FLOAT
                if et == STR:
                    r = self.fresh()
                    self.emit(f"{r} = call ptr @py_list_pop_at_str(ptr {lv}, i64 {iv})")
                    return r, STR
                if is_list_type(et) or is_obj_type(et) or is_tuple_type(et):
                    r = self.fresh()
                    self.emit(f"{r} = call ptr @py_list_pop_at_list(ptr {lv}, i64 {iv})")
                    return r, et
                # Unknown element type: default to pop_at_int (preserves bits).
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_pop_at_int(ptr {lv}, i64 {iv})")
                return r, NONE
            else:
                if et == INT or et == BOOL:
                    r = self.fresh()
                    self.emit(f"{r} = call i64 @py_list_pop_int(ptr {lv})")
                    if et == BOOL:
                        b = self.fresh()
                        self.emit(f"{b} = trunc i64 {r} to i1")
                        return b, BOOL
                    return r, INT
                if et == FLOAT:
                    r = self.fresh()
                    self.emit(f"{r} = call double @py_list_pop_float(ptr {lv})")
                    return r, FLOAT
                if et == STR:
                    r = self.fresh()
                    self.emit(f"{r} = call ptr @py_list_pop_str(ptr {lv})")
                    return r, STR
                if is_list_type(et) or is_obj_type(et) or is_tuple_type(et):
                    r = self.fresh()
                    self.emit(f"{r} = call ptr @py_list_pop_list(ptr {lv})")
                    return r, et
                # Unknown element type: default to pop_int (preserves bits).
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_pop_int(ptr {lv})")
                return r, NONE
        if m == "insert":
            iv, it = self.gen_expr(e.args[0])
            iv = self.coerce(iv, it, INT)
            v, t = self.gen_expr(e.args[1])
            if et == INT or et == BOOL:
                v = self.coerce(v, t, INT)
                self.emit(f"call void @py_list_insert_int(ptr {lv}, i64 {iv}, i64 {v})")
            elif et == FLOAT:
                v = self.coerce(v, t, FLOAT)
                self.emit(f"call void @py_list_insert_float(ptr {lv}, i64 {iv}, double {v})")
            elif et == STR:
                v = self.coerce(v, t, STR)
                self.emit(f"call void @py_list_insert_str(ptr {lv}, i64 {iv}, ptr {v})")
            elif is_list_type(et) or is_obj_type(et) or is_tuple_type(et):
                v = self.coerce(v, t, et if isinstance(et, tuple) else ("obj", "unknown"))
                self.emit(f"call void @py_list_insert_list(ptr {lv}, i64 {iv}, ptr {v})")
            elif et == NONE or et is None:
                # Unknown element type: pick insert function based on value type.
                if t == INT or t == BOOL:
                    v = self.coerce(v, t, INT)
                    self.emit(f"call void @py_list_insert_int(ptr {lv}, i64 {iv}, i64 {v})")
                elif t == FLOAT:
                    v = self.coerce(v, t, FLOAT)
                    self.emit(f"call void @py_list_insert_float(ptr {lv}, i64 {iv}, double {v})")
                elif t == STR:
                    v = self.coerce(v, t, STR)
                    self.emit(f"call void @py_list_insert_str(ptr {lv}, i64 {iv}, ptr {v})")
                else:
                    v = self.coerce(v, t, ("obj", "unknown"))
                    self.emit(f"call void @py_list_insert_list(ptr {lv}, i64 {iv}, ptr {v})")
            return "0", NONE
        if m == "index":
            v, t = self.gen_expr(e.args[0])
            if et == INT or et == BOOL:
                v = self.coerce(v, t, INT)
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_index_int(ptr {lv}, i64 {v})")
                return r, INT
            if et == STR:
                v = self.coerce(v, t, STR)
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_index_str(ptr {lv}, ptr {v})")
                return r, INT
            # For obj/list/tuple/NONE element types, use pointer equality via
            # py_list_index_int (the runtime union stores all 64-bit values the
            # same way, so comparing as i64 is equivalent to pointer equality).
            if is_list_type(et) or is_obj_type(et) or is_tuple_type(et)                     or et == NONE or et is None:
                v = self.coerce(v, t, et if isinstance(et, tuple) else ("obj", "unknown"))
                vi = self.fresh()
                self.emit(f"{vi} = ptrtoint ptr {v} to i64")
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_index_int(ptr {lv}, i64 {vi})")
                return r, INT
        if m in ("clear", "task_done", "sort", "reverse"):
            return "0", NONE
        if m == "count":
            av, at = self.gen_expr(e.args[0])
            et = list_elem_type(obj_type) if list_elem_type(obj_type) else INT
            r = self.fresh()
            if et == INT or et == BOOL:
                av = self.coerce(av, at, INT)
                self.emit(f"{r} = call i64 @py_list_count_int(ptr {lv}, i64 {av})")
            elif et == STR:
                av = self.coerce(av, at, STR)
                self.emit(f"{r} = call i64 @py_list_count_str(ptr {lv}, ptr {av})")
            else:
                av = self.coerce(av, at, et if isinstance(et, tuple) else ("obj", "unknown"))
                ai = self.fresh()
                self.emit(f"{ai} = ptrtoint ptr {av} to i64")
                self.emit(f"{r} = call i64 @py_list_count_int(ptr {lv}, i64 {ai})")
            return r, INT
        raise CodeGenError(f"unsupported list method '{m}'", e.line)

    def gen_obj_method_call(self, e, obj_type):
        """Method call on a user-defined class instance or runtime object."""
        class_name = obj_type[1]
        m = e.method
        # Runtime object methods (Lock, Event, Queue, Thread, Counter, deque).
        if class_name == "Lock":
            ov, _ = self.gen_expr(e.obj)
            if m == "acquire":
                self.emit(f"call void @py_lock_acquire(ptr {ov})")
                return "0", NONE
            if m == "release":
                self.emit(f"call void @py_lock_release(ptr {ov})")
                return "0", NONE
        if class_name == "Event":
            ov, _ = self.gen_expr(e.obj)
            if m == "set":
                self.emit(f"call void @py_event_set(ptr {ov})")
                return "0", NONE
            if m == "clear":
                self.emit(f"call void @py_event_clear(ptr {ov})")
                return "0", NONE
            if m == "wait":
                self.emit(f"call void @py_event_wait(ptr {ov})")
                return "0", NONE
            if m == "is_set":
                r = self.fresh()
                self.emit(f"{r} = call i32 @py_event_is_set(ptr {ov})")
                b = self.fresh()
                self.emit(f"{b} = trunc i32 {r} to i1")
                return b, BOOL
        if class_name == "Queue":
            ov, _ = self.gen_expr(e.obj)
            if m == "put":
                v, t = self.gen_expr(e.args[0])
                if t == STR:
                    # Strings can be stored as ptrs directly (they're already ptrs).
                    self.emit(f"call void @py_queue_put(ptr {ov}, ptr {v})")
                elif numeric_base(t) == INT or t == BOOL:
                    # Box ints into a PyList* so they can be stored as ptr.
                    boxed = self.fresh()
                    self.emit(f"{boxed} = call ptr @py_queue_box_int(i64 {v})")
                    self.emit(f"call void @py_queue_put(ptr {ov}, ptr {boxed})")
                elif t == FLOAT:
                    boxed = self.fresh()
                    self.emit(f"{boxed} = call ptr @py_queue_box_float(double {v})")
                    self.emit(f"call void @py_queue_put(ptr {ov}, ptr {boxed})")
                else:
                    # Fallback: cast to ptr (works for lists/objects)
                    self.emit(f"call void @py_queue_put(ptr {ov}, ptr {v})")
                return "0", NONE
            if m == "get":
                timeout = "0"
                if "timeout" in e.kwargs:
                    tv, tt = self.gen_expr(e.kwargs["timeout"])
                    timeout = self.coerce(tv, tt, INT)
                elif e.args:
                    tv, tt = self.gen_expr(e.args[0])
                    timeout = self.coerce(tv, tt, INT)
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_queue_get(ptr {ov}, i64 {timeout})")
                # If timed out, py_queue_get returns NULL — raise queue.Empty
                # exception so the enclosing try/except can catch it.
                is_null = self.fresh()
                self.emit(f"{is_null} = icmp eq ptr {r}, null")
                raise_label = self.fresh_label("qget_raise")
                cont_label = self.fresh_label("qget_cont")
                pred_label = self.current_label  # predecessor of cont_label
                self.cbr(is_null, raise_label, cont_label)
                self.place_block(raise_label)
                self.emit('call void @py_exc_raise(i32 10, ptr null)')
                # Use a dummy value to keep SSA valid.
                dummy = self.fresh()
                self.emit(f"{dummy} = call ptr @py_str_empty()")
                self.br(cont_label)
                self.place_block(cont_label)
                phi = self.fresh()
                self.emit(f"{phi} = phi ptr [{r}, %{pred_label}], [{dummy}, %{raise_label}]")
                # The returned value is either the original string ptr (if STR)
                # or a PyList* (if INT/FLOAT). The semantic analyzer infers
                # the return type; the codegen returns a ptr that's compatible
                # with the type. For STR, the ptr is the string itself.
                return phi, STR
            if m == "empty":
                r = self.fresh()
                self.emit(f"{r} = call i32 @py_queue_empty(ptr {ov})")
                b = self.fresh()
                self.emit(f"{b} = trunc i32 {r} to i1")
                return b, BOOL
            if m in ("qsize", "size"):
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_queue_size(ptr {ov})")
                return r, INT
            if m == "task_done":
                self.emit(f"call void @py_queue_task_done(ptr {ov})")
                return "0", NONE
            if m == "join":
                self.emit(f"call void @py_queue_join(ptr {ov})")
                return "0", NONE
        if class_name == "Thread":
            ov, _ = self.gen_expr(e.obj)
            if m == "start":
                self.emit(f"call void @py_thread_start(ptr {ov})")
                return "0", NONE
            if m == "join":
                self.emit(f"call void @py_thread_join(ptr {ov})")
                return "0", NONE
        if class_name == "Counter":
            ov, _ = self.gen_expr(e.obj)
            if m == "update":
                av, at = self.gen_expr(e.args[0])
                # If the arg is a list of strings, use update_list; otherwise
                # treat it as another Counter (obj ptr) and merge.
                if is_list_type(at):
                    self.emit(f"call void @py_counter_update_list(ptr {ov}, ptr {av})")
                else:
                    av = self.coerce(av, at, ("obj", "Counter"))
                    self.emit(f"call void @py_counter_update_counter(ptr {ov}, ptr {av})")
                return "0", NONE
            if m == "most_common":
                n = "0"
                if e.args:
                    nv, nt = self.gen_expr(e.args[0])
                    n = self.coerce(nv, nt, INT)
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_counter_most_common(ptr {ov}, i64 {n})")
                return r, ("list", ("tuple", [STR, INT]))
            if m == "values":
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_counter_values(ptr {ov})")
                return r, ("list", INT)
            if m == "keys":
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_list_new()")
                return r, ("list", STR)
            if m == "items":
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_list_new()")
                return r, ("list", ("tuple", [STR, INT]))
            if m == "get":
                return "0", INT
        if class_name == "deque":
            ov, _ = self.gen_expr(e.obj)
            if m in ("append", "appendleft", "extend", "extendleft", "clear"):
                return "0", NONE
            if m in ("pop", "popleft"):
                return "0", NONE
        if class_name == "set":
            objval, _ = self.gen_expr(e.obj)
            if m == "add":
                arg_val, arg_type = self.gen_expr(e.args[0])
                if arg_type == INT:
                    self.emit(f"call void @py_set_add_int(ptr {objval}, i64 {arg_val})")
                elif arg_type == STR:
                    self.emit(f"call void @py_set_add_str(ptr {objval}, ptr {arg_val})")
                return self.void_result()
            if m == "remove" or m == "discard":
                arg_val, arg_type = self.gen_expr(e.args[0])
                if arg_type == INT:
                    self.emit(f"call void @py_set_remove_int(ptr {objval}, i64 {arg_val})")
                elif arg_type == STR:
                    self.emit(f"call void @py_set_remove_str(ptr {objval}, ptr {arg_val})")
                return self.void_result()
            if m == "contains":
                arg_val, arg_type = self.gen_expr(e.args[0])
                r = self.fresh()
                if arg_type == INT:
                    self.emit(f"{r} = call i32 @py_set_contains_int(ptr {objval}, i64 {arg_val})")
                elif arg_type == STR:
                    self.emit(f"{r} = call i32 @py_set_contains_str(ptr {objval}, ptr {arg_val})")
                return r, BOOL
            if m == "len" or m == "__len__":
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_set_len(ptr {objval})")
                return r, INT
        # User-defined class method: call the mangled function.
        if class_name in self.classes:
            methods = self.classes[class_name]["methods"]
            if m in methods:
                mangled = methods[m]
                fn = self.funcs.get(mangled)
                if fn is not None:
                    return self._gen_method_call_fn(fn, e, mangled)
        raise CodeGenError(f"unsupported method '{m}' on {class_name}", e.line)

    def _gen_method_call_fn(self, fn, e, mangled):
        """Call a user-defined method: obj.method(args) -> fn_mangled(obj, args)."""
        ov, _ = self.gen_expr(e.obj)
        retty = fn.return_type
        argvals = [(ov, "ptr")]
        # Evaluate args, expanding Starred args.
        arg_idx = 0
        for a in e.args:
            if isinstance(a, A.Starred):
                # Unpack starred list/tuple: get elements by index.
                sv, st = self.gen_expr(a.value)
                # Determine how many to consume: based on remaining params.
                remaining = len(fn.params) - 1 - arg_idx
                for j in range(remaining):
                    pt = fn.param_types[arg_idx + 1 + j]
                    et = list_elem_type(st) if is_list_type(st) else \
                         (st[1][j] if is_tuple_type(st) else NONE)
                    ev = self._list_get_typed(sv, j, et, a.line)
                    argvals.append((self.coerce(ev, et, pt), llvm_type(pt)))
                arg_idx += remaining
            else:
                if arg_idx + 1 >= len(fn.param_types):
                    break
                pt = fn.param_types[arg_idx + 1]
                v, t = self.gen_expr(a)
                argvals.append((self.coerce(v, t, pt), llvm_type(pt)))
                arg_idx += 1
        # Fill in defaults for missing args.
        for k in range(arg_idx + 1, len(fn.params)):
            pname = fn.params[k]
            if pname in fn.defaults:
                v, t = self.gen_expr(fn.defaults[pname])
                pt = fn.param_types[k]
                argvals.append((self.coerce(v, t, pt), llvm_type(pt)))
        argstr = ", ".join(f"{ty} {v}" for v, ty in argvals)
        if retty == NONE:
            self.emit(f"call void @fn_{mangled}({argstr})")
            return "0", NONE
        r = self.fresh()
        self.emit(f"{r} = call {llvm_type(retty)} @fn_{mangled}({argstr})")
        return r, retty

    def gen_module_method_call(self, e, obj_type):
        """Method call on a module: random.randint, re.sub, time.perf_counter, etc."""
        # obj_type may be ("module", name) or ("module_attr", mod, attr).
        if obj_type[0] == "module_attr":
            mod_name = obj_type[1]
            # The actual call method is e.method (the called name).
        else:
            mod_name = obj_type[1]
        m = e.method
        # Strip dotted module path to the top module name for matching.
        top_mod = mod_name.split(".")[-1] if "." in mod_name else mod_name
        if top_mod == "random":
            if m == "randint":
                if e.args and isinstance(e.args[0], A.Starred):
                    sv, st = self.gen_expr(e.args[0].value)
                    et0 = st[1][0] if is_tuple_type(st) else (list_elem_type(st) or INT)
                    et1 = st[1][1] if is_tuple_type(st) else (list_elem_type(st) or INT)
                    lo = self._list_get_typed(sv, 0, et0, e.line)
                    hi = self._list_get_typed(sv, 1, et1, e.line)
                    lo = self.coerce(lo, et0, INT)
                    hi = self.coerce(hi, et1, INT)
                else:
                    lo, lt = self.gen_expr(e.args[0])
                    hi, ht = self.gen_expr(e.args[1])
                    lo = self.coerce(lo, lt, INT)
                    hi = self.coerce(hi, ht, INT)
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_random_randint(i64 {lo}, i64 {hi})")
                return r, INT
            if m == "seed":
                sv, st = self.gen_expr(e.args[0])
                sv = self.coerce(sv, st, INT)
                self.emit(f"call void @py_random_seed(i64 {sv})")
                return "0", NONE
            if m == "choice":
                lv, lt = self.gen_expr(e.args[0])
                et = list_elem_type(lt)
                if et == STR:
                    r = self.fresh()
                    self.emit(f"{r} = call ptr @py_random_choice_str(ptr {lv})")
                    return r, STR
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_random_choice_int(ptr {lv})")
                return r, et if et else INT
            if m == "random":
                r = self.fresh()
                self.emit(f"{r} = call double @py_random_random()")
                return r, FLOAT
        if top_mod == "time":
            if m in ("perf_counter", "time", "monotonic", "process_time"):
                r = self.fresh()
                self.emit(f"{r} = call double @py_time_perf_counter()")
                return r, FLOAT
            if m == "sleep":
                return "0", NONE
        if top_mod == "re":
            if m == "sub":
                p, _ = self.gen_expr(e.args[0])
                # If the replacement is a lambda callback, skip substitution
                # (lambda callbacks are not supported by the runtime).
                if isinstance(e.args[1], A.Name) and e.args[1].name.startswith("__lambda_"):
                    s3, _ = self.gen_expr(e.args[2])
                    return s3, STR
                r2, _ = self.gen_expr(e.args[1])
                s3, _ = self.gen_expr(e.args[2])
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_re_sub(ptr {p}, ptr {r2}, ptr {s3})")
                return r, STR
            if m == "findall":
                p, _ = self.gen_expr(e.args[0])
                s3, _ = self.gen_expr(e.args[1])
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_re_findall(ptr {p}, ptr {s3})")
                self.emit(f"call void @py_list_set_kind(ptr {r}, i32 {list_kind_tag(STR)})")
                return r, ("list", STR)
            if m in ("search", "match", "split"):
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_list_new()")
                return r, ("list", STR)
        if top_mod == "threading":
            if m == "Lock":
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_lock_new()")
                return r, ("obj", "Lock")
            if m == "Event":
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_event_new()")
                return r, ("obj", "Event")
            if m == "Thread":
                # threading.Thread(target=fn, args=(arg,)) — pass fn ptr + i64 arg.
                target = e.kwargs.get("target")
                args_expr = e.kwargs.get("args")
                fn_val = "null"
                arg_val = "0"
                fn = None
                if target is not None:
                    if isinstance(target, A.Name):
                        resolved = self._resolve_call_name(target.name)
                        if resolved in self.funcs:
                            fn_val = f"@fn_{resolved}"
                            fn = self.funcs[resolved]
                        elif target.name in self.funcs:
                            fn_val = f"@fn_{target.name}"
                            fn = self.funcs[target.name]
                    if fn_val == "null":
                        fv, ft = self.gen_expr(target)
                        fn_val = fv
                if args_expr is not None and fn is not None and len(fn.params) >= 1:
                    av, at = self.gen_expr(args_expr)
                    pt = fn.param_types[0] if fn.param_types else INT
                    if pt is None or pt == NONE:
                        pt = INT
                    ev = self._list_get_typed(av, 0, pt, e.line)
                    arg_val = self.coerce(ev, pt, INT)
                elif args_expr is not None:
                    av, at = self.gen_expr(args_expr)
                    ev = self._list_get_typed(av, 0, INT, e.line)
                    arg_val = ev
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_thread_new(ptr {fn_val}, i64 {arg_val})")
                return r, ("obj", "Thread")
        if top_mod == "queue":
            if m == "Queue":
                maxsize = "0"
                if "maxsize" in e.kwargs:
                    mv, mt = self.gen_expr(e.kwargs["maxsize"])
                    maxsize = self.coerce(mv, mt, INT)
                elif e.args:
                    mv, mt = self.gen_expr(e.args[0])
                    maxsize = self.coerce(mv, mt, INT)
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_queue_new(i64 {maxsize})")
                return r, ("obj", "Queue")
            if m == "Empty":
                return "null", ("obj", "Exception")
        if top_mod in ("collections",):
            if m == "Counter":
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_counter_new()")
                return r, ("obj", "Counter")
            if m == "deque":
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_list_new()")
                return r, ("obj", "deque")
        if top_mod == "math":
            math_float_fns = {
                "sqrt": "py_math_sqrt", "log": "py_math_log", "log2": "py_math_log2",
                "log10": "py_math_log10", "sin": "py_math_sin", "cos": "py_math_cos",
                "tan": "py_math_tan", "floor": "py_math_floor", "ceil": "py_math_ceil",
                "fabs": "py_math_fabs", "exp": "py_math_exp",
            }
            math_float2_fns = {"pow": "py_math_pow"}
            math_const_fns = {"pi": "py_math_pi", "e": "py_math_e", "inf": "py_math_inf", "nan": "py_math_nan"}
            math_int_fns = {"gcd": "py_math_gcd", "lcm": "py_math_lcm"}
            if m in math_float_fns:
                arg_val, arg_type = self.gen_expr(e.args[0])
                arg_val = self.coerce(arg_val, arg_type, FLOAT)
                r = self.fresh()
                self.emit(f"{r} = call double @{math_float_fns[m]}(double {arg_val})")
                return r, FLOAT
            if m in math_float2_fns:
                a1, t1 = self.gen_expr(e.args[0])
                a2, t2 = self.gen_expr(e.args[1])
                a1 = self.coerce(a1, t1, FLOAT)
                a2 = self.coerce(a2, t2, FLOAT)
                r = self.fresh()
                self.emit(f"{r} = call double @{math_float2_fns[m]}(double {a1}, double {a2})")
                return r, FLOAT
            if m in math_const_fns:
                r = self.fresh()
                self.emit(f"{r} = call double @{math_const_fns[m]}()")
                return r, FLOAT
            if m in math_int_fns:
                a1, t1 = self.gen_expr(e.args[0])
                a2, t2 = self.gen_expr(e.args[1])
                a1 = self.coerce(a1, t1, INT)
                a2 = self.coerce(a2, t2, INT)
                r = self.fresh()
                self.emit(f"{r} = call i64 @{math_int_fns[m]}(i64 {a1}, i64 {a2})")
                return r, INT
        if top_mod == "string":
            string_consts = {
                "ascii_letters": "py_string_ascii_letters",
                "ascii_lowercase": "py_string_ascii_lowercase",
                "ascii_uppercase": "py_string_ascii_uppercase",
                "digits": "py_string_digits",
                "hexdigits": "py_string_hexdigits",
                "octdigits": "py_string_octdigits",
                "punctuation": "py_string_punctuation",
                "whitespace": "py_string_whitespace",
            }
            if m in string_consts:
                r = self.fresh()
                self.emit(f"{r} = call ptr @{string_consts[m]}()")
                return r, STR
        # User module: direct function call
        if e.method in self.func_names:
            return self.gen_user_call(e.method, e)
        raise CodeGenError(f"unsupported module method '{m}' on {mod_name}", e.line)

    def coerce(self, value, src, dst):
        if src == dst or dst is None:
            return value
        if dst == BOOL:
            return self.to_bool(value, src)
        if src == BOOL and dst == INT:
            r = self.fresh()
            self.emit(f"{r} = zext i1 {value} to i64")
            return r
        if src == BOOL and dst == FLOAT:
            r = self.fresh()
            self.emit(f"{r} = sitofp i1 {value} to double")
            return r
        if src == INT and dst == FLOAT:
            r = self.fresh()
            self.emit(f"{r} = sitofp i64 {value} to double")
            return r
        if src == FLOAT and dst == INT:
            r = self.fresh()
            self.emit(f"{r} = fptosi double {value} to i64")
            return r
        if src == INT and dst == STR:
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_int_to_str(i64 {value})")
            return r
        if src == FLOAT and dst == STR:
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_float_to_str(double {value})")
            return r
        if src == BOOL and dst == STR:
            r = self.fresh()
            i = self.fresh()
            self.emit(f"{i} = zext i1 {value} to i64")
            self.emit(f"{r} = call ptr @py_int_to_str(i64 {i})")
            return r
        if src == NONE:
            # NONE may mean either Python's None or an unknown-typed value
            # read from a list with unknown element type. Preserve the bits:
            # i64 -> ptr via inttoptr, i64 -> double via bitcast.
            if isinstance(dst, tuple) or dst == STR:
                r = self.fresh()
                self.emit(f"{r} = inttoptr i64 {value} to ptr")
                return r
            if dst == FLOAT:
                r = self.fresh()
                self.emit(f"{r} = bitcast i64 {value} to double")
                return r
            if dst == BOOL:
                r = self.fresh()
                self.emit(f"{r} = icmp ne i64 {value}, 0")
                return r
            # INT or default: the value is already i64.
            return value
        if dst == NONE:
            return "0"
        return value

    def to_bool(self, value, t):
        if t == BOOL:
            return value
        if t == INT:
            r = self.fresh()
            self.emit(f"{r} = icmp ne i64 {value}, 0")
            return r
        if t == FLOAT:
            r = self.fresh()
            self.emit(f"{r} = fcmp one double {value}, 0.0")
            return r
        if t == STR:
            lr = self.fresh()
            self.emit(f"{lr} = call i64 @strlen(ptr {value})")
            r = self.fresh()
            self.emit(f"{r} = icmp ne i64 {lr}, 0")
            return r
        if is_list_type(t):
            lr = self.fresh()
            self.emit(f"{lr} = call i64 @py_list_len(ptr {value})")
            r = self.fresh()
            self.emit(f"{r} = icmp ne i64 {lr}, 0")
            return r
        if is_obj_type(t) or is_tuple_type(t) or isinstance(t, tuple):
            r = self.fresh()
            self.emit(f"{r} = icmp ne ptr {value}, null")
            return r
        if t == NONE:
            return "false"
        r = self.fresh()
        self.emit(f"{r} = icmp ne i64 {value}, 0")
        return r

    def gen_unary(self, e):
        val, t = self.gen_expr(e.operand)
        if e.op == "not":
            b = self.to_bool(val, t)
            r = self.fresh()
            self.emit(f"{r} = xor i1 {b}, true")
            return r, BOOL
        if e.op == "+":
            base = numeric_base(t)
            if base == INT:
                return self.coerce(val, t, INT), INT
            if base == FLOAT:
                return self.coerce(val, t, FLOAT), FLOAT
            raise CodeGenError(f"unary '+' on {t}", e.line)
        if e.op == "-":
            base = numeric_base(t)
            if base == INT:
                v = self.coerce(val, t, INT)
                r = self.fresh()
                self.emit(f"{r} = sub i64 0, {v}")
                return r, INT
            if base == FLOAT:
                v = self.coerce(val, t, FLOAT)
                r = self.fresh()
                self.emit(f"{r} = fneg double {v}")
                return r, FLOAT
            raise CodeGenError(f"unary '-' on {t}", e.line)
        raise CodeGenError(f"unknown unary op {e.op}", e.line)

    def gen_boolop(self, e):
        lv, lt = self.gen_expr(e.left)
        lb = self.to_bool(lv, lt)
        rhs_label = self.fresh_label("bool.rhs")
        end_label = self.fresh_label("bool.end")
        entry_label = self.current_label
        if e.op == "and":
            self.cbr(lb, rhs_label, end_label)
        else:
            self.cbr(lb, end_label, rhs_label)
        self.place_block(rhs_label)
        rv, rt = self.gen_expr(e.right)
        rb = self.to_bool(rv, rt)
        rhs_label_actual = self.current_label
        self.br(end_label)
        self.place_block(end_label)
        phi = self.fresh()
        if e.op == "and":
            self.emit(f"{phi} = phi i1 [false, %{entry_label}], [{rb}, %{rhs_label_actual}]")
        else:
            self.emit(f"{phi} = phi i1 [true, %{entry_label}], [{rb}, %{rhs_label_actual}]")
        return phi, BOOL

    def gen_ifexp(self, e):
        cv, ct = self.gen_expr(e.cond)
        cb = self.to_bool(cv, ct)
        then_label = self.fresh_label("tern.then")
        else_label = self.fresh_label("tern.else")
        end_label = self.fresh_label("tern.end")
        self.cbr(cb, then_label, else_label)
        self.place_block(then_label)
        tv, tt = self.gen_expr(e.then)
        restype = getattr(e, "type", tt)
        tv2 = self.coerce(tv, tt, restype)
        if not self.terminated:
            self.br(end_label)
        then_end_label = self.current_label
        self.place_block(else_label)
        ev, et = self.gen_expr(e.else_)
        ev2 = self.coerce(ev, et, restype)
        if not self.terminated:
            self.br(end_label)
        else_end_label = self.current_label
        self.place_block(end_label)
        phi = self.fresh()
        self.emit(f"{phi} = phi {llvm_type(restype)} [{tv2}, %{then_end_label}], [{ev2}, %{else_end_label}]")
        return phi, restype

    def gen_binop(self, op, lv, lt, rv, rt, result_type, line):
        if op in ("==", "!=", "<", ">", "<=", ">="):
            return self.gen_compare(op, lv, lt, rv, rt, line), BOOL
        # `in` / `not in` on a set: use py_set_contains
        if op in ("in", "not in") and is_obj_type(rt) and rt[1] == "set":
            if lt == INT:
                r = self.fresh()
                self.emit(f"{r} = call i32 @py_set_contains_int(ptr {rv}, i64 {lv})")
            else:
                lstr = self.coerce(lv, lt, STR)
                r = self.fresh()
                self.emit(f"{r} = call i32 @py_set_contains_str(ptr {rv}, ptr {lstr})")
            b = self.fresh()
            self.emit(f"{b} = icmp ne i32 {r}, 0")
            if op == "not in":
                nb = self.fresh()
                self.emit(f"{nb} = xor i1 {b}, true")
                b = nb
            return b, BOOL
        # `in` / `not in` on a list: linear scan
        if op in ("in", "not in") and is_list_type(rt):
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @py_list_len(ptr {rv})")
            et = list_elem_type(rt) if list_elem_type(rt) else INT
            i_slot = self.fresh()
            self.insert_alloca(f"{i_slot} = alloca i64")
            self.emit(f"store i64 0, ptr {i_slot}")
            # Need a flag alloca to track if found
            found_slot = self.fresh()
            self.insert_alloca(f"{found_slot} = alloca i1")
            self.emit(f"store i1 0, ptr {found_slot}")
            cond = self.fresh_label("in.cond")
            body = self.fresh_label("in.body")
            end = self.fresh_label("in.end")
            self.br(cond)
            self.place_block(cond)
            ci = self.fresh()
            self.emit(f"{ci} = load i64, ptr {i_slot}")
            cmp = self.fresh()
            self.emit(f"{cmp} = icmp slt i64 {ci}, {lenr}")
            self.cbr(cmp, body, end)
            self.place_block(body)
            ev = self._list_get_typed(rv, ci, et, line)
            # Compare lv == ev
            cv = self.gen_compare("==", lv, lt, ev, et, line)
            cvi = self.fresh()
            self.emit(f"{cvi} = zext i1 {cv} to i1")
            cur = self.fresh()
            self.emit(f"{cur} = load i1, ptr {found_slot}")
            newf = self.fresh()
            self.emit(f"{newf} = or i1 {cur}, {cvi}")
            self.emit(f"store i1 {newf}, ptr {found_slot}")
            ci2 = self.fresh()
            self.emit(f"{ci2} = load i64, ptr {i_slot}")
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {ci2}, 1")
            self.emit(f"store i64 {nxt}, ptr {i_slot}")
            self.br(cond)
            self.place_block(end)
            found = self.fresh()
            self.emit(f"{found} = load i1, ptr {found_slot}")
            if op == "not in":
                nb = self.fresh()
                self.emit(f"{nb} = xor i1 {found}, true")
                found = nb
            return found, BOOL
        # `in` / `not in` on a string: substring search (or single char)
        if op in ("in", "not in") and rt == STR:
            # Use strstr (POSIX, available via <string.h>)
            r = self.fresh()
            self.emit(f"{r} = call ptr @strstr(ptr {rv}, ptr {lv})")
            nonzero = self.fresh()
            self.emit(f"{nonzero} = icmp ne ptr {r}, null")
            if op == "not in":
                nb = self.fresh()
                self.emit(f"{nb} = xor i1 {nonzero}, true")
                nonzero = nb
            return nonzero, BOOL
        # `in` / `not in` on a dict: check if the key exists
        if op in ("in", "not in") and isinstance(rt, tuple) and rt[0] == "dict":
            lstr = self.coerce(lv, lt, STR)
            r = self.fresh()
            self.emit(f"{r} = call i32 @py_dict_contains(ptr {rv}, ptr {lstr})")
            b = self.fresh()
            self.emit(f"{b} = icmp ne i32 {r}, 0")
            if op == "not in":
                nb = self.fresh()
                self.emit(f"{nb} = xor i1 {b}, true")
                b = nb
            return b, BOOL
        # `in` / `not in` on a tuple: linear scan (tuples are PyList at runtime)
        if op in ("in", "not in") and is_tuple_type(rt):
            # Same as list
            lenr = self.fresh()
            self.emit(f"{lenr} = call i64 @py_list_len(ptr {rv})")
            et = list_elem_type(("list", rt[1][0] if rt[1] else NONE))
            if et is None:
                et = INT
            i_slot = self.fresh()
            self.insert_alloca(f"{i_slot} = alloca i64")
            self.emit(f"store i64 0, ptr {i_slot}")
            found_slot = self.fresh()
            self.insert_alloca(f"{found_slot} = alloca i1")
            self.emit(f"store i1 0, ptr {found_slot}")
            cond = self.fresh_label("in.cond")
            body = self.fresh_label("in.body")
            end = self.fresh_label("in.end")
            self.br(cond)
            self.place_block(cond)
            ci = self.fresh()
            self.emit(f"{ci} = load i64, ptr {i_slot}")
            cmp = self.fresh()
            self.emit(f"{cmp} = icmp slt i64 {ci}, {lenr}")
            self.cbr(cmp, body, end)
            self.place_block(body)
            ev = self._list_get_typed(rv, ci, et, line)
            cv = self.gen_compare("==", lv, lt, ev, et, line)
            cvi = self.fresh()
            self.emit(f"{cvi} = zext i1 {cv} to i1")
            cur = self.fresh()
            self.emit(f"{cur} = load i1, ptr {found_slot}")
            newf = self.fresh()
            self.emit(f"{newf} = or i1 {cur}, {cvi}")
            self.emit(f"store i1 {newf}, ptr {found_slot}")
            ci2 = self.fresh()
            self.emit(f"{ci2} = load i64, ptr {i_slot}")
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {ci2}, 1")
            self.emit(f"store i64 {nxt}, ptr {i_slot}")
            self.br(cond)
            self.place_block(end)
            found = self.fresh()
            self.emit(f"{found} = load i1, ptr {found_slot}")
            if op == "not in":
                nb = self.fresh()
                self.emit(f"{nb} = xor i1 {found}, true")
                found = nb
            return found, BOOL
        if op == "+" and result_type == STR:
            return self._call("py_str_concat", [lv, rv], [STR, STR], STR), STR
        if op == "*" and result_type == STR:
            if lt == STR:
                n = self.coerce(rv, rt, INT)
                return self._call("py_str_mul", [lv, n], [STR, INT], STR), STR
            n = self.coerce(lv, lt, INT)
            return self._call("py_str_mul", [rv, n], [STR, INT], STR), STR
        # List concatenation: list + list
        if op == "+" and is_list_type(result_type):
            return self.gen_list_concat(lv, rv, result_type), result_type
        # List repetition: list * int or int * list
        if op == "*" and is_list_type(result_type):
            if is_list_type(lt):
                lst, n = lv, self.coerce(rv, rt, INT)
            else:
                lst, n = rv, self.coerce(lv, lt, INT)
            return self.gen_list_repeat(lst, n, result_type), result_type
        return self.gen_arith(op, lv, lt, rv, rt, result_type, line)

    def gen_list_concat(self, lv, rv, list_type):
        et = list_elem_type(list_type)
        result = self.fresh()
        self.emit(f"{result} = call ptr @py_list_new()")
        self.emit(f"call void @py_list_set_kind(ptr {result}, i32 {list_kind_tag(et)})")
        lenl = self.fresh()
        self.emit(f"{lenl} = call i64 @py_list_len(ptr {lv})")
        i_slot = self.fresh()
        self.insert_alloca(f"{i_slot} = alloca i64")
        self.emit(f"store i64 0, ptr {i_slot}")
        cond = self.fresh_label("concat.l.cond")
        body = self.fresh_label("concat.l.body")
        cont = self.fresh_label("concat.l.cont")
        end = self.fresh_label("concat.l.end")
        self.br(cond)
        self.place_block(cond)
        ci = self.fresh()
        self.emit(f"{ci} = load i64, ptr {i_slot}")
        cmp = self.fresh()
        self.emit(f"{cmp} = icmp slt i64 {ci}, {lenl}")
        self.cbr(cmp, body, end)
        self.place_block(body)
        self._list_get_and_append(lv, ci, result, et)
        self.br(cont)
        self.place_block(cont)
        ci2 = self.fresh()
        self.emit(f"{ci2} = load i64, ptr {i_slot}")
        nxt = self.fresh()
        self.emit(f"{nxt} = add i64 {ci2}, 1")
        self.emit(f"store i64 {nxt}, ptr {i_slot}")
        self.br(cond)
        self.place_block(end)
        # Now append elements from rv
        lenr = self.fresh()
        self.emit(f"{lenr} = call i64 @py_list_len(ptr {rv})")
        self.emit(f"store i64 0, ptr {i_slot}")
        cond2 = self.fresh_label("concat.r.cond")
        body2 = self.fresh_label("concat.r.body")
        cont2 = self.fresh_label("concat.r.cont")
        end2 = self.fresh_label("concat.r.end")
        self.br(cond2)
        self.place_block(cond2)
        ci3 = self.fresh()
        self.emit(f"{ci3} = load i64, ptr {i_slot}")
        cmp2 = self.fresh()
        self.emit(f"{cmp2} = icmp slt i64 {ci3}, {lenr}")
        self.cbr(cmp2, body2, end2)
        self.place_block(body2)
        self._list_get_and_append(rv, ci3, result, et)
        self.br(cont2)
        self.place_block(cont2)
        ci4 = self.fresh()
        self.emit(f"{ci4} = load i64, ptr {i_slot}")
        nxt2 = self.fresh()
        self.emit(f"{nxt2} = add i64 {ci4}, 1")
        self.emit(f"store i64 {nxt2}, ptr {i_slot}")
        self.br(cond2)
        self.place_block(end2)
        return result

    def _list_get_and_append(self, src_list, idx, dst_list, elem_type):
        if elem_type == INT or elem_type == BOOL:
            ev = self.fresh()
            self.emit(f"{ev} = call i64 @py_list_get_int(ptr {src_list}, i64 {idx})")
            self.emit(f"call void @py_list_append_int(ptr {dst_list}, i64 {ev})")
        elif elem_type == FLOAT:
            ev = self.fresh()
            self.emit(f"{ev} = call double @py_list_get_float(ptr {src_list}, i64 {idx})")
            self.emit(f"call void @py_list_append_float(ptr {dst_list}, double {ev})")
        elif elem_type == STR:
            ev = self.fresh()
            self.emit(f"{ev} = call ptr @py_list_get_str(ptr {src_list}, i64 {idx})")
            self.emit(f"call void @py_list_append_str(ptr {dst_list}, ptr {ev})")
        elif is_list_type(elem_type):
            ev = self.fresh()
            self.emit(f"{ev} = call ptr @py_list_get_list(ptr {src_list}, i64 {idx})")
            self.emit(f"call void @py_list_append_list(ptr {dst_list}, ptr {ev})")

    def gen_list_repeat(self, lst, n, list_type):
        et = list_elem_type(list_type)
        result = self.fresh()
        self.emit(f"{result} = call ptr @py_list_new()")
        self.emit(f"call void @py_list_set_kind(ptr {result}, i32 {list_kind_tag(et)})")
        # Loop n times
        i_slot = self.fresh()
        self.insert_alloca(f"{i_slot} = alloca i64")
        self.emit(f"store i64 0, ptr {i_slot}")
        cond = self.fresh_label("rep.cond")
        body = self.fresh_label("rep.body")
        cont = self.fresh_label("rep.cont")
        end = self.fresh_label("rep.end")
        self.br(cond)
        self.place_block(cond)
        ci = self.fresh()
        self.emit(f"{ci} = load i64, ptr {i_slot}")
        cmp = self.fresh()
        self.emit(f"{cmp} = icmp slt i64 {ci}, {n}")
        self.cbr(cmp, body, end)
        self.place_block(body)
        # Inner loop: copy all elements from lst
        lenl = self.fresh()
        self.emit(f"{lenl} = call i64 @py_list_len(ptr {lst})")
        j_slot = self.fresh()
        self.insert_alloca(f"{j_slot} = alloca i64")
        self.emit(f"store i64 0, ptr {j_slot}")
        icond = self.fresh_label("rep.inner.cond")
        ibody = self.fresh_label("rep.inner.body")
        icont = self.fresh_label("rep.inner.cont")
        iend = self.fresh_label("rep.inner.end")
        self.br(icond)
        self.place_block(icond)
        cj = self.fresh()
        self.emit(f"{cj} = load i64, ptr {j_slot}")
        icmp = self.fresh()
        self.emit(f"{icmp} = icmp slt i64 {cj}, {lenl}")
        self.cbr(icmp, ibody, iend)
        self.place_block(ibody)
        self._list_get_and_append(lst, cj, result, et)
        self.br(icont)
        self.place_block(icont)
        cj2 = self.fresh()
        self.emit(f"{cj2} = load i64, ptr {j_slot}")
        jnxt = self.fresh()
        self.emit(f"{jnxt} = add i64 {cj2}, 1")
        self.emit(f"store i64 {jnxt}, ptr {j_slot}")
        self.br(icond)
        self.place_block(iend)
        self.br(cont)
        self.place_block(cont)
        ci2 = self.fresh()
        self.emit(f"{ci2} = load i64, ptr {i_slot}")
        nxt = self.fresh()
        self.emit(f"{nxt} = add i64 {ci2}, 1")
        self.emit(f"store i64 {nxt}, ptr {i_slot}")
        self.br(cond)
        self.place_block(end)
        return result

    def gen_arith(self, op, lv, lt, rv, rt, result_type, line):
        if op == "/":
            if numeric_base(lt) == INT and numeric_base(rt) == INT:
                a = self.coerce(lv, lt, INT)
                b = self.coerce(rv, rt, INT)
                return self._call("py_idiv", [a, b], [INT, INT], FLOAT), FLOAT
            a = self.coerce(lv, lt, FLOAT)
            b = self.coerce(rv, rt, FLOAT)
            r = self.fresh()
            self.emit(f"{r} = fdiv double {a}, {b}")
            return r, FLOAT
        if op == "//":
            if numeric_base(lt) == INT and numeric_base(rt) == INT:
                a = self.coerce(lv, lt, INT)
                b = self.coerce(rv, rt, INT)
                return self._call("py_ifloordiv", [a, b], [INT, INT], INT), INT
            a = self.coerce(lv, lt, FLOAT)
            b = self.coerce(rv, rt, FLOAT)
            d = self.fresh()
            self.emit(f"{d} = fdiv double {a}, {b}")
            fl = self.fresh()
            self.emit(f"{fl} = call double @llvm.floor.f64(double {d})")
            return fl, FLOAT
        if op == "%":
            if numeric_base(lt) == INT and numeric_base(rt) == INT:
                a = self.coerce(lv, lt, INT)
                b = self.coerce(rv, rt, INT)
                return self._call("py_imod", [a, b], [INT, INT], INT), INT
            a = self.coerce(lv, lt, FLOAT)
            b = self.coerce(rv, rt, FLOAT)
            d = self.fresh()
            self.emit(f"{d} = fdiv double {a}, {b}")
            fl = self.fresh()
            self.emit(f"{fl} = call double @llvm.floor.f64(double {d})")
            mul = self.fresh()
            self.emit(f"{mul} = fmul double {fl}, {b}")
            res = self.fresh()
            self.emit(f"{res} = fsub double {a}, {mul}")
            return res, FLOAT
        if op == "**":
            if numeric_base(lt) == INT and numeric_base(rt) == INT:
                a = self.coerce(lv, lt, INT)
                b = self.coerce(rv, rt, INT)
                return self._call("py_ipow", [a, b], [INT, INT], INT), INT
            a = self.coerce(lv, lt, FLOAT)
            b = self.coerce(rv, rt, FLOAT)
            r = self.fresh()
            self.emit(f"{r} = call double @llvm.pow.f64(double {a}, double {b})")
            return r, FLOAT
        # +, -, *
        if result_type == FLOAT:
            a = self.coerce(lv, lt, FLOAT)
            b = self.coerce(rv, rt, FLOAT)
            r = self.fresh()
            self.emit(f"{r} = f{ {'+':'add','-':'sub','*':'mul'}[op] } double {a}, {b}")
            return r, FLOAT
        a = self.coerce(lv, lt, INT)
        b = self.coerce(rv, rt, INT)
        r = self.fresh()
        self.emit(f"{r} = { {'+':'add','-':'sub','*':'mul'}[op] } i64 {a}, {b}")
        return r, INT

    def gen_compare(self, op, lv, lt, rv, rt, line):
        if lt == STR and rt == STR:
            c = self.fresh()
            self.emit(f"{c} = call i32 @strcmp(ptr {lv}, ptr {rv})")
            m = {"==": "eq", "!=": "ne", "<": "slt", ">": "sgt", "<=": "sle", ">=": "sge"}
            r = self.fresh()
            self.emit(f"{r} = icmp {m[op]} i32 {c}, 0")
            return r
        # If one side has unknown type (NONE, from a list with unknown element
        # type), coerce it to the other side's type so the comparison works.
        if lt == NONE and rt is not None:
            lt = rt if rt in (INT, FLOAT, STR, BOOL) or isinstance(rt, tuple) else INT
            lv = self.coerce(lv, NONE, lt)
        if rt == NONE and lt is not None:
            rt = lt if lt in (INT, FLOAT, STR, BOOL) or isinstance(lt, tuple) else INT
            rv = self.coerce(rv, NONE, rt)
        b1 = numeric_base(lt)
        b2 = numeric_base(rt)
        if b1 is not None and b2 is not None:
            if b1 == FLOAT or b2 == FLOAT:
                a = self.coerce(lv, lt, FLOAT)
                b = self.coerce(rv, rt, FLOAT)
                m = {"==": "oeq", "!=": "one", "<": "olt", ">": "ogt", "<=": "ole", ">=": "oge"}
                r = self.fresh()
                self.emit(f"{r} = fcmp {m[op]} double {a}, {b}")
                return r
            a = self.coerce(lv, lt, INT)
            b = self.coerce(rv, rt, INT)
            m = {"==": "eq", "!=": "ne", "<": "slt", ">": "sgt", "<=": "sle", ">=": "sge"}
            r = self.fresh()
            self.emit(f"{r} = icmp {m[op]} i64 {a}, {b}")
            return r
        raise CodeGenError(f"comparison {op} between {lt} and {rt} not supported", line)

    def _call(self, name, args, argtypes, rettype):
        argstr = ", ".join(f"{llvm_type(t)} {v}" for v, t in zip(args, argtypes))
        if rettype == NONE:
            self.emit(f"call void @{name}({argstr})")
            return "0"
        r = self.fresh()
        self.emit(f"{r} = call {llvm_type(rettype)} @{name}({argstr})")
        return r

    # ---- calls ----
    def _resolve_call_name(self, name):
        """Resolve a function name, accounting for hoisted nested functions.
        Mirrors semantic.py's _resolve_call_name: walk up the enclosing chain
        to find a mangled name like Enclosing__name."""
        if name in self.funcs:
            return name
        if self.current_fn_name is not None:
            enc = self.current_fn_name
            while enc is not None:
                candidate = enc + "__" + name
                if candidate in self.funcs:
                    return candidate
                enc_fn = self.funcs.get(enc)
                enc = enc_fn.enclosing_func if enc_fn else None
        return name

    def gen_call(self, e):
        # Handle module.method(args) calls
        if isinstance(e.func, A.Attribute):
            mc = A.MethodCall(e.func.obj, e.func.attr, e.args, e.line, kwargs=e.kwargs)
            mc.type = getattr(e, 'type', None)
            return self.gen_method_call(mc)
        if not isinstance(e.func, A.Name):
            raise CodeGenError("only direct calls supported", e.line)
        name = e.func.name
        # Resolve hoisted nested function calls via the enclosing chain.
        name = self._resolve_call_name(name)
        # Object constructor: ClassName(args) -> py_object_new(class_id) + __init__
        if name in self.classes:
            return self.gen_constructor(name, e)
        if name in self.funcs:
            return self.gen_user_call(name, e)
        # Check if it's a variable holding a function reference (e.g., lambda)
        if name in self.locals:
            vtype = self.locals[name][1]
            if isinstance(vtype, tuple) and vtype[0] == "func":
                fn_name = vtype[1]
                if fn_name in self.funcs:
                    return self.gen_user_call(fn_name, e)
        if name == "print":
            return self.gen_print(e)
        if name in ("len", "abs", "int", "float", "str", "bool", "input", "min", "max",
                    "sum", "isinstance", "sorted", "range", "enumerate", "tuple", "set",
                    "hex", "oct", "bin", "chr", "ord", "round", "divmod", "repr",
                    "reversed", "any", "all", "zip", "type", "id", "hash", "format"):
            return self.gen_builtin(name, e)
        # Runtime constructors referenced via imported name (from collections import Counter).
        if name == "Counter":
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_counter_new()")
            return r, ("obj", "Counter")
        if name == "deque":
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_list_new()")
            return r, ("obj", "deque")
        # Exception type construction: Exception("msg"), ValueError("msg"), etc.
        from semantic import EXCEPTION_TYPES
        if name in EXCEPTION_TYPES:
            if e.args:
                v, t = self.gen_expr(e.args[0])
                if t == STR:
                    return v, STR
                # Convert to string
                v = self.coerce(v, t, STR)
                return v, STR
            return self.intern_string(""), STR
        raise CodeGenError(f"unknown function '{name}'", e.line)

    def gen_constructor(self, class_name, e):
        """ClassName(args) -> create object and call __init__."""
        class_id = self.class_ids.get(class_name, 0)
        obj = self.fresh()
        self.emit(f"{obj} = call ptr @py_object_new(i32 {class_id})")
        # Look for __init__ method (mangled name ClassName____init__).
        init_mangled = self.classes[class_name]["methods"].get("__init__")
        if init_mangled and init_mangled in self.funcs:
            fn = self.funcs[init_mangled]
            retty = fn.return_type
            argvals = [(obj, "ptr")]
            arg_idx = 0
            for a in e.args:
                if isinstance(a, A.Starred):
                    sv, st = self.gen_expr(a.value)
                    remaining = len(fn.params) - 1 - arg_idx
                    for j in range(remaining):
                        pt = fn.param_types[arg_idx + 1 + j]
                        et = list_elem_type(st) if is_list_type(st) else \
                             (st[1][j] if is_tuple_type(st) else NONE)
                        ev = self._list_get_typed(sv, j, et, a.line)
                        argvals.append((self.coerce(ev, et, pt), llvm_type(pt)))
                    arg_idx += remaining
                else:
                    if arg_idx + 1 >= len(fn.param_types):
                        break
                    pt = fn.param_types[arg_idx + 1]
                    v, t = self.gen_expr(a)
                    argvals.append((self.coerce(v, t, pt), llvm_type(pt)))
                    arg_idx += 1
            # Fill in defaults for missing args (including kwargs).
            kwarg_done = set()
            for k, vexpr in (e.kwargs or {}).items():
                if k in fn.params:
                    idx = fn.params.index(k)
                    v, t = self.gen_expr(vexpr)
                    pt = fn.param_types[idx]
                    while len(argvals) < idx:
                        pname = fn.params[len(argvals) - 1]
                        if pname in fn.defaults:
                            dv, dt = self.gen_expr(fn.defaults[pname])
                            dpt = fn.param_types[len(argvals) - 1]
                            argvals.append((self.coerce(dv, dt, dpt), llvm_type(dpt)))
                        else:
                            argvals.append(("null", "ptr"))
                    if len(argvals) <= idx:
                        while len(argvals) < idx:
                            argvals.append(("null", "ptr"))
                        argvals.append((self.coerce(v, t, pt), llvm_type(pt)))
                    else:
                        argvals[idx] = (self.coerce(v, t, pt), llvm_type(pt))
                    kwarg_done.add(k)
            # Fill remaining defaults.
            for k in range(arg_idx + 1, len(fn.params)):
                pname = fn.params[k]
                if pname in fn.defaults and pname not in kwarg_done:
                    v, t = self.gen_expr(fn.defaults[pname])
                    pt = fn.param_types[k]
                    if len(argvals) <= k:
                        while len(argvals) < k:
                            argvals.append(("null", "ptr"))
                        argvals.append((self.coerce(v, t, pt), llvm_type(pt)))
                    else:
                        argvals[k] = (self.coerce(v, t, pt), llvm_type(pt))
            argstr = ", ".join(f"{ty} {v}" for v, ty in argvals)
            if retty == NONE:
                self.emit(f"call void @fn_{init_mangled}({argstr})")
            else:
                r = self.fresh()
                self.emit(f"{r} = call {llvm_type(retty)} @fn_{init_mangled}({argstr})")
        return obj, ("obj", class_name)

    def gen_user_call(self, name, e):
        fn = self.funcs[name]
        retty = fn.return_type
        argvals = []
        arg_idx = 0
        for a in e.args:
            if isinstance(a, A.Starred):
                sv, st = self.gen_expr(a.value)
                remaining = len(fn.params) - arg_idx
                for j in range(remaining):
                    if arg_idx + j >= len(fn.param_types):
                        break
                    pt = fn.param_types[arg_idx + j]
                    et = list_elem_type(st) if is_list_type(st) else \
                         (st[1][j] if is_tuple_type(st) else NONE)
                    ev = self._list_get_typed(sv, j, et, a.line)
                    argvals.append((self.coerce(ev, et, pt), llvm_type(pt)))
                arg_idx += remaining
            else:
                if arg_idx >= len(fn.param_types):
                    break
                pt = fn.param_types[arg_idx]
                v, t = self.gen_expr(a)
                argvals.append((self.coerce(v, t, pt), llvm_type(pt)))
                arg_idx += 1
        # Fill in defaults for missing args.
        for k in range(arg_idx, len(fn.params)):
            pname = fn.params[k]
            if pname in fn.defaults:
                v, t = self.gen_expr(fn.defaults[pname])
                pt = fn.param_types[k]
                argvals.append((self.coerce(v, t, pt), llvm_type(pt)))
            elif k < len(fn.param_types):
                pt = fn.param_types[k]
                argvals.append((zero_value(pt), llvm_type(pt)))
        argstr = ", ".join(f"{ty} {v}" for v, ty in argvals)
        if retty == NONE:
            self.emit(f"call void @fn_{name}({argstr})")
            return "0", NONE
        r = self.fresh()
        self.emit(f"{r} = call {llvm_type(retty)} @fn_{name}({argstr})")
        return r, retty

    def gen_print(self, e):
        sep_expr = e.kwargs.get("sep")
        end_expr = e.kwargs.get("end")
        sep_is_none = isinstance(sep_expr, A.NoneLit)
        end_is_none = isinstance(end_expr, A.NoneLit)
        # Python evaluates all arguments (and sep/end) before printing any.
        evaluated = [self.gen_expr(a) for a in e.args]
        sep_val = self.gen_expr(sep_expr) if (sep_expr is not None and not sep_is_none) else None
        end_val = self.gen_expr(end_expr) if (end_expr is not None and not end_is_none) else None
        for i, (v, t) in enumerate(evaluated):
            if i > 0 and not sep_is_none:
                if sep_val is None:
                    self._print_str_const(" ")
                else:
                    self._print_value(*sep_val)
            self._print_value(v, t)
        if end_is_none:
            pass
        elif end_val is None:
            self._print_str_const("\n")
        else:
            self._print_value(*end_val)
        return "0", NONE

    def _print_str_const(self, s):
        p = self.intern_string(s)
        self.emit(f"call void @py_print_str(ptr {p})")

    def _print_value(self, v, t):
        if t == INT:
            self.emit(f"call void @py_print_int(i64 {v})")
        elif t == FLOAT:
            self.emit(f"call void @py_print_float(double {v})")
        elif t == STR:
            self.emit(f"call void @py_print_str(ptr {v})")
        elif t == BOOL:
            self.emit(f"call void @py_print_bool(i1 {v})")
        elif t == NONE:
            self.emit("call void @py_print_none()")
        elif is_list_type(t):
            self.emit(f"call void @py_list_print(ptr {v})")
        else:
            raise CodeGenError(f"cannot print value of type {t}")

    def gen_builtin(self, name, e):
        args = e.args
        if name == "len":
            v, t = self.gen_expr(args[0])
            if is_list_type(t) or is_tuple_type(t):
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_list_len(ptr {v})")
                return r, INT
            if is_obj_type(t) and t[1] == "Counter":
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_counter_len(ptr {v})")
                return r, INT
            if is_obj_type(t) and t[1] == "set":
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_set_len(ptr {v})")
                return r, INT
            v = self.coerce(v, t, STR)
            r = self.fresh()
            self.emit(f"{r} = call i64 @py_len(ptr {v})")
            return r, INT
        if name == "sum":
            v, t = self.gen_expr(args[0])
            et = list_elem_type(t) if is_list_type(t) else INT
            if et is None:
                et = INT
            if numeric_base(et) == FLOAT:
                n = self.fresh()
                self.emit(f"{n} = call i64 @py_list_len(ptr {v})")
                acc = self.fresh("sumacc")
                self.insert_alloca(f"{acc} = alloca double")
                self.emit(f"store double 0.0, ptr {acc}")
                i_slot = self.fresh("sumi")
                self.insert_alloca(f"{i_slot} = alloca i64")
                self.emit(f"store i64 0, ptr {i_slot}")
                cond_lbl = self.fresh_label("sumcond")
                body_lbl = self.fresh_label("sumbody")
                done_lbl = self.fresh_label("sumdone")
                self.br(cond_lbl)
                self.place_block(cond_lbl)
                iv = self.fresh()
                self.emit(f"{iv} = load i64, ptr {i_slot}")
                cmp = self.fresh()
                self.emit(f"{cmp} = icmp slt i64 {iv}, {n}")
                self.cbr(cmp, body_lbl, done_lbl)
                self.place_block(body_lbl)
                el = self.fresh()
                self.emit(f"{el} = call double @py_list_get_float(ptr {v}, i64 {iv})")
                cur = self.fresh()
                self.emit(f"{cur} = load double, ptr {acc}")
                newv = self.fresh()
                self.emit(f"{newv} = fadd double {cur}, {el}")
                self.emit(f"store double {newv}, ptr {acc}")
                nxt = self.fresh()
                self.emit(f"{nxt} = add i64 {iv}, 1")
                self.emit(f"store i64 {nxt}, ptr {i_slot}")
                self.br(cond_lbl)
                self.place_block(done_lbl)
                final = self.fresh()
                self.emit(f"{final} = load double, ptr {acc}")
                return final, FLOAT
            # int sum
            n = self.fresh()
            self.emit(f"{n} = call i64 @py_list_len(ptr {v})")
            acc = self.fresh("sumacc")
            self.insert_alloca(f"{acc} = alloca i64")
            self.emit(f"store i64 0, ptr {acc}")
            i_slot = self.fresh("sumi")
            self.insert_alloca(f"{i_slot} = alloca i64")
            self.emit(f"store i64 0, ptr {i_slot}")
            cond_lbl = self.fresh_label("sumcond")
            body_lbl = self.fresh_label("sumbody")
            done_lbl = self.fresh_label("sumdone")
            self.br(cond_lbl)
            self.place_block(cond_lbl)
            iv = self.fresh()
            self.emit(f"{iv} = load i64, ptr {i_slot}")
            cmp = self.fresh()
            self.emit(f"{cmp} = icmp slt i64 {iv}, {n}")
            self.cbr(cmp, body_lbl, done_lbl)
            self.place_block(body_lbl)
            el = self.fresh()
            self.emit(f"{el} = call i64 @py_list_get_int(ptr {v}, i64 {iv})")
            cur = self.fresh()
            self.emit(f"{cur} = load i64, ptr {acc}")
            newv = self.fresh()
            self.emit(f"{newv} = add i64 {cur}, {el}")
            self.emit(f"store i64 {newv}, ptr {acc}")
            nxt = self.fresh()
            self.emit(f"{nxt} = add i64 {iv}, 1")
            self.emit(f"store i64 {nxt}, ptr {i_slot}")
            self.br(cond_lbl)
            self.place_block(done_lbl)
            final = self.fresh()
            self.emit(f"{final} = load i64, ptr {acc}")
            return final, INT
        if name == "sorted":
            v, t = self.gen_expr(args[0])
            et = list_elem_type(t) if is_list_type(t) else INT
            if et is None:
                et = INT
            n = self.fresh()
            self.emit(f"{n} = call i64 @py_list_len(ptr {v})")
            copy = self.fresh()
            if numeric_base(et) == FLOAT:
                self.emit(f"{copy} = call ptr @py_list_slice_float(ptr {v}, i64 0, i64 {n})")
                self.emit(f"call void @py_list_sort_float(ptr {copy})")
                return copy, ("list", FLOAT)
            elif et == STR:
                self.emit(f"{copy} = call ptr @py_list_slice_str(ptr {v}, i64 0, i64 {n})")
                self.emit(f"call void @py_list_sort_str(ptr {copy})")
                return copy, ("list", STR)
            else:
                self.emit(f"{copy} = call ptr @py_list_slice_int(ptr {v}, i64 0, i64 {n})")
                self.emit(f"call void @py_list_sort_int(ptr {copy})")
                return copy, ("list", INT)
        if name == "isinstance":
            # Minimal stub: return False (not used meaningfully in supported programs).
            return "false", BOOL
        if name == "abs":
            v, t = self.gen_expr(args[0])
            if numeric_base(t) == INT:
                a = self.coerce(v, t, INT)
                c = self.fresh()
                self.emit(f"{c} = icmp slt i64 {a}, 0")
                neg = self.fresh()
                self.emit(f"{neg} = sub i64 0, {a}")
                r = self.fresh()
                self.emit(f"{r} = select i1 {c}, i64 {neg}, i64 {a}")
                return r, INT
            if numeric_base(t) == FLOAT:
                a = self.coerce(v, t, FLOAT)
                r = self.fresh()
                self.emit(f"{r} = call double @llvm.fabs.f64(double {a})")
                return r, FLOAT
            raise CodeGenError("abs() expects numeric", e.line)
        if name == "int":
            v, t = self.gen_expr(args[0])
            if t == STR:
                r = self.fresh()
                self.emit(f"{r} = call i64 @py_int_parse(ptr {v})")
                return r, INT
            if numeric_base(t) is not None:
                return self.coerce(v, t, INT), INT
            if t == NONE:
                return "0", INT
            raise CodeGenError("int() conversion not supported", e.line)
        if name == "float":
            v, t = self.gen_expr(args[0])
            if t == STR:
                r = self.fresh()
                self.emit(f"{r} = call double @py_float_parse(ptr {v})")
                return r, FLOAT
            if numeric_base(t) is not None:
                return self.coerce(v, t, FLOAT), FLOAT
            if t == NONE:
                return "0.0", FLOAT
            raise CodeGenError("float() conversion not supported", e.line)
        if name == "str":
            v, t = self.gen_expr(args[0])
            if t == INT:
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_int_to_str(i64 {v})")
                return r, STR
            if t == FLOAT:
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_float_to_str(double {v})")
                return r, STR
            if t == BOOL:
                tn = self.intern_string("True")
                fn = self.intern_string("False")
                r = self.fresh()
                self.emit(f"{r} = select i1 {v}, ptr {tn}, ptr {fn}")
                return r, STR
            if t == STR:
                return v, STR
            if t == NONE:
                return self.intern_string("None"), STR
            if is_list_type(t):
                r = self.fresh()
                self.emit(f"{r} = call ptr @py_list_to_str(ptr {v})")
                return r, STR
            raise CodeGenError("str() conversion not supported", e.line)
        if name == "bool":
            v, t = self.gen_expr(args[0])
            return self.to_bool(v, t), BOOL
        if name == "input":
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_input()")
            return r, STR
        if name in ("min", "max"):
            return self.gen_minmax(name, args, e.line)
        if name == "set":
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_set_new()")
            return r, ("obj", "set")
        if name == "hex":
            v, t = self.gen_expr(args[0])
            v = self.coerce(v, t, INT)
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_hex(i64 {v})")
            return r, STR
        if name == "oct":
            v, t = self.gen_expr(args[0])
            v = self.coerce(v, t, INT)
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_oct(i64 {v})")
            return r, STR
        if name == "bin":
            v, t = self.gen_expr(args[0])
            v = self.coerce(v, t, INT)
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_bin(i64 {v})")
            return r, STR
        if name == "chr":
            v, t = self.gen_expr(args[0])
            v = self.coerce(v, t, INT)
            r = self.fresh()
            self.emit(f"{r} = call ptr @py_chr(i64 {v})")
            return r, STR
        if name == "ord":
            v, t = self.gen_expr(args[0])
            r = self.fresh()
            self.emit(f"{r} = call i64 @py_ord(ptr {v})")
            return r, INT
        if name == "round":
            v, t = self.gen_expr(args[0])
            if t == FLOAT:
                if len(args) > 1:
                    n, nt = self.gen_expr(args[1])
                    n = self.coerce(n, nt, INT)
                    r = self.fresh()
                    self.emit(f"{r} = call double @py_round(double {v}, i64 {n})")
                    return r, FLOAT
                else:
                    r = self.fresh()
                    self.emit(f"{r} = call i64 @py_round_int(double {v})")
                    return r, INT
            return v, t
        raise CodeGenError(f"builtin {name} not supported", e.line)

    def gen_minmax(self, name, args, line):
        if len(args) < 2:
            raise CodeGenError(f"{name}() expects at least 2 arguments", line)
        types = [getattr(a, "type", None) for a in args]
        target = FLOAT if any(numeric_base(t) == FLOAT for t in types) else INT
        best, bt = self.gen_expr(args[0])
        best = self.coerce(best, bt, target)
        for a in args[1:]:
            v, t = self.gen_expr(a)
            v = self.coerce(v, t, target)
            cond = self.fresh()
            if target == INT:
                op = "slt" if name == "min" else "sgt"
                self.emit(f"{cond} = icmp {op} i64 {v}, {best}")
            else:
                op = "olt" if name == "min" else "ogt"
                self.emit(f"{cond} = fcmp {op} double {v}, {best}")
            sel = self.fresh()
            self.emit(f"{sel} = select i1 {cond}, {llvm_type(target)} {v}, {llvm_type(target)} {best}")
            best = sel
        return best, target


def generate(info):
    return CodeGen(info).generate()
