try:
    raise ValueError("bad")
    print(0)
except ValueError:
    print(7)
