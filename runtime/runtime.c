#include "runtime.h"
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ----------------- minimal exception runtime ----------------- */

void rt_raise(const char* exc_name, const char* msg) {
    /* Minimal (no traceback yet). Matches Python's final line format. */
    if (!exc_name) exc_name = "Exception";
    if (!msg) msg = "";
    fprintf(stderr, "%s: %s\n", exc_name, msg);
    exit(1);
}

/* ----------------- input runtime ----------------- */

static char* rt_readline_stdin(void) {
    char buf[4096];
    if (!fgets(buf, sizeof(buf), stdin)) {
        rt_raise("EOFError", "EOF when reading a line");
    }
    size_t len = strlen(buf);
    if (len > 0 && buf[len - 1] == '\n') {
        buf[len - 1] = '\0';
    }
    return strdup(buf);
}

char* rt_input(void) {
    return rt_readline_stdin();
}

char* rt_input_prompt(rt_str prompt) {
    if (prompt.data && prompt.len) {
        fwrite(prompt.data, 1, prompt.len, stdout);
    }
    fflush(stdout);
    return rt_readline_stdin();
}

/* ----------------- string runtime ----------------- */

rt_str rt_str_from_cstr(const char* cstr) {
    rt_str s;
    if (!cstr) {
        s.len = 0;
        s.data = NULL;
        return s;
    }
    size_t n = strlen(cstr);
    s.data = (char*)malloc(n + 1);
    if (!s.data) {
        fprintf(stderr, "pcc runtime error: out of memory\n");
        exit(1);
    }
    memcpy(s.data, cstr, n + 1);
    s.len = n;
    return s;
}

rt_str rt_str_concat(rt_str a, rt_str b) {
    rt_str s;
    size_t n = a.len + b.len;
    s.data = (char*)malloc(n + 1);
    if (!s.data) {
        fprintf(stderr, "pcc runtime error: out of memory\n");
        exit(1);
    }
    if (a.len && a.data) memcpy(s.data, a.data, a.len);
    if (b.len && b.data) memcpy(s.data + a.len, b.data, b.len);
    s.data[n] = '\0';
    s.len = n;
    return s;
}

int rt_str_eq(rt_str a, rt_str b) {
    if (a.len != b.len) return 1;
    if (a.len == 0) return 0;
    return memcmp(a.data, b.data, a.len);
}

void rt_print_str(rt_str s) {
    if (s.data && s.len) {
        fwrite(s.data, 1, s.len, stdout);
    }
    fputc('\n', stdout);
}

void rt_str_free(rt_str* s) {
    if (!s) return;
    if (s->data) free(s->data);
    s->data = NULL;
    s->len = 0;
}

void rt_str_len(rt_int* out, const rt_str* s) {
    /* len(str) -> Python int; we map to BigInt */
    if (!out) return;
    if (!s) {
        rt_int_set_si(out, 0);
        return;
    }
    /* size_t may exceed signed 64-bit theoretically; for now set_si on common platforms */
    if (s->len > (size_t)LLONG_MAX) {
        /* fallback: convert via decimal string */
        char buf[64];
        snprintf(buf, sizeof(buf), "%zu", s->len);
        rt_int_from_dec(out, buf);
        return;
    }
    rt_int_set_si(out, (long long)s->len);
}

/* ----------------- BigInt runtime ----------------- */

static void rt_oom(void) {
    fprintf(stderr, "pcc runtime error: out of memory\n");
    exit(1);
}

void rt_int_init(rt_int* x) {
    x->sign = 0;
    x->len = 0;
    x->cap = 0;
    x->digits = NULL;
}

void rt_int_clear(rt_int* x) {
    if (!x) return;
    free(x->digits);
    x->digits = NULL;
    x->cap = 0;
    x->len = 0;
    x->sign = 0;
}

