# -*- coding: utf-8 -*-
"""
密码加密存储模块
使用 Fernet 对称加密算法对密码进行加密存储
"""
import base64
import hashlib
import os
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


class PasswordCrypt:
    """密码加密/解密类"""

    # 加密算法标识
    ALGORITHM = "Fernet"
    # PBKDF2 迭代次数
    ITERATIONS = 480000
    # 盐值长度
    SALT_LENGTH = 16

    @staticmethod
    def _get_key_from_password(password: str, salt: bytes) -> bytes:
        """
        从密码和盐值派生加密密钥
        
        Args:
            password: 用于派生密钥的密码
            salt: 盐值
            
        Returns:
            派生的加密密钥
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=PasswordCrypt.ITERATIONS,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key

    @staticmethod
    def encrypt(plaintext: str, master_password: str = None) -> str:
        """
        加密密码
        
        Args:
            plaintext: 明文密码
            master_password: 主密码（用于派生加密密钥），如果为 None 则使用默认密钥
            
        Returns:
            加密后的密码（Base64编码，包含盐值和加密数据）
        """
        if not plaintext:
            return ""

        # 如果没有提供主密码，使用系统特定的默认密钥
        if master_password is None:
            # 使用系统相关信息生成默认密钥
            machine_key = f"yunzai-llbot-{os.getlogin()}-{os.environ.get('COMPUTERNAME', 'default')}"
            master_password = machine_key

        # 生成随机盐值
        salt = os.urandom(PasswordCrypt.SALT_LENGTH)

        # 从主密码派生加密密钥
        key = PasswordCrypt._get_key_from_password(master_password, salt)
        fernet = Fernet(key)

        # 加密密码
        encrypted = fernet.encrypt(plaintext.encode())

        # 将盐值和加密数据组合并进行 Base64 编码
        combined = salt + encrypted
        return base64.urlsafe_b64encode(combined).decode('utf-8')

    @staticmethod
    def decrypt(ciphertext: str, master_password: str = None) -> str:
        """
        解密密码
        
        Args:
            ciphertext: 加密的密码（Base64编码）
            master_password: 主密码（用于派生解密密钥），如果为 None 则使用默认密钥
            
        Returns:
            解密后的明文密码
            
        Raises:
            ValueError: 如果解密失败
        """
        if not ciphertext:
            return ""

        try:
            # 如果没有提供主密码，使用系统特定的默认密钥
            if master_password is None:
                machine_key = f"yunzai-llbot-{os.getlogin()}-{os.environ.get('COMPUTERNAME', 'default')}"
                master_password = machine_key

            # 解码 Base64
            combined = base64.urlsafe_b64decode(ciphertext.encode('utf-8'))

            # 分离盐值和加密数据
            salt = combined[:PasswordCrypt.SALT_LENGTH]
            encrypted = combined[PasswordCrypt.SALT_LENGTH:]

            # 从主密码派生解密密钥
            key = PasswordCrypt._get_key_from_password(master_password, salt)
            fernet = Fernet(key)

            # 解密密码
            decrypted = fernet.decrypt(encrypted)
            return decrypted.decode('utf-8')

        except Exception as e:
            raise ValueError(f"密码解密失败: {str(e)}")

    @staticmethod
    def is_encrypted(value: str) -> bool:
        """
        检查密码是否已加密
        
        Args:
            value: 待检查的密码字符串
            
        Returns:
            True 如果已加密，False 如果是明文
        """
        if not value:
            return False

        try:
            # 尝试解码 Base64
            decoded = base64.urlsafe_b64decode(value.encode('utf-8'))
            # 检查长度是否合理（至少包含盐值和至少一些加密数据）
            return len(decoded) >= PasswordCrypt.SALT_LENGTH + 16
        except Exception:
            return False

    @staticmethod
    def hash_password(password: str) -> str:
        """
        计算密码的哈希值（用于验证密码而不存储明文）
        
        Args:
            password: 密码
            
        Returns:
            密码的 SHA-256 哈希值（十六进制字符串）
        """
        return hashlib.sha256(password.encode('utf-8')).hexdigest()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        验证密码是否匹配哈希值
        
        Args:
            password: 待验证的密码
            password_hash: 密码的哈希值
            
        Returns:
            True 如果匹配，False 如果不匹配
        """
        return PasswordCrypt.hash_password(password) == password_hash