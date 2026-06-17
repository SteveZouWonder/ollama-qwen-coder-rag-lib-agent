"""
查询执行器模块

提供安全的SQL查询执行功能。
支持查询、插入、更新、删除等操作。
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from .db_connector import DatabaseConnector

logger = logging.getLogger(__name__)


@dataclass
class QueryResult:
    """查询结果数据类"""
    rows: List[Dict[str, Any]]
    row_count: int
    columns: List[str]
    execution_time: float
    success: bool
    error_message: Optional[str] = None
    affected_rows: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'rows': self.rows,
            'row_count': self.row_count,
            'columns': self.columns,
            'execution_time': self.execution_time,
            'success': self.success,
            'error_message': self.error_message,
            'affected_rows': self.affected_rows
        }


class QueryExecutor:
    """查询执行器"""
    
    def __init__(self, connector: DatabaseConnector):
        """
        初始化查询执行器
        
        Args:
            connector: 数据库连接器
        """
        self.connector = connector
        logger.info("查询执行器初始化完成")
    
    def execute_query(self, query: str, params: Optional[Tuple] = None) -> QueryResult:
        """
        执行查询（SELECT）
        
        Args:
            query: SQL查询语句
            params: 查询参数
            
        Returns:
            查询结果
        """
        import time
        start_time = time.time()
        
        try:
            with self.connector.get_connection() as conn:
                cursor = conn.cursor()
                
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                rows = cursor.fetchall()
                columns = [description[0] for description in cursor.description] if cursor.description else []
                
                # 转换为字典列表
                row_dicts = []
                for row in rows:
                    if isinstance(row, dict):
                        row_dicts.append(row)
                    else:
                        row_dicts.append(dict(zip(columns, row)))
                
                execution_time = time.time() - start_time
                
                result = QueryResult(
                    rows=row_dicts,
                    row_count=len(row_dicts),
                    columns=columns,
                    execution_time=execution_time,
                    success=True
                )
                
                logger.info(f"查询执行成功，返回 {len(row_dicts)} 行")
                return result
        
        except Exception as e:
            execution_time = time.time() - start_time
            error_message = f"查询执行失败: {str(e)}"
            logger.error(error_message)
            
            return QueryResult(
                rows=[],
                row_count=0,
                columns=[],
                execution_time=execution_time,
                success=False,
                error_message=error_message
            )
    
    def execute_update(self, query: str, params: Optional[Tuple] = None) -> QueryResult:
        """
        执行更新操作（INSERT, UPDATE, DELETE）
        
        Args:
            query: SQL语句
            params: 查询参数
            
        Returns:
            执行结果
        """
        import time
        start_time = time.time()
        
        try:
            with self.connector.get_connection() as conn:
                cursor = conn.cursor()
                
                if params:
                    cursor.execute(query, params)
                else:
                    cursor.execute(query)
                
                conn.commit()
                affected_rows = cursor.rowcount
                
                execution_time = time.time() - start_time
                
                result = QueryResult(
                    rows=[],
                    row_count=0,
                    columns=[],
                    execution_time=execution_time,
                    success=True,
                    affected_rows=affected_rows
                )
                
                logger.info(f"更新操作成功，影响 {affected_rows} 行")
                return result
        
        except Exception as e:
            execution_time = time.time() - start_time
            error_message = f"更新操作失败: {str(e)}"
            logger.error(error_message)
            
            return QueryResult(
                rows=[],
                row_count=0,
                columns=[],
                execution_time=execution_time,
                success=False,
                error_message=error_message
            )
    
    def execute_batch(self, query: str, params_list: List[Tuple]) -> QueryResult:
        """
        批量执行操作
        
        Args:
            query: SQL语句
            params_list: 参数列表
            
        Returns:
            执行结果
        """
        import time
        start_time = time.time()
        
        try:
            with self.connector.get_connection() as conn:
                cursor = conn.cursor()
                
                cursor.executemany(query, params_list)
                conn.commit()
                affected_rows = cursor.rowcount
                
                execution_time = time.time() - start_time
                
                result = QueryResult(
                    rows=[],
                    row_count=0,
                    columns=[],
                    execution_time=execution_time,
                    success=True,
                    affected_rows=affected_rows
                )
                
                logger.info(f"批量操作成功，影响 {affected_rows} 行")
                return result
        
        except Exception as e:
            execution_time = time.time() - start_time
            error_message = f"批量操作失败: {str(e)}"
            logger.error(error_message)
            
            return QueryResult(
                rows=[],
                row_count=0,
                columns=[],
                execution_time=execution_time,
                success=False,
                error_message=error_message
            )
    
    def get_table_schema(self, table_name: str) -> Dict[str, Any]:
        """
        获取表结构
        
        Args:
            table_name: 表名
            
        Returns:
            表结构信息
        """
        try:
            with self.connector.get_connection() as conn:
                cursor = conn.cursor()
                
                if self.connector.db_type.value == "sqlite":
                    # SQLite 获取表结构
                    cursor.execute(f"PRAGMA table_info({table_name})")
                    columns_info = cursor.fetchall()
                    
                    columns = []
                    for col in columns_info:
                        columns.append({
                            'name': col[1],
                            'type': col[2],
                            'not_null': bool(col[3]),
                            'default_value': col[4],
                            'primary_key': bool(col[5])
                        })
                    
                    return {
                        'table_name': table_name,
                        'columns': columns
                    }
                else:
                    # 其他数据库类型
                    logger.warning(f"数据库类型 {self.connector.db_type.value} 的表结构获取暂未实现")
                    return {}
        
        except Exception as e:
            logger.error(f"获取表结构失败: {e}")
            return {}