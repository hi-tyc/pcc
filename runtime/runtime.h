#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>
#include <limits.h>

/* ----------------- existing string runtime ----------------- */
typedef struct {
    size_t len;
    char* data;
} rt_str;

static inline rt_str rt_str_null(void) {
    rt_str s;
    s.len = 0;
    s.data = (char*)0;
    return s;
}

rt_str rt_str_from_cstr(const char* cstr);
rt_str rt_str_concat(rt_str a, rt_str b);
int rt_str_eq(rt_str a, rt_str b);
void rt_print_str(rt_str s);
void rt_str_free(rt_str* s);

/* input(): read one line from stdin, strip newline, return heap string */
char* rt_input(void);

/* input(prompt): print prompt (no newline), flush, then read one line */
char* rt_input_prompt(rt_str prompt);

/* basic exception helpers (minimal; no traceback yet) */
void rt_raise(const char* exc_name, const char* msg);

/* ----------------- BigInt runtime: Python-style int ----------------- */

#define RT_INT_BASE 1000000000u  /* 1e9 */
#define RT_INT_BASE_DIGITS 9

typedef struct {
    int sign;          /* -1, 0, +1 */
    size_t len;        /* number of used digits */
    size_t cap;        /* allocated digits */
    uint32_t* digits;  /* little-endian base 1e9 limbs */
} rt_int;

/* len(s) for strings -> BigInt */
void rt_str_len(rt_int* out, const rt_str* s);

/* lifecycle */
void rt_int_init(rt_int* x);
void rt_int_clear(rt_int* x);

/* set/parse/copy */
void rt_int_set_si(rt_int* x, long long v);
int  rt_int_from_dec(rt_int* x, const char* dec); /* return 0 on success, nonzero on error */
int  rt_int_to_si_checked(const rt_int* a, long long* out);
void rt_int_copy(rt_int* dst, const rt_int* src);

/* helper: parse decimal, raise ValueError if invalid */
void rt_int_from_dec_or_raise(rt_int* out, const char* dec);

/* truthiness for int: non-zero => 1, zero => 0 */
int rt_int_truthy(const rt_int* a);

/* arithmetic */
void rt_int_add(rt_int* out, const rt_int* a, const rt_int* b);
void rt_int_sub(rt_int* out, const rt_int* a, const rt_int* b);
void rt_int_mul(rt_int* out, const rt_int* a, const rt_int* b);

/* exponentiation (non-negative exponent only; exponent must fit in signed 64-bit) */
void rt_int_pow(rt_int* out, const rt_int* a, const rt_int* b);

/* modular exponentiation: pow(a, b, mod) with b >= 0 and mod != 0 */
void rt_int_powmod(rt_int* out, const rt_int* a, const rt_int* b, const rt_int* mod);

/* compare: -1/0/+1 */
int rt_int_cmp(const rt_int* a, const rt_int* b);

/* print (no quotes, with newline like Python print) */
void rt_print_int(const rt_int* a);

/* helper: convert to signed 64-bit if fits; return 1 if ok, 0 if overflow */
int rt_int_to_si_checked(const rt_int* a, long long* out);

/* Python floor division & modulo (must match Python semantics) */
void rt_int_divmod(rt_int* q, rt_int* r, const rt_int* a, const rt_int* b);
void rt_int_floordiv(rt_int* out, const rt_int* a, const rt_int* b);
void rt_int_mod(rt_int* out, const rt_int* a, const rt_int* b);

#ifdef __cplusplus
}
#endif