"""
数据库连接器模块

提供安全、高效的数据库连接管理功能。
支持多种数据库类型和连接池管理。
"""

import logging
from enum import Enum
from typing import Optional, Dict, Any
from contextlib import contextmanager
import sqlite3

logger = logging.getLogger(__name__)


class DatabaseType(Enum):
    """支持的数据库类型"""
    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    MSSQL = "mssql"


class DatabaseConnector:
    """数据库连接器"""
    
    def __init__(self, db_type: DatabaseType, **connection_params):
        """
        初始化数据库连接器
        
        Args:
            db_type: 数据库类型
            connection_params: 连接参数
        """
        self.db_type = db_type
        self.connection_params = connection_params
        self._connection = None
        self._connection_pool = None
        
        logger.info(f"初始化数据库连接器: {db_type.value}")
    
    @contextmanager
    def get_connection(self):
        """
        获取数据库连接（上下文管理器）
        
        Yields:
            数据库连接对象
        """
        if self._connection is None:
            self._connection = self._create_connection()
        
        try:
            yield self._connection
        except Exception as e:
            logger.error(f"数据库操作失败: {e}")
            raise
    
    def _create_connection(self):
        """
        创建数据库连接
        
        Returns:
            数据库连接对象
        """
        try:
            if self.db_type == DatabaseType.SQLITE:
                database_path = self.connection_params.get('database', ':memory:')
                connection = sqlite3.connect(database_path)
                connection.row_factory = sqlite3.Row
                logger.info("SQLite数据库连接成功")
                return connection
            else:
                # 其他数据库类型的连接需要相应的驱动
                logger.warning(f"数据库类型 {self.db_type.value} 暂不支持")
                raise NotImplementedError(f"数据库类型 {self.db_type.value} 暂不支持")
        
        except Exception as e:
            logger.error(f"创建数据库连接失败: {e}")
            raise
    
    def test_connection(self) -> bool:
        """
        测试数据库连接是否正常
        
        Returns:
            连接是否成功
        """
        try:
            with self.get_connection() as conn:
                # 执行简单查询测试连接
                cursor = conn.cursor()
                
                if self.db_type == DatabaseType.SQLITE:
                    cursor.execute("SELECT 1")
                    cursor.fetchone()
                    logger.info("数据库连接测试成功")
                    return True
                else:
                    logger.warning(f"数据库类型 {self.db_type.value} 的连接测试暂未实现")
                    return False
        
        except Exception as e:
            logger.error(f"数据库连接测试失败: {e}")
            return False
    
    def close(self):
        """关闭数据库连接"""
        if self._connection is not None:
            try:
                self._connection.close()
                self._connection = None
                logger.info("数据库连接已关闭")
            except Exception as e:
                logger.error(f"关闭数据库连接失败: {e}")
    
    def __enter__(self):
        """支持上下文管理器"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """退出上下文管理器"""
        self.close()
    
    def get_connection_info(self) -> Dict[str, Any]:
        """
        获取连接信息
        
        Returns:
            连接信息字典
        """
        info = {
            'db_type': self.db_type.value,
            'connection_params': {k: v for k, v in self.connection_params.items() if k != 'password'},
            'is_connected': self._connection is not None
        }
        return info