"""
SQL生成器模块

提供安全的SQL查询生成功能。
支持SELECT、INSERT、UPDATE、DELETE等操作。
"""

import logging
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class SQLOperation(Enum):
    """SQL操作类型"""
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    CREATE = "CREATE"
    DROP = "DROP"


class SQLGenerator:
    """SQL生成器"""
    
    def __init__(self):
        """初始化SQL生成器"""
        logger.info("SQL生成器初始化完成")
    
    def generate_select(
        self,
        table: str,
        columns: Optional[List[str]] = None,
        where: Optional[str] = None,
        order_by: Optional[str] = None,
        limit: Optional[int] = None
    ) -> str:
        """
        生成SELECT语句
        
        Args:
            table: 表名
            columns: 列名列表，默认为所有列
            where: WHERE条件
            order_by: 排序条件
            limit: 限制行数
            
        Returns:
            SQL语句
        """
        if columns is None or len(columns) == 0:
            columns_str = "*"
        else:
            columns_str = ", ".join(columns)
        
        query = f"SELECT {columns_str} FROM {table}"
        
        if where:
            query += f" WHERE {where}"
        
        if order_by:
            query += f" ORDER BY {order_by}"
        
        if limit:
            query += f" LIMIT {limit}"
        
        logger.debug(f"生成SELECT语句: {query}")
        return query
    
    def generate_insert(
        self,
        table: str,
        data: Dict[str, Any]
    ) -> tuple:
        """
        生成INSERT语句
        
        Args:
            table: 表名
            data: 数据字典（列名: 值）
            
        Returns:
            (SQL语句, 参数元组)
        """
        columns = list(data.keys())
        values = list(data.values())
        placeholders = ", ".join(["?" for _ in values])
        columns_str = ", ".join(columns)
        
        query = f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders})"
        
        logger.debug(f"生成INSERT语句: {query}")
        return (query, tuple(values))
    
    def generate_update(
        self,
        table: str,
        data: Dict[str, Any],
        where: str
    ) -> tuple:
        """
        生成UPDATE语句
        
        Args:
            table: 表名
            data: 数据字典（列名: 值）
            where: WHERE条件
            
        Returns:
            (SQL语句, 参数元组)
        """
        set_clauses = []
        values = []
        
        for column, value in data.items():
            set_clauses.append(f"{column} = ?")
            values.append(value)
        
        set_str = ", ".join(set_clauses)
        query = f"UPDATE {table} SET {set_str} WHERE {where}"
        
        logger.debug(f"生成UPDATE语句: {query}")
        return (query, tuple(values))
    
    def generate_delete(
        self,
        table: str,
        where: str
    ) -> str:
        """
        生成DELETE语句
        
        Args:
            table: 表名
            where: WHERE条件
            
        Returns:
            SQL语句
        """
        query = f"DELETE FROM {table} WHERE {where}"
        
        logger.debug(f"生成DELETE语句: {query}")
        return query
    
    def generate_create_table(
        self,
        table: str,
        columns: Dict[str, str]
    ) -> str:
        """
        生成CREATE TABLE语句
        
        Args:
            table: 表名
            columns: 列定义字典（列名: 类型）
            
        Returns:
            SQL语句
        """
        column_definitions = []
        
        for column_name, column_type in columns.items():
            column_definitions.append(f"{column_name} {column_type}")
        
        columns_str = ", ".join(column_definitions)
        query = f"CREATE TABLE {table} ({columns_str})"
        
        logger.debug(f"生成CREATE TABLE语句: {query}")
        return query
    
    def generate_drop_table(self, table: str) -> str:
        """
        生成DROP TABLE语句
        
        Args:
            table: 表名
            
        Returns:
            SQL语句
        """
        query = f"DROP TABLE IF EXISTS {table}"
        
        logger.debug(f"生成DROP TABLE语句: {query}")
        return query
    
    def escape_identifier(self, identifier: str) -> str:
        """
        转义标识符（表名、列名等）
        
        Args:
            identifier: 标识符
            
        Returns:
            转义后的标识符
        """
        # SQLite 使用双引号转义标识符
        return f'"{identifier}"'
    
    def validate_sql(self, sql: str) -> bool:
        """
        验证SQL语句是否安全
        
        Args:
            sql: SQL语句
            
        Returns:
            是否安全
        """
        # 基本的安全检查
        dangerous_keywords = [
            'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'EXEC',
            'EXECUTE', 'xp_cmdshell', 'sp_executesql'
        ]
        
        sql_upper = sql.upper()
        
        for keyword in dangerous_keywords:
            if keyword in sql_upper:
                logger.warning(f"SQL语句包含潜在危险关键词: {keyword}")
                return False
        
        return True