static void rt_int_reserve(rt_int* x, size_t cap) {
    if (cap <= x->cap) return;
    size_t newcap = x->cap ? x->cap : 1;
    while (newcap < cap) newcap *= 2;
    uint32_t* p = (uint32_t*)realloc(x->digits, newcap * sizeof(uint32_t));
    if (!p) rt_oom();
    x->digits = p;
    x->cap = newcap;
}

static void rt_int_normalize(rt_int* x) {
    while (x->len > 0 && x->digits[x->len - 1] == 0) {
        x->len--;
    }
    if (x->len == 0) {
        x->sign = 0;
    }
}

static void rt_int_set_zero(rt_int* x) {
    x->sign = 0;
    x->len = 0;
}

void rt_int_copy(rt_int* dst, const rt_int* src) {
    if (dst == src) return;
    if (src->len == 0) {
        rt_int_set_zero(dst);
        return;
    }
    rt_int_reserve(dst, src->len);
    memcpy(dst->digits, src->digits, src->len * sizeof(uint32_t));
    dst->len = src->len;
    dst->sign = src->sign;
}

void rt_int_set_si(rt_int* x, long long v) {
    if (v == 0) {
        rt_int_set_zero(x);
        return;
    }
    unsigned long long uv;
    if (v < 0) {
        x->sign = -1;
        uv = (unsigned long long)(-(v + 1)) + 1ULL; /* avoid LLONG_MIN overflow */
    } else {
        x->sign = +1;
        uv = (unsigned long long)v;
    }
    /* up to 2 limbs is enough for 64-bit with base 1e9 */
    rt_int_reserve(x, 3);
    x->len = 0;
    while (uv > 0) {
        x->digits[x->len++] = (uint32_t)(uv % RT_INT_BASE);
        uv /= RT_INT_BASE;
    }
}

static int rt_is_space(char c) {
    return c == ' ' || c == '\t' || c == '\n' || c == '\r';
}

static void rt_int_mul_small(rt_int* x, uint32_t m) {
    if (x->sign == 0 || x->len == 0) return;
    uint64_t carry = 0;
    for (size_t i = 0; i < x->len; i++) {
        uint64_t cur = (uint64_t)x->digits[i] * (uint64_t)m + carry;
        x->digits[i] = (uint32_t)(cur % RT_INT_BASE);
        carry = cur / RT_INT_BASE;
    }
    if (carry) {
        rt_int_reserve(x, x->len + 1);
        x->digits[x->len++] = (uint32_t)carry;
    }
}

static void rt_int_add_small(rt_int* x, uint32_t a) {
    if (x->sign == 0) {
        x->sign = +1;
        rt_int_reserve(x, 1);
        x->digits[0] = a;
        x->len = (a == 0) ? 0 : 1;
        if (x->len == 0) x->sign = 0;
        return;
    }
    /* x assumed positive when parsing decimal magnitude */
    uint64_t carry = a;
    size_t i = 0;
    while (carry && i < x->len) {
        uint64_t cur = (uint64_t)x->digits[i] + carry;
        x->digits[i] = (uint32_t)(cur % RT_INT_BASE);
        carry = cur / RT_INT_BASE;
        i++;
    }
    if (carry) {
        rt_int_reserve(x, x->len + 1);
        x->digits[x->len++] = (uint32_t)carry;
    }
}

/* parse decimal string into x; supports leading +/- and spaces; returns 0 on success */
int rt_int_from_dec(rt_int* x, const char* dec) {
    if (!dec) return 1;

    while (*dec && rt_is_space(*dec)) dec++;

    int sign = +1;
    if (*dec == '+') {
        dec++;
    } else if (*dec == '-') {
        sign = -1;
        dec++;
    }

    while (*dec && rt_is_space(*dec)) dec++;

    if (*dec == '\0') return 1;

    rt_int_set_zero(x);
    x->sign = +1; /* parse magnitude as positive */

    for (const char* p = dec; *p; p++) {
        if (rt_is_space(*p)) break;
        if (*p < '0' || *p > '9') return 1;
        rt_int_mul_small(x, 10);
        rt_int_add_small(x, (uint32_t)(*p - '0'));
    }

    rt_int_normalize(x);
    if (x->sign != 0) x->sign = sign;
    return 0;
}

