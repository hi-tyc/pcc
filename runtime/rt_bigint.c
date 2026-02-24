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

/* ==================== Karatsuba Multiplication ==================== */

/* Threshold for switching to naive multiplication */
#define KARATSUBA_THRESHOLD 32

/* Add with offset: out += a * BASE^offset (for internal use) */
static rt_error_code_t rt_int_add_offset(rt_int* out, const rt_int* a, size_t offset) {
    if (rt_int_is_zero(a)) return RT_OK;
    
    size_t new_len = a->len + offset;
    if (new_len > out->len) {
        rt_error_code_t err = rt_int_ensure_cap(out, new_len);
        if (err != RT_OK) return err;
        while (out->len < new_len) {
            out->digits[out->len] = 0;
            out->len++;
        }
    }
    
    uint64_t carry = 0;
    for (size_t i = 0; i < a->len || carry; i++) {
        size_t idx = i + offset;
        if (idx >= out->len) {
            rt_error_code_t err = rt_int_ensure_cap(out, idx + 1);
            if (err != RT_OK) return err;
            out->digits[idx] = 0;
            out->len = idx + 1;
        }
        uint64_t sum = out->digits[idx] + carry;
        if (i < a->len) sum += a->digits[i];
        out->digits[idx] = (uint32_t)(sum % RT_INT_BASE);
        carry = sum / RT_INT_BASE;
    }
    
    rt_int_normalize(out);
    return RT_OK;
}

/* Get slice of BigInt: out = a[start:start+len] (for internal use) */
static rt_error_code_t rt_int_slice(rt_int* out, const rt_int* a, size_t start, size_t len) {
    if (start >= a->len || len == 0) {
        out->sign = 0;
        out->len = 0;
        return RT_OK;
    }
    
    size_t actual_len = (start + len > a->len) ? (a->len - start) : len;
    rt_error_code_t err = rt_int_ensure_cap(out, actual_len);
    if (err != RT_OK) return err;
    
    memcpy(out->digits, a->digits + start, actual_len * sizeof(uint32_t));
    out->len = actual_len;
    out->sign = (actual_len > 0) ? 1 : 0;
    rt_int_normalize(out);
    return RT_OK;
}

/* Naive multiplication for small numbers */
static rt_error_code_t rt_int_mul_naive(rt_int* out, const rt_int* a, const rt_int* b) {
    size_t result_len = a->len + b->len;
    rt_error_code_t err = rt_int_ensure_cap(out, result_len);
    if (err != RT_OK) return err;

    memset(out->digits, 0, result_len * sizeof(uint32_t));

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
    rt_int_normalize(out);
    return RT_OK;
}

