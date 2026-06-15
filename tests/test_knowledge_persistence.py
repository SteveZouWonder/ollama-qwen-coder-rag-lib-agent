#!/usr/bin/env python3
"""
测试知识库持久化功能
验证知识库是否能正确保存和加载
"""
import pytest
from rag_engine import RAGEngine
from document_loader import load_documents
from pathlib import Path
import sys

@pytest.mark.integration
def test_persistence():
    print("=" * 50)
    print("测试知识库持久化功能")
    print("=" * 50)
    
    # 1. 初始化引擎
    print("\n1. 初始化 RAG 引擎...")
    engine = RAGEngine(enable_auto_snapshot=False, enable_security=False)
    print("✅ 引擎初始化成功")
    
    # 2. 检查现有索引
    print("\n2. 检查现有索引...")
    existing_index = engine.load_index()
    if existing_index:
        print("✅ 发现现有索引")
        print(f"   索引类型: {type(existing_index)}")
        
        # 测试查询
        print("\n3. 测试查询...")
        try:
            result = engine.query("文档中有什么内容？")
            print(f"✅ 查询成功: {result[:100]}...")
        except Exception as e:
            print(f"❌ 查询失败: {e}")
        return True
    else:
        print("⚠️  未发现现有索引")
        
        # 尝试构建新索引
        print("\n4. 尝试构建新索引...")
        data_dir = Path("../data")
        if data_dir.exists():
            print(f"   使用数据目录: {data_dir}")
            documents = load_documents(str(data_dir))
            if documents:
                print(f"   加载了 {len(documents)} 个文档")
                engine.build_index(documents)
                print("✅ 索引构建完成")
                
                # 验证持久化
                print("\n5. 验证持久化...")
                engine2 = RAGEngine(enable_auto_snapshot=False, enable_security=False)
                loaded_index = engine2.load_index()
                if loaded_index:
                    print("✅ 持久化验证成功 - 索引可以重新加载")
                    return True
                else:
                    print("❌ 持久化验证失败 - 索引无法重新加载")
                    return False
            else:
                print("⚠️  数据目录中没有找到文档")
                return False
        else:
            print(f"⚠️  数据目录不存在: {data_dir}")
            print("   请创建 data 目录并添加一些文档")
            return False

if __name__ == "__main__":
    success = test_persistence()
    sys.exit(0 if success else 1)
