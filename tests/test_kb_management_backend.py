#!/usr/bin/env python3
"""test_kb_management_backend.py — 文件删除 / 快照管理 / 图谱可视化的后端单元测试。

覆盖：
- KnowledgeGraphBuilder.remove_document / subgraph_for_view / layout_positions
- KnowledgeSnapshotManager.snapshot_info / restore_apply / prune_preview / prune
- RAGEngine.remove_file / file_delete_preview（Mock Chroma + 索引）
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from knowledge_graph.graph_builder import KnowledgeGraphBuilder
from knowledge_snapshot import KnowledgeSnapshotManager


# ==================== 图谱：文档移除 / 子图 / 布局 ====================

def _builder(tmp_path):
    return KnowledgeGraphBuilder(persist_path=str(tmp_path / "g.json"), auto_persist=False)


def _seed(b: KnowledgeGraphBuilder):
    """手工构造一张小图：a-b 来自 x.md，b-c 来自 x.md 与 y.md，d 孤立来自 y.md。"""
    g = b.graph
    g.add_node("tool_a", text="A", entity_type="tool", confidence=0.9, documents=["x.md"])
    g.add_node("concept_b", text="B", entity_type="concept", confidence=0.8, documents=["x.md", "y.md"])
    g.add_node("concept_c", text="C", entity_type="concept", confidence=0.4, documents=["y.md"])
    g.add_node("person_d", text="D", entity_type="person", confidence=0.95, documents=["y.md"])
    g.add_edge("tool_a", "concept_b", relation_type="uses", confidence=0.8, documents=["x.md"])
    g.add_edge("concept_b", "concept_c", relation_type="related", confidence=0.7, documents=["x.md", "y.md"])
    return b


class TestRemoveDocument:
    def test_removes_only_contributions_of_doc(self, tmp_path):
        b = _seed(_builder(tmp_path))
        result = b.remove_document("x.md")
        assert result["nodes_removed"] == 1  # tool_a
        assert result["nodes_updated"] == 1  # concept_b 保留（还有 y.md）
        assert result["edges_removed"] == 1  # a->b
        assert result["edges_updated"] == 1  # b->c 保留
        assert "tool_a" not in b.graph
        assert b.graph.nodes["concept_b"]["documents"] == ["y.md"]
        assert b.graph["concept_b"]["concept_c"]["documents"] == ["y.md"]

    def test_unknown_doc_is_noop(self, tmp_path):
        b = _seed(_builder(tmp_path))
        before = (b.graph.number_of_nodes(), b.graph.number_of_edges())
        result = b.remove_document("nope.md")
        assert not any(result.values())
        assert (b.graph.number_of_nodes(), b.graph.number_of_edges()) == before

    def test_no_graph_returns_zeros(self, tmp_path):
        b = _builder(tmp_path)
        b.graph = None
        assert b.remove_document("x.md") == {
            "nodes_removed": 0, "edges_removed": 0, "nodes_updated": 0, "edges_updated": 0,
        }

    def test_autosave_and_layout_cache_cleared(self, tmp_path):
        b = _seed(KnowledgeGraphBuilder(persist_path=str(tmp_path / "g.json"), auto_persist=True))
        b.layout_positions(["tool_a", "concept_b"], dim=2)
        assert b._layout_cache
        b.remove_document("y.md")
        assert not b._layout_cache
        data = json.loads((tmp_path / "g.json").read_text(encoding="utf-8"))
        assert {n["id"] for n in data["nodes"]} == {"tool_a", "concept_b"}


class TestSubgraphForView:
    def test_empty_graph(self, tmp_path):
        v = _builder(tmp_path).subgraph_for_view()
        assert v["nodes"] == [] and v["edges"] == [] and v["total_nodes"] == 0

    def test_full_view_sorted_by_degree(self, tmp_path):
        v = _seed(_builder(tmp_path)).subgraph_for_view()
        assert v["total_nodes"] == 4 and v["total_edges"] == 2
        assert v["nodes"][0]["id"] == "concept_b" and v["nodes"][0]["degree"] == 2
        assert {e["relation_type"] for e in v["edges"]} == {"uses", "related"}
        assert v["truncated"] is False

    def test_type_and_confidence_filters(self, tmp_path):
        b = _seed(_builder(tmp_path))
        v = b.subgraph_for_view(types=["concept"])
        assert {n["id"] for n in v["nodes"]} == {"concept_b", "concept_c"}
        assert len(v["edges"]) == 1  # 只保留两端都在集合内的边
        v = b.subgraph_for_view(min_confidence=0.85)
        assert {n["id"] for n in v["nodes"]} == {"tool_a", "person_d"}
        assert v["edges"] == []

    def test_max_nodes_truncates(self, tmp_path):
        v = _seed(_builder(tmp_path)).subgraph_for_view(max_nodes=2)
        assert len(v["nodes"]) == 2 and v["truncated"] is True
        assert v["nodes"][0]["id"] == "concept_b"

    def test_focus_with_hops(self, tmp_path):
        b = _seed(_builder(tmp_path))
        v = b.subgraph_for_view(focus="A", hops=1)
        assert {n["id"] for n in v["nodes"]} == {"tool_a", "concept_b"}
        v = b.subgraph_for_view(focus="a", hops=2)  # 大小写不敏感
        assert {n["id"] for n in v["nodes"]} == {"tool_a", "concept_b", "concept_c"}
        v = b.subgraph_for_view(focus="zzz")
        assert v["nodes"] == [] and v["total_nodes"] == 4

    def test_bad_numeric_inputs_fallback(self, tmp_path):
        v = _seed(_builder(tmp_path)).subgraph_for_view(min_confidence="x", max_nodes="y")
        assert len(v["nodes"]) == 4

    def test_no_graph(self, tmp_path):
        b = _builder(tmp_path)
        b.graph = None
        assert b.subgraph_for_view()["nodes"] == []


class TestLayoutPositions:
    def test_dims_and_cache(self, tmp_path):
        b = _seed(_builder(tmp_path))
        ids = ["tool_a", "concept_b", "concept_c"]
        pos3 = b.layout_positions(ids, dim=3)
        assert set(pos3) == set(ids) and all(len(p) == 3 for p in pos3.values())
        pos2 = b.layout_positions(ids, dim=2)
        assert all(len(p) == 2 for p in pos2.values())
        assert b.layout_positions(ids, dim=3) is pos3  # 命中缓存
        assert b.layout_positions(list(reversed(ids)), dim=3) is pos3  # 集合哈希与顺序无关

    def test_empty_and_no_graph(self, tmp_path):
        b = _builder(tmp_path)
        assert b.layout_positions([], dim=3) == {}
        b.graph = None
        assert b.layout_positions(["a"], dim=3) == {}

    def test_cache_evicts_oldest(self, tmp_path):
        b = _seed(_builder(tmp_path))
        for i in range(12):
            b.graph.add_node(f"n{i}", text=f"N{i}", entity_type="other", documents=[])
            b.layout_positions([f"n{i}"], dim=2)
        assert len(b._layout_cache) == 8
        assert (hash(frozenset(["n0"])), 2) not in b._layout_cache

    def test_layout_failure_falls_back_to_random(self, tmp_path):
        b = _seed(_builder(tmp_path))
        with patch("knowledge_graph.graph_builder.nx.spring_layout", side_effect=RuntimeError("boom")):
            pos = b.layout_positions(["tool_a", "concept_b"], dim=2)
        assert set(pos) == {"tool_a", "concept_b"}

    def test_add_document_clears_cache(self, tmp_path):
        b = _seed(_builder(tmp_path))
        b.layout_positions(["tool_a"], dim=2)
        b.add_document("Python uses Django.", "z.md")
        assert not b._layout_cache
        b.layout_positions(["tool_a"], dim=2)
        b.clear()
        assert not b._layout_cache


# ==================== 快照：详情 / 恢复 / 清理 ====================

def _write_snapshot(snapshot_dir: Path, sid: str, docs, trigger="document_added", ts=None):
    data = {
        "snapshot_id": sid,
        "timestamp": ts or f"2026-01-01T00:00:{sid[-2:]}",
        "version": "1.0",
        "documents": [
            {"file_path": str(p), "file_name": Path(p).name, "file_type": Path(p).suffix,
             "chunk_count": 2, "file_hash": "h", "added_timestamp": "t"}
            for p in docs
        ],
        "storage_paths": {"chroma_db": "c", "llama_index": "l"},
        "model_config": {"llm_model": "qwen", "embed_model": "nomic", "ollama_base_url": "u"},
        "total_chunks": 2 * len(docs),
        "metadata": {"trigger": trigger, "created_by": "system", "document_count": len(docs)},
    }
    (snapshot_dir / f"{sid}.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def snap_env(tmp_path):
    snap_dir = tmp_path / "snaps"
    snap_dir.mkdir()
    manager = KnowledgeSnapshotManager(index_dir=str(tmp_path / "idx"), snapshot_dir=str(snap_dir))
    return manager, snap_dir


class TestSnapshotInfo:
    def test_info_marks_missing_files(self, snap_env, tmp_path):
        manager, snap_dir = snap_env
        present = tmp_path / "a.md"
        present.write_text("hi", encoding="utf-8")
        _write_snapshot(snap_dir, "s_01", [present, tmp_path / "missing.md"], trigger="manual")
        info = manager.snapshot_info("s_01")
        assert info["snapshot_id"] == "s_01" and info["trigger"] == "manual"
        assert info["document_count"] == 2 and info["missing_count"] == 1
        assert info["total_chunks"] == 4
        assert info["model_config"]["llm_model"] == "qwen"
        by_name = {d["file_name"]: d for d in info["documents"]}
        assert by_name["a.md"]["exists"] is True and by_name["missing.md"]["exists"] is False

    def test_info_unknown_returns_none(self, snap_env):
        manager, _ = snap_env
        assert manager.snapshot_info("nope") is None


class TestRestoreApply:
    def _engine(self):
        engine = MagicMock()
        engine.auto_snapshot_trigger = object()
        return engine

    def test_append_skips_missing_and_counts(self, snap_env, tmp_path):
        manager, snap_dir = snap_env
        a = tmp_path / "a.md"
        a.write_text("a", encoding="utf-8")
        _write_snapshot(snap_dir, "s_01", [a, tmp_path / "gone.md"])
        engine = self._engine()
        events = []
        loader = MagicMock(return_value=[object(), object()])
        result = manager.restore_apply("s_01", engine, mode="append", load_documents=loader, progress=events.append)
        assert result["ok"] and result["mode"] == "append"
        assert result["restored"] == 1 and result["skipped"] == 1 and result["failed"] == 0
        assert result["chunks"] == 2 and result["missing"] == [str(tmp_path / "gone.md")]
        engine.clear_index.assert_not_called()
        engine.add_documents.assert_called_once()
        assert engine.add_documents.call_args.args[1] == [str(a)]
        assert [e["stage"] for e in events] == ["plan", "load", "done"]
        # 恢复期间抑制自动快照，结束后恢复
        assert engine.auto_snapshot_trigger is not None

    def test_replace_clears_index_and_graph(self, snap_env, tmp_path):
        manager, snap_dir = snap_env
        a = tmp_path / "a.md"
        a.write_text("a", encoding="utf-8")
        _write_snapshot(snap_dir, "s_01", [a])
        engine = self._engine()
        builder = MagicMock()
        with patch("knowledge_graph.get_graph_builder", return_value=builder):
            result = manager.restore_apply("s_01", engine, mode="replace", load_documents=lambda p: [1])
        assert result["ok"] and result["restored"] == 1
        engine.clear_index.assert_called_once()
        builder.clear.assert_called_once_with(persist=True)

    def test_load_failures_are_reported(self, snap_env, tmp_path):
        manager, snap_dir = snap_env
        a = tmp_path / "a.md"
        b = tmp_path / "b.md"
        a.write_text("a", encoding="utf-8")
        b.write_text("b", encoding="utf-8")
        _write_snapshot(snap_dir, "s_01", [a, b])
        engine = self._engine()

        def loader(path):
            if path.endswith("a.md"):
                raise RuntimeError("bad")
            return []

        result = manager.restore_apply("s_01", engine, load_documents=loader)
        assert result["failed"] == 2 and result["restored"] == 0
        assert any("bad" in e for e in result["errors"]) and any("无法加载" in e for e in result["errors"])

    def test_bad_inputs(self, snap_env, tmp_path):
        manager, snap_dir = snap_env
        assert manager.restore_apply("nope", MagicMock())["ok"] is False
        _write_snapshot(snap_dir, "s_01", [tmp_path / "a.md"])
        assert "未知恢复模式" in manager.restore_apply("s_01", MagicMock(), mode="weird")["error"]

    def test_progress_errors_are_swallowed(self, snap_env, tmp_path):
        manager, snap_dir = snap_env
        _write_snapshot(snap_dir, "s_01", [])

        def bad_progress(evt):
            raise RuntimeError("ui gone")

        result = manager.restore_apply("s_01", MagicMock(), load_documents=lambda p: [1], progress=bad_progress)
        assert result["ok"] and result["total"] == 0

    def test_default_loader_import(self, snap_env, tmp_path):
        manager, snap_dir = snap_env
        _write_snapshot(snap_dir, "s_01", [])
        with patch("document_loader.load_documents") as ld:
            result = manager.restore_apply("s_01", MagicMock())
        assert result["ok"]


class TestPrune:
    def test_preview_only_auto_and_keeps_recent(self, snap_env, tmp_path):
        manager, snap_dir = snap_env
        for i in range(1, 6):
            _write_snapshot(snap_dir, f"s_0{i}", [], trigger="document_added" if i != 3 else "manual")
        pending = manager.prune_preview(keep=2)
        ids = [p["snapshot_id"] for p in pending]
        # 倒序：s_05, s_04 为最近两个自动快照被保留；s_03 手动不参与
        assert ids == ["s_02", "s_01"]
        assert manager.prune_preview(keep=10) == []
        assert [p["snapshot_id"] for p in manager.prune_preview(keep=0, auto_only=False)] == [
            "s_05", "s_04", "s_03", "s_02", "s_01",
        ]

    def test_prune_deletes_and_returns_ids(self, snap_env, tmp_path):
        manager, snap_dir = snap_env
        for i in range(1, 4):
            _write_snapshot(snap_dir, f"s_0{i}", [])
        deleted = manager.prune(keep=1)
        assert deleted == ["s_02", "s_01"]
        assert sorted(p.stem for p in snap_dir.glob("*.json")) == ["s_03"]

    def test_bad_keep_falls_back(self, snap_env, tmp_path):
        manager, snap_dir = snap_env
        _write_snapshot(snap_dir, "s_01", [])
        assert manager.prune_preview(keep="x") == []


# ==================== RAGEngine.remove_file ====================

@pytest.fixture
def engine():
    """Mock Ollama / Chroma 的 RAGEngine，带一个可控的 chroma_collection。"""
    with patch("rag_engine.Ollama"), patch("rag_engine.OllamaEmbedding"), \
            patch("rag_engine.chromadb.PersistentClient") as mock_chroma:
        collection = MagicMock()
        mock_chroma.return_value.get_or_create_collection.return_value = collection
        from rag_engine import RAGEngine

        eng = RAGEngine(enable_auto_snapshot=False, enable_security=False)
        eng.chroma_collection = collection
        yield eng


def _metas(path, n=3, name=None, ref="ref-1"):
    name = name or Path(path).name
    return [{"file_path": path, "file_name": name, "document_id": ref} for _ in range(n)]


def _collection_get(mapping):
    """按 where 条件返回不同的元数据集合。"""

    def _get(where=None, include=None):
        key = json.dumps(where, sort_keys=True)
        return {"metadatas": mapping.get(key, [])}

    return _get


class TestRemoveFile:
    def test_full_flow_via_index(self, engine):
        path = "/docs/a.md"
        engine.chroma_collection.get.side_effect = _collection_get({
            json.dumps({"file_path": path}, sort_keys=True): _metas(path),
        })
        engine.index = MagicMock()
        engine.metadata_manager = MagicMock()
        engine.metadata_manager.get_file_metadata.return_value = object()
        builder = MagicMock()
        builder.remove_document.return_value = {"nodes_removed": 2, "edges_removed": 1, "nodes_updated": 0, "edges_updated": 0}
        with patch("knowledge_graph.get_graph_builder", return_value=builder), \
                patch.object(engine, "_persist_index") as persist:
            result = engine.remove_file(path)
        assert result["chunks_deleted"] == 3 and result["graph_updated"] is True
        assert result["file_name"] == "a.md" and result["note"] == ""
        engine.index.delete_ref_doc.assert_called_once_with("ref-1", delete_from_docstore=True)
        persist.assert_called_once()
        builder.remove_document.assert_called_once_with("a.md")
        engine.metadata_manager.remove_file.assert_called_once_with(path)

    def test_falls_back_to_direct_delete_when_index_fails(self, engine):
        path = "/docs/a.md"
        engine.chroma_collection.get.side_effect = _collection_get({
            json.dumps({"file_path": path}, sort_keys=True): _metas(path, n=2),
        })
        engine.index = MagicMock()
        engine.index.delete_ref_doc.side_effect = RuntimeError("no docstore")
        engine.metadata_manager = None
        builder = MagicMock()
        builder.remove_document.return_value = {"nodes_removed": 0, "edges_removed": 0, "nodes_updated": 0, "edges_updated": 0}
        with patch("knowledge_graph.get_graph_builder", return_value=builder), patch.object(engine, "_persist_index"):
            result = engine.remove_file(path)
        engine.chroma_collection.delete.assert_called_with(where={"file_path": path})
        assert result["graph_updated"] is False and "无该文件的贡献" in result["note"]

    def test_no_index_deletes_directly(self, engine):
        path = "/docs/a.md"
        engine.chroma_collection.get.side_effect = _collection_get({
            json.dumps({"file_path": path}, sort_keys=True): _metas(path, n=1),
        })
        engine.index = None
        engine.metadata_manager = None
        with patch("knowledge_graph.get_graph_builder", return_value=MagicMock(graph=None)):
            result = engine.remove_file(path)
        engine.chroma_collection.delete.assert_called()
        assert result["chunks_deleted"] == 1

    def test_shared_basename_keeps_graph(self, engine):
        path = "/docs/a.md"
        other = "/other/a.md"
        engine.chroma_collection.get.side_effect = _collection_get({
            json.dumps({"file_path": path}, sort_keys=True): _metas(path, n=1),
            json.dumps({"file_name": "a.md"}, sort_keys=True): _metas(other, n=1),
        })
        engine.index = None
        engine.metadata_manager = None
        builder = MagicMock()
        with patch("knowledge_graph.get_graph_builder", return_value=builder):
            result = engine.remove_file(path)
        builder.remove_document.assert_not_called()
        assert result["graph_updated"] is False and "另有同名文件" in result["note"]

    def test_unknown_file_raises(self, engine):
        engine.chroma_collection.get.return_value = {"metadatas": []}
        engine.metadata_manager = MagicMock()
        engine.metadata_manager.get_file_metadata.return_value = None
        with pytest.raises(FileNotFoundError):
            engine.remove_file("/nope.md")
        with pytest.raises(ValueError):
            engine.remove_file("")

    def test_metadata_only_registration_is_removed(self, engine):
        """向量库无 chunk 但元数据已登记：仍允许删除以清理残留登记。"""
        engine.chroma_collection.get.return_value = {"metadatas": []}
        engine.metadata_manager = MagicMock()
        engine.metadata_manager.get_file_metadata.return_value = object()
        builder = MagicMock()
        builder.remove_document.return_value = {"nodes_removed": 0, "edges_removed": 0, "nodes_updated": 0, "edges_updated": 0}
        with patch("knowledge_graph.get_graph_builder", return_value=builder):
            result = engine.remove_file("/docs/x.md")
        assert result["chunks_deleted"] == 0
        engine.chroma_collection.delete.assert_not_called()
        engine.metadata_manager.remove_file.assert_called_once()

    def test_graph_failure_is_reported_in_note(self, engine):
        path = "/docs/a.md"
        engine.chroma_collection.get.side_effect = _collection_get({
            json.dumps({"file_path": path}, sort_keys=True): _metas(path, n=1),
        })
        engine.index = None
        engine.metadata_manager = MagicMock()
        engine.metadata_manager.remove_file.side_effect = RuntimeError("meta boom")
        with patch("knowledge_graph.get_graph_builder", side_effect=RuntimeError("graph boom")):
            result = engine.remove_file(path)
        assert "图谱更新失败" in result["note"]

    def test_chroma_get_failure_treated_as_empty(self, engine):
        engine.chroma_collection.get.side_effect = RuntimeError("db down")
        engine.metadata_manager = None
        with pytest.raises(FileNotFoundError):
            engine.remove_file("/docs/a.md")
        assert engine._other_files_share_basename("/x", "a.md") is False


class TestFileDeletePreview:
    def test_preview_counts_graph_contributions(self, engine, tmp_path):
        path = "/docs/a.md"
        engine.chroma_collection.get.side_effect = _collection_get({
            json.dumps({"file_path": path}, sort_keys=True): _metas(path, n=4),
        })
        engine.metadata_manager = None
        b = _seed(_builder(tmp_path))
        with patch("knowledge_graph.get_graph_builder", return_value=b):
            preview = engine.file_delete_preview("/docs/x.md")  # 图中 doc_id 为 x.md
        assert preview["graph_nodes"] == 2 and preview["graph_edges"] == 2
        with patch("knowledge_graph.get_graph_builder", return_value=b):
            preview = engine.file_delete_preview(path)
        assert preview["exists"] and preview["chunk_count"] == 4 and preview["graph_nodes"] == 0

    def test_preview_shared_basename_and_missing(self, engine):
        path = "/docs/a.md"
        engine.chroma_collection.get.side_effect = _collection_get({
            json.dumps({"file_path": path}, sort_keys=True): _metas(path, n=1),
            json.dumps({"file_name": "a.md"}, sort_keys=True): _metas("/o/a.md", n=1),
        })
        engine.metadata_manager = MagicMock()
        engine.metadata_manager.get_file_metadata.return_value = None
        preview = engine.file_delete_preview(path)
        assert preview["graph_shared_basename"] is True and preview["graph_nodes"] == 0
        assert engine.file_delete_preview("")["exists"] is False
        engine.chroma_collection.get.side_effect = None
        engine.chroma_collection.get.return_value = {"metadatas": []}
        assert engine.file_delete_preview("/nope.md")["exists"] is False

    def test_preview_graph_error_ignored(self, engine):
        path = "/docs/a.md"
        engine.chroma_collection.get.side_effect = _collection_get({
            json.dumps({"file_path": path}, sort_keys=True): _metas(path, n=1),
        })
        engine.metadata_manager = None
        with patch("knowledge_graph.get_graph_builder", side_effect=RuntimeError("x")):
            preview = engine.file_delete_preview(path)
        assert preview["graph_nodes"] == 0
