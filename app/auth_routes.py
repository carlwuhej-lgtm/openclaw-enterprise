"""
OpenClaw Enterprise - 认证相关 API 路由
"""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
import time
from threading import Lock

from database import get_db
from models import User, Tenant
from auth import (
    verify_password, get_password_hash, create_access_token, create_refresh_token,
    get_current_user, require_admin, TokenData, UserLogin, UserRegister,
    validate_password, decode_token, SECRET_KEY, ALGORITHM
)

router = APIRouter(prefix="/api/auth", tags=["认证"])

# ==================== 登录失败限制 ====================
# 同一用户 5 次失败后锁定 15 分钟
_login_failures: dict[str, dict] = {}  # username -> {"count": int, "locked_until": float}
_login_lock = Lock()

MAX_LOGIN_FAILURES = 5
LOCKOUT_DURATION_SECONDS = 15 * 60  # 15 分钟


def _check_login_lockout(username: str) -> Optional[str]:
    """检查用户是否被锁定，返回错误消息或 None"""
    with _login_lock:
        record = _login_failures.get(username)
        if not record:
            return None
        
        now = time.time()
        if record.get("locked_until") and now < record["locked_until"]:
            remaining = int(record["locked_until"] - now)
            minutes = remaining // 60
            seconds = remaining % 60
            return f"账号已锁定，请 {minutes} 分 {seconds} 秒后重试"
        
        # 锁定已过期，重置
        if record.get("locked_until") and now >= record["locked_until"]:
            del _login_failures[username]
        
        return None


def _record_login_failure(username: str):
    """记录登录失败"""
    with _login_lock:
        if username not in _login_failures:
            _login_failures[username] = {"count": 0, "locked_until": None}
        
        _login_failures[username]["count"] += 1
        
        if _login_failures[username]["count"] >= MAX_LOGIN_FAILURES:
            _login_failures[username]["locked_until"] = time.time() + LOCKOUT_DURATION_SECONDS


def _clear_login_failures(username: str):
    """清除登录失败记录（登录成功后调用）"""
    with _login_lock:
        _login_failures.pop(username, None)


class LoginResponse(BaseModel):
    """登录响应"""
    success: bool
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str
    user: dict
    message: str
    must_change_password: bool = False


class RegisterResponse(BaseModel):
    """注册响应"""
    success: bool
    user_id: int
    message: str


class UserUpdateRequest(BaseModel):
    """更新用户信息请求"""
    real_name: Optional[str] = None
    email: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class PasswordChangeRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str


@router.post("/login", response_model=LoginResponse)
async def login(credentials: UserLogin, db: Session = Depends(get_db)):
    """用户登录"""
    # 检查是否被锁定
    lockout_msg = _check_login_lockout(credentials.username)
    if lockout_msg:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=lockout_msg
        )
    
    user = db.query(User).filter(User.username == credentials.username).first()
    
    if not user:
        _record_login_failure(credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用"
        )
    
    if not verify_password(credentials.password, user.hashed_password):
        _record_login_failure(credentials.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 登录成功，清除失败记录
    _clear_login_failures(credentials.username)
    
    # 更新最后登录时间
    user.last_login = datetime.now()
    db.commit()
    
    # 创建 Token
    token_data = {
        "sub": user.username,
        "user_id": user.id,
        "role": user.role,
        "tenant_id": user.tenant_id
    }
    access_token = create_access_token(data=token_data)
    refresh_token = create_refresh_token(data=token_data)
    
    # 检查是否使用默认密码（仅提示，不强制修改）
    is_default_password = verify_password("admin", user.hashed_password)
    
    # 构建提示信息
    if is_default_password:
        message = "登录成功（首次登录建议修改默认密码）"
    else:
        message = "登录成功"
    
    return LoginResponse(
        success=True,
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        user={
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name,
            "email": user.email,
            "role": user.role,
            "tenant_id": user.tenant_id
        },
        message=message,
        must_change_password=False  # 不强制修改密码
    )


@router.post("/register", response_model=RegisterResponse)
async def register(data: UserRegister, db: Session = Depends(get_db)):
    """用户注册（默认创建 viewer 角色，需管理员激活）"""
    # 检查用户名是否已存在
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )
    
    # 密码策略验证
    is_valid, error_msg = validate_password(data.password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    # 创建用户
    user = User(
        username=data.username,
        hashed_password=get_password_hash(data.password),
        real_name=data.real_name or data.username,
        email=data.email,
        tenant_id=data.tenant_id,
        role="viewer",  # 新注册用户默认 viewer 角色
        is_active=False  # 需管理员激活
    )
    
    db.add(user)
    db.commit()
    db.refresh(user)
    
    return RegisterResponse(
        success=True,
        user_id=user.id,
        message="注册成功，请等待管理员激活"
    )


@router.get("/me")
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "real_name": current_user.real_name,
        "email": current_user.email,
        "role": current_user.role,
        "tenant_id": current_user.tenant_id,
        "is_active": current_user.is_active,
        "last_login": current_user.last_login
    }


