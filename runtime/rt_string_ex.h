/*
 * Extended string utilities module for pcc runtime.
 *
 * Provides additional string manipulation functions including:
 * - Substring extraction
 * - String searching and comparison
 * - Case conversion
 * - String-to-number conversion
 * - Whitespace trimming
 */

#pragma once

#include "rt_config.h"
#include "rt_error.h"
#include "rt_string.h"
#include "rt_bigint.h"

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdint.h>

/* ==================== Substring Operations ==================== */

/**
 * Extract a substring from a string.
 *
 * @param s Source string
 * @param start Start index (0-based, inclusive)
 * @param length Number of characters to extract (or 0 for remainder)
 * @return New string containing the substring, empty string on error
 */
rt_str rt_str_substring(rt_str s, size_t start, size_t length);

/**
 * Get a substring from start to end of string.
 *
 * @param s Source string
 * @param start Start index (0-based)
 * @return New string from start to end
 */
rt_str rt_str_slice_from(rt_str s, size_t start);

/**
 * Get a substring from beginning to end index.
 *
 * @param s Source string
 * @param end End index (exclusive)
 * @return New string from beginning to end
 */
rt_str rt_str_slice_to(rt_str s, size_t end);

/* ==================== Searching ==================== */

/**
 * Find the first occurrence of a substring.
 *
 * @param s String to search in
 * @param pattern Substring to find
 * @param start Index to start searching from
 * @return Index of first occurrence, or (size_t)-1 if not found
 */
size_t rt_str_find(rt_str s, rt_str pattern, size_t start);

/**
 * Find the first occurrence of a C string.
 *
 * @param s String to search in
 * @param pattern C string to find
 * @param start Index to start searching from
 * @return Index of first occurrence, or (size_t)-1 if not found
 */
size_t rt_str_find_cstr(rt_str s, const char* pattern, size_t start);

/**
 * Find the last occurrence of a substring.
 *
 * @param s String to search in
 * @param pattern Substring to find
 * @return Index of last occurrence, or (size_t)-1 if not found
 */
size_t rt_str_rfind(rt_str s, rt_str pattern);

/**
 * Check if string contains a substring.
 *
 * @param s String to search in
 * @param pattern Substring to find
 * @return 1 if found, 0 otherwise
 */
int rt_str_contains(rt_str s, rt_str pattern);

/**
 * Check if string starts with a prefix.
 *
 * @param s String to check
 * @param prefix Prefix to look for
 * @return 1 if s starts with prefix, 0 otherwise
 */
int rt_str_starts_with(rt_str s, rt_str prefix);

/**
 * Check if string ends with a suffix.
 *
 * @param s String to check
 * @param suffix Suffix to look for
 * @return 1 if s ends with suffix, 0 otherwise
 */
int rt_str_ends_with(rt_str s, rt_str suffix);

/* ==================== Comparison ==================== */

/**
 * Compare two strings lexicographically.
 *
 * @param a First string
 * @param b Second string
 * @return <0 if a<b, 0 if a==b, >0 if a>b
 */
int rt_str_compare(rt_str a, rt_str b);

/**
 * Check if two strings are equal.
 *
 * @param a First string
 * @param b Second string
 * @return 1 if equal, 0 otherwise
 */
int rt_str_equals(rt_str a, rt_str b);

/**
 * Compare two strings case-insensitively.
 *
 * @param a First string
 * @param b Second string
 * @return <0 if a<b, 0 if a==b, >0 if a>b (case-insensitive)
 */
int rt_str_compare_ignore_case(rt_str a, rt_str b);

/* ==================== Case Conversion ==================== */

/**
 * Convert string to uppercase.
 *
 * @param s Source string
 * @return New uppercase string
 */
rt_str rt_str_to_upper(rt_str s);

/**
 * Convert string to lowercase.
 *
 * @param s Source string
 * @return New lowercase string
 */
rt_str rt_str_to_lower(rt_str s);

/**
 * Convert first character to uppercase, rest to lowercase.
 *
 * @param s Source string
 * @return New capitalized string
 */
rt_str rt_str_capitalize(rt_str s);

/* ==================== Whitespace Handling ==================== */

/**
 * Remove leading whitespace from string.
 *
 * @param s Source string
 * @return New string with leading whitespace removed
 */
rt_str rt_str_ltrim(rt_str s);

/**
 * Remove trailing whitespace from string.
 *
 * @param s Source string
 * @return New string with trailing whitespace removed
 */
rt_str rt_str_rtrim(rt_str s);

/**
 * Remove leading and trailing whitespace from string.
 *
 * @param s Source string
 * @return New trimmed string
 */
rt_str rt_str_trim(rt_str s);

/**
 * Remove all whitespace from string.
 *
 * @param s Source string
 * @return New string with all whitespace removed
 */
rt_str rt_str_remove_whitespace(rt_str s);

/* ==================== Type Conversion ==================== */

/**
 * Convert BigInt to string representation.
 *
 * @param x BigInt to convert
 * @return String representation of the number
 */
rt_str rt_str_from_int(const rt_int* x) RT_NONNULL;

/**
 * Convert signed 64-bit integer to string.
 *
 * @param x Integer to convert
 * @return String representation
 */
rt_str rt_str_from_si(int64_t x);

/**
 * Parse string as BigInt.
 *
 * @param s String to parse
 * @param out Output BigInt (must be initialized)
 * @return RT_OK on success, RT_ERROR_INVALID if parsing fails
 */
rt_error_code_t rt_str_to_int(rt_str s, rt_int* out) RT_NONNULL;

/**
 * Parse string as signed 64-bit integer.
 *
 * @param s String to parse
 * @param out Output value
 * @return RT_OK on success, RT_ERROR_INVALID if parsing fails, RT_ERROR_OVERFLOW if too large
 */
rt_error_code_t rt_str_to_si(rt_str s, int64_t* out) RT_NONNULL;

/**
 * Check if string represents a valid integer.
 *
 * @param s String to check
 * @return 1 if valid integer, 0 otherwise
 */
int rt_str_is_integer(rt_str s);

/* ==================== String Building ==================== */

/**
 * Repeat a string n times.
 *
 * @param s String to repeat
 * @param count Number of times to repeat (must be >= 0)
 * @return New repeated string, empty if count is 0
 */
rt_str rt_str_repeat(rt_str s, int64_t count);

/**
 * Join strings with a separator.
 *
 * @param strings Array of strings
 * @param count Number of strings in array
 * @param separator Separator string
 * @return New joined string
 */
rt_str rt_str_join(rt_str* strings, size_t count, rt_str separator);

/**
 * Replace all occurrences of a substring.
 *
 * @param s Source string
 * @param old Substring to replace
 * @param replacement Replacement string
 * @return New string with replacements
 */
rt_str rt_str_replace(rt_str s, rt_str old, rt_str replacement);

/**
 * Replace first occurrence of a substring.
 *
 * @param s Source string
 * @param old Substring to replace
 * @param replacement Replacement string
 * @return New string with replacement
 */
rt_str rt_str_replace_first(rt_str s, rt_str old, rt_str replacement);

#ifdef __cplusplus
}
#endif
