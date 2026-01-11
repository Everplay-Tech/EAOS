#!/usr/bin/env python3
"""
Script to add API versioning to a service's main.py file.

This script:
1. Finds all @app.post() endpoints
2. Renames them to internal _*_handler functions
3. Creates /v1/* versioned endpoints
4. Creates legacy /* endpoints with deprecation warnings
"""

import re
import sys
from pathlib import Path


def transform_service(service_path: Path) -> bool:
    """
    Transform a service's main.py to add API versioning.

    Returns True if changes were made, False otherwise.
    """
    if not service_path.exists():
        print(f"Error: {service_path} does not exist")
        return False

    content = service_path.read_text()

    # Check if already versioned
    if '/v1/' in content and '_handler' in content:
        print(f"  ✓ {service_path.parent.name} already has versioning")
        return False

    # Find service name from path
    service_name = service_path.parent.name

    # Find all endpoint definitions
    # Pattern: @app.post("/endpoint", response_model=Reply)\nasync def endpoint(msg: Msg):
    endpoint_pattern = r'@app\.post\("(/\w+)",\s*response_model=Reply\)\s*\nasync def (\w+)\(msg: Msg\):'

    endpoints = re.findall(endpoint_pattern, content)

    if not endpoints:
        print(f"  ! No endpoints found in {service_name}")
        return False

    print(f"  Found {len(endpoints)} endpoints in {service_name}: {[e[0] for e in endpoints]}")

    # Step 1: Rename endpoint functions to _*_handler
    for path, func_name in endpoints:
        # Replace function definition
        old_def = f'@app.post("{path}", response_model=Reply)\nasync def {func_name}(msg: Msg):'
        new_def = f'async def _{func_name}_handler(msg: Msg) -> Reply:'
        content = content.replace(old_def, new_def, 1)

    # Step 2: Add section headers and new endpoints at the end
    # Find the last line before potential EOF
    lines = content.rstrip().split('\n')

    # Add section for v1 endpoints
    v1_endpoints = []
    v1_endpoints.append("")
    v1_endpoints.append("# " + "=" * 76)
    v1_endpoints.append("# API v1 Endpoints")
    v1_endpoints.append("# " + "=" * 76)
    v1_endpoints.append("")

    for path, func_name in endpoints:
        endpoint_path = path.lstrip('/')
        v1_endpoints.append(f'@app.post("/v1/{endpoint_path}", response_model=Reply)')
        v1_endpoints.append(f'async def {func_name}_v1(msg: Msg):')
        v1_endpoints.append(f'    """{func_name.replace("_", " ").title()} endpoint (API v1)."""')
        v1_endpoints.append(f'    return await _{func_name}_handler(msg)')
        v1_endpoints.append("")

    # Add section for legacy endpoints
    legacy_endpoints = []
    legacy_endpoints.append("# " + "=" * 76)
    legacy_endpoints.append("# Legacy Endpoints (Backward Compatibility)")
    legacy_endpoints.append("# " + "=" * 76)
    legacy_endpoints.append("")

    for path, func_name in endpoints:
        endpoint_path = path.lstrip('/')
        legacy_endpoints.append(f'@app.post("{path}", response_model=Reply)')
        legacy_endpoints.append(f'async def {func_name}_legacy(msg: Msg):')
        legacy_endpoints.append(f'    """')
        legacy_endpoints.append(f'    DEPRECATED: Use /v1/{endpoint_path} instead.')
        legacy_endpoints.append(f'    {func_name.replace("_", " ").title()} endpoint.')
        legacy_endpoints.append(f'    """')
        legacy_endpoints.append(f'    logger.warning("Deprecated endpoint {path} used. Please migrate to /v1/{endpoint_path}")')
        legacy_endpoints.append(f'    return await _{func_name}_handler(msg)')
        legacy_endpoints.append("")

    # Add internal handler section header before first handler
    first_handler_pattern = r'(async def _\w+_handler\(msg: Msg\) -> Reply:)'
    match = re.search(first_handler_pattern, content)
    if match:
        insert_pos = match.start()
        header = """# ============================================================================
# Internal Handler Functions
# ============================================================================

"""
        content = content[:insert_pos] + header + content[insert_pos:]

    # Combine all sections
    new_content = content.rstrip() + '\n\n' + '\n'.join(v1_endpoints) + '\n'.join(legacy_endpoints)

    # Write back
    service_path.write_text(new_content)
    print(f"  ✓ Updated {service_name} with {len(endpoints)} versioned endpoints")

    return True


def main():
    """Main function to process all services."""
    base_path = Path(__file__).parent.parent / "services"

    if not base_path.exists():
        print(f"Error: Services directory not found: {base_path}")
        sys.exit(1)

    # Find all service main.py files
    service_files = list(base_path.glob("*/main.py"))

    print(f"Found {len(service_files)} services to process\n")

    updated_count = 0
    for service_file in sorted(service_files):
        if transform_service(service_file):
            updated_count += 1

    print(f"\n✓ Updated {updated_count}/{len(service_files)} services")


if __name__ == "__main__":
    main()
