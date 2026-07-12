import tempfile
import unittest
from pathlib import Path

from pr_factory.agents.llm import HashEmbedder, get_embedder
from pr_factory.context.indexers.code_parser import get_source_files, parse_file
from pr_factory.context.indexers.hybrid_qdrant import QdrantCodeIndexer, QdrantIndexConfig
from pr_factory.context.retrievers.hybrid_qdrant import QdrantHybridRetriever


class ContextQdrantTests(unittest.TestCase):
    def test_hash_embedder_is_deterministic(self):
        embedder = get_embedder(provider="hash")

        first = embedder.embed_query("AuthProvider token")
        second = embedder.embed_query("AuthProvider token")

        self.assertIsInstance(embedder, HashEmbedder)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 384)

    def test_parse_file_extracts_symbol_chunks_without_tree_sitter_dependency(self):
        with tempfile.TemporaryDirectory(prefix="parser-test-") as tmp:
            path = Path(tmp) / "auth.py"
            path.write_text("def login():\n    return True\n\nclass AuthProvider:\n    pass\n", encoding="utf-8")

            chunks = parse_file(path)

            self.assertEqual([chunk.name for chunk in chunks], ["login", "AuthProvider"])
            self.assertEqual(chunks[0].start_line, 1)

    def test_qdrant_index_and_hybrid_retrieve(self):
        with tempfile.TemporaryDirectory(prefix="qdrant-context-test-") as tmp:
            root = Path(tmp)
            repo = root / "repo"
            (repo / "src").mkdir(parents=True)
            (repo / "src" / "AuthProvider.tsx").write_text(
                "export function AuthProvider() {\n  throw new TypeError('cannot read property token');\n}\n",
                encoding="utf-8",
            )
            (repo / "src" / "Other.ts").write_text("export const other = 1;\n", encoding="utf-8")

            config = QdrantIndexConfig(collection_name="test_chunks", qdrant_path=":memory:", recreate=True)
            embedder = HashEmbedder(dimension=64)
            indexer = QdrantCodeIndexer(config=config, embedder=embedder)
            count = indexer.index_repository(repo, repo_name="acme/widgets", commit="abc123")

            retriever = QdrantHybridRetriever(config=config, embedder=embedder, client=indexer.client)
            results = retriever.retrieve("AuthProvider TypeError token", k=3, repo="acme/widgets", commit="abc123")

            self.assertGreaterEqual(count, 1)
            self.assertTrue(results)
            self.assertEqual(results[0].path, "src/AuthProvider.tsx")
            self.assertGreater(results[0].lexical_score, 0)
            self.assertIn("AuthProvider", results[0].content)

    def test_get_source_files_skips_excluded_dirs(self):
        with tempfile.TemporaryDirectory(prefix="source-files-test-") as tmp:
            repo = Path(tmp)
            (repo / "src").mkdir()
            (repo / "node_modules").mkdir()
            (repo / "src" / "app.py").write_text("print('ok')", encoding="utf-8")
            (repo / "node_modules" / "bad.py").write_text("print('skip')", encoding="utf-8")

            files = get_source_files(repo)

            self.assertEqual([Path(file).name for file in files], ["app.py"])


if __name__ == "__main__":
    unittest.main()
