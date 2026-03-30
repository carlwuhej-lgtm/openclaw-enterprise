"""
OpenClaw Enterprise - RBAC 权限控制模块
基于角色层级的权限检查
"""
from fastapi import HTTPException, Depends
from auth import get_current_user
from models import User

ROLE_HIERARCHY = {
    'admin': 4,
    'manager': 3,
    'user': 2,
    'viewer': 1,
}

# 菜单权限配置
ROLE_MENUS = {
    'admin': ["dashboard", "devices", "agents", "alerts", "audit", "host", "analytics", "users", "tenants", "policies", "export", "settings"],
    'manager': ["dashboard", "devices", "agents", "alerts", "audit", "host", "analytics", "export"],
    'user': ["dashboard", "devices", "agents", "alerts", "audit", "host"],
    'viewer': ["dashboard", "devices", "agents", "alerts", "audit"],
}

# 操作权限配置
ROLE_ACTIONS = {
    'admin': {
        "devices": ["view", "create", "update", "delete"],
        "agents": ["view", "create", "start", "stop", "delete"],
        "users": ["view", "create", "update", "delete"],
        "tenants": ["view", "create", "update", "delete"],
        "policies": ["view", "create", "update", "delete", "toggle"],
        "alerts": ["view", "create", "resolve", "delete"],
        "audit": ["view", "delete", "clear"],
        "export": ["view", "download"],
        "settings": ["view", "update"],
    },
    'manager': {
        "devices": ["view", "create", "update"],
        "agents": ["view", "start", "stop"],
        "users": ["view"],
        "tenants": ["view"],
        "policies": ["view"],
        "alerts": ["view", "create", "resolve"],
        "audit": ["view"],
        "export": ["view", "download"],
    },
    'user': {
        "devices": ["view", "create"],
        "agents": ["view"],
        "users": ["view"],
        "policies": ["view"],
        "alerts": ["view", "create"],
        "audit": ["view"],
        "export": ["view"],
    },
    'viewer': {
        "devices": ["view"],
        "agents": ["view"],
        "alerts": ["view"],
        "audit": ["view"],
        "policies": ["view"],
    },
}


def require_role(min_role: str):
    """
    要求最低角色等级的依赖注入
    用法: current_user: User = require_role("manager")
    """
    min_level = ROLE_HIERARCHY.get(min_role, 0)
    
    def checker(current_user: User = Depends(get_current_user)):
        user_level = ROLE_HIERARCHY.get(current_user.role, 0)
        if user_level < min_level:
            raise HTTPException(
                status_code=403, 
                detail=f"需要 {min_role} 或更高权限"
            )
        return current_user
    
    return Depends(checker)


def get_user_permissions(user: User) -> dict:
    """
    获取用户的完整权限信息，用于前端权限 API
    """
    role = user.role or 'viewer'
    return {
        "role": role,
        "menus": ROLE_MENUS.get(role, ROLE_MENUS['viewer']),
        "actions": ROLE_ACTIONS.get(role, ROLE_ACTIONS['viewer']),
    }
