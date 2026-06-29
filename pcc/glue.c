/* glue.c — Hybrid Python Compiler: A+B route bridge
 *
 * This file links our compiled Python program against the system
 * libpython (route A). The compiler emits native LLVM IR for everything
 * it knows how to handle. Anything it doesn't (e.g. a C extension
 * imported as `import numpy`, an unknown method, a dynamic getattr) is
 * dispatched to this glue, which uses libpython to interpret that
 * piece. The result: 100% Python compatibility with native speed
 * wherever possible.
 */
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>

static PyObject *py_main_module = NULL;
static PyObject *py_main_dict = NULL;

/* Initialize the embedded interpreter. */
void py_embed_init(int argc, char **argv) {
    Py_Initialize();
    if (!Py_IsInitialized()) return;
    wchar_t **wargv = (wchar_t **)calloc((size_t)argc + 1, sizeof(wchar_t *));
    for (int i = 0; i < argc; i++) {
        size_t len = mbstowcs(NULL, argv[i], 0);
        if (len == (size_t)-1) { wargv[i] = (wchar_t *)L""; continue; }
        wargv[i] = (wchar_t *)calloc(len + 1, sizeof(wchar_t));
        mbstowcs(wargv[i], argv[i], len + 1);
    }
    PySys_SetArgv(argc, wargv);
    for (int i = 0; i < argc; i++) free(wargv[i]);
    free(wargv);
    /* Make `import <local_module>` work when the user runs the binary from
     * a different directory: prepend argv[0]'s directory and the current
     * working directory to sys.path. This is what CPython does for scripts
     * launched as `python script.py`. */
    if (argc > 0 && argv[0]) {
        const char *p = argv[0];
        const char *slash = strrchr(p, '/');
        char buf[4096];
        if (slash) {
            size_t n = (size_t)(slash - p);
            if (n >= sizeof(buf)) n = sizeof(buf) - 1;
            memcpy(buf, p, n);
            buf[n] = '\0';
            PyRun_SimpleString("import sys, os\n"
                               "exe_dir = os.path.dirname(os.path.abspath(sys.argv[0]))\n"
                               "if exe_dir and exe_dir not in sys.path:\n"
                               "    sys.path.insert(0, exe_dir)\n");
        }
    }
    /* Also add the current working directory so `import test` works when
     * the user runs ./prog from the project root. */
    PyRun_SimpleString("import sys, os\n"
                       "cwd = os.getcwd()\n"
                       "if cwd and cwd not in sys.path:\n"
                       "    sys.path.insert(0, cwd)\n");
    py_main_module = PyImport_AddModule("__main__");
    if (py_main_module) py_main_dict = PyModule_GetDict(py_main_module);
}

void py_embed_finalize(void) {
    if (Py_IsInitialized()) Py_Finalize();
}

/* ====== boxing: native C → PyObject* ====== */
PyObject *py_int_to_pyobject(long v) { return PyLong_FromLong(v); }
PyObject *py_float_to_pyobject(double v) { return PyFloat_FromDouble(v); }
PyObject *py_bool_to_pyobject(int v) { v = !!v; return v ? Py_True : Py_False; }
PyObject *py_str_to_pyobject(const char *s) {
    if (!s) { Py_INCREF(Py_None); return Py_None; }
    return PyUnicode_FromString(s);
}
PyObject *py_none_to_pyobject(void) { Py_INCREF(Py_None); return Py_None; }

/* Convert opaque ptr that we treat as a Python list/dict/set to a
 * PyObject*. For the hybrid bridge, we lazily create a Python list of
 * the int contents of our native PyList. */
PyObject *py_native_list_to_pylist(void *l, int elem_kind) {
    /* Placeholder: not used in current codegen paths. */
    (void)l; (void)elem_kind;
    return PyList_New(0);
}

/* Conversion helpers for the hybrid A-route: turn our native PyList*
 * (whose element layout matches runtime.c) into a real CPython list.
 * These are used when passing native lists as args to libpython. */
struct PyListHeader;  /* opaque, defined in runtime.c */
extern long py_list_len(void *l);
extern long py_list_get_int(void *l, long i);
extern const char *py_list_get_str(void *l, long i);
extern double py_list_get_float(void *l, long i);

/* Forward declarations for nested conversion. */
PyObject *py_list_int_to_pylist(void *l);
PyObject *py_list_str_to_pylist(void *l);
PyObject *py_list_float_to_pylist(void *l);
int py_list_get_kind(void *l);
long py_list_len(void *l);
long py_list_get_int(void *l, long i);
double py_list_get_float(void *l, long i);
const char *py_list_get_str(void *l, long i);
void *py_list_get_list(void *l, long i);

