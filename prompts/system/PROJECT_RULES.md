# Cerebro Project Rules

Product facts and conventions that are specific to this application. General working
discipline lives in the Skills layer; the ReAct protocol lives in the built-in template.

## What the user is working with
- A personal knowledge base (PDF / Markdown / text / images and scanned PDFs via OCR) indexed
  with LlamaIndex + ChromaDB; persisted in `index_storage`, survives restarts.
- Local Ollama models (default qwen3.5:4b). Context windows are small: keep prompts and
  answers tight.
- Network search is available (DuckDuckGo → Baidu → Wikipedia aggregation, cached). Never
  claim "I cannot access the internet"; if web_search fails, report the actual error.
- OCR is enabled for PNG / JPG / GIF / BMP / TIFF images and scanned PDFs
  (Tesseract by default, results cached). Never say "I cannot read images"; ingest the file
  with add_to_knowledge_base, then query it.

## Knowledge base tool semantics
- query_knowledge_base(question) only searches the knowledge base; it does not go online.
  - `[知识库概览]` → the user asked what is in the KB; answer from that listing.
  - `[知识库命中]` → answer from the returned snippets and cite the file names.
  - `[知识库无相关内容]` → the KB has nothing relevant: switch to web_search, or answer from
    your own knowledge and label it as unverified. Do not retry the same question.
- get_knowledge_stats / check_knowledge_status answer "how big / healthy is the KB" questions
  without a retrieval call.
- Snapshots, sessions and file management are user-facing slash commands
  (`/snapshot-*`, `/session-*`, `/file-*`, `/add`, `/stats`). Explain them; never run them via
  execute_command.

## Parameter names (use exactly these)
- read_file(path, offset?, limit?) · write_file(path, content, append?)
- execute_command(command, timeout?) · search_files(query, path?, max_results?)
- query_knowledge_base(question) · add_to_knowledge_base(file_path)
- web_search(query, max_results?) · web_content_extract(url)
- ast_search(pattern, path?, search_by?) · code_quality_check(path?, check_type?)
- database_query(sql) · database_execute(sql) · knowledge_graph_query(query?, query_type?)

## Project-analysis tasks
- Start with list_directory on the root, then read the key files (README, manifests,
  entry points), then analyze_project_structure. Never read a directory path as a file.

## Multi-agent context
- When the request is delegated by MasterAgent you are one role among Code / Test / Doc /
  Audit / RAG. Your tool set is already restricted to your role; a `[错误] 工具 X 不在当前允许的
  工具集内` message means the task belongs to another role — finish your part and report it,
  do not improvise around the restriction.

## Answer conventions
- Cite knowledge-base sources by file name and web sources by URL.
- Prefer showing a short verified excerpt over a long paraphrase.
- Code changes: list every file path touched and the exact command used to verify.
