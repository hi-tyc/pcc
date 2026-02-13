/*
 * BigInt runtime module implementation for pcc.
 *
 * Provides arbitrary-precision integer arithmetic using base 10^9 representation.
 */

#include "rt_bigint.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Base for BigInt representation: 10^9 */
#ifndef RT_INT_BASE
#define RT_INT_BASE 1000000000U
#endif
#define RT_INT_BASE_DIGITS 9

/* ==================== Internal Helpers ==================== */

/* Ensure BigInt has enough capacity */
static rt_error_code_t rt_int_ensure_cap(rt_int* x, size_t new_cap) {
    if (new_cap <= x->cap) return RT_OK;

    /* Double capacity strategy */
    size_t alloc_cap = x->cap * 2;
    if (alloc_cap < new_cap) alloc_cap = new_cap;
    if (alloc_cap < 4) alloc_cap = 4;

    uint32_t* new_digits = (uint32_t*)realloc(x->digits, alloc_cap * sizeof(uint32_t));
    RT_CHECK_NULL(new_digits, "digits realloc");

    /* Zero new capacity area */
    memset(new_digits + x->cap, 0, (alloc_cap - x->cap) * sizeof(uint32_t));

    x->digits = new_digits;
    x->cap = alloc_cap;
    return RT_OK;
}

/* Normalize BigInt (remove leading zeros, fix sign) */
static void rt_int_normalize(rt_int* x) {
    while (x->len > 0 && x->digits[x->len - 1] == 0) {
        x->len--;
    }
    if (x->len == 0) {
        x->sign = 0;
    }
}

/* Compare absolute values: returns -1, 0, or 1 */
static int rt_int_cmp_abs(const rt_int* a, const rt_int* b) {
    if (a->len != b->len) {
        return (a->len < b->len) ? -1 : 1;
    }
    for (size_t i = a->len; i-- > 0;) {
        if (a->digits[i] != b->digits[i]) {
            return (a->digits[i] < b->digits[i]) ? -1 : 1;
        }
    }
    return 0;
}

/* ==================== Lifecycle ==================== */

rt_error_code_t rt_int_init(rt_int* x) {
    RT_CHECK_NULL(x, "x");

    x->sign = 0;
    x->len = 0;
    x->cap = 0;
    x->digits = NULL;
    return RT_OK;
}

void rt_int_clear(rt_int* x) {
    if (x == NULL) return;

    free(x->digits);
    x->digits = NULL;
    x->sign = 0;
    x->len = 0;
    x->cap = 0;
}

rt_error_code_t rt_int_copy(rt_int* dst, const rt_int* src) {
    RT_CHECK_NULL(dst, "dst");
    RT_CHECK_NULL(src, "src");

    rt_error_code_t err = rt_int_ensure_cap(dst, src->len);
    if (err != RT_OK) return err;

    memcpy(dst->digits, src->digits, src->len * sizeof(uint32_t));
    dst->len = src->len;
    dst->sign = src->sign;
    return RT_OK;
}

/* ==================== Set/Convert ==================== */

rt_error_code_t rt_int_set_si(rt_int* x, int64_t v) {
    RT_CHECK_NULL(x, "x");

    /* Handle zero */
    if (v == 0) {
        x->sign = 0;
        x->len = 0;
        return RT_OK;
    }

    /* Determine sign */
    if (v < 0) {
        x->sign = -1;
        v = -v;
    } else {
        x->sign = 1;
    }

    /* Store absolute value */
    uint64_t uv = (uint64_t)v;
    size_t needed = 0;
    uint64_t tmp = uv;
    do {
        needed++;
        tmp /= RT_INT_BASE;
    } while (tmp > 0);

    rt_error_code_t err = rt_int_ensure_cap(x, needed);
    if (err != RT_OK) return err;

    x->len = needed;
    for (size_t i = 0; i < needed; i++) {
        x->digits[i] = (uint32_t)(uv % RT_INT_BASE);
        uv /= RT_INT_BASE;
    }

    return RT_OK;
}

