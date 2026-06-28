# Sieve of Eratosthenes using a string as a boolean array substitute.
# We count primes up to N by trial division (no lists yet).

def is_prime(n):
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True

count = 0
n = 2
while n < 100:
    if is_prime(n):
        count += 1
    n += 1
print("primes below 100:", count)

# Sum of primes below 100
total = 0
for k in range(2, 100):
    if is_prime(k):
        total += k
print("sum of primes below 100:", total)

# Collatz conjecture steps
def collatz_steps(n):
    steps = 0
    while n != 1:
        if n % 2 == 0:
            n = n // 2
        else:
            n = 3 * n + 1
        steps += 1
    return steps

print("collatz(27) =", collatz_steps(27))
print("collatz(97) =", collatz_steps(97))

# Power function (iterative) and Ackermann
def ipow(base, exp):
    result = 1
    while exp > 0:
        if exp % 2 == 1:
            result *= base
        base *= base
        exp = exp // 2
    return result

print("2^16 =", ipow(2, 16))
print("3^10 =", ipow(3, 10))

def ackermann(m, n):
    if m == 0:
        return n + 1
    if n == 0:
        return ackermann(m - 1, 1)
    return ackermann(m - 1, ackermann(m, n - 1))

print("ackermann(2, 3) =", ackermann(2, 3))
print("ackermann(3, 3) =", ackermann(3, 3))
