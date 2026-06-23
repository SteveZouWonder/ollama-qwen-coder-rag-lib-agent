#!/usr/bin/env python3
"""
测试命令推荐系统包级别的公共导出。

回归测试：query_interface.py 通过
``from command_recommender import CommandRecommender, RecommendationSource``
导入推荐系统。此前 ``RecommendationSource`` 未在包的 ``__init__.py`` 中导出，
导致 ImportError 被 query_interface 的 ``except ImportError`` 静默吞掉，
推荐系统被错误地标记为“未安装”（RECOMMENDER_AVAILABLE=False）。
本测试确保所有公共类型均可从包顶层导入。
"""
import importlib
import unittest

import src.command_recommender as command_recommender


class TestPackageExports(unittest.TestCase):
    """验证 command_recommender 包的公共 API。"""

    def test_recommendation_source_exported(self):
        """RecommendationSource 必须可从包顶层导入（回归测试）。"""
        from src.command_recommender import RecommendationSource

        self.assertTrue(hasattr(RecommendationSource, "WORKFLOW"))
        self.assertTrue(hasattr(RecommendationSource, "STATE"))
        self.assertTrue(hasattr(RecommendationSource, "HISTORY"))
        self.assertTrue(hasattr(RecommendationSource, "LEARNING"))

    def test_recommendation_strength_exported(self):
        """RecommendationStrength 必须可从包顶层导入。"""
        from src.command_recommender import RecommendationStrength

        self.assertTrue(hasattr(RecommendationStrength, "VERY_STRONG"))
        self.assertTrue(hasattr(RecommendationStrength, "WEAK"))

    def test_query_interface_import_line(self):
        """query_interface.py 使用的导入语句必须成功。"""
        from src.command_recommender import (  # noqa: F401
            CommandRecommender,
            RecommendationSource,
        )

        self.assertIsNotNone(CommandRecommender)
        self.assertIsNotNone(RecommendationSource)

    def test_all_names_in_all_are_importable(self):
        """__all__ 中声明的每个名称都必须真实存在于包中。"""
        for name in command_recommender.__all__:
            self.assertTrue(
                hasattr(command_recommender, name),
                f"__all__ 声明了 {name!r}，但包中不存在该属性",
            )

    def test_public_types_in_all(self):
        """核心公共类型必须在 __all__ 中声明。"""
        for name in (
            "CommandRecommender",
            "RecommendationSource",
            "RecommendationReason",
            "Recommendation",
        ):
            self.assertIn(name, command_recommender.__all__)

    def test_package_reimport_consistent(self):
        """重新导入包后 __all__ 保持一致，避免状态污染。"""
        reloaded = importlib.reload(command_recommender)
        self.assertIn("RecommendationSource", reloaded.__all__)


if __name__ == "__main__":
    unittest.main()
