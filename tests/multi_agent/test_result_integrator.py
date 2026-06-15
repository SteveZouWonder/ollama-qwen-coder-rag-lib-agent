"""
测试result_integrator模块
"""
from collaboration import ResultIntegrator
from agents.agent_types import AgentResult, AgentTask


class TestResultIntegrator:
    """测试ResultIntegrator类"""
    
    def test_integrator_creation(self):
        """测试创建结果整合器"""
        integrator = ResultIntegrator()
        
        assert integrator is not None
    
    def test_integrate_empty_results(self):
        """测试整合空结果列表"""
        integrator = ResultIntegrator()
        
        result = integrator.integrate([])
        
        assert result["success"] is False
        assert result["error"] == "No results to integrate"
    
    def test_integrate_single_result(self):
        """测试整合单个结果"""
        integrator = ResultIntegrator()
        
        agent_result = AgentResult(
            task_id="task_001",
            agent_id="agent_001",
            success=True,
            output="任务完成",
            metadata={"key": "value"},
            execution_time=1.0
        )
        
        result = integrator.integrate([agent_result])
        
        assert result["success"] is True
        assert result["total_results"] == 1
        assert result["successful_results"] == 1
        assert result["failed_results"] == 0
    
    def test_integrate_multiple_successful_results(self):
        """测试整合多个成功结果"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="任务1完成",
                metadata={},
                execution_time=1.0
            ),
            AgentResult(
                task_id="task_002",
                agent_id="agent_002",
                success=True,
                output="任务2完成",
                metadata={},
                execution_time=1.5
            ),
            AgentResult(
                task_id="task_003",
                agent_id="agent_003",
                success=True,
                output="任务3完成",
                metadata={},
                execution_time=0.8
            )
        ]
        
        result = integrator.integrate(results)
        
        assert result["success"] is True
        assert result["total_results"] == 3
        assert result["successful_results"] == 3
        assert result["failed_results"] == 0
    
    def test_integrate_mixed_results(self):
        """测试整合混合结果（成功和失败）"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="任务1完成",
                metadata={},
                execution_time=1.0
            ),
            AgentResult(
                task_id="task_002",
                agent_id="agent_002",
                success=False,
                output="",
                metadata={},
                execution_time=0.5,
                error_message="任务2失败"
            ),
            AgentResult(
                task_id="task_003",
                agent_id="agent_003",
                success=True,
                output="任务3完成",
                metadata={},
                execution_time=1.2
            )
        ]
        
        result = integrator.integrate(results)
        
        assert result["success"] is False
        assert result["total_results"] == 3
        assert result["successful_results"] == 2
        assert result["failed_results"] == 1
    
    def test_integrate_with_original_tasks(self):
        """测试整合时包含原始任务信息"""
        integrator = ResultIntegrator()
        
        tasks = [
            AgentTask(
                task_id="task_001",
                task_type="code_generation",
                description="代码任务",
                required_capabilities=["code_generation"],
                input_data={}
            ),
            AgentTask(
                task_id="task_002",
                task_type="testing",
                description="测试任务",
                required_capabilities=["testing"],
                input_data={}
            )
        ]
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="代码任务完成",
                metadata={},
                execution_time=1.0
            ),
            AgentResult(
                task_id="task_002",
                agent_id="agent_002",
                success=True,
                output="测试任务完成",
                metadata={},
                execution_time=0.5
            )
        ]
        
        result = integrator.integrate(results, tasks)
        
        assert result["success"] is True
        assert "detailed_report" in result
    
    def test_integrate_sequential(self):
        """测试顺序整合"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="任务1完成",
                metadata={},
                execution_time=1.0
            ),
            AgentResult(
                task_id="task_002",
                agent_id="agent_002",
                success=True,
                output="任务2完成",
                metadata={},
                execution_time=1.5
            )
        ]
        
        result = integrator.integrate_sequential(results)
        
        assert result["success"] is True
        assert result["total_results"] == 2
    
    def test_integrate_sequential_with_failure(self):
        """测试顺序整合时遇到失败"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="任务1完成",
                metadata={},
                execution_time=1.0
            ),
            AgentResult(
                task_id="task_002",
                agent_id="agent_002",
                success=False,
                output="",
                metadata={},
                execution_time=0.5,
                error_message="任务2失败"
            ),
            AgentResult(
                task_id="task_003",
                agent_id="agent_003",
                success=True,
                output="任务3完成",
                metadata={},
                execution_time=1.0
            )
        ]
        
        result = integrator.integrate_sequential(results)
        
        # 失败的任务及其后续任务应该被忽略
        assert result["total_results"] <= 2
    
    def test_integrate_competitive(self):
        """测试竞争整合"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="方案1",
                metadata={"approach": "A"},
                execution_time=2.0
            ),
            AgentResult(
                task_id="task_001",
                agent_id="agent_002",
                success=True,
                output="方案2",
                metadata={"approach": "B"},
                execution_time=1.5
            ),
            AgentResult(
                task_id="task_001",
                agent_id="agent_003",
                success=True,
                output="方案3",
                metadata={"approach": "C"},
                execution_time=1.8
            )
        ]
        
        result = integrator.integrate_competitive(results)
        
        assert result["success"] is True
        assert "best_result" in result
        assert "all_results" in result
        # 应该选择执行时间最短的结果
        assert result["best_result"]["agent_id"] == "agent_002"
    
    def test_integrate_competitive_all_failed(self):
        """测试竞争整合所有结果都失败"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=False,
                output="",
                metadata={},
                execution_time=2.0,
                error_message="失败1"
            ),
            AgentResult(
                task_id="task_001",
                agent_id="agent_002",
                success=False,
                output="",
                metadata={},
                execution_time=1.5,
                error_message="失败2"
            )
        ]
        
        result = integrator.integrate_competitive(results)
        
        assert result["success"] is False
        # 应该选择执行时间最短的失败结果
        assert result["best_result"]["execution_time"] == 1.5
    
    def test_integrate_hierarchical(self):
        """测试层级整合"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="层级1任务",
                metadata={},
                execution_time=1.0
            ),
            AgentResult(
                task_id="task_002",
                agent_id="agent_002",
                success=True,
                output="层级2任务",
                metadata={},
                execution_time=1.0
            )
        ]
        
        task_hierarchy = {
            "level_0": ["task_001"],
            "level_1": ["task_002"]
        }
        
        result = integrator.integrate_hierarchical(results, task_hierarchy)
        
        assert result["success"] is True
        assert "hierarchical_results" in result
    
    def test_integrate_hierarchical_no_hierarchy(self):
        """测试层级整合无层级信息"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="任务完成",
                metadata={},
                execution_time=1.0
            )
        ]
        
        result = integrator.integrate_hierarchical(results)
        
        # 无层级信息时应该使用普通整合
        assert result["success"] is True
    
    def test_merge_outputs_concatenate(self):
        """测试合并输出（连接模式）"""
        integrator = ResultIntegrator()
        
        outputs = ["输出1", "输出2", "输出3"]
        
        merged = integrator.merge_outputs(outputs, mode="concatenate")
        
        assert "输出1" in merged
        assert "输出2" in merged
        assert "输出3" in merged
    
    def test_merge_outputs_smart(self):
        """测试合并输出（智能模式）"""
        integrator = ResultIntegrator()
        
        outputs = ["输出1", "输出2", "输出1", "输出3"]
        
        merged = integrator.merge_outputs(outputs, mode="smart_merge")
        
        # 去重后应该只有3个输出
        lines = merged.split("\n\n")
        assert len(lines) == 3
    
    def test_merge_outputs_empty(self):
        """测试合并空输出列表"""
        integrator = ResultIntegrator()
        
        merged = integrator.merge_outputs([])
        
        assert merged == ""
    
    def test_generate_summary(self):
        """测试生成摘要"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="完成",
                metadata={},
                execution_time=1.0
            ),
            AgentResult(
                task_id="task_002",
                agent_id="agent_002",
                success=False,
                output="",
                metadata={},
                execution_time=0.5,
                error_message="失败"
            )
        ]
        
        summary = integrator._generate_summary(results)
        
        assert "执行了 2 个任务" in summary
        assert "成功 1 个" in summary
        assert "失败 1 个" in summary
    
    def test_generate_detailed_report(self):
        """测试生成详细报告"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="任务1完成",
                metadata={"test": True},
                execution_time=1.0
            )
        ]
        
        report = integrator._generate_detailed_report(results)
        
        assert "详细执行报告" in report
        assert "task_001" in report
        assert "agent_001" in report
        assert "统计信息" in report
    
    def test_integrate_parallel(self):
        """测试并行整合"""
        integrator = ResultIntegrator()
        
        results = [
            AgentResult(
                task_id="task_001",
                agent_id="agent_001",
                success=True,
                output="任务1",
                metadata={},
                execution_time=1.0
            ),
            AgentResult(
                task_id="task_002",
                agent_id="agent_002",
                success=True,
                output="任务2",
                metadata={},
                execution_time=1.0
            )
        ]
        
        result = integrator.integrate_parallel(results)
        
        assert result["success"] is True
        assert result["total_results"] == 2
    
    def test_merge_outputs_default_mode(self):
        """测试使用默认模式合并输出"""
        integrator = ResultIntegrator()
        
        outputs = ["输出1", "输出2"]
        
        # 使用无效模式应该回退到默认
        merged = integrator.merge_outputs(outputs, mode="invalid_mode")
        
        assert "输出1" in merged
        assert "输出2" in merged
