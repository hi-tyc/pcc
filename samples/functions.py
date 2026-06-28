def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)

def fib(n):
    if n < 2:
        return n
    return fib(n - 1) + fib(n - 2)

def gcd(a, b):
    while b != 0:
        t = b
        b = a % b
        a = t
    return a

print("factorial(5) =", factorial(5))
print("factorial(10) =", factorial(10))
print("fib(10) =", fib(10))
print("fib(20) =", fib(20))
print("gcd(48, 36) =", gcd(48, 36))

# loops
total = 0
for i in range(1, 11):
    total += i
print("sum 1..10 =", total)

# range with step
for i in range(0, 10, 2):
    print(i)

# while with break/continue
n = 0
while True:
    n += 1
    if n > 5:
        break
    if n == 3:
        continue
    print("n =", n)
