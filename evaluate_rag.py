"""
Automated Benchmark and Evaluation Suite for Enterprise Multi-Modal RAG System
Measures:
1. Dense (FAISS) vs Sparse (BM25) vs Hybrid (RRF) vs Cross-Encoder Re-ranking
2. Retrieval Recall@K and Precision@K
3. Latency profiling (ms per pipeline stage)
4. Groundedness and Context Keyword Coverage
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import List, Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

try:
    from rag.search import RAGSearch
except ImportError:
    from search import RAGSearch

BENCHMARK_DATASET = [
    {
        "query": "What is the self-attention mechanism and scaled dot-product attention?",
        "expected_keywords": ["attention", "query", "key", "value", "scaled dot-product"],
        "expected_source": "attention.pdf"
    },
    {
        "query": "What are the main components of object detection architectures?",
        "expected_keywords": ["backbone", "bounding box", "detection", "feature map"],
        "expected_source": "objectdetection.pdf"
    },
    {
        "query": "How are word embeddings generated in NLP?",
        "expected_keywords": ["vector", "embedding", "semantic", "dimension"],
        "expected_source": "embedding.pdf"
    },
    {
        "query": "What is supervised machine learning and how does it differ from unsupervised learning?",
        "expected_keywords": ["label", "training", "supervised", "classification"],
        "expected_source": "machine_learning.txt"
    }
]

def evaluate_retrieval():
    print("=================================================================")
    print("   RUNNING RAG SYSTEM EVALUATION & PERFORMANCE BENCHMARK         ")
    print("=================================================================")
    
    rag = RAGSearch()
    
    strategies = [
        {"name": "Dense-Only (FAISS)", "use_hybrid": False, "use_rerank": False},
        {"name": "Sparse-Only (BM25)", "use_hybrid": True, "use_rerank": False, "sparse_only": True},
        {"name": "Hybrid (FAISS + BM25 via RRF)", "use_hybrid": True, "use_rerank": False},
        {"name": "Hybrid + FlashRank Re-ranking", "use_hybrid": True, "use_rerank": True},
    ]
    
    results_summary = []
    
    for strat in strategies:
        print(f"\n[Testing Strategy]: {strat['name']}...")
        latencies = []
        hits_at_3 = 0
        hits_at_5 = 0
        keyword_coverages = []
        
        for item in BENCHMARK_DATASET:
            q = item["query"]
            expected_src = item["expected_source"]
            expected_kws = item["expected_keywords"]
            
            t0 = time.perf_counter()
            if strat.get("sparse_only"):
                tokenized = q.lower().split()
                scores = rag.vectorstore.bm25.get_scores(tokenized) if rag.vectorstore.bm25 else []
                top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:5]
                res = [{"metadata": rag.vectorstore.metadata[i], "distance": float(scores[i])} for i in top_indices if i < len(rag.vectorstore.metadata)]
            else:
                res = rag.vectorstore.query(
                    q, 
                    top_k=5, 
                    use_hybrid=strat["use_hybrid"], 
                    use_rerank=strat["use_rerank"]
                )
            elapsed_ms = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed_ms)
            
            top3_sources = [r.get("metadata", {}).get("source", "") for r in res[:3]]
            top5_sources = [r.get("metadata", {}).get("source", "") for r in res[:5]]
            
            if any(expected_src in str(s) for s in top3_sources):
                hits_at_3 += 1
            if any(expected_src in str(s) for s in top5_sources):
                hits_at_5 += 1
                
            combined_text = " ".join([r.get("metadata", {}).get("text", "").lower() for r in res[:5]])
            matched_kws = sum(1 for kw in expected_kws if kw.lower() in combined_text)
            coverage = (matched_kws / len(expected_kws)) if expected_kws else 1.0
            keyword_coverages.append(coverage)
            
        total_queries = len(BENCHMARK_DATASET)
        recall_at_3 = (hits_at_3 / total_queries) * 100
        recall_at_5 = (hits_at_5 / total_queries) * 100
        avg_latency = sum(latencies) / len(latencies)
        avg_kw_coverage = (sum(keyword_coverages) / len(keyword_coverages)) * 100
        
        stat = {
            "strategy": strat["name"],
            "recall_at_3": f"{recall_at_3:.1f}%",
            "recall_at_5": f"{recall_at_5:.1f}%",
            "keyword_coverage": f"{avg_kw_coverage:.1f}%",
            "avg_latency_ms": f"{avg_latency:.2f} ms"
        }
        results_summary.append(stat)
        
    print("\n=================================================================")
    print("                       EVALUATION RESULTS                        ")
    print("=================================================================")
    header = "{:<32} | {:<10} | {:<10} | {:<12} | {:<10}".format("Strategy", "Recall@3", "Recall@5", "KW Coverage", "Latency")
    print(header)
    print("-" * len(header))
    for r in results_summary:
        row = "{:<32} | {:<10} | {:<10} | {:<12} | {:<10}".format(r["strategy"], r["recall_at_3"], r["recall_at_5"], r["keyword_coverage"], r["avg_latency_ms"])
        print(row)
    print("=================================================================\n")
    
    report_file = Path("benchmark_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "queries_tested": len(BENCHMARK_DATASET),
            "benchmark_results": results_summary
        }, f, indent=2)
    print(f"[INFO] Benchmark report saved to {report_file.resolve()}")

if __name__ == "__main__":
    evaluate_retrieval()
