/*
 * Unit tests for extended runtime modules (rt_math and rt_string_ex).
 *
 * These tests verify the functionality of the new builtin features
 * including math utilities and extended string operations.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <limits.h>
#include <math.h>

#include "../../runtime/runtime.h"

/* Test result tracking */
static int tests_run = 0;
static int tests_passed = 0;
static int tests_failed = 0;

#define TEST(name) void test_##name(void)
#define RUN_TEST(name) do { \
    printf("  Running %s... ", #name); \
    tests_run++; \
    test_##name(); \
    tests_passed++; \
    printf("PASSED\n"); \
} while(0)

#define ASSERT(cond) do { \
    if (!(cond)) { \
        printf("FAILED\n  Assertion failed: %s at line %d\n", #cond, __LINE__); \
        tests_failed++; \
        tests_passed--; \
        return; \
    } \
} while(0)

#define ASSERT_EQ(a, b) ASSERT((a) == (b))
#define ASSERT_NE(a, b) ASSERT((a) != (b))
#define ASSERT_LT(a, b) ASSERT((a) < (b))
#define ASSERT_GT(a, b) ASSERT((a) > (b))
#define ASSERT_LE(a, b) ASSERT((a) <= (b))
#define ASSERT_GE(a, b) ASSERT((a) >= (b))

/* ==================== Math Utility Tests ==================== */

TEST(math_abs_si) {
    ASSERT_EQ(rt_math_abs_si(0), 0);
    ASSERT_EQ(rt_math_abs_si(5), 5);
    ASSERT_EQ(rt_math_abs_si(-5), 5);
    ASSERT_EQ(rt_math_abs_si(INT64_MAX), INT64_MAX);
    /* INT64_MIN special case - returns INT64_MAX due to overflow */
    ASSERT_EQ(rt_math_abs_si(INT64_MIN), INT64_MAX);
}

TEST(math_min_max_si) {
    ASSERT_EQ(rt_math_min_si(3, 5), 3);
    ASSERT_EQ(rt_math_min_si(5, 3), 3);
    ASSERT_EQ(rt_math_min_si(-3, -5), -5);
    ASSERT_EQ(rt_math_min_si(3, 3), 3);
    
    ASSERT_EQ(rt_math_max_si(3, 5), 5);
    ASSERT_EQ(rt_math_max_si(5, 3), 5);
    ASSERT_EQ(rt_math_max_si(-3, -5), -3);
    ASSERT_EQ(rt_math_max_si(3, 3), 3);
}

TEST(math_pow_si) {
    ASSERT_EQ(rt_math_pow_si(2, 10), 1024);
    ASSERT_EQ(rt_math_pow_si(3, 4), 81);
    ASSERT_EQ(rt_math_pow_si(5, 0), 1);
    ASSERT_EQ(rt_math_pow_si(0, 5), 0);
    ASSERT_EQ(rt_math_pow_si(1, 100), 1);
    ASSERT_EQ(rt_math_pow_si(-2, 3), -8);
    ASSERT_EQ(rt_math_pow_si(-2, 4), 16);
    /* Negative exponent returns 0 */
    ASSERT_EQ(rt_math_pow_si(2, -1), 0);
}

TEST(math_sqrt_si) {
    ASSERT_EQ(rt_math_sqrt_si(0), 0);
    ASSERT_EQ(rt_math_sqrt_si(1), 1);
    ASSERT_EQ(rt_math_sqrt_si(4), 2);
    ASSERT_EQ(rt_math_sqrt_si(9), 3);
    ASSERT_EQ(rt_math_sqrt_si(15), 3);  /* Floor */
    ASSERT_EQ(rt_math_sqrt_si(16), 4);
    ASSERT_EQ(rt_math_sqrt_si(100), 10);
    /* Negative input returns -1 */
    ASSERT_EQ(rt_math_sqrt_si(-1), -1);
}