rt_error_code_t rt_int_from_dec(rt_int* x, const char* dec) {
    RT_CHECK_NULL(x, "x");
    RT_CHECK_NULL(dec, "dec");

    /* Skip whitespace */
    while (*dec == ' ' || *dec == '\t') dec++;

    /* Handle sign */
    int sign = 1;
    if (*dec == '-') {
        sign = -1;
        dec++;
    } else if (*dec == '+') {
        dec++;
    }

    /* Skip leading zeros */
    while (*dec == '0') dec++;

    /* Handle zero */
    if (*dec == '\0') {
        x->sign = 0;
        x->len = 0;
        return RT_OK;
    }

    /* Count digits */
    const char* p = dec;
    size_t num_digits = 0;
    while (*p >= '0' && *p <= '9') {
        num_digits++;
        p++;
    }

    if (num_digits == 0) {
        RT_SET_ERROR(RT_ERROR_INVALID, "Invalid decimal string");
        return RT_ERROR_INVALID;
    }

    /* Initialize result */
    rt_error_code_t err = rt_int_init(x);
    if (err != RT_OK) return err;

    x->sign = sign;

    /* Process digits from left to right */
    for (const char* p = dec; *p >= '0' && *p <= '9'; p++) {
        int digit = *p - '0';

        /* Multiply current value by 10 and add digit */
        uint64_t carry = (uint64_t)digit;
        for (size_t i = 0; i < x->len || carry > 0; i++) {
            if (i >= x->len) {
                err = rt_int_ensure_cap(x, i + 1);
                if (err != RT_OK) return err;
                x->len = i + 1;
            }
            uint64_t prod = (uint64_t)x->digits[i] * 10 + carry;
            x->digits[i] = (uint32_t)(prod % RT_INT_BASE);
            carry = prod / RT_INT_BASE;
        }
    }

    rt_int_normalize(x);
    return RT_OK;
}

rt_error_code_t rt_int_to_si_checked(const rt_int* a, int64_t* out) {
    RT_CHECK_NULL(a, "a");
    RT_CHECK_NULL(out, "out");

    if (a->sign == 0) {
        *out = 0;
        return RT_OK;
    }

    /* Check if value fits in int64_t */
    if (a->len > 2) {
        return RT_ERROR_OVERFLOW;
    }

    uint64_t val = 0;
    for (size_t i = a->len; i-- > 0;) {
        val = val * RT_INT_BASE + a->digits[i];
    }

    /* Check overflow for positive */
    if (a->sign > 0 && val > INT64_MAX) {
        return RT_ERROR_OVERFLOW;
    }

    /* Check overflow for negative */
    if (a->sign < 0 && val > (uint64_t)INT64_MAX + 1) {
        return RT_ERROR_OVERFLOW;
    }

    *out = (a->sign > 0) ? (int64_t)val : -(int64_t)val;
    return RT_OK;
}

/* ==================== Comparison ==================== */

int rt_int_cmp(const rt_int* a, const rt_int* b) {
    if (a == NULL || b == NULL) return 0;

    /* Handle zeros */
    int a_zero = (a->sign == 0 || a->len == 0);
    int b_zero = (b->sign == 0 || b->len == 0);

    if (a_zero && b_zero) return 0;
    if (a_zero) return (b->sign > 0) ? -1 : 1;
    if (b_zero) return (a->sign > 0) ? 1 : -1;

    /* Different signs */
    if (a->sign != b->sign) {
        return (a->sign > b->sign) ? 1 : -1;
    }

    /* Same sign - compare absolute values */
    int cmp = rt_int_cmp_abs(a, b);
    return (a->sign > 0) ? cmp : -cmp;
}

int rt_int_is_zero(const rt_int* x) {
    if (x == NULL) return 1;
    return (x->sign == 0 || x->len == 0);
}

/* ==================== Arithmetic ==================== */

