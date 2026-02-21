# -*- coding: utf-8 -*-
"""
密码强度验证模块
提供密码强度验证和评分功能
"""
import re
from typing import Dict


class PasswordStrength:
    """密码强度级别"""
    VERY_WEAK = 0
    WEAK = 1
    MEDIUM = 2
    STRONG = 3
    VERY_STRONG = 4

    @classmethod
    def get_label(cls, level: int) -> str:
        """获取强度级别标签"""
        labels = {
            cls.VERY_WEAK: "非常弱",
            cls.WEAK: "弱",
            cls.MEDIUM: "中等",
            cls.STRONG: "强",
            cls.VERY_STRONG: "非常强"
        }
        return labels.get(level, "未知")

    @classmethod
    def get_color(cls, level: int) -> str:
        """获取强度级别对应的颜色（用于前端显示）"""
        colors = {
            cls.VERY_WEAK: "#dc3545",  # 红色
            cls.WEAK: "#fd7e14",       # 橙色
            cls.MEDIUM: "#ffc107",     # 黄色
            cls.STRONG: "#20c997",     # 青绿色
            cls.VERY_STRONG: "#28a745" # 绿色
        }
        return colors.get(level, "#6c757d")


class PasswordValidator:
    """密码验证器"""

    # 强密码策略配置
    MIN_LENGTH = 8
    MAX_LENGTH = 64
    REQUIRE_UPPERCASE = True
    REQUIRE_LOWERCASE = True
    REQUIRE_DIGIT = True
    REQUIRE_SPECIAL = False  # 可选

    # 常见弱密码列表
    COMMON_WEAK_PASSWORDS = {
        'password', '12345678', 'qwerty', 'abc123', 'password1',
        '123456789', '11111111', 'admin', 'admin123', 'root',
        'welcome', 'monkey', 'dragon', 'master', 'letmein',
        'login', 'passw0rd', 'qwerty123', '123abc', 'test123',
        'admin1234', 'password123', '1234567890', 'qwertyuiop',
        'asdfghjkl', 'zxcvbnm', '1q2w3e4r', 'a1b2c3d4'
    }

    @staticmethod
    def validate(password: str):
        """
        验证密码是否符合强密码策略
        
        Args:
            password: 待验证的密码
            
        Returns:
            (是否通过验证, 错误消息列表)
        """
        errors = []

        # 检查密码长度
        if len(password) < PasswordValidator.MIN_LENGTH:
            errors.append(f"密码长度不能少于{PasswordValidator.MIN_LENGTH}位")
        
        if len(password) > PasswordValidator.MAX_LENGTH:
            errors.append(f"密码长度不能超过{PasswordValidator.MAX_LENGTH}位")

        # 检查是否包含大写字母
        if PasswordValidator.REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            errors.append("密码必须包含至少一个大写字母")

        # 检查是否包含小写字母
        if PasswordValidator.REQUIRE_LOWERCASE and not re.search(r'[a-z]', password):
            errors.append("密码必须包含至少一个小写字母")

        # 检查是否包含数字
        if PasswordValidator.REQUIRE_DIGIT and not re.search(r'\d', password):
            errors.append("密码必须包含至少一个数字")

        # 检查是否包含特殊字符（可选）
        if PasswordValidator.REQUIRE_SPECIAL and not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            errors.append("密码必须包含至少一个特殊字符")

        # 检查是否为常见弱密码
        if password.lower() in PasswordValidator.COMMON_WEAK_PASSWORDS:
            errors.append("密码过于简单，请使用更复杂的密码")

        # 检查是否包含连续重复字符（如：aaa, 111）
        if re.search(r'(.)\1{2,}', password):
            errors.append("密码不应包含连续重复的字符")

        # 检查是否包含连续序列（如：123, abc）
        if re.search(r'(012|123|234|345|456|567|678|789|890|abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)', password.lower()):
            errors.append("密码不应包含连续的数字或字母序列")

        return len(errors) == 0, errors

    @staticmethod
    def get_strength_score(password: str) -> int:
        """
        计算密码强度分数（0-100）
        
        Args:
            password: 待评估的密码
            
        Returns:
            强度分数（0-100）
        """
        score = 0

        # 基础分数：长度贡献
        length_score = min(len(password) * 4, 40)
        score += length_score

        # 字符类型多样性加分
        if re.search(r'[a-z]', password):
            score += 10
        if re.search(r'[A-Z]', password):
            score += 10
        if re.search(r'\d', password):
            score += 10
        if re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            score += 15

        # 字符种类数量加分（鼓励使用多种字符）
        char_types = 0
        if re.search(r'[a-z]', password):
            char_types += 1
        if re.search(r'[A-Z]', password):
            char_types += 1
        if re.search(r'\d', password):
            char_types += 1
        if re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
            char_types += 1
        
        if char_types == 4:
            score += 15
        elif char_types == 3:
            score += 10

        # 惩罚项
        # 常见弱密码惩罚
        if password.lower() in PasswordValidator.COMMON_WEAK_PASSWORDS:
            score -= 30

        # 连续重复字符惩罚
        if re.search(r'(.)\1{2,}', password):
            score -= 10

        # 连续序列惩罚
        if re.search(r'(012|123|234|345|456|567|678|789|890|abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)', password.lower()):
            score -= 10

        # 确保分数在 0-100 范围内
        return max(0, min(100, score))

    @staticmethod
    def get_strength_level(password: str) -> int:
        """
        获取密码强度级别
        
        Args:
            password: 待评估的密码
            
        Returns:
            强度级别（PasswordStrength常量）
        """
        score = PasswordValidator.get_strength_score(password)

        if score < 30:
            return PasswordStrength.VERY_WEAK
        elif score < 50:
            return PasswordStrength.WEAK
        elif score < 70:
            return PasswordStrength.MEDIUM
        elif score < 90:
            return PasswordStrength.STRONG
        else:
            return PasswordStrength.VERY_STRONG

    @staticmethod
    def get_strength_info(password: str) -> Dict:
        """
        获取密码强度详细信息
        
        Args:
            password: 待评估的密码
            
        Returns:
            包含强度详细信息的字典
        """
        level = PasswordValidator.get_strength_level(password)
        score = PasswordValidator.get_strength_score(password)
        is_valid, errors = PasswordValidator.validate(password)

        return {
            'level': level,
            'level_label': PasswordStrength.get_label(level),
            'score': score,
            'color': PasswordStrength.get_color(level),
            'is_valid': is_valid,
            'errors': errors,
            'requirements': {
                'min_length': PasswordValidator.MIN_LENGTH,
                'max_length': PasswordValidator.MAX_LENGTH,
                'require_uppercase': PasswordValidator.REQUIRE_UPPERCASE,
                'require_lowercase': PasswordValidator.REQUIRE_LOWERCASE,
                'require_digit': PasswordValidator.REQUIRE_DIGIT,
                'require_special': PasswordValidator.REQUIRE_SPECIAL
            },
            'checks': {
                'length_ok': len(password) >= PasswordValidator.MIN_LENGTH,
                'has_uppercase': bool(re.search(r'[A-Z]', password)),
                'has_lowercase': bool(re.search(r'[a-z]', password)),
                'has_digit': bool(re.search(r'\d', password)),
                'has_special': bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', password)),
                'not_common': password.lower() not in PasswordValidator.COMMON_WEAK_PASSWORDS,
                'no_repeat': not bool(re.search(r'(.)\1{2,}', password)),
                'no_sequence': not bool(re.search(r'(012|123|234|345|456|567|678|789|890|abc|bcd|cde|def|efg|fgh|ghi|hij|ijk|jkl|klm|lmn|mno|nop|opq|pqr|qrs|rst|stu|tuv|uvw|vwx|wxy|xyz)', password.lower()))
            }
        }

    @staticmethod
    def get_password_requirements_text() -> str:
        """获取密码要求说明文本"""
        requirements = []
        requirements.append(f"密码长度：{PasswordValidator.MIN_LENGTH}-{PasswordValidator.MAX_LENGTH}位")
        if PasswordValidator.REQUIRE_UPPERCASE:
            requirements.append("必须包含大写字母")
        if PasswordValidator.REQUIRE_LOWERCASE:
            requirements.append("必须包含小写字母")
        if PasswordValidator.REQUIRE_DIGIT:
            requirements.append("必须包含数字")
        if PasswordValidator.REQUIRE_SPECIAL:
            requirements.append("必须包含特殊字符")
        return "；".join(requirements)