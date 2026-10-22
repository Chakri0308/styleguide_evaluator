# StyleLens

AI style guide analysis & compliance app: ingest brand/style guides, extract a canonical style profile
(colors, typography, logo, imagery, voice & tone, rules), compare a candidate document against a reference
guide, and chat with the guide using verified, clickable citations.

> Status: under active development. See the milestone plan below.

## Stack
- **Web:** Next.js (App Router) · TypeScript · Tailwind · shadcn/ui · Framer Motion · react-pdf
- **API:** FastAPI (Python) · SSE streaming
- **Worker:** Arq + Redis (ingestion, extraction, indexing, comparison)
- **Storage:** PostgreSQL + pgvector · S3-compatible object storage (MinIO locally)
- **Models:** Anthropic Claude (generation, vision, extraction) · local bge-m3 embeddings · local bge-reranker-v2-m3

## Milestones
1. Foundation — compose stack, DB schema, upload, UI shell + design system
2. Ingestion — PDF/DOCX/image parsing with page + bbox, progress events
3. Extraction — colors, typography, images, rules → canonical schema → Guide Profile UI
4. Retrieval — chunking, embeddings, BM25 + vector, RRF, reranking, eval harness
5. Chat — streaming dock, verified citations, highlighted source viewer
6. Comparison — alignment, ΔE2000/WCAG checks, LLM judgment, report UI, export
7. Polish — motion, a11y, performance, PPTX/HTML/Markdown