PyObject *py_list_int_to_pylist(void *l) {
    if (!l) return PyList_New(0);
    long n = py_list_len(l);
    PyObject *list = PyList_New(n);
    int kind = py_list_get_kind(l);
    for (long i = 0; i < n; i++) {
        PyObject *v;
        if (kind == 4 /* LE_LIST */) {
            v = py_list_int_to_pylist(py_list_get_list(l, i));
        } else {
            v = PyLong_FromLong(py_list_get_int(l, i));
        }
        PyList_SET_ITEM(list, i, v);
    }
    return list;
}
PyObject *py_list_str_to_pylist(void *l) {
    if (!l) return PyList_New(0);
    long n = py_list_len(l);
    PyObject *list = PyList_New(n);
    for (long i = 0; i < n; i++) {
        const char *s = py_list_get_str(l, i);
        PyObject *v = PyUnicode_FromString(s ? s : "");
        PyList_SET_ITEM(list, i, v);
    }
    return list;
}
PyObject *py_list_float_to_pylist(void *l) {
    if (!l) return PyList_New(0);
    long n = py_list_len(l);
    PyObject *list = PyList_New(n);
    for (long i = 0; i < n; i++) {
        PyObject *v = PyFloat_FromDouble(py_list_get_float(l, i));
        PyList_SET_ITEM(list, i, v);
    }
    return list;
}

/* ====== unboxing: PyObject* → native C ====== */
long py_object_to_int(PyObject *o) {
    if (!o) return 0;
    if (PyLong_Check(o)) return PyLong_AsLong(o);
    if (PyFloat_Check(o)) return (long)PyFloat_AsDouble(o);
    if (PyUnicode_Check(o)) return (long)PyLong_AsLong(PyNumber_Long(o));
    if (PyNumber_Check(o)) {
        PyObject *n = PyNumber_Long(o);
        if (n) { long v = PyLong_AsLong(n); Py_DECREF(n); return v; }
    }
    return 0;
}
double py_object_to_float(PyObject *o) {
    if (!o) return 0.0;
    if (PyFloat_Check(o)) return PyFloat_AsDouble(o);
    if (PyLong_Check(o)) return (double)PyLong_AsLong(o);
    return 0.0;
}
const char *py_object_to_str(PyObject *o) {
    if (!o) return "";
    PyObject *s = PyObject_Str(o);
    if (!s) return "";
    const char *r = PyUnicode_AsUTF8(s);
    Py_DECREF(s);
    return r ? r : "";
}
int py_object_to_bool(PyObject *o) {
    if (!o) return 0;
    return PyObject_IsTrue(o);
}

/* ====== type checks ====== */
int py_is_int(PyObject *o) { return o && PyLong_Check(o); }
int py_is_float(PyObject *o) { return o && PyFloat_Check(o); }
int py_is_str(PyObject *o) { return o && PyUnicode_Check(o); }
int py_is_list(PyObject *o) { return o && PyList_Check(o); }
int py_is_dict(PyObject *o) { return o && PyDict_Check(o); }
int py_is_none(PyObject *o) { return o == Py_None; }

/* ====== module / attribute / item access ====== */
PyObject *py_fallback_import(const char *name) {
    PyObject *m = PyImport_ImportModule(name);
    if (!m) PyErr_Print();
    return m;
}
PyObject *py_fallback_getattr(PyObject *obj, const char *name) {
    if (!obj) return NULL;
    PyObject *r = PyObject_GetAttrString(obj, name);
    if (!r) PyErr_Clear();
    return r;
}
int py_fallback_setattr(PyObject *obj, const char *name, PyObject *val) {
    if (!obj) return -1;
    int r = PyObject_SetAttrString(obj, name, val);
    if (r < 0) PyErr_Print();
    return r;
}
PyObject *py_fallback_getitem(PyObject *obj, PyObject *key) {
    if (!obj) return NULL;
    PyObject *r = PyObject_GetItem(obj, key);
    if (!r) PyErr_Clear();
    return r;
}
int py_fallback_setitem(PyObject *obj, PyObject *key, PyObject *val) {
    if (!obj) return -1;
    int r = PyObject_SetItem(obj, key, val);
    if (r < 0) PyErr_Print();
    return r;
}
int py_fallback_delitem(PyObject *obj, PyObject *key) {
    if (!obj) return -1;
    int r = PyObject_DelItem(obj, key);
    if (r < 0) PyErr_Print();
    return r;
}

