/*
 * Math utilities implementation for pcc runtime.
 */

#include "rt_math.h"
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include <math.h>

/* ==================== Native Integer Math ==================== */

int64_t rt_math_abs_si(int64_t x) {
    if (x == INT64_MIN) {
        return INT64_MAX;  /* Special case: abs(INT64_MIN) overflows */
    }
    return x < 0 ? -x : x;
}

int64_t rt_math_min_si(int64_t a, int64_t b) {
    return a < b ? a : b;
}

int64_t rt_math_max_si(int64_t a, int64_t b) {
    return a > b ? a : b;
}

int64_t rt_math_pow_si(int64_t base, int64_t exp) {
    if (exp < 0) {
        return 0;  /* Negative exponents not supported for integers */
    }
    if (exp == 0) {
        return 1;
    }
    if (base == 0) {
        return 0;
    }
    if (base == 1) {
        return 1;
    }
    
    int64_t result = 1;
    int64_t b = base;
    int64_t e = exp;
    
    /* Fast exponentiation by squaring */
    while (e > 0) {
        if (e & 1) {
            /* Check for overflow */
            if (result > INT64_MAX / b) {
                return INT64_MAX;  /* Overflow */
            }
            result *= b;
        }
        e >>= 1;
        if (e > 0) {
            /* Check for overflow */
            if (b > INT64_MAX / b) {
                if (e > 0) {
                    return INT64_MAX;  /* Overflow */
                }
            }
            b *= b;
        }
    }
    
    return result;
}

int64_t rt_math_sqrt_si(int64_t x) {
    if (x < 0) {
        return -1;  /* Error: negative input */
    }
    if (x <= 1) {
        return x;
    }
    
    /* Binary search for integer square root */
    int64_t low = 1, high = x;
    int64_t result = 0;
    
    while (low <= high) {
        int64_t mid = low + (high - low) / 2;
        int64_t div = x / mid;
        
        if (div == mid) {
            return mid;  /* Exact square root */
        } else if (div > mid) {
            low = mid + 1;
            result = mid;  /* Floor candidate */
        } else {
            high = mid - 1;
        }
    }
    
    return result;
}

int64_t rt_math_gcd_si(int64_t a, int64_t b) {
    /* Euclidean algorithm */
    a = rt_math_abs_si(a);
    b = rt_math_abs_si(b);
    
    while (b != 0) {
        int64_t temp = b;
        b = a % b;
        a = temp;
    }
    
    return a;
}

int64_t rt_math_lcm_si(int64_t a, int64_t b) {
    if (a == 0 || b == 0) {
        return 0;
    }
    
    int64_t gcd = rt_math_gcd_si(a, b);
    int64_t abs_a = rt_math_abs_si(a);
    int64_t abs_b = rt_math_abs_si(b);
    
    /* LCM = |a * b| / GCD(a, b) */
    /* Compute as (|a| / GCD) * |b| to avoid overflow */
    int64_t temp = abs_a / gcd;
    
    /* Check for overflow */
    if (temp > INT64_MAX / abs_b) {
        return INT64_MAX;  /* Overflow */
    }
    
    return temp * abs_b;
}

/* ==================== BigInt Math ==================== */

rt_error_code_t rt_math_abs(rt_int* out, const rt_int* x) {
    RT_CHECK_NULL(out, "out");
    RT_CHECK_NULL(x, "x");
    
    rt_error_code_t err = rt_int_copy(out, x);
    if (err != RT_OK) {
        return err;
    }
    
    if (out->sign < 0) {
        out->sign = 1;
    }
    
    return RT_OK;
}

rt_error_code_t rt_math_min(rt_int* out, const rt_int* a, const rt_int* b) {
    RT_CHECK_NULL(out, "out");
    RT_CHECK_NULL(a, "a");
    RT_CHECK_NULL(b, "b");
    
    int cmp = rt_int_cmp(a, b);
    const rt_int* src = (cmp <= 0) ? a : b;
    
    return rt_int_copy(out, src);
}

rt_error_code_t rt_math_max(rt_int* out, const rt_int* a, const rt_int* b) {
    RT_CHECK_NULL(out, "out");
    RT_CHECK_NULL(a, "a");
    RT_CHECK_NULL(b, "b");
    
    int cmp = rt_int_cmp(a, b);
    const rt_int* src = (cmp >= 0) ? a : b;
    
    return rt_int_copy(out, src);
}