void rt_int_from_dec_or_raise(rt_int* out, const char* dec) {
    if (!out) return;
    if (!dec) {
        rt_raise("ValueError", "invalid literal for int() with base 10: ''");
    }
    if (rt_int_from_dec(out, dec) != 0) {
        /* Keep message simple & stable; later we can match CPython exact quoting */
        rt_raise("ValueError", "invalid literal for int() with base 10");
    }
}

static int rt_int_cmp_abs(const rt_int* a, const rt_int* b) {
    if (a->len < b->len) return -1;
    if (a->len > b->len) return +1;
    for (size_t i = a->len; i > 0; i--) {
        uint32_t da = a->digits[i - 1];
        uint32_t db = b->digits[i - 1];
        if (da < db) return -1;
        if (da > db) return +1;
    }
    return 0;
}

int rt_int_cmp(const rt_int* a, const rt_int* b) {
    if (a->sign < b->sign) return -1;
    if (a->sign > b->sign) return +1;
    if (a->sign == 0) return 0;
    int c = rt_int_cmp_abs(a, b);
    return (a->sign > 0) ? c : -c;
}

/* out = |a| + |b| (both treated as non-negative magnitudes) */
static void rt_int_add_abs(rt_int* out, const rt_int* a, const rt_int* b) {
    size_t n = (a->len > b->len) ? a->len : b->len;
    rt_int_reserve(out, n + 1);
    uint64_t carry = 0;
    for (size_t i = 0; i < n; i++) {
        uint64_t av = (i < a->len) ? a->digits[i] : 0;
        uint64_t bv = (i < b->len) ? b->digits[i] : 0;
        uint64_t cur = av + bv + carry;
        out->digits[i] = (uint32_t)(cur % RT_INT_BASE);
        carry = cur / RT_INT_BASE;
    }
    out->len = n;
    if (carry) {
        out->digits[out->len++] = (uint32_t)carry;
    }
    rt_int_normalize(out);
}

/* out = |a| - |b|, assuming |a| >= |b| */
static void rt_int_sub_abs(rt_int* out, const rt_int* a, const rt_int* b) {
    rt_int_reserve(out, a->len);
    int64_t borrow = 0;
    for (size_t i = 0; i < a->len; i++) {
        int64_t av = (int64_t)a->digits[i];
        int64_t bv = (i < b->len) ? (int64_t)b->digits[i] : 0;
        int64_t cur = av - bv - borrow;
        if (cur < 0) {
            cur += (int64_t)RT_INT_BASE;
            borrow = 1;
        } else {
            borrow = 0;
        }
        out->digits[i] = (uint32_t)cur;
    }
    out->len = a->len;
    rt_int_normalize(out);
}

void rt_int_add(rt_int* out, const rt_int* a, const rt_int* b) {
    if (a->sign == 0) { rt_int_copy(out, b); return; }
    if (b->sign == 0) { rt_int_copy(out, a); return; }

    if (a->sign == b->sign) {
        rt_int_add_abs(out, a, b);
        out->sign = a->sign;
        return;
    }

    /* different signs: subtract magnitudes */
    int c = rt_int_cmp_abs(a, b);
    if (c == 0) {
        rt_int_set_zero(out);
        return;
    }
    if (c > 0) {
        rt_int_sub_abs(out, a, b);
        out->sign = a->sign;
    } else {
        rt_int_sub_abs(out, b, a);
        out->sign = b->sign;
    }
}

void rt_int_sub(rt_int* out, const rt_int* a, const rt_int* b) {
    if (b->sign == 0) { rt_int_copy(out, a); return; }
    rt_int nb = *b;
    nb.sign = -nb.sign;
    rt_int_add(out, a, &nb);
}