/* ====== function calls ====== */
/* Build a tuple of args from a NULL-terminated array of PyObject*. */
PyObject *_py_make_args(PyObject **args, int n) {
    PyObject *t = PyTuple_New(n);
    for (int i = 0; i < n; i++) {
        if (args[i]) Py_INCREF(args[i]);
        PyTuple_SET_ITEM(t, i, args[i] ? args[i] : Py_None);
    }
    return t;
}
PyObject *py_call_obj(PyObject *callable, PyObject **args, int nargs) {
    if (!callable) return NULL;
    PyObject *tup = _py_make_args(args, nargs);
    /* Unpack the tuple as positional args to PyObject_CallObject. */
    PyObject *r = NULL;
    if (nargs == 0) {
        r = PyObject_CallObject(callable, NULL);
    } else if (nargs == 1) {
        r = PyObject_CallFunctionObjArgs(callable, args[0], NULL);
    } else {
        r = PyObject_CallObject(callable, tup);
    }
    Py_DECREF(tup);
    if (!r) PyErr_Print();
    return r;
}
PyObject *py_call_method(PyObject *obj, const char *name, PyObject **args, int nargs) {
    if (!obj) return NULL;
    PyObject *r;
    /* Use PyObject_CallMethodObjArgs for proper arg unpacking. */
    switch (nargs) {
        case 0:
            r = PyObject_CallMethod(obj, name, NULL);
            break;
        case 1:
            r = PyObject_CallFunctionObjArgs(PyObject_GetAttrString(obj, name), args[0], NULL);
            break;
        case 2:
            r = PyObject_CallFunctionObjArgs(PyObject_GetAttrString(obj, name),
                                              args[0], args[1], NULL);
            break;
        case 3:
            r = PyObject_CallFunctionObjArgs(PyObject_GetAttrString(obj, name),
                                              args[0], args[1], args[2], NULL);
            break;
        default: {
            PyObject *tup = _py_make_args(args, nargs);
            r = PyObject_CallMethod(obj, name, "O", tup);
            Py_DECREF(tup);
            break;
        }
    }
    if (!r) PyErr_Print();
    return r;
}

/* ====== operators (handle all type combinations via Python protocols) ====== */
PyObject *py_op_add(PyObject *a, PyObject *b) { return a && b ? PyNumber_Add(a, b) : NULL; }
PyObject *py_op_sub(PyObject *a, PyObject *b) { return a && b ? PyNumber_Subtract(a, b) : NULL; }
PyObject *py_op_mul(PyObject *a, PyObject *b) { return a && b ? PyNumber_Multiply(a, b) : NULL; }
PyObject *py_op_div(PyObject *a, PyObject *b) { return a && b ? PyNumber_TrueDivide(a, b) : NULL; }
PyObject *py_op_floordiv(PyObject *a, PyObject *b) { return a && b ? PyNumber_FloorDivide(a, b) : NULL; }
PyObject *py_op_mod(PyObject *a, PyObject *b) { return a && b ? PyNumber_Remainder(a, b) : NULL; }
PyObject *py_op_pow(PyObject *a, PyObject *b) { return a && b ? PyNumber_Power(a, b, Py_None) : NULL; }
PyObject *py_op_neg(PyObject *a) { return a ? PyNumber_Negative(a) : NULL; }
PyObject *py_op_pos(PyObject *a) { return a ? PyNumber_Positive(a) : NULL; }
PyObject *py_op_invert(PyObject *a) { return a ? PyNumber_Invert(a) : NULL; }

int py_op_eq(PyObject *a, PyObject *b) { return a && b ? PyObject_RichCompareBool(a, b, Py_EQ) : 0; }
int py_op_ne(PyObject *a, PyObject *b) { return a && b ? PyObject_RichCompareBool(a, b, Py_NE) : 0; }
int py_op_lt(PyObject *a, PyObject *b) { return a && b ? PyObject_RichCompareBool(a, b, Py_LT) : 0; }
int py_op_le(PyObject *a, PyObject *b) { return a && b ? PyObject_RichCompareBool(a, b, Py_LE) : 0; }
int py_op_gt(PyObject *a, PyObject *b) { return a && b ? PyObject_RichCompareBool(a, b, Py_GT) : 0; }
int py_op_ge(PyObject *a, PyObject *b) { return a && b ? PyObject_RichCompareBool(a, b, Py_GE) : 0; }
int py_op_contains(PyObject *container, PyObject *item) {
    if (!container || !item) return 0;
    int r = PySequence_Contains(container, item);
    if (r < 0) { PyErr_Clear(); return 0; }
    return r;
}

