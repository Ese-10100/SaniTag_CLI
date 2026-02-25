# def generate_art ( height, width ):
#     shape = ""
#     for character in range(width):
#         if character == 0 or character == width - 1:
#             shape += "#" * height + "\n"
#         else:
#             shape += "#" + " " * (height - 2) + "#" + "\n"
#     return shape
#
#
# shape = generate_art(6, 4)
# print(shape)
#
#
# def generate_triangle ( length ):
#     max_length = length
#     for i in range(max_length):
#         print("" * i + "@" * (2 * (max_length - i - 1) + 1))
#
#
# triangle = generate_triangle(5)
# print(triangle)
# from dataclasses import replace

simple = ["simple","_"]
empty = []

def insertAList(arr):
    if len(arr) == 0:
        arr.append("@")
    arr.insert(1, "encryption".index("c"))  # Inserts 2 at index 1

    for ele in arr:
        print(arr[-1])  # Prints the last character of each element



insertAList(simple)
insertAList(empty)
print(simple)
print(empty)