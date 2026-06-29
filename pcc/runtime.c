/* Runtime support library for the compiled Python programs.
 *
 * The LLVM IR emitted by the compiler calls into these helpers for
 * operations that are awkward to express inline: dynamic string
 * construction, Python-semantic floor division / modulo, float
 * formatting, and console I/O.
 *
 * Build with: clang -c -O2 runtime.c -o runtime.o
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <ctype.h>
#include <pthread.h>
#include <regex.h>
#include <time.h>
#include <sys/time.h>
#include <errno.h>

/* ---- string construction ---- */

const char *py_str_empty(void) { return strdup(""); }
const char *py_str_concat(const char *a, const char *b) {
    size_t la = strlen(a), lb = strlen(b);
    char *r = (char *)malloc(la + lb + 1);
    memcpy(r, a, la);
    memcpy(r + la, b, lb);
    r[la + lb] = '\0';
    return r;
}

char *py_str_mul(const char *s, long n) {
    if (n <= 0) {
        char *r = (char *)malloc(1);
        r[0] = '\0';
        return r;
    }
    size_t ls = strlen(s);
    char *r = (char *)malloc(ls * (size_t)n + 1);
    for (long i = 0; i < n; i++) memcpy(r + i * ls, s, ls);
    r[ls * (size_t)n] = '\0';
    return r;
}

char *py_int_to_str(long n) {
    char buf[32];
    snprintf(buf, sizeof buf, "%ld", n);
    return strdup(buf);
}

char *py_float_to_str(double f) {
    /* Approximate Python's float repr: shortest round-tripping decimal. */
    if (isnan(f)) return strdup("nan");
    if (isinf(f)) return f > 0 ? strdup("inf") : strdup("-inf");
    char buf[64];
    int prec;
    for (prec = 1; prec <= 17; prec++) {
        snprintf(buf, sizeof buf, "%.*g", prec, f);
        if (strtod(buf, NULL) == f) break;
    }
    /* Python always shows a decimal point or exponent for floats. */
    int has_special = (strchr(buf, '.') != NULL) ||
                      (strchr(buf, 'e') != NULL) ||
                      (strchr(buf, 'E') != NULL);
    if (!has_special) {
        size_t len = strlen(buf);
        buf[len] = '.';
        buf[len + 1] = '0';
        buf[len + 2] = '\0';
    }
    return strdup(buf);
}

const char *py_bool_to_str(int b) {
    return b ? "True" : "False";
}

long py_len(const char *s) {
    return (long)strlen(s);
}

long py_int_parse(const char *s) {
    /* Python int(str) tolerates leading/trailing whitespace and sign. */
    while (*s && isspace((unsigned char)*s)) s++;
    return strtol(s, NULL, 10);
}

double py_float_parse(const char *s) {
    while (*s && isspace((unsigned char)*s)) s++;
    return strtod(s, NULL);
}

/* ---- numeric helpers with Python semantics ---- */

long py_ipow(long a, long b) {
    /* integer power; b assumed >= 0 (negative handled by float path) */
    if (b < 0) {
        /* fall back to float semantics */
        return (long)pow((double)a, (double)b);
    }
    long result = 1;
    long base = a;
    while (b > 0) {
        if (b & 1) result *= base;
        base *= base;
        b >>= 1;
    }
    return result;
}

double py_fpow(double a, double b) {
    return pow(a, b);
}

long py_ifloordiv(long a, long b) {
    if (b == 0) {
        fprintf(stderr, "ZeroDivisionError: integer division or modulo by zero\n");
        exit(1);
    }
    long q = a / b;
    long r = a % b;
    /* floor toward negative infinity */
    if ((r != 0) && ((r < 0) != (b < 0))) q -= 1;
    return q;
}

long py_imod(long a, long b) {
    if (b == 0) {
        fprintf(stderr, "ZeroDivisionError: integer division or modulo by zero\n");
        exit(1);
    }
    long r = a % b;
    /* result takes sign of divisor */
    if (r != 0 && ((r < 0) != (b < 0))) r += b;
    return r;
}

double py_idiv(long a, long b) {
    if (b == 0) {
        fprintf(stderr, "ZeroDivisionError: division by zero\n");
        exit(1);
    }
    return (double)a / (double)b;
}

/* ---- input ---- */

char *py_input(void) {
    size_t cap = 64, len = 0;
    char *buf = (char *)malloc(cap);
    int c;
    while ((c = getchar()) != EOF && c != '\n') {
        if (len + 1 >= cap) {
            cap *= 2;
            buf = (char *)realloc(buf, cap);
        }
        buf[len++] = (char)c;
    }
    buf[len] = '\0';
    return buf;
}

/* ---- print helpers (each prints without a trailing newline) ---- */

void py_print_int(long n) { printf("%ld", n); }
void py_print_float(double f) { fputs(py_float_to_str(f), stdout); }
void py_print_str(const char *s) { fputs(s ? s : "", stdout); }
void py_print_bool(int b) { fputs(py_bool_to_str(b), stdout); }
void py_print_none(void) { fputs("None", stdout); }

/* ---- list (dynamic array) ---- */

/* Element kind tags for generic printing/repr. */
enum { LE_INT=0, LE_FLOAT=1, LE_STR=2, LE_BOOL=3, LE_LIST=4 };

typedef struct PyList {
    void *data;
    long length;
    long capacity;
    int elem_kind;
} PyList;

PyList *py_list_new(void) {
    PyList *l = (PyList *)malloc(sizeof(PyList));
    l->data = malloc(8 * sizeof(long));
    l->length = 0;
    l->capacity = 8;
    l->elem_kind = LE_INT;
    return l;
}

void py_list_set_kind(PyList *l, int kind) {
    l->elem_kind = kind;
}

int py_list_get_kind(PyList *l) {
    return l ? l->elem_kind : 0;
}

static void py_list_grow(PyList *l, long needed) {
    if (needed <= l->capacity) return;
    long newcap = l->capacity;
    while (newcap < needed) newcap *= 2;
    l->data = realloc(l->data, newcap * sizeof(long));
    l->capacity = newcap;
}

void py_list_append_int(PyList *l, long v) {
    py_list_grow(l, l->length + 1);
    ((long *)l->data)[l->length] = v;
    l->length++;
}

void py_list_append_float(PyList *l, double v) {
    py_list_grow(l, l->length + 1);
    ((double *)l->data)[l->length] = v;
    l->length++;
}

void py_list_append_str(PyList *l, const char *v) {
    py_list_grow(l, l->length + 1);
    ((const char **)l->data)[l->length] = v;
    l->length++;
}

void py_list_append_list(PyList *l, PyList *v) {
    py_list_grow(l, l->length + 1);
    ((PyList **)l->data)[l->length] = v;
    l->length++;
    /* Promote to list kind if needed. */
    if (l->elem_kind == LE_INT) l->elem_kind = LE_LIST;
}

long py_list_get_int(PyList *l, long i) {
    if (i < 0) i += l->length;
    return ((long *)l->data)[i];
}

double py_list_get_float(PyList *l, long i) {
    if (i < 0) i += l->length;
    return ((double *)l->data)[i];
}

const char *py_list_get_str(PyList *l, long i) {
    if (i < 0) i += l->length;
    return ((const char **)l->data)[i];
}

PyList *py_list_get_list(PyList *l, long i) {
    if (i < 0) i += l->length;
    return ((PyList **)l->data)[i];
}

void py_list_set_int(PyList *l, long i, long v) {
    if (i < 0) i += l->length;
    ((long *)l->data)[i] = v;
}

void py_list_set_float(PyList *l, long i, double v) {
    if (i < 0) i += l->length;
    ((double *)l->data)[i] = v;
}

void py_list_set_str(PyList *l, long i, const char *v) {
    if (i < 0) i += l->length;
    ((const char **)l->data)[i] = v;
}

void py_list_set_list(PyList *l, long i, PyList *v) {
    if (i < 0) i += l->length;
    ((PyList **)l->data)[i] = v;
}

long py_list_len(PyList *l) {
    return l->length;
}

long py_list_pop_int(PyList *l) {
    l->length--;
    return ((long *)l->data)[l->length];
}

double py_list_pop_float(PyList *l) {
    l->length--;
    return ((double *)l->data)[l->length];
}

const char *py_list_pop_str(PyList *l) {
    l->length--;
    return ((const char **)l->data)[l->length];
}

PyList *py_list_pop_list(PyList *l) {
    l->length--;
    return ((PyList **)l->data)[l->length];
}

void py_list_insert_int(PyList *l, long i, long v) {
    if (i < 0) i += l->length;
    if (i < 0) i = 0;
    if (i > l->length) i = l->length;
    py_list_grow(l, l->length + 1);
    long *d = (long *)l->data;
    for (long k = l->length; k > i; k--) d[k] = d[k - 1];
    d[i] = v;
    l->length++;
}