/* ====== iteration / sequence ====== */
PyObject *py_iter(PyObject *o) { return o ? PyObject_GetIter(o) : NULL; }
PyObject *py_iter_next(PyObject *it) {
    if (!it) return NULL;
    PyObject *r = PyIter_Next(it);
    if (!r && PyErr_Occurred()) PyErr_Clear();
    return r;
}
long py_object_len(PyObject *o) { return o ? (long)PyObject_Length(o) : 0; }
long py_embed_len(PyObject *o) { return o ? (long)PyObject_Length(o) : 0; }

/* ====== print ====== */
void py_print_obj(PyObject *o) {
    if (o) {
        /* PyObject_Print can be unreliable for C-extension types in embedded
         * mode. Use repr() instead, which always produces a valid string. */
        PyObject *s = PyObject_Repr(o);
        if (s) {
            const char *r = PyUnicode_AsUTF8(s);
            if (r) printf("%s", r);
            Py_DECREF(s);
        } else {
            PyErr_Clear();
            PyObject_Print(o, stdout, Py_PRINT_RAW);
        }
    } else {
        printf("None");
    }
    fflush(stdout);
}
void py_println(void) { printf("\n"); fflush(stdout); }

/* ====== conversion helpers ====== */
long py_str_to_int(const char *s) {
    if (!s) return 0;
    return (long)PyLong_AsLong(PyLong_FromString(s, NULL, 10));
}
double py_str_to_float(const char *s) {
    if (!s) return 0.0;
    PyObject *o = PyUnicode_FromString(s);
    if (!o) return 0.0;
    double d = PyFloat_AsDouble(o);
    Py_DECREF(o);
    return d;
}

/* ====== reference counting helpers ====== */
void py_incref(PyObject *o) { if (o) Py_INCREF(o); }
void py_decref(PyObject *o) { if (o) Py_DECREF(o); }

/* ====== subscript assign: obj[key] = value ====== */
void py_object_setitem(PyObject *obj, PyObject *key, PyObject *value) {
    if (!obj || !key) return;
    if (PyObject_SetItem(obj, key, value) < 0) {
        PyErr_Print();
    }
}

/* ====== real Python dict helpers (embed mode) ====== */
PyObject *py_dict_new(void) {
    return PyDict_New();
}
void py_dict_setitem(PyObject *dict, PyObject *key, PyObject *value) {
    if (!dict || !key) return;
    if (PyDict_SetItem(dict, key, value) < 0) {
        PyErr_Print();
    }
}

/* ====== string incref (embed mode: convert PyStr -> PyObject) ====== */
PyObject *py_str_incref(const char *s) {
    if (!s) return NULL;
    return PyUnicode_FromString(s);
}

/* ====== run source ====== */
int py_run_string(const char *src) {
    return PyRun_SimpleString(src ? src : "");
}

/* ====== hybrid: convert a PyObject* iterable to a native PyList* of int ====== */
struct PyListHeader;  /* opaque, defined in runtime.c */
extern void *py_list_new(void);
extern void py_list_set_kind(void *l, int kind);
extern void py_list_append_int(void *l, long v);
extern void py_list_append_float(void *l, double v);
extern void py_list_append_str(void *l, const char *s);
extern void py_list_append_list(void *l, void *v);
extern long py_list_len(void *l);
extern long py_list_get_int(void *l, long i);
extern double py_list_get_float(void *l, long i);
extern const char *py_list_get_str(void *l, long i);

