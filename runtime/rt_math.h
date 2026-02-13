/*
 * Math utilities module for pcc runtime.
 *
 * Provides common mathematical functions for BigInt and native integers
 * with proper error handling and edge case management.
 */

#pragma once

#include "rt_config.h"
#include "rt_error.h"
#include "rt_bigint.h"

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stddef.h>

/* ==================== Native Integer Math ==================== */

/**
 * Compute the absolute value of a signed 64-bit integer.
 *
 * @param x Input value
 * @return Absolute value (returns INT64_MAX for INT64_MIN)
 */
int64_t rt_math_abs_si(int64_t x);

/**
 * Compute the minimum of two signed 64-bit integers.
 *
 * @param a First value
 * @param b Second value
 * @return Minimum value
 */
int64_t rt_math_min_si(int64_t a, int64_t b);

/**
 * Compute the maximum of two signed 64-bit integers.
 *
 * @param a First value
 * @param b Second value
 * @return Maximum value
 */
int64_t rt_math_max_si(int64_t a, int64_t b);

/**
 * Compute integer power: base^exp.
 *
 * @param base Base value
 * @param exp Exponent (must be non-negative)
 * @return base^exp, or 0 if exp is negative
 */
int64_t rt_math_pow_si(int64_t base, int64_t exp);

/**
 * Compute integer square root (floor).
 *
 * @param x Input value (must be non-negative)
 * @return Floor of square root, or -1 if x is negative
 */
int64_t rt_math_sqrt_si(int64_t x);

/**
 * Compute greatest common divisor (GCD) using Euclidean algorithm.
 *
 * @param a First value
 * @param b Second value
 * @return GCD of a and b (always non-negative)
 */
int64_t rt_math_gcd_si(int64_t a, int64_t b);

/**
 * Compute least common multiple (LCM).
 *
 * @param a First value
 * @param b Second value
 * @return LCM of a and b, or 0 if either is 0
 */
int64_t rt_math_lcm_si(int64_t a, int64_t b);

/* ==================== BigInt Math ==================== */

/**
 * Compute absolute value of a BigInt.
 *
 * @param out Result BigInt (must be initialized)
 * @param x Input BigInt
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_math_abs(rt_int* out, const rt_int* x) RT_NONNULL;

/**
 * Compute minimum of two BigInts.
 *
 * @param out Result BigInt (must be initialized)
 * @param a First BigInt
 * @param b Second BigInt
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_math_min(rt_int* out, const rt_int* a, const rt_int* b) RT_NONNULL;

/**
 * Compute maximum of two BigInts.
 *
 * @param out Result BigInt (must be initialized)
 * @param a First BigInt
 * @param b Second BigInt
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_math_max(rt_int* out, const rt_int* a, const rt_int* b) RT_NONNULL;

/**
 * Compute integer power: base^exp.
 *
 * @param out Result BigInt (must be initialized)
 * @param base Base BigInt
 * @param exp Exponent (must be non-negative)
 * @return RT_OK on success, RT_ERROR_INVALID if exp is negative
 */
rt_error_code_t rt_math_pow(rt_int* out, const rt_int* base, int64_t exp) RT_NONNULL;

/**
 * Compute integer square root (floor) of a BigInt.
 *
 * @param out Result BigInt (must be initialized)
 * @param x Input BigInt (must be non-negative)
 * @return RT_OK on success, RT_ERROR_INVALID if x is negative
 */
rt_error_code_t rt_math_sqrt(rt_int* out, const rt_int* x) RT_NONNULL;

/**
 * Compute factorial: n!.
 *
 * @param out Result BigInt (must be initialized)
 * @param n Input value (must be non-negative)
 * @return RT_OK on success, RT_ERROR_INVALID if n is negative
 */
rt_error_code_t rt_math_factorial(rt_int* out, int64_t n) RT_NONNULL;

/**
 * Compute binomial coefficient: C(n, k) = n! / (k! * (n-k)!).
 *
 * @param out Result BigInt (must be initialized)
 * @param n Total items (must be non-negative)
 * @param k Items to choose (must be 0 <= k <= n)
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_math_binomial(rt_int* out, int64_t n, int64_t k) RT_NONNULL;

/* ==================== Utility Functions ==================== */

/**
 * Check if a 64-bit integer is a prime number.
 *
 * @param n Number to check (must be >= 2)
 * @return 1 if prime, 0 if not prime or n < 2
 */
int rt_math_is_prime_si(int64_t n);

/**
 * Get the next prime number greater than or equal to n.
 *
 * @param n Starting value
 * @return Next prime >= n, or 0 if overflow would occur
 */
int64_t rt_math_next_prime_si(int64_t n);

/**
 * Compute the number of digits in a BigInt (base 10).
 *
 * @param x BigInt to count digits
 * @return Number of digits (1 for zero)
 */
size_t rt_math_num_digits(const rt_int* x) RT_NONNULL;

#ifdef __cplusplus
}
#endif
