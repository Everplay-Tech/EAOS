# Role-Based Access Control (RBAC) Implementation

## Overview

BIOwerk now implements comprehensive Role-Based Access Control (RBAC) to secure all resources and endpoints. This ensures that users can only access resources they have permissions for, preventing unauthorized access to sensitive data.

## Roles

The system defines four standard roles:

### 1. **Admin** (`admin`)
- **Priority**: 100
- **Default**: No
- **Permissions**: Full access to all resources and operations
- **Use Case**: System administrators, super users

### 2. **User** (`user`)
- **Priority**: 50
- **Default**: Yes (auto-assigned to new users)
- **Permissions**: Read/write access to projects, artifacts, and executions
- **Use Case**: Standard users who create and manage their own resources

### 3. **Viewer** (`viewer`)
- **Priority**: 25
- **Default**: No
- **Permissions**: Read-only access to permitted resources
- **Use Case**: Auditors, observers, stakeholders who need visibility without modification rights

### 4. **Service Account** (`service_account`)
- **Priority**: 75
- **Default**: No
- **Permissions**: Read/write access to artifacts and executions (no project access)
- **Use Case**: Automated processes, background jobs, API integrations

## Permissions

Permissions are defined by two components:

### Actions
- `read` - View resources
- `write` - Create and modify resources
- `delete` - Remove resources
- `admin` - Full administrative control

### Resource Types
- `project` - User projects
- `artifact` - Generated documents/spreadsheets/presentations
- `execution` - Execution logs and audit trails
- `user` - User accounts
- `api_key` - API keys for service-to-service auth
- `global` - System-wide resources

## Permission Matrix

| Role | Projects | Artifacts | Executions | Users | API Keys |
|------|----------|-----------|------------|-------|----------|
| Admin | Full | Full | Full | Full | Full |
| User | Read/Write | Read/Write | Read/Write | Read (self) | Read/Write (own) |
| Viewer | Read | Read | Read | None | None |
| Service Account | None | Read/Write | Read/Write | None | None |

## Resource Ownership

The system tracks resource ownership to enable owner-based access control:

- **Owner**: User who created the resource
- **Ownership Transfer**: Resources can be transferred between users
- **Owner Permissions**: Owners can perform actions on their resources even without explicit role permissions

## Implementation Components

### 1. Database Models (`matrix/db_models.py`)

Five new tables support RBAC:

- **`roles`** - Role definitions
- **`permissions`** - Permission definitions
- **`role_permissions`** - Role-to-permission mappings
- **`user_roles`** - User-to-role assignments (supports scoping and expiration)
- **`resource_ownership`** - Resource ownership tracking

### 2. Authorization Functions (`matrix/auth_dependencies.py`)

Core authorization functions:

```python
# Role checking
get_user_roles(user_id, db) -> List[str]
require_role(*roles) -> Dependency

# Permission checking
get_user_permissions(user_id, db) -> List[Tuple[str, str]]
has_permission(user, action, resource_type, db) -> bool
require_permission(action, resource_type) -> Dependency

# Resource access
is_resource_owner(user, resource_type, resource_id, db) -> bool
check_resource_access(user, resource_type, resource_id, action, db) -> bool
require_resource_permission(action, resource_type) -> Dependency
```

### 3. Gateway Middleware (`mesh/main.py`)

The mesh gateway enforces RBAC on all service endpoints via `SERVICE_PERMISSION_MAP`:

```python
SERVICE_PERMISSION_MAP = {
    "osteon": {
        "outline": ("write", "artifact"),
        "draft": ("write", "artifact"),
        "edit": ("write", "artifact"),
        ...
    },
    "nucleus": {
        "plan": ("admin", "project"),  # Requires admin
        ...
    }
}
```

### 4. Database Migration (`alembic/versions/005_add_rbac_tables.py`)

Run the migration to create RBAC tables:

```bash
alembic upgrade head
```

This automatically creates:
- RBAC tables and indexes
- Default roles (admin, user, viewer, service_account)
- Default permissions for all resource types
- Role-permission mappings

## Usage Examples

### Protecting Endpoints with RBAC

#### Require Specific Role

