# Small program with optimization opportunities:
# - constant folding (2+3, 4*5)
# - dead code (unused variable)
# - loop unrolling candidate

def compute(n):
    a = 2 + 3
    b = 4 * 5
    c = a * b
    unused = 999
    total = 0
    for i in range(n):
        total += c
    return total + a

print(compute(5))