rt_error_code_t rt_int_add(rt_int* out, const rt_int* a, const rt_int* b) {
    RT_CHECK_NULL(out, "out");
    RT_CHECK_NULL(a, "a");
    RT_CHECK_NULL(b, "b");

    /* Handle zeros */
    if (rt_int_is_zero(a)) return rt_int_copy(out, b);
    if (rt_int_is_zero(b)) return rt_int_copy(out, a);

    /* Same sign - add absolute values */
    if (a->sign == b->sign) {
        size_t max_len = (a->len > b->len) ? a->len : b->len;
        rt_error_code_t err = rt_int_ensure_cap(out, max_len + 1);
        if (err != RT_OK) return err;

        uint64_t carry = 0;
        for (size_t i = 0; i < max_len || carry; i++) {
            uint64_t sum = carry;
            if (i < a->len) sum += a->digits[i];
            if (i < b->len) sum += b->digits[i];

            out->digits[i] = (uint32_t)(sum % RT_INT_BASE);
            carry = sum / RT_INT_BASE;

            if (i >= out->len) out->len = i + 1;
        }

        out->sign = a->sign;
        rt_int_normalize(out);
        return RT_OK;
    }

    /* Different signs - subtract smaller from larger */
    const rt_int* larger = a;
    const rt_int* smaller = b;
    int cmp = rt_int_cmp_abs(a, b);

    if (cmp < 0) {
        larger = b;
        smaller = a;
    } else if (cmp == 0) {
        /* Equal magnitude, opposite sign = zero */
        out->sign = 0;
        out->len = 0;
        return RT_OK;
    }

    rt_error_code_t err = rt_int_ensure_cap(out, larger->len);
    if (err != RT_OK) return err;

    int64_t borrow = 0;
    for (size_t i = 0; i < larger->len; i++) {
        int64_t diff = (int64_t)larger->digits[i] - borrow;
        if (i < smaller->len) diff -= smaller->digits[i];

        if (diff < 0) {
            diff += RT_INT_BASE;
            borrow = 1;
        } else {
            borrow = 0;
        }

        out->digits[i] = (uint32_t)diff;
    }

    out->len = larger->len;
    out->sign = larger->sign;
    rt_int_normalize(out);
    return RT_OK;
}

rt_error_code_t rt_int_sub(rt_int* out, const rt_int* a, const rt_int* b) {
    RT_CHECK_NULL(out, "out");
    RT_CHECK_NULL(a, "a");
    RT_CHECK_NULL(b, "b");

    /* a - b = a + (-b) */
    rt_int b_neg = *b;
    b_neg.sign = -b->sign;

    return rt_int_add(out, a, &b_neg);
}

rt_error_code_t rt_int_mul(rt_int* out, const rt_int* a, const rt_int* b) {
    RT_CHECK_NULL(out, "out");
    RT_CHECK_NULL(a, "a");
    RT_CHECK_NULL(b, "b");

    /* Handle zeros */
    if (rt_int_is_zero(a) || rt_int_is_zero(b)) {
        out->sign = 0;
        out->len = 0;
        return RT_OK;
    }

    size_t result_len = a->len + b->len;
    rt_error_code_t err = rt_int_ensure_cap(out, result_len);
    if (err != RT_OK) return err;

    /* Clear result digits */
    memset(out->digits, 0, result_len * sizeof(uint32_t));

    /* Multiply */
    for (size_t i = 0; i < a->len; i++) {
        uint64_t carry = 0;
        for (size_t j = 0; j < b->len || carry; j++) {
            uint64_t prod = out->digits[i + j] + carry;
            if (j < b->len) {
                prod += (uint64_t)a->digits[i] * b->digits[j];
            }
            out->digits[i + j] = (uint32_t)(prod % RT_INT_BASE);
            carry = prod / RT_INT_BASE;
        }
    }

    out->len = result_len;
    out->sign = a->sign * b->sign;
    rt_int_normalize(out);
    return RT_OK;
}

