def sum_to(n):
    i = 1
    s = 0
    while i <= n:
        s = s + i
        i = i + 1
    return s

print(sum_to(5))