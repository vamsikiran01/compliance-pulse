# 03 — End-to-End RAG Ingestion & Retrieval Pipeline

![RAG Pipeline](../designs/rag_pipeline.png)

Chunking: 512 tokens, 15% overlap, MD5 deduplication, Hybrid pgvector + BM25 search with `>= 0.65` similarity floor.
