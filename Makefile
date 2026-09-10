.PHONY: build install install-dev test

# 运行时依赖（版本已在 requirements.txt 中全部钉死）
install:
	python -m pip install --upgrade pip
	pip install -r requirements.txt

# 开发/测试依赖（requirements-dev.txt 通过 -r 引用 requirements.txt）
install-dev:
	python -m pip install --upgrade pip
	pip install -r requirements-dev.txt

# CI（pr-build-vulnerability-gate.yml）使用：装运行时依赖 + 语法编译检查
build: install
	git ls-files '*.py' | xargs -r python -m py_compile
	@echo "Build completed."

test:
	python -m pytest tests -q -n 4
