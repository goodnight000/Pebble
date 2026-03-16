import os
import re

prd_dir = "/Users/charleszheng/Desktop/Ideas/Journeyman/plans/"
files = [f for f in os.listdir(prd_dir) if f.endswith('.md')]

def extract_section(text, header_regex):
    match = re.search(header_regex, text, re.IGNORECASE | re.MULTILINE)
    if not match: return "Not found"
    
    start_idx = match.end()
    # Find next header of same or higher level, or end of string
    header_level = len(match.group(1))
    next_header_regex = r"^#{1," + str(header_level) + r"}\s+"
    next_match = re.search(next_header_regex, text[start_idx:], re.MULTILINE)
    
    if next_match:
        return text[start_idx:start_idx+next_match.start()].strip()[:400] + "..." # truncate for brevity
    return text[start_idx:].strip()[:400] + "..."

for f in files:
    path = os.path.join(prd_dir, f)
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
        
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1) if title_match else f
        
        print(f"=== {title} ===")
        print("COMPETITION:")
        print(extract_section(content, r"^(#+)\s+.*competit.*"))
        print("\nMOAT:")
        print(extract_section(content, r"^(#+)\s+.*moat.*defens.*"))
        print("\n" + "-"*40 + "\n")