@router.post("/logout")
async def logout():
    """用户登出（前端清除 Token 即可）"""
    return {"success": True, "message": "登出成功"}


@router.post("/change-password")
async def change_password(
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """修改密码"""
    if not verify_password(data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误"
        )
    
    # 密码策略验证
    is_valid, error_msg = validate_password(data.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    current_user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    
    return {"success": True, "message": "密码修改成功"}


# ==================== Token 刷新 ====================

class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh")
async def refresh_token(data: RefreshRequest, db: Session = Depends(get_db)):
    """用 refresh token 换新的 access token"""
    from jose import JWTError, jwt as jose_jwt
    
    try:
        payload = jose_jwt.decode(data.refresh_token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # 验证是 refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的 refresh token"
            )
        
        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的 refresh token"
            )
        
        # 查询用户
        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在或已被禁用"
            )
        
        # 生成新的 access token
        token_data = {
            "sub": user.username,
            "user_id": user.id,
            "role": user.role,
            "tenant_id": user.tenant_id
        }
        new_access_token = create_access_token(data=token_data)
        
        return {
            "success": True,
            "access_token": new_access_token,
            "token_type": "bearer",
            "message": "Token 已刷新"
        }
    
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="refresh token 已过期或无效"
        )


# ==================== 权限查询 ====================

@router.get("/permissions")
async def get_permissions(current_user: User = Depends(get_current_user)):
    """获取当前用户的菜单和操作权限"""
    from rbac import get_user_permissions
    return get_user_permissions(current_user)


# ==================== 管理员接口 ====================

@router.get("/users", dependencies=[Depends(require_admin)])
async def list_users(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取用户列表（管理员）"""
    users = db.query(User).offset(skip).limit(limit).all()
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "real_name": u.real_name,
                "email": u.email,
                "role": u.role,
                "tenant_id": u.tenant_id,
                "is_active": u.is_active,
                "last_login": u.last_login,
                "created_at": u.created_at
            }
            for u in users
        ]
    }


@router.put("/users/{user_id}", dependencies=[Depends(require_admin)])
async def update_user(
    user_id: int,
    data: UserUpdateRequest,
    db: Session = Depends(get_db)
):
    """更新用户信息（管理员）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    if data.real_name is not None:
        user.real_name = data.real_name
    if data.email is not None:
        user.email = data.email
    if data.role is not None:
        user.role = data.role
    if data.is_active is not None:
        user.is_active = data.is_active
    
    db.commit()
    return {"success": True, "message": "用户更新成功"}


@router.post("/users/{user_id}/reset-password", dependencies=[Depends(require_admin)])
async def reset_password(
    user_id: int,
    new_password: str,
    db: Session = Depends(get_db)
):
    """重置用户密码（管理员）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    user.hashed_password = get_password_hash(new_password)
    db.commit()
    return {"success": True, "message": "密码已重置"}


@router.delete("/users/{user_id}", dependencies=[Depends(require_admin)])
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    """删除用户（管理员）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    db.delete(user)
    db.commit()
    return {"success": True, "message": "用户已删除"}