```python
from matrix.auth_dependencies import require_role

@app.post("/admin/settings")
async def update_settings(user: User = Depends(require_role("admin"))):
    # Only admin users can access this
    return {"message": "Settings updated"}
```

#### Require Specific Permission

```python
from matrix.auth_dependencies import require_permission

@app.post("/projects")
async def create_project(
    user: User = Depends(require_permission("write", "project"))
):
    # Only users with write permission on projects can access
    return {"message": "Project created"}
```

#### Require Resource Permission with Ownership

```python
from matrix.auth_dependencies import require_resource_permission

@app.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    user_and_resource: tuple = Depends(
        require_resource_permission("delete", "project", allow_owner=True)
    )
):
    user, resource_id = user_and_resource
    # User has delete permission OR is the project owner
    return {"message": "Project deleted"}
```

### Programmatic Permission Checking

```python
from matrix.auth_dependencies import has_permission, is_resource_owner

# Check if user has permission
if await has_permission(user, "write", "artifact", db):
    # Allow write operation
    pass

# Check if user owns resource
if await is_resource_owner(user, "project", project_id, db):
    # Allow owner-specific operation
    pass
```

## Security Features

### 1. **Admin Bypass**
- Users with `is_admin=True` automatically have all permissions
- Simplifies admin user management

### 2. **Role Expiration**
- User roles can have expiration dates (`expires_at`)
- Expired roles are automatically excluded from permission checks

### 3. **Scoped Roles**
- Roles can be scoped to specific projects or resources
- Example: Project-specific admin role

### 4. **Permission Conditions**
- Role permissions support JSON conditions for advanced rules
- Example: Time-based access, IP whitelisting

### 5. **Ownership-Based Access**
- Resource owners can perform operations even without explicit permissions
- Prevents users from being locked out of their own resources

## Default Behavior

### New Users
- Automatically assigned the `user` role (via `is_default=True`)
- Can create and manage their own projects, artifacts, and executions
- Cannot access other users' resources without permission

### Admin Users
- Set `is_admin=True` on user record
- Bypass all RBAC checks
- Have unrestricted access to all resources

### Service Accounts
- Assign `service_account` role
- Limited to artifact and execution operations
- Cannot access projects or user management

## Testing

Comprehensive test suite in `tests/test_auth.py`:

```bash
pytest tests/test_auth.py -v
```

Tests cover:
- Role assignment and retrieval
- Permission checking for all roles
- Resource ownership tracking
- Access control for different user types
- Role expiration
- Scoped role assignments

## Migration Guide

### For Existing Deployments

1. **Run the migration**:
   ```bash
   alembic upgrade head
   ```

2. **Assign roles to existing users**:
   ```python
   # Assign default 'user' role to all existing users
   from matrix.db_models import User, Role, UserRole

   users = await db.execute(select(User))
   user_role = await db.execute(select(Role).where(Role.name == "user"))

   for user in users.scalars():
       ur = UserRole(
           user_id=user.id,
           role_id=user_role.scalar_one().id,
           scope_type="global",
           is_active=True
       )
       db.add(ur)

   await db.commit()
   ```

3. **Update admin users**:
   ```python
   # Ensure admin users have is_admin=True flag
   admin_user = await db.execute(
       select(User).where(User.email == "admin@example.com")
   )
   admin_user.scalar_one().is_admin = True
   await db.commit()
   ```

## Acceptance Criteria ✓

- ✅ Cannot access resources without proper role
- ✅ Admin can manage all resources
- ✅ Users can only access their own resources
- ✅ Service accounts have limited scope
- ✅ All endpoints protected by permission checks

## Security Considerations

1. **Principle of Least Privilege**: Users have minimal permissions by default
2. **Defense in Depth**: Multiple layers of authorization (gateway + service level)
3. **Audit Trail**: All access attempts logged via existing audit system
4. **Secure Defaults**: New users get minimal `user` role, not admin
5. **Owner Protection**: Resource owners can't be locked out of their own data

## Future Enhancements

- **Dynamic Permission Assignment**: UI for admins to assign custom permissions
- **Role Hierarchy**: Inherit permissions from parent roles
- **Temporary Access**: Time-limited permission grants
- **Delegation**: Users can delegate access to specific resources
- **Advanced Conditions**: IP-based, time-based, location-based access rules