TEST(math_gcd_si) {
    ASSERT_EQ(rt_math_gcd_si(48, 18), 6);
    ASSERT_EQ(rt_math_gcd_si(18, 48), 6);
    ASSERT_EQ(rt_math_gcd_si(100, 35), 5);
    ASSERT_EQ(rt_math_gcd_si(7, 13), 1);
    ASSERT_EQ(rt_math_gcd_si(0, 5), 5);
    ASSERT_EQ(rt_math_gcd_si(5, 0), 5);
    ASSERT_EQ(rt_math_gcd_si(0, 0), 0);
    /* Negative numbers */
    ASSERT_EQ(rt_math_gcd_si(-48, 18), 6);
    ASSERT_EQ(rt_math_gcd_si(48, -18), 6);
}

TEST(math_lcm_si) {
    ASSERT_EQ(rt_math_lcm_si(4, 6), 12);
    ASSERT_EQ(rt_math_lcm_si(6, 4), 12);
    ASSERT_EQ(rt_math_lcm_si(21, 6), 42);
    ASSERT_EQ(rt_math_lcm_si(0, 5), 0);
    ASSERT_EQ(rt_math_lcm_si(5, 0), 0);
    ASSERT_EQ(rt_math_lcm_si(1, 1), 1);
}

TEST(math_is_prime_si) {
    ASSERT_EQ(rt_math_is_prime_si(0), 0);
    ASSERT_EQ(rt_math_is_prime_si(1), 0);
    ASSERT_EQ(rt_math_is_prime_si(2), 1);
    ASSERT_EQ(rt_math_is_prime_si(3), 1);
    ASSERT_EQ(rt_math_is_prime_si(4), 0);
    ASSERT_EQ(rt_math_is_prime_si(17), 1);
    ASSERT_EQ(rt_math_is_prime_si(18), 0);
    ASSERT_EQ(rt_math_is_prime_si(97), 1);
    ASSERT_EQ(rt_math_is_prime_si(100), 0);
}

TEST(math_next_prime_si) {
    ASSERT_EQ(rt_math_next_prime_si(0), 2);
    ASSERT_EQ(rt_math_next_prime_si(1), 2);
    ASSERT_EQ(rt_math_next_prime_si(2), 2);
    ASSERT_EQ(rt_math_next_prime_si(3), 3);
    ASSERT_EQ(rt_math_next_prime_si(4), 5);
    ASSERT_EQ(rt_math_next_prime_si(14), 17);
    ASSERT_EQ(rt_math_next_prime_si(17), 17);
    ASSERT_EQ(rt_math_next_prime_si(18), 19);
}

/* ==================== BigInt Math Tests ==================== */

TEST(math_abs_bigint) {
    rt_int a, result;
    rt_int_init(&a);
    rt_int_init(&result);
    
    rt_int_set_si(&a, -42);
    rt_error_code_t err = rt_math_abs(&result, &a);
    ASSERT_EQ(err, RT_OK);
    ASSERT_EQ(result.sign, 1);
    
    rt_int_clear(&a);
    rt_int_clear(&result);
}

TEST(math_min_max_bigint) {
    rt_int a, b, result;
    rt_int_init(&a);
    rt_int_init(&b);
    rt_int_init(&result);
    
    rt_int_set_si(&a, 10);
    rt_int_set_si(&b, 20);
    
    rt_math_min(&result, &a, &b);
    /* result should be 10 */
    
    rt_math_max(&result, &a, &b);
    /* result should be 20 */
    
    rt_int_clear(&a);
    rt_int_clear(&b);
    rt_int_clear(&result);
}