void py_list_insert_float(PyList *l, long i, double v) {
    if (i < 0) i += l->length;
    if (i < 0) i = 0;
    if (i > l->length) i = l->length;
    py_list_grow(l, l->length + 1);
    double *d = (double *)l->data;
    for (long k = l->length; k > i; k--) d[k] = d[k - 1];
    d[i] = v;
    l->length++;
}

void py_list_insert_str(PyList *l, long i, const char *v) {
    if (i < 0) i += l->length;
    if (i < 0) i = 0;
    if (i > l->length) i = l->length;
    py_list_grow(l, l->length + 1);
    const char **d = (const char **)l->data;
    for (long k = l->length; k > i; k--) d[k] = d[k - 1];
    d[i] = v;
    l->length++;
}

void py_list_insert_list(PyList *l, long i, PyList *v) {
    if (i < 0) i += l->length;
    if (i < 0) i = 0;
    if (i > l->length) i = l->length;
    py_list_grow(l, l->length + 1);
    PyList **d = (PyList **)l->data;
    for (long k = l->length; k > i; k--) d[k] = d[k - 1];
    d[i] = v;
    l->length++;
}

long py_list_index_int(PyList *l, long v) {
    long *d = (long *)l->data;
    for (long i = 0; i < l->length; i++) if (d[i] == v) return i;
    return -1;
}
long py_list_index_str(PyList *l, const char *v) {
    const char **d = (const char **)l->data;
    for (long i = 0; i < l->length; i++) if (strcmp(d[i], v) == 0) return i;
    return -1;
}
long py_list_count_int(PyList *l, long v) {
    long *d = (long *)l->data;
    long c = 0;
    for (long i = 0; i < l->length; i++) if (d[i] == v) c++;
    return c;
}
long py_list_count_str(PyList *l, const char *v) {
    const char **d = (const char **)l->data;
    long c = 0;
    for (long i = 0; i < l->length; i++) if (strcmp(d[i], v) == 0) c++;
    return c;
}

/* ---- list printing (generic, recursive for nested lists) ---- */

void py_list_print(PyList *l) {
    putchar('[');
    for (long i = 0; i < l->length; i++) {
        if (i > 0) fputs(", ", stdout);
        switch (l->elem_kind) {
            case LE_INT:
                printf("%ld", ((long *)l->data)[i]);
                break;
            case LE_FLOAT:
                fputs(py_float_to_str(((double *)l->data)[i]), stdout);
                break;
            case LE_STR: {
                const char *s = ((const char **)l->data)[i];
                putchar('\'');
                fputs(s ? s : "", stdout);
                putchar('\'');
                break;
            }
            case LE_BOOL:
                fputs(((long *)l->data)[i] ? "True" : "False", stdout);
                break;
            case LE_LIST:
                py_list_print(((PyList **)l->data)[i]);
                break;
        }
    }
    putchar(']');
}

static void list_repr_append(char **pbuf, size_t *plen, size_t *pcap, const char *s, size_t sl) {
    while (*plen + sl + 2 >= *pcap) { *pcap *= 2; *pbuf = realloc(*pbuf, *pcap); }
    memcpy(*pbuf + *plen, s, sl); *plen += sl;
}

char *py_list_to_str(PyList *l) {
    size_t cap = 64, len = 0;
    char *buf = (char *)malloc(cap);
    buf[len++] = '[';
    for (long i = 0; i < l->length; i++) {
        if (i > 0) { buf[len++] = ','; buf[len++] = ' '; }
        switch (l->elem_kind) {
            case LE_INT: {
                char tmp[32];
                int tl = snprintf(tmp, sizeof tmp, "%ld", ((long *)l->data)[i]);
                list_repr_append(&buf, &len, &cap, tmp, tl);
                break;
            }
            case LE_FLOAT: {
                char *fs = py_float_to_str(((double *)l->data)[i]);
                list_repr_append(&buf, &len, &cap, fs, strlen(fs));
                break;
            }
            case LE_STR: {
                const char *s = ((const char **)l->data)[i];
                buf[len++] = '\'';
                if (s) list_repr_append(&buf, &len, &cap, s, strlen(s));
                buf[len++] = '\'';
                break;
            }
            case LE_BOOL: {
                const char *bs = ((long *)l->data)[i] ? "True" : "False";
                list_repr_append(&buf, &len, &cap, bs, strlen(bs));
                break;
            }
            case LE_LIST: {
                char *inner = py_list_to_str(((PyList **)l->data)[i]);
                list_repr_append(&buf, &len, &cap, inner, strlen(inner));
                free(inner);
                break;
            }
        }
    }
    buf[len++] = ']'; buf[len] = '\0';
    return buf;
}

/* ---- object (class instance) ---- */
typedef struct PyObject {
    int class_id;
    int n_attrs;
    const char *attr_names[64];
    int attr_types[64]; /* 0=int, 1=float, 2=str, 3=bool, 4=list, 5=object, 6=none */
    union {
        long i;
        double f;
        const char *s;
        int b;
        PyList *l;
        struct PyObject *o;
    } attr_values[64];
} PyObject;

PyObject *py_object_new(int class_id) {
    PyObject *o = (PyObject *)malloc(sizeof(PyObject));
    o->class_id = class_id;
    o->n_attrs = 0;
    return o;
}

static int py_object_find_attr(PyObject *o, const char *name) {
    for (int i = 0; i < o->n_attrs; i++)
        if (strcmp(o->attr_names[i], name) == 0) return i;
    return -1;
}

static void py_object_set_attr_type(PyObject *o, const char *name, int type_tag) {
    int idx = py_object_find_attr(o, name);
    if (idx < 0) { idx = o->n_attrs++; o->attr_names[idx] = name; }
    o->attr_types[idx] = type_tag;
}

long py_object_get_int(PyObject *o, const char *name) {
    int idx = py_object_find_attr(o, name);
    return idx >= 0 ? o->attr_values[idx].i : 0;
}
double py_object_get_float(PyObject *o, const char *name) {
    int idx = py_object_find_attr(o, name);
    return idx >= 0 ? o->attr_values[idx].f : 0.0;
}
const char *py_object_get_str(PyObject *o, const char *name) {
    int idx = py_object_find_attr(o, name);
    return idx >= 0 ? o->attr_values[idx].s : NULL;
}
int py_object_get_bool(PyObject *o, const char *name) {
    int idx = py_object_find_attr(o, name);
    return idx >= 0 ? o->attr_values[idx].b : 0;
}
PyList *py_object_get_list(PyObject *o, const char *name) {
    int idx = py_object_find_attr(o, name);
    return idx >= 0 ? o->attr_values[idx].l : NULL;
}
PyObject *py_object_get_obj(PyObject *o, const char *name) {
    int idx = py_object_find_attr(o, name);
    return idx >= 0 ? o->attr_values[idx].o : NULL;
}
void py_object_set_int(PyObject *o, const char *name, long v) {
    int idx = py_object_find_attr(o, name);
    if (idx < 0) { idx = o->n_attrs++; o->attr_names[idx] = name; }
    o->attr_types[idx] = 0; o->attr_values[idx].i = v;
}
void py_object_set_float(PyObject *o, const char *name, double v) {
    int idx = py_object_find_attr(o, name);
    if (idx < 0) { idx = o->n_attrs++; o->attr_names[idx] = name; }
    o->attr_types[idx] = 1; o->attr_values[idx].f = v;
}
void py_object_set_str(PyObject *o, const char *name, const char *v) {
    int idx = py_object_find_attr(o, name);
    if (idx < 0) { idx = o->n_attrs++; o->attr_names[idx] = name; }
    o->attr_types[idx] = 2; o->attr_values[idx].s = v;
}
void py_object_set_bool(PyObject *o, const char *name, int v) {
    int idx = py_object_find_attr(o, name);
    if (idx < 0) { idx = o->n_attrs++; o->attr_names[idx] = name; }
    o->attr_types[idx] = 3; o->attr_values[idx].b = v;
}
void py_object_set_list(PyObject *o, const char *name, PyList *v) {
    int idx = py_object_find_attr(o, name);
    if (idx < 0) { idx = o->n_attrs++; o->attr_names[idx] = name; }
    o->attr_types[idx] = 4; o->attr_values[idx].l = v;
}
void py_object_set_obj(PyObject *o, const char *name, PyObject *v) {
    int idx = py_object_find_attr(o, name);
    if (idx < 0) { idx = o->n_attrs++; o->attr_names[idx] = name; }
    o->attr_types[idx] = 5; o->attr_values[idx].o = v;
}
void py_object_set_none(PyObject *o, const char *name) {
    int idx = py_object_find_attr(o, name);
    if (idx < 0) { idx = o->n_attrs++; o->attr_names[idx] = name; }
    o->attr_types[idx] = 6; o->attr_values[idx].o = NULL;
}
int py_object_is_none(PyObject *o, const char *name) {
    int idx = py_object_find_attr(o, name);
    if (idx < 0) return 1;
    return o->attr_types[idx] == 6 || o->attr_values[idx].o == NULL;
}

