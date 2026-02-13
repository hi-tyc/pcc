/*
 * String runtime module for pcc.
 *
 * Provides string operations with proper memory management and error handling.
 */

#pragma once

#include "rt_config.h"
#include "rt_error.h"

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

/* String structure */
typedef struct {
    size_t len;      /* Length of string in bytes */
    size_t cap;      /* Capacity of allocated buffer */
    char* data;      /* Null-terminated character data */
} rt_str;

/* ==================== Lifecycle ==================== */

/**
 * Initialize a string to empty state.
 *
 * @param s String to initialize
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_str_init(rt_str* s) RT_NONNULL;

/**
 * Create a string from a C string.
 *
 * @param cstr Source C string (can be NULL for empty string)
 * @return Initialized string
 */
rt_str rt_str_from_cstr(const char* cstr);

/**
 * Create an empty string.
 *
 * @return Empty string
 */
static inline rt_str rt_str_null(void) {
    rt_str s = {0, 0, NULL};
    return s;
}

/**
 * Clear a string and free its memory.
 *
 * @param s String to clear
 */
void rt_str_clear(rt_str* s);

/* ==================== Operations ==================== */

/**
 * Concatenate two strings.
 *
 * @param a First string
 * @param b Second string
 * @return New string containing a + b
 */
rt_str rt_str_concat(rt_str a, rt_str b);

/**
 * Append a C string to an existing string.
 *
 * @param s String to append to (modified in place)
 * @param cstr C string to append
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_str_append_cstr(rt_str* s, const char* cstr) RT_NONNULL;

/**
 * Get the length of a string.
 *
 * @param s String
 * @return Length in bytes
 */
static inline size_t rt_str_len(const rt_str* s) {
    return s ? s->len : 0;
}

/**
 * Check if string is empty.
 *
 * @param s String
 * @return 1 if empty, 0 otherwise
 */
static inline int rt_str_is_empty(const rt_str* s) {
    return !s || s->len == 0 || !s->data || s->data[0] == '\0';
}

/* ==================== I/O ==================== */

/**
 * Print a string to stdout with newline.
 *
 * @param s String to print
 */
void rt_print_str(rt_str s);

/**
 * Print a string to a file.
 *
 * @param fp File pointer
 * @param s String to print
 * @return RT_OK on success, error code on failure
 */
rt_error_code_t rt_str_fprint(FILE* fp, rt_str s);

#ifdef __cplusplus
}
#endif