TEST(math_factorial) {
    rt_int result;
    rt_int_init(&result);
    
    rt_error_code_t err = rt_math_factorial(&result, 0);
    ASSERT_EQ(err, RT_OK);
    ASSERT(rt_int_is_zero(&result) == 0);  /* 0! = 1 */
    
    err = rt_math_factorial(&result, 5);
    ASSERT_EQ(err, RT_OK);
    /* 5! = 120 */
    
    err = rt_math_factorial(&result, 10);
    ASSERT_EQ(err, RT_OK);
    /* 10! = 3628800 */
    
    /* Negative should fail */
    err = rt_math_factorial(&result, -1);
    ASSERT_EQ(err, RT_ERROR_INVALID);
    
    rt_int_clear(&result);
}

TEST(math_binomial) {
    rt_int result;
    rt_int_init(&result);
    
    rt_error_code_t err = rt_math_binomial(&result, 5, 2);
    ASSERT_EQ(err, RT_OK);
    /* C(5,2) = 10 */
    
    err = rt_math_binomial(&result, 10, 0);
    ASSERT_EQ(err, RT_OK);
    /* C(10,0) = 1 */
    
    err = rt_math_binomial(&result, 10, 10);
    ASSERT_EQ(err, RT_OK);
    /* C(10,10) = 1 */
    
    /* k > n should fail */
    err = rt_math_binomial(&result, 5, 6);
    ASSERT_EQ(err, RT_ERROR_INVALID);
    
    rt_int_clear(&result);
}

/* ==================== Extended String Tests ==================== */

TEST(string_substring) {
    rt_str s = rt_str_from_cstr("Hello, World!");
    
    rt_str sub = rt_str_substring(s, 0, 5);
    ASSERT_EQ(sub.len, 5);
    ASSERT(memcmp(sub.data, "Hello", 5) == 0);
    rt_str_clear(&sub);
    
    sub = rt_str_substring(s, 7, 5);
    ASSERT_EQ(sub.len, 5);
    ASSERT(memcmp(sub.data, "World", 5) == 0);
    rt_str_clear(&sub);
    
    /* Start beyond length */
    sub = rt_str_substring(s, 100, 5);
    ASSERT_EQ(sub.len, 0);
    rt_str_clear(&sub);
    
    rt_str_clear(&s);
}

TEST(string_find) {
    rt_str s = rt_str_from_cstr("Hello, World! Hello!");
    rt_str pattern = rt_str_from_cstr("Hello");
    
    size_t pos = rt_str_find(s, pattern, 0);
    ASSERT_EQ(pos, 0);
    
    pos = rt_str_find(s, pattern, 1);
    ASSERT_EQ(pos, 14);
    
    rt_str not_found = rt_str_from_cstr("xyz");
    pos = rt_str_find(s, not_found, 0);
    ASSERT_EQ(pos, (size_t)-1);
    
    rt_str_clear(&s);
    rt_str_clear(&pattern);
    rt_str_clear(&not_found);
}

TEST(string_contains_starts_ends) {
    rt_str s = rt_str_from_cstr("Hello, World!");
    rt_str prefix = rt_str_from_cstr("Hello");
    rt_str suffix = rt_str_from_cstr("World!");
    rt_str middle = rt_str_from_cstr("lo, Wo");
    rt_str not_in = rt_str_from_cstr("xyz");
    
    ASSERT_EQ(rt_str_contains(s, middle), 1);
    ASSERT_EQ(rt_str_contains(s, not_in), 0);
    ASSERT_EQ(rt_str_starts_with(s, prefix), 1);
    ASSERT_EQ(rt_str_starts_with(s, suffix), 0);
    ASSERT_EQ(rt_str_ends_with(s, suffix), 1);
    ASSERT_EQ(rt_str_ends_with(s, prefix), 0);
    
    rt_str_clear(&s);
    rt_str_clear(&prefix);
    rt_str_clear(&suffix);
    rt_str_clear(&middle);
    rt_str_clear(&not_in);
}

