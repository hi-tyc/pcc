# Test list support: literals, indexing, methods, iteration, concat, repeat.

# List literals
nums = [1, 2, 3, 4, 5]
print(nums)
print(len(nums))

# Indexing (positive and negative)
print(nums[0])
print(nums[2])
print(nums[-1])

# Mutation via subscript assignment
nums[0] = 10
print(nums)

# List methods
fruits = ["apple", "banana", "cherry"]
print(fruits)
fruits.append("date")
print(fruits)
print(len(fruits))

# Pop
last = fruits.pop()
print(last)
print(fruits)

# Iteration
total = 0
for n in nums:
    total += n
print("sum:", total)

# List of strings iteration
for f in fruits:
    print(f)

# List concatenation
a = [1, 2, 3]
b = [4, 5, 6]
c = a + b
print(c)

# List repetition
d = [0] * 5
print(d)
e = [1, 2] * 3
print(e)

# Building a list with append
squares = []
for i in range(1, 6):
    squares.append(i * i)
print(squares)

# Nested loop with list
matrix = []
for i in range(3):
    row = []
    for j in range(3):
        row.append(i * 3 + j)
    matrix.append(row)

# Print each row
for row in matrix:
    print(row)

# List of floats
temps = [98.6, 100.4, 97.5, 99.1]
print(temps)
print(temps[0])
print(temps[-1])

# insert and index
colors = ["red", "blue"]
colors.insert(1, "green")
print(colors)
print(colors.index("blue"))

# str() on list
print(str([1, 2, 3]))
print(str(["a", "b", "c"]))
