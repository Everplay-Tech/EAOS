#!/usr/bin/env python3
"""Script to add API versioning to GDPR service with nested paths."""

import re
from pathlib import Path


def transform_gdpr():
    """Transform GDPR service to add API versioning."""
    service_path = Path(__file__).parent.parent / "services" / "gdpr" / "main.py"

    if not service_path.exists():
        print(f"Error: {service_path} does not exist")
        return False

    content = service_path.read_text()

    # Find all POST endpoint definitions
    # Pattern: @app.post("/path/subpath", response_model=Reply)\nasync def function_name(
    endpoint_pattern = r'@app\.post\("(/[^"]+)",\s*response_model=Reply\)\s*\nasync def (\w+)\('

    endpoints = re.findall(endpoint_pattern, content)

    print(f"Found {len(endpoints)} endpoints in GDPR service:")
    for path, func in endpoints:
        print(f"  {path} -> {func}()")

    # Step 1: Rename endpoint functions to _*_handler
    for path, func_name in endpoints:
        # Find the full function definition including parameters
        old_pattern = rf'@app\.post\("{re.escape(path)}",\s*response_model=Reply\)\s*\nasync def {func_name}\('
        new_def = f'async def _{func_name}_handler('

        content = re.sub(old_pattern, new_def, content, count=1)

    # Step 2: Insert internal handler section header
    first_handler_pattern = r'(async def _\w+_handler\()'
    match = re.search(first_handler_pattern, content)
    if match:
        insert_pos = match.start()
        header = """# ============================================================================
# Internal Handler Functions
# ============================================================================

"""
        content = content[:insert_pos] + header + content[insert_pos:]

    # Step 3: Add v1 and legacy endpoints at the end, before if __name__ == "__main__"
    # Find where to insert (before main block if it exists, otherwise at end)
    main_block = 'if __name__ == "__main__":'
    if main_block in content:
        insert_pos = content.index(main_block)
    else:
        insert_pos = len(content)

    # Build v1 endpoints
    v1_section = []
    v1_section.append("\n\n")
    v1_section.append("# " + "=" * 76 + "\n")
    v1_section.append("# API v1 Endpoints\n")
    v1_section.append("# " + "=" * 76 + "\n\n")

    for path, func_name in endpoints:
        # Extract parameters - need to read the actual function to get them
        # For now, assume standard pattern
        v1_section.append(f'@app.post("/v1{path}", response_model=Reply)\n')
        v1_section.append(f'async def {func_name}_v1(msg: Msg):\n')
        v1_section.append(f'    """{func_name.replace("_", " ").title()} (API v1)."""\n')
        v1_section.append(f'    return await _{func_name}_handler(msg)\n\n')

    # Build legacy endpoints
    legacy_section = []
    legacy_section.append("# " + "=" * 76 + "\n")
    legacy_section.append("# Legacy Endpoints (Backward Compatibility)\n")
    legacy_section.append("# " + "=" * 76 + "\n\n")

    for path, func_name in endpoints:
        legacy_section.append(f'@app.post("{path}", response_model=Reply)\n')
        legacy_section.append(f'async def {func_name}_legacy(msg: Msg):\n')
        legacy_section.append(f'    """\n')
        legacy_section.append(f'    DEPRECATED: Use /v1{path} instead.\n')
        legacy_section.append(f'    {func_name.replace("_", " ").title()}.\n')
        legacy_section.append(f'    """\n')
        legacy_section.append(f'    logger.warning("Deprecated endpoint {path} used. Please migrate to /v1{path}")\n')
        legacy_section.append(f'    return await _{func_name}_handler(msg)\n\n')

    # Insert new sections
    new_sections = ''.join(v1_section) + ''.join(legacy_section)
    content = content[:insert_pos] + new_sections + '\n' + content[insert_pos:]

    # Write back
    service_path.write_text(content)
    print(f"\n✓ Updated GDPR service with {len(endpoints)} versioned endpoints")

    return True


if __name__ == "__main__":
    transform_gdpr()