rt_error_code_t rt_math_pow(rt_int* out, const rt_int* base, int64_t exp) {
    RT_CHECK_NULL(out, "out");
    RT_CHECK_NULL(base, "base");
    
    if (exp < 0) {
        RT_SET_ERROR(RT_ERROR_INVALID, "Negative exponent not supported");
        return RT_ERROR_INVALID;
    }
    
    if (exp == 0) {
        rt_int_set_si(out, 1);
        return RT_OK;
    }
    
    if (rt_int_is_zero(base)) {
        rt_int_set_si(out, 0);
        return RT_OK;
    }
    
    /* Fast exponentiation by squaring */
    rt_int result, b, temp;
    rt_int_init(&result);
    rt_int_init(&b);
    rt_int_init(&temp);
    
    rt_int_set_si(&result, 1);
    rt_error_code_t err = rt_int_copy(&b, base);
    if (err != RT_OK) {
        goto cleanup;
    }
    
    int64_t e = exp;
    
    while (e > 0) {
        if (e & 1) {
            err = rt_int_mul(&temp, &result, &b);
            if (err != RT_OK) goto cleanup;
            rt_int_copy(&result, &temp);
        }
        e >>= 1;
        if (e > 0) {
            err = rt_int_mul(&temp, &b, &b);
            if (err != RT_OK) goto cleanup;
            rt_int_copy(&b, &temp);
        }
    }
    
    err = rt_int_copy(out, &result);
    
cleanup:
    rt_int_clear(&result);
    rt_int_clear(&b);
    rt_int_clear(&temp);
    
    return err;
}

rt_error_code_t rt_math_sqrt(rt_int* out, const rt_int* x) {
    RT_CHECK_NULL(out, "out");
    RT_CHECK_NULL(x, "x");
    
    if (x->sign < 0) {
        RT_SET_ERROR(RT_ERROR_INVALID, "Cannot compute square root of negative number");
        return RT_ERROR_INVALID;
    }
    
    if (rt_int_is_zero(x)) {
        rt_int_set_si(out, 0);
        return RT_OK;
    }
    
    /* Binary search for integer square root */
    rt_int low, high, mid, temp, div_result;
    rt_int_init(&low);
    rt_int_init(&high);
    rt_int_init(&mid);
    rt_int_init(&temp);
    rt_int_init(&div_result);
    
    rt_int_set_si(&low, 1);
    rt_error_code_t err = rt_int_copy(&high, x);
    if (err != RT_OK) goto cleanup_sqrt;
    
    rt_int result;
    rt_int_init(&result);
    rt_int_set_si(&result, 0);
    
    while (rt_int_cmp(&low, &high) <= 0) {
        /* mid = low + (high - low) / 2 */
        err = rt_int_sub(&temp, &high, &low);
        if (err != RT_OK) goto cleanup_sqrt;
        
        rt_int floordiv_result;
        rt_int_init(&floordiv_result);
        rt_int_set_si(&floordiv_result, 2);
        err = rt_int_floordiv(&mid, &temp, &floordiv_result);
        rt_int_clear(&floordiv_result);
        if (err != RT_OK) goto cleanup_sqrt;
        
        err = rt_int_add(&temp, &low, &mid);
        if (err != RT_OK) goto cleanup_sqrt;
        rt_int_copy(&mid, &temp);
        
        /* div = x / mid */
        err = rt_int_floordiv(&div_result, x, &mid);
        if (err != RT_OK) goto cleanup_sqrt;
        
        int cmp_div = rt_int_cmp(&div_result, &mid);
        
        if (cmp_div == 0) {
            /* Exact square root */
            rt_int_copy(out, &mid);
            goto cleanup_sqrt;
        } else if (cmp_div > 0) {
            /* mid is too small */
            err = rt_int_add(&temp, &mid, &low);
            if (err != RT_OK) goto cleanup_sqrt;
            rt_int_copy(&low, &temp);
            rt_int_copy(&result, &mid);  /* Floor candidate */
        } else {
            /* mid is too large */
            err = rt_int_sub(&temp, &mid, &high);
            if (err != RT_OK) goto cleanup_sqrt;
            rt_int_copy(&high, &temp);
        }
    }
    
    err = rt_int_copy(out, &result);
    rt_int_clear(&result);
    
cleanup_sqrt:
    rt_int_clear(&low);
    rt_int_clear(&high);
    rt_int_clear(&mid);
    rt_int_clear(&temp);
    rt_int_clear(&div_result);
    
    return err;
}