/* Karatsuba multiplication (internal, works on absolute values) */
static rt_error_code_t rt_int_mul_karatsuba_impl(rt_int* out, const rt_int* a, const rt_int* b) {
    size_t n = (a->len > b->len) ? a->len : b->len;
    
    /* Use naive multiplication for small numbers */
    if (n < KARATSUBA_THRESHOLD) {
        return rt_int_mul_naive(out, a, b);
    }
    
    size_t m = n / 2;
    
    /* Split: a = a1 * B^m + a0, b = b1 * B^m + b0 */
    rt_int a0, a1, b0, b1;
    rt_int_init(&a0);
    rt_int_init(&a1);
    rt_int_init(&b0);
    rt_int_init(&b1);
    
    rt_error_code_t err;
    
    /* a0 = lower m digits of a */
    err = rt_int_slice(&a0, a, 0, m);
    if (err != RT_OK) goto cleanup;
    
    /* a1 = upper digits of a */
    err = rt_int_slice(&a1, a, m, a->len - m);
    if (err != RT_OK) goto cleanup;
    
    /* b0 = lower m digits of b */
    err = rt_int_slice(&b0, b, 0, m);
    if (err != RT_OK) goto cleanup;
    
    /* b1 = upper digits of b */
    err = rt_int_slice(&b1, b, m, b->len - m);
    if (err != RT_OK) goto cleanup;
    
    /* z0 = a0 * b0 */
    rt_int z0;
    rt_int_init(&z0);
    err = rt_int_mul_karatsuba_impl(&z0, &a0, &b0);
    if (err != RT_OK) {
        rt_int_clear(&z0);
        goto cleanup;
    }
    
    /* z2 = a1 * b1 */
    rt_int z2;
    rt_int_init(&z2);
    err = rt_int_mul_karatsuba_impl(&z2, &a1, &b1);
    if (err != RT_OK) {
        rt_int_clear(&z0);
        rt_int_clear(&z2);
        goto cleanup;
    }
    
    /* z1 = (a1 + a0) * (b1 + b0) - z2 - z0 */
    rt_int a_sum, b_sum, z1_temp;
    rt_int_init(&a_sum);
    rt_int_init(&b_sum);
    rt_int_init(&z1_temp);
    
    err = rt_int_add(&a_sum, &a0, &a1);
    if (err != RT_OK) {
        rt_int_clear(&z0);
        rt_int_clear(&z2);
        rt_int_clear(&a_sum);
        rt_int_clear(&b_sum);
        rt_int_clear(&z1_temp);
        goto cleanup;
    }
    
    err = rt_int_add(&b_sum, &b0, &b1);
    if (err != RT_OK) {
        rt_int_clear(&z0);
        rt_int_clear(&z2);
        rt_int_clear(&a_sum);
        rt_int_clear(&b_sum);
        rt_int_clear(&z1_temp);
        goto cleanup;
    }
    
    err = rt_int_mul_karatsuba_impl(&z1_temp, &a_sum, &b_sum);
    if (err != RT_OK) {
        rt_int_clear(&z0);
        rt_int_clear(&z2);
        rt_int_clear(&a_sum);
        rt_int_clear(&b_sum);
        rt_int_clear(&z1_temp);
        goto cleanup;
    }
    
    rt_int z1;
    rt_int_init(&z1);
    err = rt_int_sub(&z1, &z1_temp, &z2);
    if (err != RT_OK) {
        rt_int_clear(&z0);
        rt_int_clear(&z2);
        rt_int_clear(&a_sum);
        rt_int_clear(&b_sum);
        rt_int_clear(&z1_temp);
        rt_int_clear(&z1);
        goto cleanup;
    }
    
    rt_int z1_final;
    rt_int_init(&z1_final);
    err = rt_int_sub(&z1_final, &z1, &z0);
    if (err != RT_OK) {
        rt_int_clear(&z0);
        rt_int_clear(&z2);
        rt_int_clear(&a_sum);
        rt_int_clear(&b_sum);
        rt_int_clear(&z1_temp);
        rt_int_clear(&z1);
        rt_int_clear(&z1_final);
        goto cleanup;
    }
    
    /* result = z2 * B^(2m) + z1 * B^m + z0 */
    out->sign = 0;
    out->len = 0;
    err = rt_int_ensure_cap(out, a->len + b->len);
    if (err != RT_OK) {
        rt_int_clear(&z0);
        rt_int_clear(&z2);
        rt_int_clear(&a_sum);
        rt_int_clear(&b_sum);
        rt_int_clear(&z1_temp);
        rt_int_clear(&z1);
        rt_int_clear(&z1_final);
        goto cleanup;
    }
    memset(out->digits, 0, (a->len + b->len) * sizeof(uint32_t));
    out->len = 0;
    
    /* Add z0 */
    err = rt_int_add_offset(out, &z0, 0);
    if (err != RT_OK) {
        rt_int_clear(&z0);
        rt_int_clear(&z2);
        rt_int_clear(&a_sum);
        rt_int_clear(&b_sum);
        rt_int_clear(&z1_temp);
        rt_int_clear(&z1);
        rt_int_clear(&z1_final);
        goto cleanup;
    }
    
    /* Add z1 * B^m */
    err = rt_int_add_offset(out, &z1_final, m);
    if (err != RT_OK) {
        rt_int_clear(&z0);
        rt_int_clear(&z2);
        rt_int_clear(&a_sum);
        rt_int_clear(&b_sum);
        rt_int_clear(&z1_temp);
        rt_int_clear(&z1);
        rt_int_clear(&z1_final);
        goto cleanup;
    }
    
    /* Add z2 * B^(2m) */
    err = rt_int_add_offset(out, &z2, 2 * m);
    
    rt_int_clear(&z0);
    rt_int_clear(&z2);
    rt_int_clear(&a_sum);
    rt_int_clear(&b_sum);
    rt_int_clear(&z1_temp);
    rt_int_clear(&z1);
    rt_int_clear(&z1_final);
    
cleanup:
    rt_int_clear(&a0);
    rt_int_clear(&a1);
    rt_int_clear(&b0);
    rt_int_clear(&b1);
    
    rt_int_normalize(out);
    return err;
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

    /* Determine result sign */
    int result_sign = a->sign * b->sign;
    
    /* Create temporary copies with positive sign for Karatsuba */
    rt_int a_abs, b_abs;
    rt_int_init(&a_abs);
    rt_int_init(&b_abs);
    
    rt_error_code_t err = rt_int_copy(&a_abs, a);
    if (err != RT_OK) {
        rt_int_clear(&a_abs);
        rt_int_clear(&b_abs);
        return err;
    }
    a_abs.sign = 1;
    
    err = rt_int_copy(&b_abs, b);
    if (err != RT_OK) {
        rt_int_clear(&a_abs);
        rt_int_clear(&b_abs);
        return err;
    }
    b_abs.sign = 1;
    
    /* Use Karatsuba for large numbers, naive for small */
    size_t n = (a_abs.len > b_abs.len) ? a_abs.len : b_abs.len;
    if (n >= KARATSUBA_THRESHOLD) {
        err = rt_int_mul_karatsuba_impl(out, &a_abs, &b_abs);
    } else {
        err = rt_int_mul_naive(out, &a_abs, &b_abs);
    }
    
    out->sign = result_sign;
    
    rt_int_clear(&a_abs);
    rt_int_clear(&b_abs);
    
    rt_int_normalize(out);
    return err;
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

/* ==================== Knuth's Algorithm D (Long Division) ==================== */

/* 
 * Knuth's Algorithm D from "The Art of Computer Programming, Vol. 2"
 * Divides a non-negative integer u by a non-negative integer v.
 * u has m+n digits, v has n digits, where n >= 1.
 * Returns quotient q (m digits) and remainder r (n digits).
 * 
 * This implementation works with base B = 10^9.
 */

/* Compare two BigInts at a specific position (for division) */
static int rt_int_cmp_at_pos(const rt_int* a, const rt_int* b, size_t pos) {
    /* Compare a[pos:pos+b->len] with b */
    size_t a_len = a->len - pos;
    if (a_len > b->len) a_len = b->len;
    
    for (size_t i = b->len; i-- > a_len;) {
        if (b->digits[i] != 0) return -1; /* b is larger */
    }
    
    for (size_t i = a_len; i-- > 0;) {
        if (a->digits[pos + i] < b->digits[i]) return -1;
        if (a->digits[pos + i] > b->digits[i]) return 1;
    }
    return 0;
}

/* Subtract b from a at position pos: a[pos:] -= b */
static void rt_int_sub_at_pos(rt_int* a, const rt_int* b, size_t pos) {
    int64_t borrow = 0;
    for (size_t i = 0; i < b->len; i++) {
        int64_t diff = (int64_t)a->digits[pos + i] - borrow - b->digits[i];
        if (diff < 0) {
            diff += RT_INT_BASE;
            borrow = 1;
        } else {
            borrow = 0;
        }
        a->digits[pos + i] = (uint32_t)diff;
    }
    /* Propagate borrow */
    for (size_t i = pos + b->len; borrow && i < a->len; i++) {
        int64_t diff = (int64_t)a->digits[i] - borrow;
        if (diff < 0) {
            diff += RT_INT_BASE;
            borrow = 1;
        } else {
            borrow = 0;
        }
        a->digits[i] = (uint32_t)diff;
    }
}

/* Add b to a at position pos: a[pos:] += b */
static void rt_int_add_at_pos(rt_int* a, const rt_int* b, size_t pos) {
    uint64_t carry = 0;
    for (size_t i = 0; i < b->len || carry; i++) {
        size_t idx = pos + i;
        if (idx >= a->len) {
            rt_int_ensure_cap((rt_int*)a, idx + 1);
            a->digits[idx] = 0;
            a->len = idx + 1;
        }
        uint64_t sum = a->digits[idx] + carry;
        if (i < b->len) sum += b->digits[i];
        a->digits[idx] = (uint32_t)(sum % RT_INT_BASE);
        carry = sum / RT_INT_BASE;
    }
}

/* Knuth's Algorithm D implementation */
static rt_error_code_t rt_int_divmod_knuth(rt_int* q, rt_int* r, const rt_int* u, const rt_int* v) {
    size_t n = v->len;
    size_t m = u->len - n;
    
    /* D1: Normalize */
    /* Find d such that v[n-1] >= B/2 */
    uint32_t d = 1;
    uint64_t v_top = v->digits[n - 1];
    while (v_top < RT_INT_BASE / 2) {
        v_top *= 2;
        d *= 2;
    }
    
    /* Create normalized copies */
    rt_int u_norm, v_norm;
    rt_int_init(&u_norm);
    rt_int_init(&v_norm);
    
    /* Multiply u by d */
    rt_int_copy(&u_norm, u);
    u_norm.sign = 1;
    if (d > 1) {
        uint64_t carry = 0;
        for (size_t i = 0; i < u_norm.len || carry; i++) {
            if (i >= u_norm.len) {
                rt_int_ensure_cap(&u_norm, i + 1);
                u_norm.len = i + 1;
            }
            uint64_t prod = (uint64_t)u_norm.digits[i] * d + carry;
            u_norm.digits[i] = (uint32_t)(prod % RT_INT_BASE);
            carry = prod / RT_INT_BASE;
        }
        rt_int_normalize(&u_norm);
    }
    
    /* Multiply v by d */
    rt_int_copy(&v_norm, v);
    v_norm.sign = 1;
    if (d > 1) {
        uint64_t carry = 0;
        for (size_t i = 0; i < v_norm.len || carry; i++) {
            if (i >= v_norm.len) {
                rt_int_ensure_cap(&v_norm, i + 1);
                v_norm.len = i + 1;
            }
            uint64_t prod = (uint64_t)v_norm.digits[i] * d + carry;
            v_norm.digits[i] = (uint32_t)(prod % RT_INT_BASE);
            carry = prod / RT_INT_BASE;
        }
        rt_int_normalize(&v_norm);
    }
    
    /* Ensure u_norm has enough digits */
    while (u_norm.len < n + m + 1) {
        rt_int_ensure_cap(&u_norm, u_norm.len + 1);
        u_norm.digits[u_norm.len] = 0;
        u_norm.len++;
    }
    
    /* Initialize quotient */
    if (q) {
        rt_int_ensure_cap(q, m + 1);
        memset(q->digits, 0, (m + 1) * sizeof(uint32_t));
        q->len = m + 1;
    }
    
    /* D2-D7: Main loop */
    for (size_t j = m + 1; j-- > 0;) {
        /* D3: Calculate q_hat */
        uint64_t q_hat;
        uint64_t r_hat;
        
        uint64_t u_jn = (j + n < u_norm.len) ? u_norm.digits[j + n] : 0;
        uint64_t u_jn1 = (j + n - 1 < u_norm.len) ? u_norm.digits[j + n - 1] : 0;
        
        q_hat = (u_jn * RT_INT_BASE + u_jn1) / v_norm.digits[n - 1];
        r_hat = (u_jn * RT_INT_BASE + u_jn1) % v_norm.digits[n - 1];
        
        /* D3: Test q_hat */
        while (q_hat >= RT_INT_BASE ||
               (n >= 2 && q_hat * v_norm.digits[n - 2] > 
                RT_INT_BASE * r_hat + 
                ((j + n - 2 < u_norm.len) ? u_norm.digits[j + n - 2] : 0))) {
            q_hat--;
            r_hat += v_norm.digits[n - 1];
            if (r_hat >= RT_INT_BASE) break;
        }
        
        /* D4: Multiply and subtract */
        uint64_t borrow = 0;
        for (size_t i = 0; i < n; i++) {
            uint64_t prod = q_hat * v_norm.digits[i];
            uint64_t diff = u_norm.digits[j + i] - borrow - (prod % RT_INT_BASE);
            borrow = prod / RT_INT_BASE;
            if (diff < 0) {
                diff += RT_INT_BASE;
                borrow++;
            }
            u_norm.digits[j + i] = (uint32_t)diff;
        }
        
        uint64_t u_jn_val = (j + n < u_norm.len) ? u_norm.digits[j + n] : 0;
        int64_t diff = u_jn_val - borrow;
        
        if (diff < 0) {
            /* D5: Test remainder - add back */
            q_hat--;
            borrow = 0;
            for (size_t i = 0; i < n; i++) {
                uint64_t sum = u_norm.digits[j + i] + v_norm.digits[i] + borrow;
                u_norm.digits[j + i] = (uint32_t)(sum % RT_INT_BASE);
                borrow = sum / RT_INT_BASE;
            }
        }
        
        if (j + n < u_norm.len) {
            u_norm.digits[j + n] = (diff >= 0) ? (uint32_t)diff : 0;
        }
        
        /* Store quotient digit */
        if (q) {
            q->digits[j] = (uint32_t)q_hat;
        }
    }
    
    /* D8: Unnormalize remainder */
    if (r) {
        rt_int_normalize(&u_norm);
        /* Divide u_norm by d to get remainder */
        if (d > 1) {
            uint64_t carry = 0;
            for (size_t i = u_norm.len; i-- > 0;) {
                uint64_t cur = carry * RT_INT_BASE + u_norm.digits[i];
                u_norm.digits[i] = (uint32_t)(cur / d);
                carry = cur % d;
            }
            rt_int_normalize(&u_norm);
        }
        rt_int_copy(r, &u_norm);
    }
    
    if (q) {
        rt_int_normalize(q);
    }
    
    rt_int_clear(&u_norm);
    rt_int_clear(&v_norm);
    
    return RT_OK;
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
    
    /* Compare absolute values */
    int cmp = rt_int_cmp_abs(a, b);
    
    /* If |a| < |b|, quotient is 0, remainder is a */
    if (cmp < 0) {
        if (q) {
            q->sign = 0;
            q->len = 0;
        }
        if (r) {
            rt_int_copy(r, a);
        }
        return RT_OK;
    }
    
    /* If |a| == |b|, quotient is 1 (or -1), remainder is 0 */
    if (cmp == 0) {
        if (q) {
            rt_int_set_si(q, a->sign * b->sign);
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
        if (rem != 0 && a->sign != b->sign) {
            if (q) {
                rt_int one;
                rt_int_init(&one);
                rt_int_set_si(&one, 1);
                rt_int_sub(q, q, &one);
                rt_int_clear(&one);
            }
            if (r) {
                rt_int_add(r, r, b);
            }
        }

        return RT_OK;
    }

    /* General case: use Knuth's Algorithm D */
    int result_sign = a->sign * b->sign;
    
    /* Create absolute value copies */
    rt_int a_abs, b_abs;
    rt_int_init(&a_abs);
    rt_int_init(&b_abs);
    
    rt_int_copy(&a_abs, a);
    a_abs.sign = 1;
    
    rt_int_copy(&b_abs, b);
    b_abs.sign = 1;
    
    rt_int q_temp, r_temp;
    rt_int_init(&q_temp);
    rt_int_init(&r_temp);
    
    rt_error_code_t err = rt_int_divmod_knuth(&q_temp, &r_temp, &a_abs, &b_abs);
    
    if (err == RT_OK) {
        /* Adjust for Python-style floor division */
        if (!rt_int_is_zero(&r_temp) && a->sign != b->sign) {
            rt_int one;
            rt_int_init(&one);
            rt_int_set_si(&one, 1);
            rt_int_sub(&q_temp, &q_temp, &one);
            rt_int_clear(&one);
            
            rt_int_add(&r_temp, &r_temp, &b_abs);
        }
        
        if (q) {
            rt_int_copy(q, &q_temp);
            q->sign = rt_int_is_zero(q) ? 0 : result_sign;
        }
        if (r) {
            rt_int_copy(r, &r_temp);
            r->sign = rt_int_is_zero(r) ? 0 : a->sign;
        }
    }
    
    rt_int_clear(&a_abs);
    rt_int_clear(&b_abs);
    rt_int_clear(&q_temp);
    rt_int_clear(&r_temp);
    
    return err;
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
