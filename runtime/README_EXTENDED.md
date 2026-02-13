# PCC Extended Runtime Documentation

This document describes the enhanced runtime components added to PCC, including math utilities and extended string operations.

## Table of Contents

- [Overview](#overview)
- [Math Utilities (rt_math)](#math-utilities-rt_math)
- [Extended String Operations (rt_string_ex)](#extended-string-operations-rt_string_ex)
- [Error Handling](#error-handling)
- [Performance Considerations](#performance-considerations)
- [Usage Examples](#usage-examples)

## Overview

The extended runtime provides additional builtin functionality for:

1. **Math Operations**: Common mathematical functions for both native integers and BigInt
2. **String Manipulation**: Substring extraction, searching, case conversion, trimming, and more
3. **Type Conversion**: Converting between strings and integers

All functions follow the existing PCC runtime conventions:
- Proper error handling with `rt_error_code_t` return values
- Memory safety with automatic cleanup
- NULL pointer checks
- Clear documentation

## Math Utilities (rt_math)

The math module provides mathematical functions for both native 64-bit integers and BigInt types.

### Native Integer Functions

#### Basic Operations

```c
int64_t rt_math_abs_si(int64_t x);
int64_t rt_math_min_si(int64_t a, int64_t b);
int64_t rt_math_max_si(int64_t a, int64_t b);
```

- `rt_math_abs_si()`: Returns absolute value (handles INT64_MIN by returning INT64_MAX)
- `rt_math_min_si()`: Returns the smaller of two values
- `rt_math_max_si()`: Returns the larger of two values

#### Power and Root

```c
int64_t rt_math_pow_si(int64_t base, int64_t exp);
int64_t rt_math_sqrt_si(int64_t x);
```

- `rt_math_pow_si()`: Integer exponentiation (returns 0 for negative exponents)
- `rt_math_sqrt_si()`: Integer square root (floor value, returns -1 for negative input)

#### Number Theory

```c
int64_t rt_math_gcd_si(int64_t a, int64_t b);
int64_t rt_math_lcm_si(int64_t a, int64_t b);
int rt_math_is_prime_si(int64_t n);
int64_t rt_math_next_prime_si(int64_t n);
```

- `rt_math_gcd_si()`: Greatest common divisor (Euclidean algorithm)
- `rt_math_lcm_si()`: Least common multiple
- `rt_math_is_prime_si()`: Primality test (returns 1 if prime, 0 otherwise)
- `rt_math_next_prime_si()`: Find next prime >= n

### BigInt Functions

```c
rt_error_code_t rt_math_abs(rt_int* out, const rt_int* x);
rt_error_code_t rt_math_min(rt_int* out, const rt_int* a, const rt_int* b);
rt_error_code_t rt_math_max(rt_int* out, const rt_int* a, const rt_int* b);
rt_error_code_t rt_math_pow(rt_int* out, const rt_int* base, int64_t exp);
rt_error_code_t rt_math_sqrt(rt_int* out, const rt_int* x);
rt_error_code_t rt_math_factorial(rt_int* out, int64_t n);
rt_error_code_t rt_math_binomial(rt_int* out, int64_t n, int64_t k);
size_t rt_math_num_digits(const rt_int* x);
```

All BigInt functions:
- Return `RT_OK` on success
- Return `RT_ERROR_INVALID` for invalid inputs (e.g., negative numbers where not allowed)
- Return `RT_ERROR_NOMEM` if memory allocation fails
- Require initialized output BigInt

## Extended String Operations (rt_string_ex)

### Substring Operations

```c
rt_str rt_str_substring(rt_str s, size_t start, size_t length);
rt_str rt_str_slice_from(rt_str s, size_t start);
rt_str rt_str_slice_to(rt_str s, size_t end);
```

- `rt_str_substring()`: Extract substring from start with given length (0 = to end)
- `rt_str_slice_from()`: Get substring from start to end of string
- `rt_str_slice_to()`: Get substring from beginning to end index (exclusive)

### Searching

```c
size_t rt_str_find(rt_str s, rt_str pattern, size_t start);
size_t rt_str_find_cstr(rt_str s, const char* pattern, size_t start);
size_t rt_str_rfind(rt_str s, rt_str pattern);
int rt_str_contains(rt_str s, rt_str pattern);
int rt_str_starts_with(rt_str s, rt_str prefix);
int rt_str_ends_with(rt_str s, rt_str suffix);
```

- `rt_str_find()`: Find first occurrence of pattern starting from index
- `rt_str_rfind()`: Find last occurrence of pattern
- `rt_str_contains()`: Check if pattern exists in string
- `rt_str_starts_with()`: Check prefix
- `rt_str_ends_with()`: Check suffix

### Comparison

```c
int rt_str_compare(rt_str a, rt_str b);
int rt_str_equals(rt_str a, rt_str b);
int rt_str_compare_ignore_case(rt_str a, rt_str b);
```

- `rt_str_compare()`: Lexicographic comparison (<0, 0, >0)
- `rt_str_equals()`: Equality check (1 = equal, 0 = not equal)
- `rt_str_compare_ignore_case()`: Case-insensitive comparison

### Case Conversion

```c
rt_str rt_str_to_upper(rt_str s);
rt_str rt_str_to_lower(rt_str s);
rt_str rt_str_capitalize(rt_str s);
```

- `rt_str_to_upper()`: Convert all characters to uppercase
- `rt_str_to_lower()`: Convert all characters to lowercase
- `rt_str_capitalize()`: First character uppercase, rest lowercase

### Whitespace Handling

```c
rt_str rt_str_ltrim(rt_str s);
rt_str rt_str_rtrim(rt_str s);
rt_str rt_str_trim(rt_str s);
rt_str rt_str_remove_whitespace(rt_str s);
```

- `rt_str_ltrim()`: Remove leading whitespace
- `rt_str_rtrim()`: Remove trailing whitespace
- `rt_str_trim()`: Remove both leading and trailing whitespace
- `rt_str_remove_whitespace()`: Remove all whitespace characters

### Type Conversion

```c
rt_str rt_str_from_int(const rt_int* x);
rt_str rt_str_from_si(int64_t x);
rt_error_code_t rt_str_to_int(rt_str s, rt_int* out);
rt_error_code_t rt_str_to_si(rt_str s, int64_t* out);
int rt_str_is_integer(rt_str s);
```

- `rt_str_from_int()`: Convert BigInt to string
- `rt_str_from_si()`: Convert int64 to string
- `rt_str_to_int()`: Parse string as BigInt
- `rt_str_to_si()`: Parse string as int64
- `rt_str_is_integer()`: Check if string represents valid integer

### String Building

```c
rt_str rt_str_repeat(rt_str s, int64_t count);
rt_str rt_str_join(rt_str* strings, size_t count, rt_str separator);
rt_str rt_str_replace(rt_str s, rt_str old, rt_str replacement);
rt_str rt_str_replace_first(rt_str s, rt_str old, rt_str replacement);
```

- `rt_str_repeat()`: Repeat string n times
- `rt_str_join()`: Join array of strings with separator
- `rt_str_replace()`: Replace all occurrences of substring
- `rt_str_replace_first()`: Replace first occurrence only

## Error Handling

All new functions follow PCC's error handling conventions:

```c
typedef enum {
    RT_OK = 0,                    /* Success */
    RT_ERROR_NOMEM = 1,           /* Out of memory */
    RT_ERROR_DIVZERO = 2,         /* Division by zero */
    RT_ERROR_OVERFLOW = 3,        /* Arithmetic overflow */
    RT_ERROR_INVALID = 4,         /* Invalid argument */
    RT_ERROR_IO = 5,              /* I/O error */
    RT_ERROR_UNKNOWN = 99         /* Unknown error */
} rt_error_code_t;
```

Functions that can fail return `rt_error_code_t`. Functions that cannot fail (like comparison functions) return the result directly.

## Performance Considerations

### Math Functions

- Native integer functions are O(1) or O(log n) complexity
- BigInt operations depend on the size of numbers
- `rt_math_pow()` uses fast exponentiation (O(log exp))
- `rt_math_sqrt()` uses binary search (O(log n))
- `rt_math_factorial()` is O(n) - use with caution for large n

### String Functions

- Most operations are O(n) where n is string length
- `rt_str_find()` uses naive search (O(n*m) worst case)
- `rt_str_replace()` may allocate new memory proportional to result size
- All functions create new strings (immutable operations)

### Memory Management

- All functions that return `rt_str` allocate new memory
- Use `rt_str_clear()` to free memory when done
- No automatic garbage collection - manual cleanup required

## Usage Examples

### Math Examples

```c
#include "runtime.h"

/* Native integer math */
int64_t result = rt_math_pow_si(2, 10);  /* result = 1024 */
int64_t sqrt_val = rt_math_sqrt_si(17);  /* sqrt_val = 4 */
int64_t gcd = rt_math_gcd_si(48, 18);    /* gcd = 6 */

/* BigInt math */
rt_int fact, base;
rt_int_init(&fact);
rt_int_init(&base);

rt_math_factorial(&fact, 20);  /* 20! */
rt_int_set_si(&base, 2);
rt_math_pow(&fact, &base, 100);  /* 2^100 */

rt_int_clear(&fact);
rt_int_clear(&base);
```

### String Examples

```c
#include "runtime.h"

/* Substring extraction */
rt_str s = rt_str_from_cstr("Hello, World!");
rt_str sub = rt_str_substring(s, 7, 5);  /* "World" */

/* Searching */
size_t pos = rt_str_find(s, rt_str_from_cstr("World"), 0);  /* pos = 7 */
int has_world = rt_str_contains(s, rt_str_from_cstr("World"));  /* 1 */

/* Case conversion */
rt_str upper = rt_str_to_upper(s);  /* "HELLO, WORLD!" */
rt_str lower = rt_str_to_lower(s);  /* "hello, world!" */

/* Trimming */
rt_str spaced = rt_str_from_cstr("  hello  ");
rt_str trimmed = rt_str_trim(spaced);  /* "hello" */

/* Replacement */
rt_str replaced = rt_str_replace(s, 
    rt_str_from_cstr("World"), 
    rt_str_from_cstr("Universe"));  /* "Hello, Universe!" */

/* Cleanup */
rt_str_clear(&s);
rt_str_clear(&sub);
rt_str_clear(&upper);
rt_str_clear(&lower);
rt_str_clear(&spaced);
rt_str_clear(&trimmed);
rt_str_clear(&replaced);
```

### Error Handling Example

```c
#include "runtime.h"

rt_int result;
rt_int_init(&result);

rt_error_code_t err = rt_math_factorial(&result, -1);
if (err != RT_OK) {
    printf("Error: %s\n", rt_error_string(err));
    rt_error_print();  /* Print detailed error */
}

rt_int_clear(&result);
```

## Backward Compatibility

All new features are additive and do not modify existing APIs:
- Original `rt_string.h` functions remain unchanged
- Original `rt_bigint.h` functions remain unchanged
- New functions are in separate headers (`rt_math.h`, `rt_string_ex.h`)
- All existing tests continue to pass

## Future Enhancements

Potential additions for future versions:
- Regular expression support
- Unicode/UTF-8 handling
- Additional math functions (trigonometry, logarithms)
- Collection types (arrays, maps)
- File I/O utilities
