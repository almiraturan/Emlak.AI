with open("c:/Users/AET/EmlakProject/Emlak.AI/app/templates/listings_emlakjet.html", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines, 1):
    l = line.strip()
    if "function buildListingsQuery" in l:
        print(f"buildListingsQuery start at line {i}")
    elif "function createListingCard" in l:
        print(f"createListingCard start at line {i}")
    elif "</style>" in l:
        print(f"style end at line {i}")
