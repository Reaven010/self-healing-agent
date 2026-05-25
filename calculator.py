def add(a, b):
    return a + b

def divide(a, b):
    # Let Python raise ZeroDivisionError naturally
    return a / b

if __name__ == "__main__":
    print(add(2, 3))
    try:
        result = divide(10, 0)
        print(result)
    except ZeroDivisionError:
        print("Error: Cannot divide by zero")