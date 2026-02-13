/*
 * Error handling module for pcc runtime.
 *
 * Provides structured error handling with error codes, messages,
 * and graceful error recovery instead of abrupt termination.
 */

#pragma once

#include "rt_config.h"

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>

/* Error codes */
typedef enum {
    RT_OK = 0,                    /* Success */
    RT_ERROR_NOMEM = 1,           /* Out of memory */
    RT_ERROR_DIVZERO = 2,         /* Division by zero */
    RT_ERROR_OVERFLOW = 3,        /* Arithmetic overflow */
    RT_ERROR_INVALID = 4,         /* Invalid argument */
    RT_ERROR_IO = 5,              /* I/O error */
    RT_ERROR_UNKNOWN = 99         /* Unknown error */
} rt_error_code_t;

/* Error context structure */
typedef struct {
    rt_error_code_t code;
    char message[RT_ERROR_BUFFER_SIZE];
    const char* file;
    int line;
} rt_error_t;

/* Global error state (thread-local in multi-threaded environments) */
extern rt_error_t rt_last_error;

/* Error handling macros */
#define RT_SET_ERROR(code, msg) rt_error_set(code, msg, __FILE__, __LINE__)
#define RT_CLEAR_ERROR() rt_error_clear()
#define RT_HAS_ERROR() (rt_last_error.code != RT_OK)

/* Function prototypes */

/**
 * Set an error with context information.
 *
 * @param code Error code
 * @param message Error message (can be NULL for default message)
 * @param file Source file where error occurred
 * @param line Line number where error occurred
 */
void rt_error_set(rt_error_code_t code, const char* message, const char* file, int line);

/**
 * Clear the current error state.
 */
void rt_error_clear(void);

/**
 * Get a human-readable error message for an error code.
 *
 * @param code Error code
 * @return Static string describing the error
 */
const char* rt_error_string(rt_error_code_t code);

/**
 * Print the current error to stderr.
 */
void rt_error_print(void);

/**
 * Check if an operation succeeded, print error and return if failed.
 *
 * @param expr Expression to evaluate (should return rt_error_code_t)
 */
#define RT_CHECK(expr) do { \
    rt_error_code_t _rt_err = (expr); \
    if (_rt_err != RT_OK) { \
        rt_error_print(); \
        return _rt_err; \
    } \
} while(0)

/**
 * Check if pointer is non-NULL, set error and return if NULL.
 *
 * @param ptr Pointer to check
 * @param name Name of the pointer (for error message)
 */
#define RT_CHECK_NULL(ptr, name) do { \
    if ((ptr) == NULL) { \
        RT_SET_ERROR(RT_ERROR_INVALID, name " is NULL"); \
        rt_error_print(); \
        return RT_ERROR_INVALID; \
    } \
} while(0)

#ifdef __cplusplus
}
#endif
