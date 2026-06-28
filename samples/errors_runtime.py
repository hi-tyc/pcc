# Demonstrates runtime error handling for division by zero.
# The program computes a result safely (guarding against zero), then
# deliberately triggers a ZeroDivisionError to show that the compiled
# executable matches CPython's behavior.

def safe_div(a, b):
    if b == 0:
        print("cannot divide by zero")
        return 0
    return a // b

print("safe_div(10, 2) =", safe_div(10, 2))
print("safe_div(7, 0) =", safe_div(7, 0))

# Now trigger the actual error (matches CPython's ZeroDivisionError).
x = 10
y = 0
print("about to divide by zero...")
z = x // y
print("unreachable")
