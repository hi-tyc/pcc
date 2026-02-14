/*
 * Exception handling runtime module for pcc (M3).
 *
 * Provides a minimal, C-level exception mechanism based on setjmp/longjmp.
 *
 * Design goals:
 *  - Enable `try/except` and `raise` in generated code.
 *  - Allow runtime modules (list/dict) and codegen checks (division by zero)
 *    to signal structured errors instead of abort().
 *
 * Notes:
 *  - This is intentionally small and single-threaded.
 *  - When an exception is unhandled, we print to stderr and exit(1).
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

#include <setjmp.h>

typedef enum {
    RT_EXC_Exception = 0,
    RT_EXC_ZeroDivisionError = 1,
    RT_EXC_IndexError = 2,
    RT_EXC_KeyError = 3,
    RT_EXC_TypeError = 4,
    RT_EXC_ValueError = 5,
} rt_exc_type_t;

typedef struct {
    rt_exc_type_t type;
    const char* message; /* Points to static storage or string literal */
    const char* file;
    int line;
} rt_exc_t;

typedef struct rt_try_ctx {
    jmp_buf env;
    struct rt_try_ctx* prev;
} rt_try_ctx;

/* Enter a try scope. Returns 0 on first entry; non-zero after a raise. */
int rt_try_push(rt_try_ctx* ctx);

/* Leave the current try scope (must be the matching ctx). */
void rt_try_pop(rt_try_ctx* ctx);

/* Raise a new exception. Never returns if there is a handler. */
void rt_raise(rt_exc_type_t type, const char* message, const char* file, int line);

/* Re-raise the current exception. */
void rt_reraise(void);

/* Access/clear current exception. */
const rt_exc_t* rt_exc_current(void);
void rt_exc_clear(void);

/* Helpers */
const char* rt_exc_name(rt_exc_type_t type);
int rt_exc_is(rt_exc_type_t type);

/* Convenience macro */
#define RT_RAISE(type, msg) rt_raise((type), (msg), __FILE__, __LINE__)

#ifdef __cplusplus
}
#endif
