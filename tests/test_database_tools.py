#!/usr/bin/env python3
"""
数据库工具模块单元测试
"""
import pytest
import tempfile
import os

# 导入被测试的模块
from database_tools.db_connector import DatabaseConnector, DatabaseType
from database_tools.query_executor import QueryExecutor, QueryResult
from database_tools.sql_generator import SQLGenerator, SQLOperation


class TestDatabaseConnector:
    """测试数据库连接器"""
    
    def test_initialization(self):
        """测试初始化"""
        connector = DatabaseConnector(DatabaseType.SQLITE, database=":memory:")
        assert connector is not None
        assert connector.db_type == DatabaseType.SQLITE
        assert connector.connection_params['database'] == ":memory:"
    
    def test_sqlite_connection(self):
        """测试SQLite连接"""
        connector = DatabaseConnector(DatabaseType.SQLITE, database=":memory:")
        assert connector.test_connection() is True
    
    def test_context_manager(self):
        """测试上下文管理器"""
        connector = DatabaseConnector(DatabaseType.SQLITE, database=":memory:")
        
        with connector.get_connection() as conn:
            assert conn is not None
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            result = cursor.fetchone()
            # SQLite Row factory returns Row object, convert to tuple
            result_tuple = tuple(result) if result else result
            assert result_tuple == (1,)
    
    def test_close_connection(self):
        """测试关闭连接"""
        connector = DatabaseConnector(DatabaseType.SQLITE, database=":memory:")
        connector.test_connection()
        
        assert connector._connection is not None
        connector.close()
        assert connector._connection is None
    
    def test_with_statement(self):
        """测试with语句"""
        with DatabaseConnector(DatabaseType.SQLITE, database=":memory:") as connector:
            assert connector.test_connection() is True
    
    def test_unsupported_database_type(self):
        """测试不支持的数据库类型"""
        connector = DatabaseConnector(DatabaseType.MYSQL, database="test")
        assert connector.test_connection() is False
    
    def test_get_connection_info(self):
        """测试获取连接信息"""
        connector = DatabaseConnector(DatabaseType.SQLITE, database=":memory:")
        info = connector.get_connection_info()
        
        assert info['db_type'] == 'sqlite'
        assert info['is_connected'] == False  # 尚未连接
        assert 'database' in info['connection_params']


