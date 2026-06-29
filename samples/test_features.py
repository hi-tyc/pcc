"""Test new compiler features."""
import math
import string

# Test math module
print("=== Math Module ===")
print(math.sqrt(16))
print(math.pi)
print(math.floor(3.7))
print(math.ceil(3.2))
print(math.gcd(12, 8))

# Test string module
print("=== String Module ===")
print(string.ascii_letters)
print(string.digits)

# Test hex/oct/bin/chr/ord
print("=== Builtins ===")
print(hex(255))
print(oct(8))
print(bin(10))
print(chr(65))
print(ord("A"))

# Test set
print("=== Set ===")
s = set()
s.add(1)
s.add(2)
s.add(3)
s.add(1)
print(len(s))

# Test lambda
print("=== Lambda ===")
f = lambda x: x * 2
print(f(5))

# Test exception handling
print("=== Exceptions ===")
try:
    print("before raise")
    raise ValueError("test error")
    print("after raise")
except Exception as e:
    print("caught exception")
print("after try")

# Test dict methods
print("=== Dict ===")
d = {"a": 1, "b": 2}
keys = d.keys()
print(len(keys))

# Test f-strings
print("=== F-strings ===")
name = "world"
age = 30
print(f"Hello, {name}!")
print(f"Age: {age}")
print(f"Next year: {age + 1}")
print(f"Pi: {3.14159:.2f}")
print(f"Hex: {255:#x}")
print(f"Aligned: {'hi':>10}")
