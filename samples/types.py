# floats
pi = 3.14
r = 2.0
area = pi * r * r
print("area =", area)
print(7.0 / 2.0)
print(7 / 2)
print(7 // 2)
print(7 % 3)
print(2 ** 10)
print(2.0 ** 0.5)
print(-3.5)
print(abs(-7))
print(abs(-3.14))

# strings
greeting = "Hello"
name = "World"
msg = greeting + ", " + name + "!"
print(msg)
print(len(msg))
print("ab" * 3)
for ch in "abc":
    print(ch)

# booleans and logic
t = True
f = False
print(t and f)
print(t or f)
print(not t)
print(5 > 3)
print(5 == 5)
print(5 != 5)
print(1 < 2 and 3 < 4)

# conditionals
x = 7
if x > 10:
    print("big")
elif x > 5:
    print("medium")
else:
    print("small")

# ternary
y = 10 if x > 5 else 0
print("y =", y)

# conversions
print(int("42"))
print(float("3.14"))
print(str(123))
print(str(2.5))
print(int(3.9))
print(float(5))

# min / max
print(min(3, 7, 2, 9))
print(max(3, 7, 2, 9))
print(min(1.5, 2.5))
