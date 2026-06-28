# Module-level globals read from inside functions.

PI = 3.14
COUNTER = 0
GREETING = "hello"


def circle_area(r):
    # Read a float global.
    return PI * r * r


def bump():
    # Read and write a global via `global` declaration.
    global COUNTER
    COUNTER = COUNTER + 1
    return COUNTER


def shout():
    # Read a string global.
    return GREETING + "!"


print("area(2.0) =", circle_area(2.0))
print("area(3.0) =", circle_area(3.0))

print("counter:", bump())
print("counter:", bump())
print("counter:", bump())

print(shout())
print(GREETING)
