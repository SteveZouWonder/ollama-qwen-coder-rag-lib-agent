"""runtime_paths：app_state_dir（.cerebro）与 .devin 旧目录的一次性迁移。"""
import logging

import pytest

import runtime_paths as rp


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    """走真实解析路径：关闭 conftest 的 app_state 根覆盖，并把用户数据目录指向 tmp。"""
    monkeypatch.setattr(rp, "_APP_STATE_ROOT_OVERRIDE", None)
    monkeypatch.setattr(rp, "user_data_dir", lambda: tmp_path)
    return tmp_path


class TestAppStateDir:
    def test_root_without_relative(self, data_root):
        assert rp.app_state_dir() == data_root / ".cerebro"
        assert not (data_root / ".cerebro").exists()  # 不主动创建

    def test_override_root_skips_migration(self, tmp_path, monkeypatch):
        monkeypatch.setattr(rp, "user_data_dir", lambda: tmp_path)
        (tmp_path / ".devin" / "knowledge").mkdir(parents=True)
        override = tmp_path / "override"
        rp.set_app_state_root(override)
        try:
            assert rp.app_state_dir("knowledge") == override / "knowledge"
            assert rp.app_state_dir() == override
            assert (tmp_path / ".devin" / "knowledge").exists()  # 未触发迁移
        finally:
            rp.set_app_state_root(None)

    def test_relative_path(self, data_root):
        assert rp.app_state_dir("knowledge/snapshots") == data_root / ".cerebro" / "knowledge" / "snapshots"

    def test_cwd_data_dir_still_available(self, data_root):
        assert rp.cwd_data_dir("index_storage") == data_root / "index_storage"


class TestLegacyMigration:
    def test_moves_old_dir_when_target_missing(self, data_root, caplog):
        old = data_root / ".devin" / "knowledge" / "snapshots"
        old.mkdir(parents=True)
        (old / "a.json").write_text("{}")
        with caplog.at_level(logging.INFO, logger="runtime_paths"):
            target = rp.app_state_dir("knowledge/snapshots")
        assert target == data_root / ".cerebro" / "knowledge" / "snapshots"
        assert (target / "a.json").exists()
        assert not old.exists()
        assert any("已迁移运行时数据" in r.message for r in caplog.records)

    def test_moves_old_file(self, data_root):
        old = data_root / ".devin" / "knowledge" / "graph.json"
        old.parent.mkdir(parents=True)
        old.write_text('{"nodes": []}')
        target = rp.app_state_dir("knowledge/graph.json")
        assert target.read_text() == '{"nodes": []}'
        assert not old.exists()

    def test_does_not_overwrite_existing_target(self, data_root):
        old = data_root / ".devin" / "file_metadata"
        old.mkdir(parents=True)
        (old / "metadata.json").write_text("old")
        new = data_root / ".cerebro" / "file_metadata"
        new.mkdir(parents=True)
        (new / "metadata.json").write_text("new")
        rp.app_state_dir("file_metadata")
        assert (new / "metadata.json").read_text() == "new"
        assert (old / "metadata.json").read_text() == "old"  # 旧数据保留，不丢

    def test_no_old_no_target_is_noop(self, data_root):
        target = rp.app_state_dir("knowledge")
        assert not target.exists() and not (data_root / ".devin").exists()

    def test_partial_migration_per_relative(self, data_root):
        """按 relative 粒度迁移：只搬请求的那一部分，其他旧数据原地保留。"""
        (data_root / ".devin" / "knowledge" / "snapshots").mkdir(parents=True)
        (data_root / ".devin" / "file_metadata").mkdir(parents=True)
        rp.app_state_dir("file_metadata")
        assert (data_root / ".cerebro" / "file_metadata").exists()
        assert (data_root / ".devin" / "knowledge" / "snapshots").exists()

    def test_migration_failure_is_logged_not_raised(self, data_root, monkeypatch, caplog):
        old = data_root / ".devin" / "knowledge"
        old.mkdir(parents=True)
        import shutil
        monkeypatch.setattr(shutil, "move", lambda *a, **k: (_ for _ in ()).throw(OSError("boom")))
        with caplog.at_level(logging.WARNING, logger="runtime_paths"):
            target = rp.app_state_dir("knowledge")
        assert target == data_root / ".cerebro" / "knowledge"
        assert any("迁移运行时数据失败" in r.message for r in caplog.records)

    def test_helper_returns_bool(self, data_root):
        old = data_root / ".devin" / "x"
        old.mkdir(parents=True)
        assert rp._migrate_legacy_state(old, data_root / ".cerebro" / "x") is True
        assert rp._migrate_legacy_state(old, data_root / ".cerebro" / "x") is False


class TestDefaultConsumers:
    """三个持久化模块的默认路径都落到 .cerebro/。"""

    def test_file_metadata_default(self, data_root, monkeypatch):
        import file_metadata as fm
        mgr = fm.FileMetadataManager()
        assert mgr.storage_path == data_root / ".cerebro" / "file_metadata"

    def test_snapshot_default(self, data_root):
        import knowledge_snapshot as ks
        mgr = ks.KnowledgeSnapshotManager()
        assert mgr.snapshot_dir == data_root / ".cerebro" / "knowledge" / "snapshots"
