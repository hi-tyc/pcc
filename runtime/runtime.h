/*
 * Main runtime header for pcc.
 *
 * This is the primary header file that includes all runtime modules.
 * For modular includes, use the individual rt_*.h headers.
 */

#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* Configuration and error handling */
#include "rt_config.h"
#include "rt_error.h"

/* String runtime */
#include "rt_string.h"
#include "rt_string_ex.h"

/* BigInt runtime */
#include "rt_bigint.h"

/* Math utilities */
#include "rt_math.h"

#ifdef __cplusplus
}
#endif