/* ---- list slicing and more list methods ---- */
PyList *py_list_slice_int(PyList *l, long start, long stop) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_INT);
    if (start < 0) start += l->length;
    if (stop < 0) stop += l->length;
    if (start < 0) start = 0;
    if (stop > l->length) stop = l->length;
    long *d = (long *)l->data;
    for (long i = start; i < stop; i++) py_list_append_int(r, d[i]);
    return r;
}
PyList *py_list_slice_float(PyList *l, long start, long stop) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_FLOAT);
    if (start < 0) start += l->length;
    if (stop < 0) stop += l->length;
    if (start < 0) start = 0;
    if (stop > l->length) stop = l->length;
    double *d = (double *)l->data;
    for (long i = start; i < stop; i++) py_list_append_float(r, d[i]);
    return r;
}
PyList *py_list_slice_str(PyList *l, long start, long stop) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_STR);
    if (start < 0) start += l->length;
    if (stop < 0) stop += l->length;
    if (start < 0) start = 0;
    if (stop > l->length) stop = l->length;
    const char **d = (const char **)l->data;
    for (long i = start; i < stop; i++) py_list_append_str(r, d[i]);
    return r;
}
PyList *py_list_slice_list(PyList *l, long start, long stop) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_LIST);
    if (start < 0) start += l->length;
    if (stop < 0) stop += l->length;
    if (start < 0) start = 0;
    if (stop > l->length) stop = l->length;
    PyList **d = (PyList **)l->data;
    for (long i = start; i < stop; i++) py_list_append_list(r, d[i]);
    return r;
}
void py_list_extend_int(PyList *dst, PyList *src) {
    long *d = (long *)src->data;
    for (long i = 0; i < src->length; i++) py_list_append_int(dst, d[i]);
}
void py_list_extend_float(PyList *dst, PyList *src) {
    double *d = (double *)src->data;
    for (long i = 0; i < src->length; i++) py_list_append_float(dst, d[i]);
}
void py_list_extend_str(PyList *dst, PyList *src) {
    const char **d = (const char **)src->data;
    for (long i = 0; i < src->length; i++) py_list_append_str(dst, d[i]);
}
void py_list_extend_list(PyList *dst, PyList *src) {
    PyList **d = (PyList **)src->data;
    for (long i = 0; i < src->length; i++) py_list_append_list(dst, d[i]);
}
long py_list_pop_at_int(PyList *l, long idx) {
    if (idx < 0) idx += l->length;
    long r = ((long *)l->data)[idx];
    for (long i = idx; i < l->length - 1; i++) ((long *)l->data)[i] = ((long *)l->data)[i+1];
    l->length--;
    return r;
}
double py_list_pop_at_float(PyList *l, long idx) {
    if (idx < 0) idx += l->length;
    double r = ((double *)l->data)[idx];
    for (long i = idx; i < l->length - 1; i++) ((double *)l->data)[i] = ((double *)l->data)[i+1];
    l->length--;
    return r;
}
const char *py_list_pop_at_str(PyList *l, long idx) {
    if (idx < 0) idx += l->length;
    const char *r = ((const char **)l->data)[idx];
    for (long i = idx; i < l->length - 1; i++) ((const char **)l->data)[i] = ((const char **)l->data)[i+1];
    l->length--;
    return r;
}
PyList *py_list_pop_at_list(PyList *l, long idx) {
    if (idx < 0) idx += l->length;
    PyList *r = ((PyList **)l->data)[idx];
    for (long i = idx; i < l->length - 1; i++) ((PyList **)l->data)[i] = ((PyList **)l->data)[i+1];
    l->length--;
    return r;
}

/* ---- random ---- */
void py_random_seed(long seed) { srandom((unsigned int)seed); }
long py_random_randint(long lo, long hi) { return lo + (random() % (hi - lo + 1)); }
long py_random_choice_int(PyList *l) { return ((long *)l->data)[random() % l->length]; }
const char *py_random_choice_str(PyList *l) { return ((const char **)l->data)[random() % l->length]; }
double py_random_random(void) { return (double)random() / (double)RAND_MAX; }

/* ---- string lower/upper ---- */
char *py_str_lower(const char *s) {
    size_t n = strlen(s);
    char *r = (char *)malloc(n + 1);
    for (size_t i = 0; i < n; i++) r[i] = tolower((unsigned char)s[i]);
    r[n] = '\0';
    return r;
}
char *py_str_upper(const char *s) {
    size_t n = strlen(s);
    char *r = (char *)malloc(n + 1);
    for (size_t i = 0; i < n; i++) r[i] = toupper((unsigned char)s[i]);
    r[n] = '\0';
    return r;
}

char *py_str_replace(const char *s, const char *old, const char *newstr) {
    size_t slen = strlen(s), olen = strlen(old);
    if (olen == 0) return strdup(s);
    /* Count occurrences */
    size_t count = 0;
    const char *p = s;
    while ((p = strstr(p, old)) != NULL) { count++; p += olen; }
    size_t nlen = strlen(newstr);
    char *r = (char *)malloc(slen + count * (nlen > olen ? nlen - olen : 0) + 1);
    char *out = r;
    p = s;
    while (1) {
        const char *m = strstr(p, old);
        if (!m) {
            size_t rest = strlen(p);
            memcpy(out, p, rest);
            out += rest;
            break;
        }
        size_t chunk = m - p;
        memcpy(out, p, chunk);
        out += chunk;
        memcpy(out, newstr, nlen);
        out += nlen;
        p = m + olen;
    }
    *out = '\0';
    return r;
}

int py_str_startswith(const char *s, const char *prefix) {
    size_t sl = strlen(s), pl = strlen(prefix);
    if (pl > sl) return 0;
    return memcmp(s, prefix, pl) == 0;
}

int py_str_endswith(const char *s, const char *suffix) {
    size_t sl = strlen(s), sufl = strlen(suffix);
    if (sufl > sl) return 0;
    return memcmp(s + sl - sufl, suffix, sufl) == 0;
}

long py_str_find(const char *s, const char *sub) {
    const char *m = strstr(s, sub);
    if (!m) return -1;
    return (long)(m - s);
}

char *py_str_strip(const char *s);

char *py_str_lstrip(const char *s) {
    while (*s && isspace((unsigned char)*s)) s++;
    return strdup(s);
}

char *py_str_rstrip(const char *s) {
    size_t n = strlen(s);
    while (n > 0 && isspace((unsigned char)s[n - 1])) n--;
    char *r = (char *)malloc(n + 1);
    memcpy(r, s, n);
    r[n] = '\0';
    return r;
}

char *py_str_strip(const char *s) {
    return py_str_rstrip(py_str_lstrip(s));
}

PyList *py_str_split(const char *s, const char *delim) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_STR);
    size_t dlen = strlen(delim);
    if (dlen == 0) {
        py_list_append_str(r, s);
        return r;
    }
    const char *p = s, *start = s;
    while (1) {
        const char *m = strstr(p, delim);
        if (!m) {
            size_t chunk = strlen(start);
            char *piece = (char *)malloc(chunk + 1);
            memcpy(piece, start, chunk);
            piece[chunk] = '\0';
            py_list_append_str(r, piece);
            break;
        }
        size_t chunk = m - start;
        char *piece = (char *)malloc(chunk + 1);
        memcpy(piece, start, chunk);
        piece[chunk] = '\0';
        py_list_append_str(r, piece);
        p = m + dlen;
        start = p;
    }
    return r;
}

PyList *py_str_split_ws(const char *s) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_STR);
    const char *p = s;
    while (*p) {
        while (*p && isspace((unsigned char)*p)) p++;
        if (!*p) break;
        const char *start = p;
        while (*p && !isspace((unsigned char)*p)) p++;
        size_t chunk = p - start;
        char *piece = (char *)malloc(chunk + 1);
        memcpy(piece, start, chunk);
        piece[chunk] = '\0';
        py_list_append_str(r, piece);
    }
    return r;
}

/* ---- list sort (int, ascending, in place) ---- */
static int cmp_long(const void *a, const void *b) {
    long la = *(const long *)a, lb = *(const long *)b;
    return (la > lb) - (la < lb);
}
void py_list_sort_int(PyList *l) {
    if (l->length > 1)
        qsort(l->data, (size_t)l->length, sizeof(long), cmp_long);
}