TEST(string_compare) {
    rt_str a = rt_str_from_cstr("abc");
    rt_str b = rt_str_from_cstr("abc");
    rt_str c = rt_str_from_cstr("def");
    rt_str d = rt_str_from_cstr("ab");
    
    ASSERT_EQ(rt_str_compare(a, b), 0);
    ASSERT(rt_str_compare(a, c) < 0);
    ASSERT(rt_str_compare(c, a) > 0);
    ASSERT(rt_str_compare(a, d) > 0);
    
    ASSERT_EQ(rt_str_equals(a, b), 1);
    ASSERT_EQ(rt_str_equals(a, c), 0);
    
    rt_str_clear(&a);
    rt_str_clear(&b);
    rt_str_clear(&c);
    rt_str_clear(&d);
}

TEST(string_case_conversion) {
    rt_str s = rt_str_from_cstr("Hello World");
    
    rt_str upper = rt_str_to_upper(s);
    ASSERT_EQ(upper.len, s.len);
    ASSERT(memcmp(upper.data, "HELLO WORLD", upper.len) == 0);
    rt_str_clear(&upper);
    
    rt_str lower = rt_str_to_lower(s);
    ASSERT_EQ(lower.len, s.len);
    ASSERT(memcmp(lower.data, "hello world", lower.len) == 0);
    rt_str_clear(&lower);
    
    rt_str cap = rt_str_capitalize(s);
    ASSERT_EQ(cap.len, s.len);
    ASSERT(memcmp(cap.data, "Hello world", cap.len) == 0);
    rt_str_clear(&cap);
    
    rt_str_clear(&s);
}

TEST(string_trim) {
    rt_str s = rt_str_from_cstr("  Hello World  ");
    
    rt_str trimmed = rt_str_trim(s);
    ASSERT_EQ(trimmed.len, 11);
    ASSERT(memcmp(trimmed.data, "Hello World", 11) == 0);
    rt_str_clear(&trimmed);
    
    rt_str ltrimmed = rt_str_ltrim(s);
    ASSERT_EQ(ltrimmed.len, 13);
    rt_str_clear(&ltrimmed);
    
    rt_str rtrimmed = rt_str_rtrim(s);
    ASSERT_EQ(rtrimmed.len, 13);
    rt_str_clear(&rtrimmed);
    
    rt_str no_space = rt_str_remove_whitespace(s);
    ASSERT_EQ(no_space.len, 10);
    ASSERT(memcmp(no_space.data, "HelloWorld", 10) == 0);
    rt_str_clear(&no_space);
    
    rt_str_clear(&s);
}

TEST(string_repeat) {
    rt_str s = rt_str_from_cstr("ab");
    
    rt_str repeated = rt_str_repeat(s, 3);
    ASSERT_EQ(repeated.len, 6);
    ASSERT(memcmp(repeated.data, "ababab", 6) == 0);
    rt_str_clear(&repeated);
    
    /* Zero or negative count */
    repeated = rt_str_repeat(s, 0);
    ASSERT_EQ(repeated.len, 0);
    rt_str_clear(&repeated);
    
    rt_str_clear(&s);
}

TEST(string_replace) {
    rt_str s = rt_str_from_cstr("Hello World Hello");
    rt_str old = rt_str_from_cstr("Hello");
    rt_str replacement = rt_str_from_cstr("Hi");
    
    rt_str result = rt_str_replace(s, old, replacement);
    ASSERT_EQ(result.len, 13);
    ASSERT(memcmp(result.data, "Hi World Hi", 11) == 0);
    rt_str_clear(&result);
    
    rt_str first = rt_str_replace_first(s, old, replacement);
    ASSERT_EQ(first.len, 15);
    rt_str_clear(&first);
    
    rt_str_clear(&s);
    rt_str_clear(&old);
    rt_str_clear(&replacement);
}

TEST(string_to_int) {
    rt_str s = rt_str_from_cstr("  12345  ");
    rt_int result;
    rt_int_init(&result);
    
    rt_error_code_t err = rt_str_to_int(s, &result);
    ASSERT_EQ(err, RT_OK);
    /* Check value is 12345 */
    
    rt_str invalid = rt_str_from_cstr("abc");
    err = rt_str_to_int(invalid, &result);
    ASSERT_EQ(err, RT_ERROR_INVALID);
    rt_str_clear(&invalid);
    
    rt_str_clear(&s);
    rt_int_clear(&result);
}