void rt_int_mul(rt_int* out, const rt_int* a, const rt_int* b) {
    if (a->sign == 0 || b->sign == 0 || a->len == 0 || b->len == 0) {
        rt_int_set_zero(out);
        return;
    }
    size_t n = a->len;
    size_t m = b->len;
    rt_int_reserve(out, n + m);
    /* zero initialize */
    for (size_t i = 0; i < n + m; i++) out->digits[i] = 0;
    out->len = n + m;

    for (size_t i = 0; i < n; i++) {
        uint64_t carry = 0;
        uint64_t ai = a->digits[i];
        for (size_t j = 0; j < m; j++) {
            uint64_t cur = (uint64_t)out->digits[i + j] + ai * (uint64_t)b->digits[j] + carry;
            out->digits[i + j] = (uint32_t)(cur % RT_INT_BASE);
            carry = cur / RT_INT_BASE;
        }
        size_t k = i + m;
        while (carry) {
            uint64_t cur = (uint64_t)out->digits[k] + carry;
            out->digits[k] = (uint32_t)(cur % RT_INT_BASE);
            carry = cur / RT_INT_BASE;
            k++;
        }
    }

    rt_int_normalize(out);
    out->sign = a->sign * b->sign;
}

void rt_int_pow(rt_int* out, const rt_int* a, const rt_int* b) {
    long long exp_ll = 0;
    if (!rt_int_to_si_checked(b, &exp_ll)) {
        rt_raise("OverflowError", "exponent too large");
    }
    if (exp_ll < 0) {
        /* CPython: negative int exponent produces float. Not implemented in this MVP. */
        rt_raise("NotImplementedError", "negative exponent produces float (not supported yet)");
    }

    /* Python semantics: 0**0 == 1 */
    if (exp_ll == 0) {
        rt_int_set_si(out, 1);
        return;
    }

    rt_int result;
    rt_int base;
    rt_int tmp;

    rt_int_init(&result);
    rt_int_init(&base);
    rt_int_init(&tmp);

    rt_int_set_si(&result, 1);
    rt_int_copy(&base, a);

    unsigned long long e = (unsigned long long)exp_ll;
    while (e > 0ULL) {
        if (e & 1ULL) {
            rt_int_mul(&tmp, &result, &base);
            rt_int_copy(&result, &tmp);
        }
        e >>= 1ULL;
        if (e) {
            rt_int_mul(&tmp, &base, &base);
            rt_int_copy(&base, &tmp);
        }
    }

    rt_int_copy(out, &result);
    rt_int_clear(&tmp);
    rt_int_clear(&base);
    rt_int_clear(&result);
}

void rt_int_powmod(rt_int* out, const rt_int* a, const rt_int* b, const rt_int* mod) {
    /* mod must be non-zero */
    if (mod->sign == 0 || mod->len == 0) {
        rt_raise("ValueError", "pow() 3rd argument cannot be 0");
    }

    long long exp_ll = 0;
    if (!rt_int_to_si_checked(b, &exp_ll)) {
        rt_raise("OverflowError", "exponent too large");
    }
    if (exp_ll < 0) {
        rt_raise("ValueError", "pow() 2nd argument cannot be negative when 3rd argument specified");
    }

    rt_int result;
    rt_int base;
    rt_int tmp;

    rt_int_init(&result);
    rt_int_init(&base);
    rt_int_init(&tmp);

    /* base = a % mod */
    rt_int_mod(&base, a, mod);

    /* result = 1 % mod (keeps consistent semantics for negative mod via rt_int_mod) */
    rt_int_set_si(&result, 1);
    rt_int_mod(&result, &result, mod);

    unsigned long long e = (unsigned long long)exp_ll;
    while (e > 0ULL) {
        if (e & 1ULL) {
            rt_int_mul(&tmp, &result, &base);
            rt_int_mod(&result, &tmp, mod);
        }
        e >>= 1ULL;
        if (e) {
            rt_int_mul(&tmp, &base, &base);
            rt_int_mod(&base, &tmp, mod);
        }
    }

    rt_int_copy(out, &result);
    rt_int_clear(&tmp);
    rt_int_clear(&base);
    rt_int_clear(&result);
}