class TestQueryExecutor:
    """测试查询执行器"""
    
    def setup_method(self):
        """每个测试方法前设置"""
        self.connector = DatabaseConnector(DatabaseType.SQLITE, database=":memory:")
        self.executor = QueryExecutor(self.connector)
    
    def test_initialization(self):
        """测试初始化"""
        assert self.executor is not None
        assert self.executor.connector is not None
    
    def test_execute_query_success(self):
        """测试成功的查询执行"""
        with self.connector.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            conn.commit()
        
        result = self.executor.execute_query("SELECT * FROM test")
        
        assert result.success is True
        assert result.row_count == 0
        assert result.columns == ['id', 'name']
    
    def test_execute_query_with_data(self):
        """测试带数据的查询执行"""
        with self.connector.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            cursor.execute("INSERT INTO test VALUES (1, 'Alice')")
            cursor.execute("INSERT INTO test VALUES (2, 'Bob')")
            conn.commit()
        
        result = self.executor.execute_query("SELECT * FROM test")
        
        assert result.success is True
        assert result.row_count == 2
        assert len(result.rows) == 2
        assert result.rows[0]['name'] == 'Alice'
    
    def test_execute_query_with_params(self):
        """测试带参数的查询执行"""
        with self.connector.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            cursor.execute("INSERT INTO test VALUES (1, 'Alice')")
            cursor.execute("INSERT INTO test VALUES (2, 'Bob')")
            conn.commit()
        
        result = self.executor.execute_query("SELECT * FROM test WHERE id = ?", (1,))
        
        assert result.success is True
        assert result.row_count == 1
        assert result.rows[0]['name'] == 'Alice'
    
    def test_execute_query_failure(self):
        """测试查询执行失败"""
        result = self.executor.execute_query("SELECT * FROM nonexistent_table")
        
        assert result.success is False
        assert result.error_message is not None
        assert result.row_count == 0
    
    def test_execute_update_success(self):
        """测试成功的更新执行"""
        with self.connector.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            conn.commit()
        
        result = self.executor.execute_update("INSERT INTO test VALUES (1, 'Alice')")
        
        assert result.success is True
        assert result.affected_rows == 1
    
    def test_execute_update_with_params(self):
        """测试带参数的更新执行"""
        with self.connector.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            cursor.execute("INSERT INTO test VALUES (1, 'Alice')")
            conn.commit()
        
        result = self.executor.execute_update("UPDATE test SET name = ? WHERE id = ?", ("Bob", 1))
        
        assert result.success is True
        assert result.affected_rows == 1
    
    def test_execute_update_failure(self):
        """测试更新执行失败"""
        result = self.executor.execute_update("INSERT INTO nonexistent_table VALUES (1, 'Alice')")
        
        assert result.success is False
        assert result.error_message is not None
    
    def test_execute_batch_success(self):
        """测试成功的批量执行"""
        with self.connector.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER, name TEXT)")
            conn.commit()
        
        params_list = [(1, 'Alice'), (2, 'Bob'), (3, 'Charlie')]
        result = self.executor.execute_batch("INSERT INTO test VALUES (?, ?)", params_list)
        
        assert result.success is True
        assert result.affected_rows == 3
    
    def test_execute_batch_failure(self):
        """测试批量执行失败"""
        params_list = [(1, 'Alice'), (2, 'Bob')]
        result = self.executor.execute_batch("INSERT INTO nonexistent_table VALUES (?, ?)", params_list)
        
        assert result.success is False
        assert result.error_message is not None
    
    def test_get_table_schema(self):
        """测试获取表结构"""
        with self.connector.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
            conn.commit()
        
        schema = self.executor.get_table_schema("test")
        
        assert schema is not None
        assert schema['table_name'] == 'test'
        assert len(schema['columns']) == 2
        assert schema['columns'][0]['name'] == 'id'
        assert schema['columns'][1]['name'] == 'name'
    
    def test_get_table_schema_failure(self):
        """测试获取表结构失败"""
        schema = self.executor.get_table_schema("nonexistent_table")
        
        # get_table_schema返回表结构信息，即使表不存在也可能返回空结构
        assert schema is not None
        assert schema.get('table_name') == 'nonexistent_table'
        assert len(schema.get('columns', [])) == 0
    
    def test_get_table_schema_other_database_type(self):
        """测试其他数据库类型的表结构获取"""
        # 使用MySQL连接器（不支持）
        mysql_connector = DatabaseConnector(DatabaseType.MYSQL, database="test")
        mysql_executor = QueryExecutor(mysql_connector)
        
        schema = mysql_executor.get_table_schema("test")
        
        assert schema == {}


