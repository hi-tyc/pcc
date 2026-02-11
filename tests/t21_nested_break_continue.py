i = 0
while i < 3:
    j = 0
    while j < 5:
        j = j + 1
        if j == 2:
            continue
        if j == 4:
            break
        print(j)
    i = i + 1