void *py_object_to_list(PyObject *o) {
    /* Convert a PyObject* iterable to a native PyList*. */
    void *out = NULL;
    if (!o) return NULL;
    /* Fast path: it's already a PyList of ints. */
    if (PyList_Check(o)) {
        out = py_list_new();
        py_list_set_kind(out, 0 /* LE_INT */);
        Py_ssize_t n = PyList_GET_SIZE(o);
        for (Py_ssize_t i = 0; i < n; i++) {
            PyObject *v = PyList_GET_ITEM(o, i);
            if (PyLong_Check(v)) {
                py_list_append_int(out, PyLong_AsLong(v));
            } else if (PyFloat_Check(v)) {
                py_list_set_kind(out, 1 /* LE_FLOAT */);
                py_list_append_float(out, PyFloat_AsDouble(v));
            } else if (PyUnicode_Check(v)) {
                py_list_set_kind(out, 2 /* LE_STR */);
                py_list_append_str(out, PyUnicode_AsUTF8(v));
            } else {
                py_list_set_kind(out, 4 /* LE_LIST */);
                py_list_append_list(out, py_object_to_list(v));
            }
        }
        return out;
    }
    /* Fallback: iterate using PyObject_GetIter. */
    PyObject *it = PyObject_GetIter(o);
    if (!it) { PyErr_Clear(); return NULL; }
    out = py_list_new();
    py_list_set_kind(out, 0 /* LE_INT */);
    PyObject *item;
    while ((item = PyIter_Next(it))) {
        /* Use PyNumber_Index / PyNumber_Float to coerce numpy scalars. */
        if (PyLong_Check(item)) {
            py_list_append_int(out, PyLong_AsLong(item));
        } else if (PyFloat_Check(item)) {
            py_list_set_kind(out, 1 /* LE_FLOAT */);
            py_list_append_float(out, PyFloat_AsDouble(item));
        } else if (PyUnicode_Check(item)) {
            py_list_set_kind(out, 2 /* LE_STR */);
            py_list_append_str(out, PyUnicode_AsUTF8(item));
        } else if (PyNumber_Check(item)) {
            /* Coerce numpy scalars to int or float. */
            PyObject *as_float = PyNumber_Float(item);
            if (as_float) {
                double dv = PyFloat_AsDouble(as_float);
                py_list_set_kind(out, 1 /* LE_FLOAT */);
                py_list_append_float(out, dv);
                Py_DECREF(as_float);
            } else {
                PyErr_Clear();
                /* Try as a nested list. */
                py_list_set_kind(out, 4 /* LE_LIST */);
                py_list_append_list(out, py_object_to_list(item));
            }
        } else {
            py_list_set_kind(out, 4 /* LE_LIST */);
            py_list_append_list(out, py_object_to_list(item));
        }
        Py_DECREF(item);
    }
    PyErr_Clear();
    Py_DECREF(it);
    return out;
}

/* Same but returns a Python str representation (for printing numpy arrays). */
const char *py_object_to_repr(PyObject *o) {
    if (!o) return strdup("None");
    PyObject *s = PyObject_Repr(o);
    if (!s) { PyErr_Clear(); return strdup("None"); }
    const char *r = PyUnicode_AsUTF8(s);
    const char *r2 = r ? strdup(r) : strdup("None");
    Py_DECREF(s);
    return r2;
}

/* ====== format helper for f-strings ====== */
const char *py_format_obj(PyObject *o, const char *spec) {
    if (!o) return strdup("");
    PyObject *fmt = PyObject_CallMethod(o, "__format__", "s", spec ? spec : "");
    if (!fmt) { PyErr_Clear(); return strdup(""); }
    const char *r = PyUnicode_AsUTF8(fmt);
    const char *r2 = r ? strdup(r) : strdup("");
    Py_DECREF(fmt);
    return r2;
}

/* ====== range, enumerate, zip, map, filter (Python versions via libpython) ====== */
PyObject *py_range(PyObject **args, int n) {
    /* Equivalent to Python's range(): int args. Returns iterator. */
    PyObject *tup = _py_make_args(args, n);
    PyObject *r = PyObject_Call((PyObject *)&PyRange_Type, tup, NULL);
    Py_DECREF(tup);
    return r;
}

PyObject *py_enumerate(PyObject *iter) {
    if (!iter) return NULL;
    PyObject *r = PyObject_CallFunctionObjArgs(
        PyObject_GetAttrString(PyImport_ImportModule("builtins"), "enumerate"),
        iter, NULL);
    return r;
}

PyObject *py_zip(PyObject **args, int n) {
    PyObject *tup = _py_make_args(args, n);
    PyObject *bm = PyImport_ImportModule("builtins");
    PyObject *r = PyObject_CallFunctionObjArgs(PyObject_GetAttrString(bm, "zip"), tup, NULL);
    Py_DECREF(tup);
    return r;
}

PyObject *py_map(PyObject *fn, PyObject *iter) {
    PyObject *bm = PyImport_ImportModule("builtins");
    return PyObject_CallFunctionObjArgs(PyObject_GetAttrString(bm, "map"), fn, iter, NULL);
}

PyObject *py_filter(PyObject *fn, PyObject *iter) {
    PyObject *bm = PyImport_ImportModule("builtins");
    return PyObject_CallFunctionObjArgs(PyObject_GetAttrString(bm, "filter"), fn, iter, NULL);
}

/* ====== exceptions ====== */
void py_raise(PyObject *exc_class, const char *msg) {
    PyErr_SetString(exc_class, msg ? msg : "");
}

/* ====== truthiness / bool conversion ====== */
int py_truthy(PyObject *o) { return o ? PyObject_IsTrue(o) : 0; }