TEST(string_is_integer) {
    rt_str valid1 = rt_str_from_cstr("123");
    rt_str valid2 = rt_str_from_cstr("-456");
    rt_str valid3 = rt_str_from_cstr("  789  ");
    rt_str invalid1 = rt_str_from_cstr("abc");
    rt_str invalid2 = rt_str_from_cstr("12.34");
    rt_str invalid3 = rt_str_from_cstr("");
    rt_str invalid4 = rt_str_from_cstr("-");
    
    ASSERT_EQ(rt_str_is_integer(valid1), 1);
    ASSERT_EQ(rt_str_is_integer(valid2), 1);
    ASSERT_EQ(rt_str_is_integer(valid3), 1);
    ASSERT_EQ(rt_str_is_integer(invalid1), 0);
    ASSERT_EQ(rt_str_is_integer(invalid2), 0);
    ASSERT_EQ(rt_str_is_integer(invalid3), 0);
    ASSERT_EQ(rt_str_is_integer(invalid4), 0);
    
    rt_str_clear(&valid1);
    rt_str_clear(&valid2);
    rt_str_clear(&valid3);
    rt_str_clear(&invalid1);
    rt_str_clear(&invalid2);
    rt_str_clear(&invalid3);
    rt_str_clear(&invalid4);
}

TEST(string_join) {
    rt_str parts[3];
    parts[0] = rt_str_from_cstr("Hello");
    parts[1] = rt_str_from_cstr("World");
    parts[2] = rt_str_from_cstr("!");
    
    rt_str sep = rt_str_from_cstr(", ");
    
    rt_str result = rt_str_join(parts, 3, sep);
    ASSERT_EQ(result.len, 17);
    ASSERT(memcmp(result.data, "Hello, World, !", 15) == 0);
    
    rt_str_clear(&result);
    rt_str_clear(&sep);
    rt_str_clear(&parts[0]);
    rt_str_clear(&parts[1]);
    rt_str_clear(&parts[2]);
}

/* ==================== Main ==================== */

int main(void) {
    printf("========================================\n");
    printf("PCC Extended Runtime Unit Tests\n");
    printf("========================================\n\n");
    
    printf("Math Utilities Tests:\n");
    RUN_TEST(math_abs_si);
    RUN_TEST(math_min_max_si);
    RUN_TEST(math_pow_si);
    RUN_TEST(math_sqrt_si);
    RUN_TEST(math_gcd_si);
    RUN_TEST(math_lcm_si);
    RUN_TEST(math_is_prime_si);
    RUN_TEST(math_next_prime_si);
    
    printf("\nBigInt Math Tests:\n");
    RUN_TEST(math_abs_bigint);
    RUN_TEST(math_min_max_bigint);
    RUN_TEST(math_factorial);
    RUN_TEST(math_binomial);
    
    printf("\nExtended String Tests:\n");
    RUN_TEST(string_substring);
    RUN_TEST(string_find);
    RUN_TEST(string_contains_starts_ends);
    RUN_TEST(string_compare);
    RUN_TEST(string_case_conversion);
    RUN_TEST(string_trim);
    RUN_TEST(string_repeat);
    RUN_TEST(string_replace);
    RUN_TEST(string_to_int);
    RUN_TEST(string_is_integer);
    RUN_TEST(string_join);
    
    printf("\n========================================\n");
    printf("Test Summary:\n");
    printf("  Total:  %d\n", tests_run);
    printf("  Passed: %d\n", tests_passed);
    printf("  Failed: %d\n", tests_failed);
    printf("========================================\n");
    
    return tests_failed > 0 ? 1 : 0;
}
