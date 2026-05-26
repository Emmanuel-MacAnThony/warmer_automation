from backend.intelligence.template_generator import _sanitize

cases = [
    # The exact pattern from the user's report
    "I was speaking with {{warm_opener}} your name came up.",
    # Variant with "recently and" after
    "{{warm_opener}} recently and your name came up.",
    # topic_hook wrapping
    "your expertise in {{topic_hook | fallback: \"\"}} could make an impact.",
    "given your interest in {{topic_hook}}, I wanted to reach out.",
    # giving_reference wrapping
    "Given {{giving_reference | fallback: \"your generous support\"}}, I wanted to reach out.",
]

print("=== SANITIZER TEST ===\n")
for bad in cases:
    _, fixed = _sanitize("", bad)
    status = "OK" if fixed != bad else "UNCHANGED"
    print(f"IN:  {bad}")
    print(f"OUT: {fixed}  [{status}]")
    print()
