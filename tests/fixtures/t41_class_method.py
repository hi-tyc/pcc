class Counter:
    value = 0

    def increment(self):
        self.value = self.value + 1

c = Counter()
c.increment()
c.increment()
print(c.value)
