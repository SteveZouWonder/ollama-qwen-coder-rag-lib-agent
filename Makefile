.PHONY: build

build:
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	git ls-files '*.py' | xargs -r python -m py_compile
	@echo "Build completed."
