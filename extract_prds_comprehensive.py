import os
import re

prd_dir = "/Users/charleszheng/Desktop/Ideas/Journeyman/plans/"
files = [f for f in os.listdir(prd_dir) if f.endswith('.md')]

def extract_section(text, keywords):
    # Try to find a header containing any of the keywords
    pattern = r"^(#+)\s+.*(" + "|".join(keywords) + r").*"
    match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if not match: return "Not found"
    
    start_idx = match.end()
    header_level = len(match.group(1))
    next_header_regex = r"^#{1," + str(header_level) + r"}\s+"
    next_match = re.search(next_header_regex, text[start_idx:], re.MULTILINE)
    
    if next_match:
        content = text[start_idx:start_idx+next_match.start()].strip()
    else:
        content = text[start_idx:].strip()
        
    # Truncate if too long, but keep enough context
    return content[:800] + ("..." if len(content) > 800 else "")

for f in files:
    path = os.path.join(prd_dir, f)
    with open(path, 'r', encoding='utf-8') as file:
        content = file.read()
        
        title_match = re.search(r"^#\s+(.+)", content, re.MULTILINE)
        title = title_match.group(1) if title_match else f
        
        print(f"=== {title} ===")
        print("PROBLEM/EXECUTIVE SUMMARY:")
        print(extract_section(content, ["problem", "executive summary", "overview"]))
        print("\nMARKET SIZE / TAM:")
        print(extract_section(content, ["market size", "tam", "target market", "market opportunity"]))
        print("\nGTM / DISTRIBUTION:")
        print(extract_section(content, ["go-to-market", "gtm", "distribution", "wedge", "sales"]))
        print("\nBUSINESS MODEL / PRICING:")
        print(extract_section(content, ["business model", "pricing", "revenue model"]))
        print("\n" + "="*80 + "\n")