void rt_print_int(const rt_int* a) {
    if (a->sign == 0 || a->len == 0) {
        printf("0\n");
        return;
    }
    if (a->sign < 0) putchar('-');

    /* print most significant limb without leading zeros */
    size_t i = a->len - 1;
    printf("%u", a->digits[i]);

    /* remaining limbs with zero-padding to 9 digits */
    while (i > 0) {
        i--;
        printf("%09u", a->digits[i]);
    }
    putchar('\n');
}

int rt_int_to_si_checked(const rt_int* a, long long* out) {
    if (!out) return 0;
    if (a->sign == 0 || a->len == 0) {
        *out = 0;
        return 1;
    }
    /* Reconstruct into unsigned long long and check overflow */
    unsigned long long acc = 0;
    for (size_t i = a->len; i > 0; i--) {
        uint32_t limb = a->digits[i - 1];
        /* acc = acc * base + limb; check overflow */
        if (acc > (ULLONG_MAX / RT_INT_BASE)) return 0;
        acc *= (unsigned long long)RT_INT_BASE;
        if (acc > ULLONG_MAX - (unsigned long long)limb) return 0;
        acc += (unsigned long long)limb;
    }

    if (a->sign > 0) {
        if (acc > (unsigned long long)LLONG_MAX) return 0;
        *out = (long long)acc;
        return 1;
    } else {
        /* allow LLONG_MIN */
        if (acc > (unsigned long long)LLONG_MAX + 1ULL) return 0;
        if (acc == (unsigned long long)LLONG_MAX + 1ULL) {
            *out = LLONG_MIN;
        } else {
            *out = -(long long)acc;
        }
        return 1;
    }
}

/* ----------------- BigInt: Python floor division & modulo ----------------- */

static int rt_int_is_zero(const rt_int* x) {
    return x->sign == 0 || x->len == 0;
}

int rt_int_truthy(const rt_int* a) {
    return !rt_int_is_zero(a);
}

static void rt_int_abs_copy(rt_int* dst, const rt_int* src) {
    rt_int_copy(dst, src);
    if (!rt_int_is_zero(dst)) dst->sign = +1;
}

static void rt_int_neg_inplace(rt_int* x) {
    if (!rt_int_is_zero(x)) x->sign = -x->sign;
}

/* r = r*BASE + limb, where BASE is RT_INT_BASE and limb < BASE */
static void rt_int_shift_add_limb(rt_int* r, uint32_t limb) {
    if (rt_int_is_zero(r)) {
        if (limb == 0) return;
        rt_int_reserve(r, 1);
        r->digits[0] = limb;
        r->len = 1;
        r->sign = +1;
        return;
    }
    rt_int_reserve(r, r->len + 1);
    memmove(r->digits + 1, r->digits, r->len * sizeof(uint32_t));
    r->digits[0] = limb;
    r->len += 1;
    r->sign = +1;
    rt_int_normalize(r);
}

/* tmp = b * qdigit (0<=qdigit<BASE), b is non-negative */
static void rt_int_mul_small_copy(rt_int* tmp, const rt_int* b, uint32_t qdigit) {
    rt_int_copy(tmp, b);
    if (qdigit == 0 || rt_int_is_zero(tmp)) {
        rt_int_set_zero(tmp);
        return;
    }
    rt_int_mul_small(tmp, qdigit);
    tmp->sign = +1;
    rt_int_normalize(tmp);
}

