import numpy as np

# Test 1: matrix multiplication
a = np.array([[1, 2], [3, 4]])
b = np.array([[5, 6], [7, 8]])
c = a.dot(b)
print("a.dot(b) =")
print(c)

# Test 2: broadcasting
x = np.array([1, 2, 3])
y = x * 2
print("x*2 =", list(y))

# Test 3: with native loop
total = 0
for i in range(5):
    total = total + int(a.sum())
print("total =", total)
