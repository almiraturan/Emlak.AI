import re

with open("c:/Users/AET/EmlakProject/Emlak.AI/app/templates/listings_emlakjet.html", "r", encoding="utf-8") as f:
    content = f.read()

# Split the content into sections
# Section 1: Block 1 (from {% block extra_js %} to the first {% endblock %})
# Section 2: Block 2 (from the second {% block extra_js %} to the end)

blocks = content.split("{% block extra_js %}")
if len(blocks) >= 3:
    block1 = blocks[1].split("{% endblock %}")[0]
    block2 = blocks[2].split("{% endblock %}")[0]
    
    # Let's extract functions from both blocks and compare their lengths/contents
    def get_functions(text):
        # Find all function boundaries (this is a simple approximation)
        funcs = {}
        matches = list(re.finditer(r"function\s+(\w+)\s*\(", text))
        for i, m in enumerate(matches):
            name = m.group(1)
            start = m.start()
            end = matches[i+1].start() if i+1 < len(matches) else len(text)
            funcs[name] = text[start:end].strip()
        return funcs

    f1 = get_functions(block1)
    f2 = get_functions(block2)
    
    print("Function comparison (Block 1 vs Block 2):")
    for name in sorted(f1.keys()):
        if name in f2:
            len1 = len(f1[name])
            len2 = len(f2[name])
            if f1[name] != f2[name]:
                print(f"  {name}: DIFFERENT (Block 1 length={len1}, Block 2 length={len2})")
            else:
                print(f"  {name}: IDENTICAL")
        else:
            print(f"  {name}: ONLY IN BLOCK 1")
    for name in sorted(f2.keys()):
        if name not in f1:
            print(f"  {name}: ONLY IN BLOCK 2")
else:
    print("Could not find three sections separated by {% block extra_js %}")
