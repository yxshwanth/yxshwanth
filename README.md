<picture>
  <source media="(prefers-color-scheme: dark)" srcset="dark_mode.svg" />
  <source media="(prefers-color-scheme: light)" srcset="light_mode.svg" />
  <img alt="yxshwanth's GitHub profile" src="dark_mode.svg" />
</picture>

# Hi, I'm Yashwanth 👋

**Software Engineer** • MS CS @ CU Boulder (’26)  
Building high-throughput services, authorization systems, and data platforms.

---

## 🎓 Education

**University of Colorado Boulder** | Boulder, CO  
Master of Science in Computer Science | GPA: 3.9/4.0 | May 2026

**Chaitanya Bharathi Institute of Technology** | Hyderabad, India  
Bachelor of Engineering, AI & Data Science | GPA: 8.7/10.0 | May 2024

---

## 🛠️ Tech Stack

**Languages:**
![Go](https://img.shields.io/badge/Go-00ADD8?style=flat&logo=go&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white)
![Java](https://img.shields.io/badge/Java-ED8B00?style=flat&logo=java&logoColor=white)
![SQL](https://img.shields.io/badge/SQL-4479A1?style=flat&logo=postgresql&logoColor=white)
![C++](https://img.shields.io/badge/C++-00599C?style=flat&logo=c%2B%2B&logoColor=white)

**Distributed Systems:**
- Kafka, gRPC, Protobuf, Redis, REST APIs, OAuth2, Event-Driven Architecture, OpenTelemetry

**Cloud & Infrastructure:**
- AWS (ECS, Lambda, S3, SQS, DynamoDB), Docker, Kubernetes, Terraform, CI/CD (Jenkins, GitHub Actions)

**Databases:**
- PostgreSQL, CockroachDB, Neo4j, Redis, MongoDB, BigQuery, DuckDB

**AI/ML & Observability:**
- LangGraph, LangChain, Ollama, RAG Architectures, Sentence-transformers, Prometheus, Grafana, Jaeger

---

## 💼 Experience


### Software Engineer (Full-time Internship) @ IntelleWings (FinTech)
**July 2023 – June 2024** | Chandigarh, India

- Architected an asynchronous fraud detection pipeline on AWS ECS processing 100K+ monthly events with sub-200ms P99 latency, leveraging SQS for buffering and Lambda for event processing, while implementing PgBouncer connection pooling to scale database capacity by 6x (300 → 1,800 connections) and eliminate connection exhaustion during 10x traffic spikes
- Optimized API throughput by 85% (800ms → 120ms) through 3-tier Redis caching with TTL-based invalidation, reducing PostgreSQL load by 70% for 50K+ daily user profile reads and maintaining P99 latency <150ms under peak load
- Reduced deployment time by 87% (2hr → 15min) by automating rollback capabilities in Jenkins CI/CD pipeline with health-check validation and canary deployments, enabling zero-downtime daily production releases

---

## 🚀 Featured Projects

### [Zenith: Distributed Authorization Engine](https://github.com/yxshwanth/Zenith)
**Go, CockroachDB, gRPC, Redis** | Sept 2025 – Dec 2025

Engineered Zanzibar-inspired ReBAC system in Go solving multi-tenancy authorization for 10K+ organizations, supporting recursive permission expansion with formal causal consistency proofs validated through Jepsen-style testing.

- Eliminated stale-read anomalies ("new enemy problem") by implementing HLC timestamp-based consistency tokens (Zookies) in gRPC metadata, ensuring linearizable permission checks across distributed CockroachDB clusters
- Achieved sub-10ms P95 latency for direct checks and <25ms for 3-level nested permissions across 100K+ relationships by combining Singleflight deduplication with LRU caching, reducing redundant graph traversals by 80%
- Increased throughput to 10K+ requests/sec using CockroachDB AS OF SYSTEM TIME for stale-consistent follower reads, reducing primary node load by 65% while maintaining strong consistency guarantees

### [LineageGraph: GraphRAG Data Lineage Engine](https://github.com/yxshwanth/LineageGraph)
**Python, PostgreSQL, LangGraph, FastAPI** | Aug 2025 – Dec 2025

Architected zero-cost GraphRAG pipeline integrating local LLM inference (Ollama/Mistral 7B) with 384-dim vector embeddings, achieving sub-200ms semantic search and <50ms graph traversal at depth=3 through LangGraph state machine orchestration.

- Eliminated LLM hallucination by implementing two-phase validation (semantic discovery + deterministic graph verification), achieving 70% node recall and 65% answer relevance by grounding agent reasoning in PostgreSQL recursive CTEs
- Deployed production-grade observability across 4 agent nodes and 6 specialized tools using OpenTelemetry distributed tracing with Jaeger, enabling root-cause analysis of agent decisions with <5ms instrumentation overhead

### [High-Concurrency Flash Sale System](https://github.com/yxshwanth/flash-sale-engine)
**Go, Kafka, Redis, Docker** | Oct 2025 – Nov 2025

Built a distributed microservices platform handling 1,000+ concurrent requests/sec for flash sales with <50ms P99 latency, using Kafka for event streaming and traffic decoupling across order, inventory, and payment services, while implementing sliding-window rate limiting and Prometheus/Grafana observability with real-time alerting.

- Guaranteed strict data consistency by implementing idempotency keys and atomic Redis Lua scripts for inventory management, eliminating race conditions during 1,000 RPS bursts through pessimistic locking and WATCH-based optimistic transactions
- Achieved 99.9% system availability during simulated 30-second payment outages using Circuit Breaker pattern and Dead Letter Queues with exponential backoff, enabling graceful degradation and automatic retry while reducing incident detection time by 60% through anomaly alerting

---

---

## 📊 GitHub Stats

![GitHub Stats](https://github-readme-stats.vercel.app/api?username=yxshwanth&show_icons=true&theme=radical&hide_border=true&bg_color=0D1117)

![Top Languages](https://github-readme-stats.vercel.app/api/top-langs/?username=yxshwanth&layout=compact&theme=radical&hide_border=true&bg_color=0D1117)

---

## 📫 Connect

- **Email:** [yama6766@colorado.edu](mailto:yama6766@colorado.edu)
- **Phone:** 303-949-7624
- **LinkedIn:** [linkedin.com/in/yashwanth-mali](https://linkedin.com/in/yashwanth-mali)
- **GitHub:** [github.com/yxshwanth](https://github.com/yxshwanth)
- **Location:** Boulder, CO

---

*Building scalable systems, one commit at a time.* ⚡
