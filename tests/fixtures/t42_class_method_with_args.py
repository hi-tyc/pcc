class Point:
    x = 0
    y = 0

    def move(self, dx, dy):
        self.x = self.x + dx
        self.y = self.y + dy

p = Point()
p.move(3, 4)
print(p.x)
print(p.y)