static int cmp_double(const void *a, const void *b) {
    double la = *(const double *)a, lb = *(const double *)b;
    return (la > lb) - (la < lb);
}
void py_list_sort_float(PyList *l) {
    if (l->length > 1)
        qsort(l->data, (size_t)l->length, sizeof(double), cmp_double);
}

static int cmp_str(const void *a, const void *b) {
    const char *sa = *(const char **)a, *sb = *(const char **)b;
    return strcmp(sa, sb);
}
void py_list_sort_str(PyList *l) {
    if (l->length > 1)
        qsort(l->data, (size_t)l->length, sizeof(const char *), cmp_str);
}

/* ---- Tuple support ---- */
typedef struct {
    void **data;       /* array of typed element pointers */
    long length;
    int *kinds;        /* per-element kind: 0=int, 1=float, 2=str, 3=bool, 4=list */
} PyTuple;

PyTuple *py_tuple_new(long n) {
    PyTuple *t = (PyTuple *)malloc(sizeof(PyTuple));
    t->length = n;
    t->data = (void **)calloc((size_t)n, sizeof(void *));
    t->kinds = (int *)calloc((size_t)n, sizeof(int));
    return t;
}

void py_tuple_set_int(PyTuple *t, long i, long v) {
    long *p = (long *)malloc(sizeof(long));
    *p = v;
    t->data[i] = p;
    t->kinds[i] = 0;
}

void py_tuple_set_str(PyTuple *t, long i, const char *v) {
    char *p = strdup(v);
    t->data[i] = p;
    t->kinds[i] = 2;
}

const char *py_tuple_get_str(PyTuple *t, long i) {
    return (const char *)t->data[i];
}

/* Sort a list of PyTuple* whose first element is an int and the rest are
   values to keep aligned. The list is itself a PyList*. */
static int cmp_tuple_int_first(const void *a, const void *b) {
    PyTuple *ta = *(PyTuple **)a, *tb = *(PyTuple **)b;
    long la = *(long *)ta->data[0], lb = *(long *)tb->data[0];
    return (la > lb) - (la < lb);
}
void py_list_sort_tuple_int_first(PyList *l) {
    if (l->length > 1)
        qsort(l->data, (size_t)l->length, sizeof(PyTuple *), cmp_tuple_int_first);
}

/* ---- os module ---- */
#include <unistd.h>
const char *py_os_getcwd(void) {
    char buf[4096];
    if (getcwd(buf, sizeof buf)) return strdup(buf);
    return strdup("");
}
const char *py_os_environ_get(const char *name) {
    const char *v = getenv(name);
    return v ? strdup(v) : strdup("");
}
long py_os_environ_count(void) {
    extern char **environ;
    long n = 0;
    while (environ[n]) n++;
    return n;
}
const char *py_os_environ_name(long i) {
    extern char **environ;
    const char *e = environ[i];
    const char *eq = strchr(e, '=');
    if (!eq) return strdup(e);
    long n = eq - e;
    char *r = (char *)malloc(n + 1);
    memcpy(r, e, n);
    r[n] = '\0';
    return r;
}
const char *py_os_environ_value(long i) {
    extern char **environ;
    const char *e = environ[i];
    const char *eq = strchr(e, '=');
    return strdup(eq ? eq + 1 : "");
}
const char *py_os_listdir(const char *path) {
    /* Return newline-separated entries; simplified: use `ls`-style fallback. */
    char cmd[1024];
    snprintf(cmd, sizeof cmd, "ls -1 %s 2>/dev/null", path);
    FILE *f = popen(cmd, "r");
    if (!f) return strdup("");
    size_t cap = 256, len = 0;
    char *buf = (char *)malloc(cap);
    char line[256];
    while (fgets(line, sizeof line, f)) {
        size_t l = strlen(line);
        if (l > 0 && line[l - 1] == '\n') line[--l] = '\0';
        while (len + l + 2 >= cap) { cap *= 2; buf = realloc(buf, cap); }
        memcpy(buf + len, line, l);
        buf[len + l] = '\n';
        len += l + 1;
    }
    buf[len] = '\0';
    pclose(f);
    return buf;
}

/* ---- sys module ---- */
int py_sys_argc(void) { return 1; /* placeholder; updated in main */ }
const char *py_sys_argv(int i) { return ""; /* placeholder */ }

/* ---- json module ---- */
const char *py_json_dumps_str(const char *s) {
    size_t n = strlen(s);
    char *r = (char *)malloc(n * 6 + 8);
    char *p = r;
    *p++ = '"';
    for (size_t i = 0; i < n; i++) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') { *p++ = '\\'; *p++ = c; }
        else if (c == '\n') { *p++ = '\\'; *p++ = 'n'; }
        else if (c == '\r') { *p++ = '\\'; *p++ = 'r'; }
        else if (c == '\t') { *p++ = '\\'; *p++ = 't'; }
        else if (c < 0x20) { p += sprintf(p, "\\u%04x", c); }
        else *p++ = c;
    }
    *p++ = '"';
    *p = '\0';
    return r;
}
const char *py_json_dumps_int(long v) {
    char *r = (char *)malloc(32);
    snprintf(r, 32, "%ld", v);
    return r;
}
const char *py_json_dumps_float(double v) {
    char *r = (char *)malloc(64);
    snprintf(r, 64, "%g", v);
    return r;
}
const char *py_json_dumps_bool(int b) {
    return strdup(b ? "true" : "false");
}
const char *py_json_dumps_none(void) { return strdup("null"); }
const char *py_json_dumps_list(PyList *l);
const char *py_json_dumps_list(PyList *l) {
    size_t cap = 256, len = 0;
    char *buf = (char *)malloc(cap);
    buf[len++] = '[';
    for (long i = 0; i < l->length; i++) {
        if (i > 0) {
            while (len + 2 >= cap) { cap *= 2; buf = realloc(buf, cap); }
            buf[len++] = ',';
        }
        const char *item = NULL;
        char buf2[64];
        switch (l->elem_kind) {
            case LE_INT: snprintf(buf2, sizeof buf2, "%ld", ((long *)l->data)[i]); item = buf2; break;
            case LE_FLOAT: snprintf(buf2, sizeof buf2, "%g", ((double *)l->data)[i]); item = buf2; break;
            case LE_BOOL: item = ((long *)l->data)[i] ? "true" : "false"; break;
            case LE_STR: item = ((const char **)l->data)[i]; break;
            default: item = "null"; break;
        }
        if (l->elem_kind == LE_STR) {
            const char *q = py_json_dumps_str(item);
            size_t ql = strlen(q);
            while (len + ql + 1 >= cap) { cap *= 2; buf = realloc(buf, cap); }
            memcpy(buf + len, q, ql); len += ql; free((void *)q);
        } else {
            size_t il = strlen(item);
            while (len + il + 1 >= cap) { cap *= 2; buf = realloc(buf, cap); }
            memcpy(buf + len, item, il); len += il;
        }
    }
    while (len + 2 >= cap) { cap *= 2; buf = realloc(buf, cap); }
    buf[len++] = ']';
    buf[len] = '\0';
    return buf;
}
const char *py_json_dumps(PyList *l) {
    if (!l) return strdup("[]");
    return py_json_dumps_list(l);
}

/* ---- time ---- */
double py_time_perf_counter(void) {
    struct timeval tv;
    gettimeofday(&tv, NULL);
    return (double)tv.tv_sec + (double)tv.tv_usec / 1000000.0;
}

/* ---- threading (pthread-based) ---- */
typedef struct {
    pthread_t tid;
    void (*func_i64)(long);
    long i64_arg;
    int started;
} PyThread;

static void *py_thread_shim(void *p) {
    PyThread *t = (PyThread *)p;
    t->func_i64(t->i64_arg);
    return NULL;
}

PyThread *py_thread_new(void (*func_i64)(long), long i64_arg) {
    PyThread *t = (PyThread *)malloc(sizeof(PyThread));
    t->func_i64 = func_i64;
    t->i64_arg = i64_arg;
    t->started = 0;
    return t;
}
void py_thread_start(PyThread *t) {
    pthread_create(&t->tid, NULL, py_thread_shim, t);
    t->started = 1;
}
void py_thread_join(PyThread *t) {
    if (t->started) pthread_join(t->tid, NULL);
}

pthread_mutex_t *py_lock_new(void) {
    pthread_mutex_t *m = (pthread_mutex_t *)malloc(sizeof(pthread_mutex_t));
    pthread_mutex_init(m, NULL);
    return m;
}
void py_lock_acquire(pthread_mutex_t *m) { pthread_mutex_lock(m); }
void py_lock_release(pthread_mutex_t *m) { pthread_mutex_unlock(m); }

typedef struct {
    pthread_mutex_t mutex;
    pthread_cond_t cond;
    int flag;
} PyEvent;