/* Absolute divmod: a_abs, b_abs are non-negative, b_abs > 0.
   Produces q,r such that: a_abs = q*b_abs + r, and 0 <= r < b_abs.
*/
static void rt_int_divmod_abs(rt_int* q, rt_int* r, const rt_int* a_abs, const rt_int* b_abs) {
    if (rt_int_cmp_abs(a_abs, b_abs) < 0) {
        rt_int_set_zero(q);
        rt_int_copy(r, a_abs);
        if (!rt_int_is_zero(r)) r->sign = +1;
        return;
    }

    rt_int_reserve(q, a_abs->len);
    for (size_t i = 0; i < a_abs->len; i++) q->digits[i] = 0;
    q->len = a_abs->len;
    q->sign = +1;

    rt_int_set_zero(r);

    rt_int tmp;
    rt_int_init(&tmp);

    for (size_t i = a_abs->len; i > 0; i--) {
        uint32_t limb = a_abs->digits[i - 1];
        rt_int_shift_add_limb(r, limb);

        uint32_t lo = 0;
        uint32_t hi = RT_INT_BASE - 1;
        uint32_t best = 0;

        while (lo <= hi) {
            uint32_t mid = lo + (hi - lo) / 2;
            rt_int_mul_small_copy(&tmp, b_abs, mid);
            int cmp = rt_int_cmp_abs(&tmp, r);
            if (cmp <= 0) {
                best = mid;
                lo = mid + 1;
            } else {
                if (mid == 0) break;
                hi = mid - 1;
            }
        }

        if (best != 0) {
            rt_int_mul_small_copy(&tmp, b_abs, best);
            rt_int_sub_abs(r, r, &tmp); /* in-place ok */
            if (!rt_int_is_zero(r)) r->sign = +1;
        }

        q->digits[i - 1] = best;
    }

    rt_int_normalize(q);
    rt_int_normalize(r);

    rt_int_clear(&tmp);
}

void rt_int_divmod(rt_int* q, rt_int* r, const rt_int* a, const rt_int* b) {
    if (rt_int_is_zero(b)) {
        rt_raise("ZeroDivisionError", "integer division or modulo by zero");
    }

    rt_int aa, bb, q0, r0;
    rt_int_init(&aa); rt_int_init(&bb);
    rt_int_init(&q0); rt_int_init(&r0);

    rt_int_abs_copy(&aa, a);
    rt_int_abs_copy(&bb, b);

    rt_int_divmod_abs(&q0, &r0, &aa, &bb); /* q0,r0 >=0 */

    int sign_a = a->sign;
    int sign_b = b->sign;

    rt_int_copy(q, &q0);
    rt_int_copy(r, &r0);

    if (rt_int_is_zero(&r0)) {
        if (sign_a * sign_b < 0) {
            rt_int_neg_inplace(q);
        }
        /* r is 0 */
    } else {
        if (sign_a * sign_b < 0) {
            /* q = -(q0 + 1), r = |b| - r0 */
            rt_int one;
            rt_int_init(&one);
            rt_int_set_si(&one, 1LL);

            rt_int_add(q, &q0, &one);
            rt_int_neg_inplace(q);

            rt_int_sub_abs(r, &bb, &r0);
            rt_int_normalize(r);

            rt_int_clear(&one);
        }
    }

    /* r must have sign of b (or be 0) */
    if (!rt_int_is_zero(r) && sign_b < 0) {
        rt_int_neg_inplace(r);
    }

    rt_int_clear(&aa); rt_int_clear(&bb);
    rt_int_clear(&q0); rt_int_clear(&r0);
}

void rt_int_floordiv(rt_int* out, const rt_int* a, const rt_int* b) {
    rt_int q, r;
    rt_int_init(&q); rt_int_init(&r);
    rt_int_divmod(&q, &r, a, b);
    rt_int_copy(out, &q);
    rt_int_clear(&q);
    rt_int_clear(&r);
}

void rt_int_mod(rt_int* out, const rt_int* a, const rt_int* b) {
    rt_int q, r;
    rt_int_init(&q); rt_int_init(&r);
    rt_int_divmod(&q, &r, a, b);
    rt_int_copy(out, &r);
    rt_int_clear(&q);
    rt_int_clear(&r);
}