class TestSQLGenerator:
    """测试SQL生成器"""
    
    def setup_method(self):
        """每个测试方法前设置"""
        self.generator = SQLGenerator()
    
    def test_initialization(self):
        """测试初始化"""
        assert self.generator is not None
    
    def test_generate_select_all(self):
        """测试生成SELECT所有列"""
        sql = self.generator.generate_select("users")
        
        assert sql == "SELECT * FROM users"
    
    def test_generate_select_specific_columns(self):
        """测试生成SELECT特定列"""
        sql = self.generator.generate_select("users", columns=["id", "name"])
        
        assert sql == "SELECT id, name FROM users"
    
    def test_generate_select_with_where(self):
        """测试生成带WHERE的SELECT"""
        sql = self.generator.generate_select("users", where="age > 18")
        
        assert sql == "SELECT * FROM users WHERE age > 18"
    
    def test_generate_select_with_order_by(self):
        """测试生成带ORDER BY的SELECT"""
        sql = self.generator.generate_select("users", order_by="name ASC")
        
        assert sql == "SELECT * FROM users ORDER BY name ASC"
    
    def test_generate_select_with_limit(self):
        """测试生成带LIMIT的SELECT"""
        sql = self.generator.generate_select("users", limit=10)
        
        assert sql == "SELECT * FROM users LIMIT 10"
    
    def test_generate_select_complex(self):
        """测试生成复杂SELECT"""
        sql = self.generator.generate_select(
            "users",
            columns=["id", "name"],
            where="age > 18",
            order_by="name ASC",
            limit=10
        )
        
        assert sql == "SELECT id, name FROM users WHERE age > 18 ORDER BY name ASC LIMIT 10"
    
    def test_generate_insert(self):
        """测试生成INSERT"""
        sql, params = self.generator.generate_insert("users", {"name": "Alice", "age": 25})
        
        assert sql == "INSERT INTO users (name, age) VALUES (?, ?)"
        assert params == ("Alice", 25)
    
    def test_generate_update(self):
        """测试生成UPDATE"""
        sql, params = self.generator.generate_update("users", {"age": 26}, "id = 1")
        
        assert sql == "UPDATE users SET age = ? WHERE id = 1"
        assert params == (26,)
    
    def test_generate_update_multiple_fields(self):
        """测试生成UPDATE多个字段"""
        sql, params = self.generator.generate_update(
            "users",
            {"name": "Bob", "age": 30},
            "id = 1"
        )
        
        assert "SET name = ?, age = ?" in sql
        assert params == ("Bob", 30)
    
    def test_generate_delete(self):
        """测试生成DELETE"""
        sql = self.generator.generate_delete("users", "id = 1")
        
        assert sql == "DELETE FROM users WHERE id = 1"
    
    def test_generate_create_table(self):
        """测试生成CREATE TABLE"""
        columns = {"id": "INTEGER PRIMARY KEY", "name": "TEXT", "age": "INTEGER"}
        sql = self.generator.generate_create_table("users", columns)
        
        assert sql == "CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)"
    
    def test_generate_drop_table(self):
        """测试生成DROP TABLE"""
        sql = self.generator.generate_drop_table("users")
        
        assert sql == "DROP TABLE IF EXISTS users"
    
    def test_escape_identifier(self):
        """测试转义标识符"""
        escaped = self.generator.escape_identifier("table_name")
        
        assert escaped == '"table_name"'
    
    def test_validate_sql_safe(self):
        """测试验证安全的SQL"""
        safe_sql = "SELECT * FROM users WHERE name = 'Alice'"
        assert self.generator.validate_sql(safe_sql) is True
    
    def test_validate_sql_dangerous(self):
        """测试验证危险的SQL"""
        dangerous_sql = "DROP TABLE users"
        assert self.generator.validate_sql(dangerous_sql) is False


class TestQueryResult:
    """测试查询结果数据类"""
    
    def test_to_dict(self):
        """测试转换为字典"""
        result = QueryResult(
            rows=[{"id": 1, "name": "Alice"}],
            row_count=1,
            columns=["id", "name"],
            execution_time=0.5,
            success=True
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['rows'] == [{"id": 1, "name": "Alice"}]
        assert result_dict['row_count'] == 1
        assert result_dict['success'] is True
        assert result_dict['execution_time'] == 0.5
    
    def test_to_dict_with_error(self):
        """测试带错误的转换"""
        result = QueryResult(
            rows=[],
            row_count=0,
            columns=[],
            execution_time=0.1,
            success=False,
            error_message="Table not found"
        )
        
        result_dict = result.to_dict()
        
        assert result_dict['success'] is False
        assert result_dict['error_message'] == "Table not found"