PyEvent *py_event_new(void) {
    PyEvent *e = (PyEvent *)malloc(sizeof(PyEvent));
    pthread_mutex_init(&e->mutex, NULL);
    pthread_cond_init(&e->cond, NULL);
    e->flag = 0;
    return e;
}
void py_event_set(PyEvent *e) {
    pthread_mutex_lock(&e->mutex);
    e->flag = 1;
    pthread_cond_broadcast(&e->cond);
    pthread_mutex_unlock(&e->mutex);
}
int py_event_is_set(PyEvent *e) { return e->flag; }
void py_event_clear(PyEvent *e) { e->flag = 0; }
void py_event_wait(PyEvent *e) {
    pthread_mutex_lock(&e->mutex);
    while (!e->flag) pthread_cond_wait(&e->cond, &e->mutex);
    pthread_mutex_unlock(&e->mutex);
}

/* ---- thread-safe queue ---- */
typedef struct PyQueue {
    pthread_mutex_t mutex;
    pthread_cond_t not_empty;
    pthread_cond_t not_full;
    PyList *items; /* stored as a list of void* */
    long maxsize;
    long unfinished; /* tracks pending tasks for join() */
} PyQueue;

PyQueue *py_queue_new(long maxsize) {
    PyQueue *q = (PyQueue *)malloc(sizeof(PyQueue));
    pthread_mutex_init(&q->mutex, NULL);
    pthread_cond_init(&q->not_empty, NULL);
    pthread_cond_init(&q->not_full, NULL);
    q->items = py_list_new();
    q->items->elem_kind = LE_LIST; /* store void* as list ptrs */
    q->maxsize = maxsize;
    q->unfinished = 0;
    return q;
}
void py_queue_put(PyQueue *q, void *item) {
    pthread_mutex_lock(&q->mutex);
    while (q->maxsize > 0 && q->items->length >= q->maxsize)
        pthread_cond_wait(&q->not_full, &q->mutex);
    py_list_append_list(q->items, (PyList *)item);
    q->unfinished++;
    pthread_cond_signal(&q->not_empty);
    pthread_mutex_unlock(&q->mutex);
}
void *py_queue_get(PyQueue *q, long timeout_sec) {
    pthread_mutex_lock(&q->mutex);
    while (q->items->length == 0) {
        if (timeout_sec > 0) {
            struct timespec ts;
            struct timeval tv;
            gettimeofday(&tv, NULL);
            ts.tv_sec = tv.tv_sec + timeout_sec;
            ts.tv_nsec = tv.tv_usec * 1000;
            int rc = pthread_cond_timedwait(&q->not_empty, &q->mutex, &ts);
            if (rc == ETIMEDOUT) { pthread_mutex_unlock(&q->mutex); return NULL; }
        } else {
            pthread_cond_wait(&q->not_empty, &q->mutex);
        }
    }
    void *item = (void *)((PyList **)q->items->data)[0];
    for (long i = 0; i < q->items->length - 1; i++)
        ((PyList **)q->items->data)[i] = ((PyList **)q->items->data)[i+1];
    q->items->length--;
    pthread_cond_signal(&q->not_full);
    pthread_mutex_unlock(&q->mutex);
    return item;
}
/* Box typed scalar values into a heap PyList (so they can be stored as ptr). */
PyList *py_queue_box_int(long v) {
    PyList *box = py_list_new();
    py_list_append_int(box, v);
    return box;
}
PyList *py_queue_box_float(double v) {
    PyList *box = py_list_new();
    py_list_append_float(box, v);
    return box;
}
PyList *py_queue_box_str(const char *v) {
    PyList *box = py_list_new();
    py_list_append_str(box, v);
    return box;
}
long py_queue_size(PyQueue *q) { return q->items->length; }
int py_queue_empty(PyQueue *q) { return q->items->length == 0; }
void py_queue_task_done(PyQueue *q) {
    pthread_mutex_lock(&q->mutex);
    if (q->unfinished > 0) q->unfinished--;
    if (q->unfinished == 0) pthread_cond_broadcast(&q->not_empty);
    pthread_mutex_unlock(&q->mutex);
}
void py_queue_join(PyQueue *q) {
    pthread_mutex_lock(&q->mutex);
    while (q->unfinished > 0)
        pthread_cond_wait(&q->not_empty, &q->mutex);
    pthread_mutex_unlock(&q->mutex);
}

/* ---- Counter (collections) ----
 * Represented as a PyObject (class_id 100) with two list attributes:
 *   "keys"   -> PyList of const char*
 *   "counts" -> PyList of long
 */
#define COUNTER_CLASS_ID 100

PyObject *py_counter_new(void) {
    PyObject *o = py_object_new(COUNTER_CLASS_ID);
    PyList *keys = py_list_new();
    keys->elem_kind = LE_STR;
    PyList *counts = py_list_new();
    counts->elem_kind = LE_INT;
    py_object_set_list(o, "keys", keys);
    py_object_set_list(o, "counts", counts);
    return o;
}

static long counter_find(PyObject *o, const char *key) {
    PyList *keys = py_object_get_list(o, "keys");
    for (long i = 0; i < keys->length; i++) {
        if (strcmp(((const char **)keys->data)[i], key) == 0) return i;
    }
    return -1;
}

void py_counter_update_list(PyObject *o, PyList *items) {
    PyList *keys = py_object_get_list(o, "keys");
    PyList *counts = py_object_get_list(o, "counts");
    for (long i = 0; i < items->length; i++) {
        const char *k = ((const char **)items->data)[i];
        long idx = counter_find(o, k);
        if (idx < 0) {
            py_list_append_str(keys, k);
            py_list_append_int(counts, 1);
        } else {
            ((long *)counts->data)[idx] += 1;
        }
    }
}

void py_counter_update_counter(PyObject *dst, PyObject *src) {
    PyList *dkeys = py_object_get_list(dst, "keys");
    PyList *dcounts = py_object_get_list(dst, "counts");
    PyList *skeys = py_object_get_list(src, "keys");
    PyList *scounts = py_object_get_list(src, "counts");
    for (long i = 0; i < skeys->length; i++) {
        const char *k = ((const char **)skeys->data)[i];
        long c = ((long *)scounts->data)[i];
        long idx = counter_find(dst, k);
        if (idx < 0) {
            py_list_append_str(dkeys, k);
            py_list_append_int(dcounts, c);
        } else {
            ((long *)dcounts->data)[idx] += c;
        }
    }
}

PyList *py_counter_values(PyObject *o) {
    PyList *counts = py_object_get_list(o, "counts");
    PyList *r = py_list_new();
    r->elem_kind = LE_INT;
    for (long i = 0; i < counts->length; i++)
        py_list_append_int(r, ((long *)counts->data)[i]);
    return r;
}

long py_counter_len(PyObject *o) {
    return py_object_get_list(o, "keys")->length;
}

/* most_common(n): returns a PyList of tuples (each a PyList [str, int]),
 * sorted by count descending. n<0 means all. */
typedef struct { long count; const char *key; } KC;
static int cmp_kc_desc(const void *a, const void *b) {
    long ca = ((const KC *)a)->count, cb = ((const KC *)b)->count;
    if (ca != cb) return (ca < cb) ? 1 : -1; /* descending */
    return strcmp(((const KC *)a)->key, ((const KC *)b)->key); /* tiebreak: key asc */
}
PyList *py_counter_most_common(PyObject *o, long n) {
    PyList *keys = py_object_get_list(o, "keys");
    PyList *counts = py_object_get_list(o, "counts");
    long total = keys->length;
    KC *arr = (KC *)malloc(sizeof(KC) * (total > 0 ? total : 1));
    for (long i = 0; i < total; i++) {
        arr[i].key = ((const char **)keys->data)[i];
        arr[i].count = ((long *)counts->data)[i];
    }
    if (total > 1) qsort(arr, (size_t)total, sizeof(KC), cmp_kc_desc);
    if (n < 0 || n > total) n = total;
    PyList *r = py_list_new();
    r->elem_kind = LE_LIST;
    for (long i = 0; i < n; i++) {
        PyList *tup = py_list_new();
        py_list_append_str(tup, arr[i].key);
        py_list_append_int(tup, arr[i].count);
        py_list_append_list(r, tup);
    }
    free(arr);
    return r;
}

/* Format a dict/object attribute value as a string based on its stored type. */
char *py_object_get_as_str(PyObject *o, const char *name) {
    int idx = py_object_find_attr(o, name);
    if (idx < 0) return strdup("None");
    char buf[64];
    switch (o->attr_types[idx]) {
        case 0: snprintf(buf, sizeof buf, "%ld", o->attr_values[idx].i); return strdup(buf);
        case 1: return py_float_to_str(o->attr_values[idx].f);
        case 2: return strdup(o->attr_values[idx].s ? o->attr_values[idx].s : "");
        case 3: return strdup(o->attr_values[idx].b ? "True" : "False");
        case 4: return py_list_to_str(o->attr_values[idx].l);
        case 5: return strdup("<object>");
        case 6: return strdup("None");
    }
    return strdup("None");
}

