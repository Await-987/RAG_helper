"""
用户认证和权限管理模块
"""
import os
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger
from datetime import datetime, timedelta


# 用户数据文件路径（放在隐藏目录 .user 中，更安全）
USERS_FILE = Path(__file__).parent.parent / ".user" / "users.json"
DATA_DIR = USERS_FILE.parent


class UserRole:
    """用户角色"""
    ADMIN = "admin"      # 管理员：所有权限
    USER = "user"        # 普通用户：只能聊天和查看文件


class UserAuth:
    """用户认证管理类"""

    def __init__(self):
        self._ensure_data_dir()
        self._ensure_users_file()

    def _ensure_data_dir(self):
        """确保数据目录存在"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    def _ensure_users_file(self):
        """确保用户文件存在，并创建默认管理员账户"""
        if not USERS_FILE.exists():
            default_users = {
                "users": [
                    {
                        "username": "admin",
                        "password_hash": self._hash_password("admin123"),
                        "role": UserRole.ADMIN,
                        "created_at": datetime.now().isoformat(),
                        "last_login": None
                    }
                ],
                "version": "1.0"
            }
            self._save_users(default_users)
            logger.info("已创建默认用户文件，默认管理员: admin/admin123")

    def _load_users(self) -> Dict:
        """加载用户数据"""
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载用户数据失败: {e}")
            return {"users": [], "version": "1.0"}

    def _save_users(self, data: Dict) -> bool:
        """保存用户数据"""
        try:
            with open(USERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"保存用户数据失败: {e}")
            return False

    def _hash_password(self, password: str) -> str:
        """密码哈希（SHA256）"""
        return hashlib.sha256(password.encode()).hexdigest()

    def verify_password(self, password: str, password_hash: str) -> bool:
        """验证密码"""
        return self._hash_password(password) == password_hash

    def authenticate(self, username: str, password: str) -> Optional[Dict]:
        """
        验证用户登录

        Returns:
            用户信息字典，验证失败返回 None
        """
        data = self._load_users()
        for user in data["users"]:
            if user["username"] == username:
                if self.verify_password(password, user["password_hash"]):
                    # 更新最后登录时间
                    user["last_login"] = datetime.now().isoformat()
                    self._save_users(data)
                    return {
                        "username": user["username"],
                        "role": user["role"],
                        "created_at": user.get("created_at"),
                        "last_login": user["last_login"]
                    }
        return None

    def get_all_users(self) -> List[Dict]:
        """获取所有用户列表"""
        data = self._load_users()
        users = []
        for user in data["users"]:
            users.append({
                "username": user["username"],
                "role": user["role"],
                "created_at": user.get("created_at"),
                "last_login": user.get("last_login")
            })
        return users

    def add_user(self, username: str, password: str, role: str, operator: str) -> Tuple[bool, str]:
        """
        添加用户

        Returns:
            (是否成功, 消息)
        """
        # 验证角色
        if role not in [UserRole.ADMIN, UserRole.USER]:
            return False, "无效的用户角色"

        # 验证密码长度
        if len(password) < 6:
            return False, "密码长度至少6位"

        data = self._load_users()

        # 检查用户是否已存在
        for user in data["users"]:
            if user["username"] == username:
                return False, "用户名已存在"

        # 添加新用户
        new_user = {
            "username": username,
            "password_hash": self._hash_password(password),
            "role": role,
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "created_by": operator
        }
        data["users"].append(new_user)

        if self._save_users(data):
            logger.info(f"用户 {operator} 创建了新用户: {username} ({role})")
            return True, "用户添加成功"
        return False, "保存失败"

    def delete_user(self, username: str, operator: str) -> Tuple[bool, str]:
        """
        删除用户

        Returns:
            (是否成功, 消息)
        """
        # 不允许删除自己
        if username == operator:
            return False, "不能删除自己的账户"

        # 不允许删除最后一个管理员
        data = self._load_users()
        admin_count = sum(1 for u in data["users"] if u["role"] == UserRole.ADMIN)
        target_user = None
        for user in data["users"]:
            if user["username"] == username:
                target_user = user
                break

        if not target_user:
            return False, "用户不存在"

        if target_user["role"] == UserRole.ADMIN and admin_count <= 1:
            return False, "不能删除最后一个管理员账户"

        # 删除用户
        data["users"] = [u for u in data["users"] if u["username"] != username]

        if self._save_users(data):
            logger.info(f"用户 {operator} 删除了用户: {username}")
            return True, "用户删除成功"
        return False, "保存失败"

    def change_password(self, username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        修改密码

        Returns:
            (是否成功, 消息)
        """
        if len(new_password) < 6:
            return False, "新密码长度至少6位"

        data = self._load_users()

        for user in data["users"]:
            if user["username"] == username:
                if not self.verify_password(old_password, user["password_hash"]):
                    return False, "原密码错误"

                user["password_hash"] = self._hash_password(new_password)
                if self._save_users(data):
                    logger.info(f"用户 {username} 修改了密码")
                    return True, "密码修改成功"
                return False, "保存失败"

        return False, "用户不存在"

    def change_user_role(self, username: str, new_role: str, operator: str) -> Tuple[bool, str]:
        """
        修改用户角色

        Returns:
            (是否成功, 消息)
        """
        if new_role not in [UserRole.ADMIN, UserRole.USER]:
            return False, "无效的用户角色"

        # 不允许修改自己的角色
        if username == operator:
            return False, "不能修改自己的角色"

        data = self._load_users()

        # 检查是否还有其他管理员
        if new_role == UserRole.USER:
            admin_count = sum(1 for u in data["users"] if u["role"] == UserRole.ADMIN)
            target_user = None
            for user in data["users"]:
                if user["username"] == username:
                    target_user = user
                    break

            if target_user and target_user["role"] == UserRole.ADMIN and admin_count <= 1:
                return False, "不能将最后一个管理员降为普通用户"

        # 修改角色
        for user in data["users"]:
            if user["username"] == username:
                old_role = user["role"]
                user["role"] = new_role
                if self._save_users(data):
                    logger.info(f"用户 {operator} 将 {username} 的角色从 {old_role} 改为 {new_role}")
                    return True, "角色修改成功"
                return False, "保存失败"

        return False, "用户不存在"

    def reset_password(self, username: str, new_password: str, operator: str) -> Tuple[bool, str]:
        """
        管理员重置用户密码

        Returns:
            (是否成功, 消息)
        """
        if len(new_password) < 6:
            return False, "密码长度至少6位"

        data = self._load_users()

        for user in data["users"]:
            if user["username"] == username:
                user["password_hash"] = self._hash_password(new_password)
                if self._save_users(data):
                    logger.info(f"管理员 {operator} 重置了用户 {username} 的密码")
                    return True, "密码重置成功"
                return False, "保存失败"

        return False, "用户不存在"


# 全局实例
auth = UserAuth()
