def add(a, b):
    return a + b

def divide(a, b):
    # BUG: Doesn't handle division by zero
    return a / b

if __name__ == "__main__":
    print(add(2, 3))
    print(divide(10, 0)) # This will crash