/* ---- regex (POSIX) ---- */
const char *py_re_sub(const char *pattern, const char *repl, const char *string) {
    regex_t regex;
    if (regcomp(&regex, pattern, REG_EXTENDED) != 0) return string;
    /* Simple: find first match and replace */
    regmatch_t match;
    const char *cur = string;
    size_t cap = strlen(string) + 256;
    char *result = (char *)malloc(cap);
    size_t len = 0;
    while (regexec(&regex, cur, 1, &match, 0) == 0) {
        /* copy before match */
        size_t before = match.rm_so;
        while (len + before + strlen(repl) + 1 >= cap) { cap *= 2; result = realloc(result, cap); }
        memcpy(result + len, cur, before); len += before;
        size_t repl_len = strlen(repl);
        memcpy(result + len, repl, repl_len); len += repl_len;
        cur += match.rm_eo;
        if (match.rm_so == match.rm_eo) { result[len++] = *cur++; if (!*cur) break; }
    }
    size_t rest = strlen(cur);
    while (len + rest + 1 >= cap) { cap *= 2; result = realloc(result, cap); }
    memcpy(result + len, cur, rest); len += rest;
    result[len] = '\0';
    regfree(&regex);
    return result;
}
PyList *py_re_findall(const char *pattern, const char *string) {
    PyList *result = py_list_new();
    py_list_set_kind(result, LE_STR);
    regex_t regex;
    if (regcomp(&regex, pattern, REG_EXTENDED) != 0) return result;
    regmatch_t match;
    const char *cur = string;
    while (regexec(&regex, cur, 1, &match, 0) == 0) {
        size_t len = match.rm_eo - match.rm_so;
        char *s = (char *)malloc(len + 1);
        memcpy(s, cur + match.rm_so, len);
        s[len] = '\0';
        py_list_append_str(result, s);
        cur += match.rm_eo;
        if (match.rm_so == match.rm_eo) { if (!*cur) break; cur++; }
    }
    regfree(&regex);
    return result;
}

/* ---- string formatting ----
 * Spec grammar (colon prefix optional): [align][width][.precision][type]
 *   align: '<' (left) | '>' (right)   width: integer   precision: .N   type: f|d|s
 */
static void parse_fmt_spec(const char *spec, char *align, int *width, int *prec, int *has_prec, char *type) {
    *align = 0; *width = 0; *prec = 0; *has_prec = 0; *type = 0;
    if (!spec || !spec[0]) return;
    if (spec[0] == ':') spec++;
    if (spec[0] == '<' || spec[0] == '>' || spec[0] == '=' || spec[0] == '^') { *align = spec[0]; spec++; }
    /* fill char */
    if (*spec && *spec != '0' && (*spec == '+' || *spec == '-' || *spec == ' ')) spec++;
    /* alternate form (#) */
    if (*spec == '#') spec++;
    /* zero pad */
    if (*spec == '0') spec++;
    /* width: leading digits */
    if (*spec >= '0' && *spec <= '9') {
        *width = atoi(spec);
        while (*spec >= '0' && *spec <= '9') spec++;
    }
    /* precision */
    if (*spec == '.') {
        spec++;
        *has_prec = 1;
        *prec = atoi(spec);
        while ((*spec >= '0' && *spec <= '9')) spec++;
    }
    /* type */
    if (*spec == 'f' || *spec == 'd' || *spec == 's' || *spec == 'e' || *spec == 'g'
            || *spec == 'x' || *spec == 'X' || *spec == 'o' || *spec == 'b'
            || *spec == 'n' || *spec == 'c' || *spec == '%') *type = *spec;
}

char *py_format_int(long val, const char *spec) {
    char align; int width, prec, has_prec; char type;
    parse_fmt_spec(spec, &align, &width, &prec, &has_prec, &type);
    char inner[64];
    int has_prefix = 0;
    if (type == 'x' || type == 'X') {
        unsigned long u = (unsigned long)val;
        if (type == 'X') snprintf(inner, sizeof inner, "%lX", u);
        else snprintf(inner, sizeof inner, "%lx", u);
        /* Check for # prefix (alternate form) */
        if (spec && strchr(spec, '#')) {
            memmove(inner + 2, inner, strlen(inner) + 1);
            inner[0] = '0';
            inner[1] = (type == 'X') ? 'X' : 'x';
            has_prefix = 1;
        }
    } else if (type == 'o') {
        snprintf(inner, sizeof inner, "%lo", (unsigned long)val);
        if (spec && strchr(spec, '#') && val != 0) {
            memmove(inner + 1, inner, strlen(inner) + 1);
            inner[0] = '0';
            has_prefix = 1;
        }
    } else if (type == 'b') {
        /* Binary format */
        unsigned long u = (unsigned long)val;
        char tmp[80]; int n = 0;
        if (u == 0) tmp[n++] = '0';
        while (u > 0) { tmp[n++] = '0' + (u & 1); u >>= 1; }
        for (int i = 0; i < n; i++) inner[i] = tmp[n - 1 - i];
        inner[n] = '\0';
        if (spec && strchr(spec, '#')) {
            memmove(inner + 2, inner, strlen(inner) + 1);
            inner[0] = '0';
            inner[1] = 'b';
            has_prefix = 1;
        }
    } else {
        snprintf(inner, sizeof inner, "%ld", val);
    }
    int len = (int)strlen(inner);
    if (width <= len) return strdup(inner);
    char *buf = (char *)malloc(width + 1);
    if (align == '>') {
        for (int i = 0; i < width - len; i++) buf[i] = ' ';
        memcpy(buf + width - len, inner, len);
    } else { /* default and '<' -> left align */
        memcpy(buf, inner, len);
        for (int i = len; i < width; i++) buf[i] = ' ';
    }
    buf[width] = '\0';
    return buf;
}

char *py_format_float(double val, const char *spec) {
    char align; int width, prec, has_prec; char type;
    parse_fmt_spec(spec, &align, &width, &prec, &has_prec, &type);
    char inner[128];
    if (has_prec) {
        snprintf(inner, sizeof inner, "%.*f", prec, val);
    } else if (type == 'f') {
        snprintf(inner, sizeof inner, "%.6f", val);
    } else {
        snprintf(inner, sizeof inner, "%s", py_float_to_str(val));
    }
    int len = (int)strlen(inner);
    if (width <= len) return strdup(inner);
    char *buf = (char *)malloc(width + 1);
    if (align == '>') {
        for (int i = 0; i < width - len; i++) buf[i] = ' ';
        memcpy(buf + width - len, inner, len);
    } else {
        memcpy(buf, inner, len);
        for (int i = len; i < width; i++) buf[i] = ' ';
    }
    buf[width] = '\0';
    return buf;
}

char *py_format_str(const char *val, const char *spec) {
    char align; int width, prec, has_prec; char type;
    parse_fmt_spec(spec, &align, &width, &prec, &has_prec, &type);
    int len = (int)strlen(val);
    if (width <= len) return strdup(val);
    char *buf = (char *)malloc(width + 1);
    if (align == '>') {
        for (int i = 0; i < width - len; i++) buf[i] = ' ';
        memcpy(buf + width - len, val, len);
    } else {
        memcpy(buf, val, len);
        for (int i = len; i < width; i++) buf[i] = ' ';
    }
    buf[width] = '\0';
    return buf;
}

/* ---- Set support ---- */
typedef struct {
    PyList *items;  /* reuse PyList internally to store unique elements */
} PySet;

PySet *py_set_new(void) {
    PySet *s = (PySet *)malloc(sizeof(PySet));
    s->items = py_list_new();
    return s;
}

void py_set_add_int(PySet *s, long val) {
    long *d = (long *)s->items->data;
    for (long i = 0; i < s->items->length; i++)
        if (d[i] == val) return;
    s->items->elem_kind = LE_INT;
    py_list_append_int(s->items, val);
}

void py_set_add_str(PySet *s, const char *val) {
    const char **d = (const char **)s->items->data;
    for (long i = 0; i < s->items->length; i++)
        if (strcmp(d[i], val) == 0) return;
    s->items->elem_kind = LE_STR;
    py_list_append_str(s->items, val);
}

int py_set_contains_int(PySet *s, long val) {
    long *d = (long *)s->items->data;
    for (long i = 0; i < s->items->length; i++)
        if (d[i] == val) return 1;
    return 0;
}

int py_set_contains_str(PySet *s, const char *val) {
    const char **d = (const char **)s->items->data;
    for (long i = 0; i < s->items->length; i++)
        if (strcmp(d[i], val) == 0) return 1;
    return 0;
}