rt_error_code_t rt_int_floordiv(rt_int* out, const rt_int* a, const rt_int* b) {
    rt_int dummy;
    rt_int_init(&dummy);
    rt_error_code_t result = rt_int_divmod(out, &dummy, a, b);
    rt_int_clear(&dummy);
    return result;
}

rt_error_code_t rt_int_mod(rt_int* out, const rt_int* a, const rt_int* b) {
    rt_int dummy;
    rt_int_init(&dummy);
    rt_error_code_t result = rt_int_divmod(&dummy, out, a, b);
    rt_int_clear(&dummy);
    return result;
}

rt_error_code_t rt_int_divmod(rt_int* q, rt_int* r, const rt_int* a, const rt_int* b) {
    RT_CHECK_NULL(a, "a");
    RT_CHECK_NULL(b, "b");

    if (rt_int_is_zero(b)) {
        RT_SET_ERROR(RT_ERROR_DIVZERO, "Division by zero");
        return RT_ERROR_DIVZERO;
    }

    /* Handle zero dividend */
    if (rt_int_is_zero(a)) {
        if (q) {
            q->sign = 0;
            q->len = 0;
        }
        if (r) {
            r->sign = 0;
            r->len = 0;
        }
        return RT_OK;
    }

    /* Simple case: single digit divisor */
    if (b->len == 1 && b->digits[0] < RT_INT_BASE) {
        if (q) {
            rt_error_code_t err = rt_int_ensure_cap(q, a->len);
            if (err != RT_OK) return err;
        }

        uint64_t divisor = b->digits[0];
        uint64_t rem = 0;

        for (size_t i = a->len; i-- > 0;) {
            uint64_t dividend = rem * RT_INT_BASE + a->digits[i];
            if (q) {
                q->digits[i] = (uint32_t)(dividend / divisor);
            }
            rem = dividend % divisor;
        }

        if (q) {
            q->len = a->len;
            q->sign = a->sign * b->sign;
            rt_int_normalize(q);
        }

        if (r) {
            rt_error_code_t err = rt_int_set_si(r, (int64_t)rem);
            if (err != RT_OK) return err;
            r->sign = a->sign;
            if (rem == 0) r->sign = 0;
        }

        /* Adjust for Python-style floor division */
        /* If there's a remainder and signs differ, adjust q and r */
        if (rem != 0 && a->sign != b->sign) {
            if (q) {
                /* q = q - 1 */
                rt_int one;
                rt_int_init(&one);
                rt_int_set_si(&one, 1);
                rt_int_sub(q, q, &one);
                rt_int_clear(&one);
            }
            if (r) {
                /* r = r + b (to give r the same sign as b) */
                rt_int_add(r, r, b);
            }
        }

        return RT_OK;
    }

    /* General case - use long division algorithm */
    /* For now, return error for complex division */
    RT_SET_ERROR(RT_ERROR_INVALID, "Complex division not yet implemented");
    return RT_ERROR_INVALID;
}

/* ==================== I/O ==================== */

void rt_print_int(const rt_int* a) {
    if (a == NULL) {
        printf("null\n");
        return;
    }

    if (a->sign == 0 || a->len == 0) {
        printf("0\n");
        return;
    }

    if (a->sign < 0) {
        printf("-");
    }

    /* Print most significant digit without leading zeros */
    printf("%u", a->digits[a->len - 1]);

    /* Print remaining digits with leading zeros */
    for (size_t i = a->len - 1; i-- > 0;) {
        printf("%09u", a->digits[i]);
    }

    printf("\n");
}

rt_error_code_t rt_int_fprint(FILE* fp, const rt_int* a) {
    RT_CHECK_NULL(fp, "fp");
    RT_CHECK_NULL(a, "a");

    if (a->sign == 0 || a->len == 0) {
        fprintf(fp, "0");
        return RT_OK;
    }

    if (a->sign < 0) {
        fprintf(fp, "-");
    }

    fprintf(fp, "%u", a->digits[a->len - 1]);

    for (size_t i = a->len - 1; i-- > 0;) {
        fprintf(fp, "%09u", a->digits[i]);
    }

    return RT_OK;
}