rt_error_code_t rt_math_factorial(rt_int* out, int64_t n) {
    RT_CHECK_NULL(out, "out");
    
    if (n < 0) {
        RT_SET_ERROR(RT_ERROR_INVALID, "Factorial of negative number is undefined");
        return RT_ERROR_INVALID;
    }
    
    rt_error_code_t err = rt_int_set_si(out, 1);
    if (err != RT_OK) return err;
    
    if (n <= 1) {
        return RT_OK;
    }
    
    rt_int temp, i_val;
    rt_int_init(&temp);
    rt_int_init(&i_val);
    
    for (int64_t i = 2; i <= n; i++) {
        err = rt_int_set_si(&i_val, i);
        if (err != RT_OK) goto cleanup_fact;
        
        err = rt_int_mul(&temp, out, &i_val);
        if (err != RT_OK) goto cleanup_fact;
        
        err = rt_int_copy(out, &temp);
        if (err != RT_OK) goto cleanup_fact;
    }
    
cleanup_fact:
    rt_int_clear(&temp);
    rt_int_clear(&i_val);
    
    return err;
}

rt_error_code_t rt_math_binomial(rt_int* out, int64_t n, int64_t k) {
    RT_CHECK_NULL(out, "out");
    
    if (n < 0) {
        RT_SET_ERROR(RT_ERROR_INVALID, "n must be non-negative");
        return RT_ERROR_INVALID;
    }
    
    if (k < 0 || k > n) {
        RT_SET_ERROR(RT_ERROR_INVALID, "k must satisfy 0 <= k <= n");
        return RT_ERROR_INVALID;
    }
    
    /* C(n, k) = C(n, n-k), so use the smaller k for efficiency */
    if (k > n - k) {
        k = n - k;
    }
    
    rt_error_code_t err = rt_int_set_si(out, 1);
    if (err != RT_OK) return err;
    
    if (k == 0) {
        return RT_OK;
    }
    
    rt_int temp, num, den;
    rt_int_init(&temp);
    rt_int_init(&num);
    rt_int_init(&den);
    
    /* Compute C(n, k) = product((n-k+1..n) / (1..k)) */
    for (int64_t i = 1; i <= k; i++) {
        /* Multiply by (n - k + i) */
        err = rt_int_set_si(&num, n - k + i);
        if (err != RT_OK) goto cleanup_binom;
        
        err = rt_int_mul(&temp, out, &num);
        if (err != RT_OK) goto cleanup_binom;
        
        err = rt_int_copy(out, &temp);
        if (err != RT_OK) goto cleanup_binom;
        
        /* Divide by i */
        err = rt_int_set_si(&den, i);
        if (err != RT_OK) goto cleanup_binom;
        
        err = rt_int_floordiv(&temp, out, &den);
        if (err != RT_OK) goto cleanup_binom;
        
        err = rt_int_copy(out, &temp);
        if (err != RT_OK) goto cleanup_binom;
    }
    
cleanup_binom:
    rt_int_clear(&temp);
    rt_int_clear(&num);
    rt_int_clear(&den);
    
    return err;
}

/* ==================== Utility Functions ==================== */

int rt_math_is_prime_si(int64_t n) {
    if (n < 2) {
        return 0;
    }
    if (n == 2) {
        return 1;
    }
    if (n % 2 == 0) {
        return 0;
    }
    
    /* Check odd divisors up to sqrt(n) */
    int64_t sqrt_n = rt_math_sqrt_si(n);
    for (int64_t i = 3; i <= sqrt_n; i += 2) {
        if (n % i == 0) {
            return 0;
        }
    }
    
    return 1;
}

int64_t rt_math_next_prime_si(int64_t n) {
    if (n <= 2) {
        return 2;
    }
    
    /* Start from next odd number */
    if (n % 2 == 0) {
        n++;
    } else {
        n += 2;
    }
    
    /* Search for next prime */
    while (n > 0) {
        if (rt_math_is_prime_si(n)) {
            return n;
        }
        n += 2;
        
        /* Check for overflow */
        if (n < 0) {
            return 0;
        }
    }
    
    return 0;
}

size_t rt_math_num_digits(const rt_int* x) {
    if (!x || rt_int_is_zero(x)) {
        return 1;  /* "0" has 1 digit */
    }
    
    /* Count digits in base 1e9 representation */
    size_t digits = (x->len - 1) * RT_INT_BASE_DIGITS;
    
    /* Count digits in most significant limb */
    uint32_t last = x->digits[x->len - 1];
    while (last > 0) {
        digits++;
        last /= 10;
    }
    
    return digits;
}