long py_set_len(PySet *s) {
    return s->items->length;
}

void py_set_remove_int(PySet *s, long val) {
    long *d = (long *)s->items->data;
    for (long i = 0; i < s->items->length; i++) {
        if (d[i] == val) { py_list_pop_at_int(s->items, i); return; }
    }
}

void py_set_remove_str(PySet *s, const char *val) {
    for (long i = 0; i < s->items->length; i++) {
        if (strcmp(((const char **)s->items->data)[i], val) == 0) {
            py_list_pop_at_str(s->items, i);
            return;
        }
    }
}

PyList *py_set_to_list_int(PySet *s) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_INT);
    long *d = (long *)s->items->data;
    for (long i = 0; i < s->items->length; i++)
        py_list_append_int(r, d[i]);
    return r;
}

PyList *py_set_to_list_str(PySet *s) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_STR);
    const char **d = (const char **)s->items->data;
    for (long i = 0; i < s->items->length; i++)
        py_list_append_str(r, d[i]);
    return r;
}

/* ---- Dict methods ----
 * The current dict representation is a PyObject whose attr_names are the
 * string keys. Iterate over attr_names to implement keys/values/items. */
PyList *py_dict_keys(PyObject *dict) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_STR);
    for (int i = 0; i < dict->n_attrs; i++)
        py_list_append_str(r, dict->attr_names[i]);
    return r;
}

PyList *py_dict_values(PyObject *dict) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_INT);
    for (int i = 0; i < dict->n_attrs; i++)
        py_list_append_int(r, dict->attr_values[i].i);
    return r;
}

PyList *py_dict_items(PyObject *dict) {
    PyList *r = py_list_new();
    py_list_set_kind(r, LE_LIST);
    for (int i = 0; i < dict->n_attrs; i++) {
        PyList *pair = py_list_new();
        py_list_append_str(pair, dict->attr_names[i]);
        py_list_append_int(pair, dict->attr_values[i].i);
        py_list_append_list(r, pair);
    }
    return r;
}

int py_dict_contains(PyObject *dict, const char *key) {
    return py_object_find_attr(dict, key) >= 0;
}

long py_dict_get_int(PyObject *dict, const char *key, long defv) {
    int idx = py_object_find_attr(dict, key);
    if (idx < 0) return defv;
    if (dict->attr_types[idx] == 0) return dict->attr_values[idx].i;
    if (dict->attr_types[idx] == 3) return dict->attr_values[idx].b;
    return defv;
}

double py_dict_get_float(PyObject *dict, const char *key, double defv) {
    int idx = py_object_find_attr(dict, key);
    if (idx < 0) return defv;
    if (dict->attr_types[idx] == 1) return dict->attr_values[idx].f;
    return defv;
}

const char *py_dict_get_str(PyObject *dict, const char *key, const char *defv) {
    int idx = py_object_find_attr(dict, key);
    if (idx < 0) return defv;
    if (dict->attr_types[idx] == 2) return dict->attr_values[idx].s;
    return defv;
}

PyObject *py_dict_get_obj(PyObject *dict, const char *key, PyObject *defv) {
    int idx = py_object_find_attr(dict, key);
    if (idx < 0) return defv;
    if (dict->attr_types[idx] == 5) return dict->attr_values[idx].o;
    return defv;
}

/* ---- Math module ---- */
double py_math_sqrt(double x) { return sqrt(x); }
double py_math_pow(double x, double y) { return pow(x, y); }
double py_math_log(double x) { return log(x); }
double py_math_log2(double x) { return log2(x); }
double py_math_log10(double x) { return log10(x); }
double py_math_sin(double x) { return sin(x); }
double py_math_cos(double x) { return cos(x); }
double py_math_tan(double x) { return tan(x); }
double py_math_floor(double x) { return floor(x); }
double py_math_ceil(double x) { return ceil(x); }
double py_math_fabs(double x) { return fabs(x); }
double py_math_exp(double x) { return exp(x); }

long py_math_gcd(long a, long b) {
    if (a < 0) a = -a;
    if (b < 0) b = -b;
    while (b != 0) {
        long t = b;
        b = a % b;
        a = t;
    }
    return a;
}

long py_math_lcm(long a, long b) {
    if (a == 0 || b == 0) return 0;
    long g = py_math_gcd(a, b);
    long aa = a < 0 ? -a : a;
    long bb = b < 0 ? -b : b;
    return aa / g * bb;
}

double py_math_pi(void) { return 3.14159265358979323846; }
double py_math_e(void) { return 2.71828182845904523536; }
double py_math_inf(void) { return INFINITY; }
double py_math_nan(void) { return NAN; }

/* ---- Exception handling ---- */
#include <setjmp.h>

#define MAX_EXC_MSG 256

typedef struct {
    int active;
    char msg[MAX_EXC_MSG];
    int kind;  /* 0=none, 1=Exception, 2=ValueError, 3=TypeError,
                * 4=ZeroDivisionError, 5=KeyError, 6=IndexError,
                * 7=FileNotFoundError, 8=StopIteration, 9=custom,
                * 10=queue.Empty */
} PyExceptionFrame;

static PyExceptionFrame __exc_stack[256];
static int __exc_sp = 0;

void py_exc_push(void) {
    if (__exc_sp < 256) {
        __exc_stack[__exc_sp].active = 0;
        __exc_stack[__exc_sp].kind = 0;
        __exc_stack[__exc_sp].msg[0] = '\0';
        __exc_sp++;
    }
}

int py_exc_catch(void) {
    /* returns 1 if exception caught, 0 if no exception */
    if (__exc_sp > 0 && __exc_stack[__exc_sp - 1].active) return 1;
    return 0;
}

void py_exc_pop(void) {
    if (__exc_sp > 0) {
        __exc_sp--;
        __exc_stack[__exc_sp].active = 0;
    }
}

const char *py_exc_msg(void) {
    if (__exc_sp > 0) return __exc_stack[__exc_sp - 1].msg;
    return "";
}

int py_exc_kind(void) {
    if (__exc_sp > 0) return __exc_stack[__exc_sp - 1].kind;
    return 0;
}

void py_exc_raise(int kind, const char *msg) {
    if (__exc_sp > 0) {
        PyExceptionFrame *f = &__exc_stack[__exc_sp - 1];
        f->active = 1;
        f->kind = kind;
        if (msg) {
            strncpy(f->msg, msg, MAX_EXC_MSG - 1);
            f->msg[MAX_EXC_MSG - 1] = '\0';
        } else {
            f->msg[0] = '\0';
        }
        /* Flag-based: don't use longjmp. The codegen checks py_exc_catch()
         * after each statement in the try body. */
    } else {
        fprintf(stderr, "Unhandled exception: %s\n", msg ? msg : "");
        exit(1);
    }
}

void py_exc_raise_value(const char *msg) { py_exc_raise(2, msg); }
void py_exc_raise_type(const char *msg) { py_exc_raise(3, msg); }
void py_exc_raise_zerodiv(const char *msg) { py_exc_raise(4, msg); }
void py_exc_raise_key(const char *msg) { py_exc_raise(5, msg); }
void py_exc_raise_index(const char *msg) { py_exc_raise(6, msg); }
void py_exc_raise_stopiter(void) { py_exc_raise(8, ""); }

/* ---- More string methods ---- */
char *py_str_ljust(const char *s, long width, const char *fillchar) {
    long len = (long)strlen(s);
    if (len >= width) return strdup(s);
    char fc = (fillchar && fillchar[0]) ? fillchar[0] : ' ';
    char *r = (char *)malloc((size_t)width + 1);
    memcpy(r, s, len);
    for (long i = len; i < width; i++) r[i] = fc;
    r[width] = '\0';
    return r;
}

char *py_str_rjust(const char *s, long width, const char *fillchar) {
    long len = (long)strlen(s);
    if (len >= width) return strdup(s);
    long pad = width - len;
    char fc = (fillchar && fillchar[0]) ? fillchar[0] : ' ';
    char *r = (char *)malloc((size_t)width + 1);
    for (long i = 0; i < pad; i++) r[i] = fc;
    memcpy(r + pad, s, len);
    r[width] = '\0';
    return r;
}

char *py_str_center(const char *s, long width, const char *fillchar) {
    long len = (long)strlen(s);
    if (len >= width) return strdup(s);
    long total = width - len;
    long left = total / 2;
    long right = total - left;
    char fc = (fillchar && fillchar[0]) ? fillchar[0] : ' ';
    char *r = (char *)malloc((size_t)width + 1);
    for (long i = 0; i < left; i++) r[i] = fc;
    memcpy(r + left, s, len);
    for (long i = 0; i < right; i++) r[left + len + i] = fc;
    r[width] = '\0';
    return r;
}

