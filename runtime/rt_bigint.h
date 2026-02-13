/*
 * BigInt runtime module for pcc.
 *
 * Provides arbitrary-precision integer arithmetic with proper error handling.
 */

#pragma once

#include "rt_config.h"
#include "rt_error.h"

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>

/* BigInt structure using base 10^9 representation */
typedef struct {
    int sign;          /* -1, 0, +1 (0 indicates zero value) */
    size_t len;        /* Number of used digits */
    size_t cap;        /* Allocated capacity */
    uint32_t* digits;  /* Little-endian base 1e9 limbs */
} rt_int;

/* ==================== Lifecycle ==================== */

/**
 * Initialize a BigInt to zero.
 *
 * @param x BigInt to initialize
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_int_init(rt_int* x) RT_NONNULL;

/**
 * Clear a BigInt and free its memory.
 *
 * @param x BigInt to clear
 */
void rt_int_clear(rt_int* x);

/**
 * Create a copy of a BigInt.
 *
 * @param dst Destination BigInt (must be initialized)
 * @param src Source BigInt
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_int_copy(rt_int* dst, const rt_int* src) RT_NONNULL;

/* ==================== Set/Convert ==================== */

/**
 * Set BigInt from a signed 64-bit integer.
 *
 * @param x BigInt to set
 * @param v Value to set
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_int_set_si(rt_int* x, int64_t v) RT_NONNULL;

/**
 * Parse BigInt from decimal string.
 *
 * @param x BigInt to store result
 * @param dec Decimal string (can have +/- prefix)
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_int_from_dec(rt_int* x, const char* dec) RT_NONNULL;

/**
 * Convert BigInt to signed 64-bit if it fits.
 *
 * @param a BigInt to convert
 * @param out Output pointer for the result
 * @return RT_OK if conversion succeeded, RT_ERROR_OVERFLOW if too large
 */
rt_error_code_t rt_int_to_si_checked(const rt_int* a, int64_t* out) RT_NONNULL;

/* ==================== Comparison ==================== */

/**
 * Compare two BigInts.
 *
 * @param a First BigInt
 * @param b Second BigInt
 * @return -1 if a < b, 0 if a == b, +1 if a > b
 */
int rt_int_cmp(const rt_int* a, const rt_int* b) RT_NONNULL;

/**
 * Check if BigInt is zero.
 *
 * @param x BigInt to check
 * @return 1 if zero, 0 otherwise
 */
int rt_int_is_zero(const rt_int* x) RT_NONNULL;

/* ==================== Arithmetic ==================== */

/**
 * Add two BigInts: out = a + b
 *
 * @param out Result BigInt (must be initialized)
 * @param a First operand
 * @param b Second operand
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_int_add(rt_int* out, const rt_int* a, const rt_int* b) RT_NONNULL;

/**
 * Subtract two BigInts: out = a - b
 *
 * @param out Result BigInt (must be initialized)
 * @param a First operand
 * @param b Second operand
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_int_sub(rt_int* out, const rt_int* a, const rt_int* b) RT_NONNULL;

/**
 * Multiply two BigInts: out = a * b
 *
 * @param out Result BigInt (must be initialized)
 * @param a First operand
 * @param b Second operand
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_int_mul(rt_int* out, const rt_int* a, const rt_int* b) RT_NONNULL;

/**
 * Divide two BigInts (floor division): out = a // b
 *
 * @param out Result BigInt (must be initialized)
 * @param a Dividend
 * @param b Divisor (must not be zero)
 * @return RT_OK on success, RT_ERROR_DIVZERO if b is zero
 */
rt_error_code_t rt_int_floordiv(rt_int* out, const rt_int* a, const rt_int* b) RT_NONNULL;

/**
 * Modulo two BigInts: out = a % b
 *
 * @param out Result BigInt (must be initialized)
 * @param a Dividend
 * @param b Divisor (must not be zero)
 * @return RT_OK on success, RT_ERROR_DIVZERO if b is zero
 */
rt_error_code_t rt_int_mod(rt_int* out, const rt_int* a, const rt_int* b) RT_NONNULL;

/**
 * Combined division and modulo: a = q * b + r
 *
 * @param q Quotient (can be NULL if not needed)
 * @param r Remainder (can be NULL if not needed)
 * @param a Dividend
 * @param b Divisor (must not be zero)
 * @return RT_OK on success, RT_ERROR_DIVZERO if b is zero
 */
rt_error_code_t rt_int_divmod(rt_int* q, rt_int* r, const rt_int* a, const rt_int* b) RT_NONNULL;

/* ==================== I/O ==================== */

/**
 * Print BigInt to stdout with newline.
 *
 * @param a BigInt to print
 */
void rt_print_int(const rt_int* a) RT_NONNULL;

/**
 * Print BigInt to file.
 *
 * @param fp File pointer
 * @param a BigInt to print
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_int_fprint(FILE* fp, const rt_int* a) RT_NONNULL;

#ifdef __cplusplus
}
#endif