char *py_str_zfill(const char *s, long width) {
    long len = (long)strlen(s);
    if (len >= width) return strdup(s);
    long pad = width - len;
    char *r = (char *)malloc((size_t)width + 1);
    if (len > 0 && (s[0] == '+' || s[0] == '-')) {
        r[0] = s[0];
        for (long i = 0; i < pad; i++) r[1 + i] = '0';
        memcpy(r + 1 + pad, s + 1, len - 1);
    } else {
        for (long i = 0; i < pad; i++) r[i] = '0';
        memcpy(r + pad, s, len);
    }
    r[width] = '\0';
    return r;
}

char *py_str_title(const char *s) {
    size_t n = strlen(s);
    char *r = (char *)malloc(n + 1);
    int prev_alpha = 0;
    for (size_t i = 0; i < n; i++) {
        unsigned char c = (unsigned char)s[i];
        if (isalpha(c)) {
            r[i] = prev_alpha ? tolower(c) : toupper(c);
            prev_alpha = 1;
        } else {
            r[i] = s[i];
            prev_alpha = 0;
        }
    }
    r[n] = '\0';
    return r;
}

char *py_str_capitalize(const char *s) {
    size_t n = strlen(s);
    char *r = (char *)malloc(n + 1);
    if (n == 0) { r[0] = '\0'; return r; }
    r[0] = toupper((unsigned char)s[0]);
    for (size_t i = 1; i < n; i++) r[i] = tolower((unsigned char)s[i]);
    r[n] = '\0';
    return r;
}

char *py_str_swapcase(const char *s) {
    size_t n = strlen(s);
    char *r = (char *)malloc(n + 1);
    for (size_t i = 0; i < n; i++) {
        unsigned char c = (unsigned char)s[i];
        if (isupper(c)) r[i] = tolower(c);
        else if (islower(c)) r[i] = toupper(c);
        else r[i] = s[i];
    }
    r[n] = '\0';
    return r;
}

char *py_str_removeprefix(const char *s, const char *prefix) {
    size_t lp = strlen(prefix);
    if (strncmp(s, prefix, lp) == 0) {
        size_t ls = strlen(s);
        char *r = (char *)malloc(ls - lp + 1);
        memcpy(r, s + lp, ls - lp);
        r[ls - lp] = '\0';
        return r;
    }
    return strdup(s);
}

char *py_str_removesuffix(const char *s, const char *suffix) {
    size_t ls = strlen(s);
    size_t lsf = strlen(suffix);
    if (lsf <= ls && strcmp(s + ls - lsf, suffix) == 0) {
        char *r = (char *)malloc(ls - lsf + 1);
        memcpy(r, s, ls - lsf);
        r[ls - lsf] = '\0';
        return r;
    }
    return strdup(s);
}

char *py_str_repeat(const char *s, long n) {
    /* same as py_str_mul */
    return py_str_mul(s, n);
}

long py_str_count(const char *s, const char *sub) {
    if (*sub == '\0') return (long)strlen(s) + 1;
    long count = 0;
    size_t lsub = strlen(sub);
    const char *p = s;
    while ((p = strstr(p, sub)) != NULL) {
        count++;
        p += lsub;
    }
    return count;
}

char *py_str_format_simple(const char *fmt, const char *val) {
    /* simple {} substitution: replace all {} with val */
    size_t lv = strlen(val);
    size_t cap = strlen(fmt) + lv + 16;
    char *r = (char *)malloc(cap);
    size_t len = 0;
    const char *p = fmt;
    while (*p) {
        if (p[0] == '{' && p[1] == '}') {
            while (len + lv + 1 >= cap) { cap *= 2; r = realloc(r, cap); }
            memcpy(r + len, val, lv); len += lv;
            p += 2;
        } else {
            if (len + 2 >= cap) { cap *= 2; r = realloc(r, cap); }
            r[len++] = *p++;
        }
    }
    r[len] = '\0';
    return r;
}

/* ---- More builtins ---- */
char *py_hex(long n) {
    char buf[32];
    if (n >= 0) snprintf(buf, sizeof buf, "0x%lx", n);
    else snprintf(buf, sizeof buf, "-0x%lx", -n);
    return strdup(buf);
}

char *py_oct(long n) {
    char buf[32];
    if (n >= 0) snprintf(buf, sizeof buf, "0o%lo", n);
    else snprintf(buf, sizeof buf, "-0o%lo", -n);
    return strdup(buf);
}

char *py_bin(long n) {
    if (n == 0) return strdup("0b0");
    int neg = n < 0;
    unsigned long u = neg ? (unsigned long)(-n) : (unsigned long)n;
    char tmp[80];
    int ti = 0;
    while (u > 0) { tmp[ti++] = (char)('0' + (u & 1)); u >>= 1; }
    int rlen = ti + 2 + (neg ? 1 : 0);
    char *r = (char *)malloc((size_t)rlen + 1);
    int ri = 0;
    if (neg) r[ri++] = '-';
    r[ri++] = '0'; r[ri++] = 'b';
    for (int i = ti - 1; i >= 0; i--) r[ri++] = tmp[i];
    r[ri] = '\0';
    return r;
}

long py_ord(const char *s) {
    /* first character's ASCII value */
    if (!s || !*s) return 0;
    return (long)(unsigned char)s[0];
}

char *py_chr(long n) {
    char *r = (char *)malloc(2);
    r[0] = (char)n;
    r[1] = '\0';
    return r;
}

double py_round(double x, long ndigits) {
    double factor = pow(10.0, (double)ndigits);
    double scaled = x * factor;
    double rounded = (scaled >= 0) ? floor(scaled + 0.5) : ceil(scaled - 0.5);
    return rounded / factor;
}

long py_round_int(double x) {
    return (long)((x >= 0) ? floor(x + 0.5) : ceil(x - 0.5));
}

void py_divmod(long a, long b, long *q, long *r) {
    *q = py_ifloordiv(a, b);
    *r = py_imod(a, b);
}

/* ---- String module constants (as functions returning const char*) ---- */
const char *py_string_ascii_letters(void) {
    return "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
}
const char *py_string_ascii_lowercase(void) { return "abcdefghijklmnopqrstuvwxyz"; }
const char *py_string_ascii_uppercase(void) { return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"; }
const char *py_string_digits(void) { return "0123456789"; }
const char *py_string_hexdigits(void) { return "0123456789abcdefABCDEF"; }
const char *py_string_octdigits(void) { return "01234567"; }
const char *py_string_punctuation(void) { return "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"; }
const char *py_string_whitespace(void) { return " \t\n\r\x0b\x0c"; }

/* ---- Iterator support ---- */
typedef struct {
    PyList *list;
    long index;
    int kind;  /* 0=list, 1=string, 2=dict_keys, 3=dict_values, 4=dict_items, 5=set, 6=range */
    const char *str;  /* for string iteration */
    long range_start;
    long range_stop;
    long range_step;
} PyIterator;

PyIterator *py_iter_list(PyList *list) {
    PyIterator *it = (PyIterator *)malloc(sizeof(PyIterator));
    it->list = list;
    it->index = 0;
    it->kind = 0;
    it->str = NULL;
    it->range_start = 0; it->range_stop = 0; it->range_step = 1;
    return it;
}

PyIterator *py_iter_str(const char *str) {
    PyIterator *it = (PyIterator *)malloc(sizeof(PyIterator));
    it->list = NULL;
    it->index = 0;
    it->kind = 1;
    it->str = str;
    it->range_start = 0; it->range_stop = 0; it->range_step = 1;
    return it;
}

PyIterator *py_iter_range(long start, long stop, long step) {
    PyIterator *it = (PyIterator *)malloc(sizeof(PyIterator));
    it->list = NULL;
    it->index = 0;
    it->kind = 6;
    it->str = NULL;
    it->range_start = start;
    it->range_stop = stop;
    it->range_step = step;
    return it;
}

int py_iter_has_next(PyIterator *it) {
    switch (it->kind) {
        case 0: return it->index < it->list->length;
        case 1: return it->str[it->index] != '\0';
        case 6:
            if (it->range_step > 0) return it->range_start < it->range_stop;
            if (it->range_step < 0) return it->range_start > it->range_stop;
            return 0;
    }
    return 0;
}

long py_iter_next_int(PyIterator *it) {
    switch (it->kind) {
        case 0: return py_list_get_int(it->list, it->index++);
        case 1: return (long)(unsigned char)it->str[it->index++];
        case 6: {
            long v = it->range_start;
            it->range_start += it->range_step;
            return v;
        }
    }
    return 0;
}

const char *py_iter_next_str(PyIterator *it) {
    switch (it->kind) {
        case 0: return py_list_get_str(it->list, it->index++);
        case 1: {
            char *r = (char *)malloc(2);
            r[0] = it->str[it->index++];
            r[1] = '\0';
            return r;
        }
    }
    return "";
}
