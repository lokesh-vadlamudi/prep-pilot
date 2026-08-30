"""Immutable, side-effect-free catalog for the inference engineering course."""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Iterable


COURSE_KEY = "inference-engineering"
COURSE_VERSION = "2026.08.29"
VALID_PLATFORMS = frozenset({"dgx", "mac", "both", "optional_cloud"})
VALID_ARTIFACT_FORMATS = frozenset({"csv", "markdown"})
SOURCE_KINDS = frozenset({
    "section", "topic", "resource", "hands_on", "workplace_project", "workplace_task",
    "personal_project", "paper", "hardware", "routine",
})
EVIDENCE_SOURCE_KINDS = frozenset({
    "hands_on", "workplace_project", "workplace_task", "personal_project", "paper", "hardware", "routine",
})
_FORBIDDEN_COPY = re.compile(
    r"\b(?:xp|points?|streaks?|scores?|grades?|badges?|leaderboards?|percentages?|sm[- ]?2)\b",
    re.IGNORECASE,
)


class CatalogValidationError(ValueError):
    """Raised when static course content violates a catalog invariant."""


@dataclass(frozen=True, slots=True)
class SourceItem:
    id: str
    kind: str
    label: str
    module_id: str


@dataclass(frozen=True, slots=True)
class LabDescriptor:
    title: str
    platform: str
    steps: tuple[str, ...]
    verification: str
    safety: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CheckpointDescriptor:
    id: str
    prompts: tuple[str, ...]
    pass_condition: str


@dataclass(frozen=True, slots=True)
class OralDescriptor:
    id: str
    opening_prompt: str
    rubric: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CompletionEntry:
    source_id: str
    label: str


@dataclass(frozen=True, slots=True)
class ArtifactCompletionRule:
    id: str
    collection_field: str
    entry_id_field: str
    entry_value_field: str
    entries: tuple[CompletionEntry, ...]
    chosen_id_field: str | None = None
    evidence_field: str | None = None
    evidence_id_field: str | None = None
    evidence_value_field: str | None = None
    maximum_value_length: int = 2000


@dataclass(frozen=True, slots=True)
class ArtifactDescriptor:
    id: str
    title: str
    template_key: str
    output_format: str
    template_fields: tuple[str, ...]
    verification_rubric: tuple[str, ...]
    source_ids: tuple[str, ...]
    completion_rule: ArtifactCompletionRule | None = None


@dataclass(frozen=True, slots=True)
class SupplementAlias:
    """One audited exact alias for a global supplement concept."""

    id: str
    slug_alias: str
    title_alias: str
    module_id: str
    lesson_id: str
    source_id: str


@dataclass(frozen=True, slots=True)
class LegacyIdentity:
    """One exact, audited identity emitted by the legacy book importer."""

    id: str
    slug_prefix: str
    title_alias: str
    chapter_alias: str
    sequence: int
    module_id: str
    lesson_id: str
    source_id: str


@dataclass(frozen=True, slots=True)
class CourseModule:
    id: str
    order: int
    callsign: str
    title: str
    mission_brief: str
    prerequisites: tuple[str, ...]
    learning_objectives: tuple[str, ...]
    lesson_outline: tuple[str, ...]
    lab: LabDescriptor
    checkpoint: CheckpointDescriptor
    oral: OralDescriptor
    artifacts: tuple[ArtifactDescriptor, ...]
    source_ids: tuple[str, ...]
    debrief_prompt: str
    selection_rule: SelectionRule | None = None


@dataclass(frozen=True, slots=True)
class CourseCatalog:
    key: str
    version: str
    title: str
    audience: str
    modules: tuple[CourseModule, ...]
    source_manifest: tuple[SourceItem, ...]
    supplement_aliases: tuple[SupplementAlias, ...] = ()
    legacy_identities: tuple[LegacyIdentity, ...] = ()


@dataclass(frozen=True, slots=True)
class SelectionRule:
    minimum: int
    maximum: int
    options: tuple[str, ...]


# code, module, section label, checklist topics, named resources, hands-on items
_SECTION_DATA = (
    ("P1-1", "IC-01", "Transformer Architecture Internals", (
        ("TOKENIZATION", "BPE, SentencePiece, and tiktoken tokenization"),
        ("EMBEDDINGS", "Embedding layers and positional encoding"),
        ("SELF-ATTENTION", "Self-attention with Q, K, and V matrices"),
        ("MULTI-HEAD-ATTENTION", "Multi-head attention"),
        ("TRANSFORMER-BLOCK", "Feed-forward layers, layer norms, and residual connections"),
        ("ARCHITECTURE-FAMILIES", "Encoder-decoder and decoder-only architectures"),
        ("AUTOREGRESSIVE-LOOP", "Autoregressive next-token generation"),
    ), (
        ("TRANSFORMER-PAPER", "Attention Is All You Need paper"),
        ("THREE-BLUE-ONE-BROWN", "3Blue1Brown GPT explainer series"),
        ("ILLUSTRATED-TRANSFORMER", "The Illustrated Transformer"),
        ("KARPATHY-GPT", "Build GPT from scratch with Andrej Karpathy"),
        ("UMAR-JAMIL", "Umar Jamil transformer explainer videos"),
    ), (
        ("MINIMAL-TRANSFORMER", "Implement a minimal transformer in PyTorch"),
        ("FORWARD-PASS-TRACE", "Trace a complete forward pass to sampled token"),
    )),
    ("P1-2", "IC-02", "LLM Generation Deep Dive", (
        ("PREFILL-DECODE", "Prefill and decode phases"),
        ("KV-CACHE", "KV cache contents and growth"),
        ("SAMPLING", "Greedy, top-k, top-p, and temperature sampling"),
        ("STOP-CONDITIONS", "Stop conditions and EOS tokens"),
        ("CONTEXT-WINDOW", "Context windows and positional limits"),
        ("ROPE", "Rotary Position Embeddings"),
    ), (
        ("HF-GENERATION-SOURCE", "Hugging Face generation source"),
        ("INFERENCE-SURVEY", "Efficient inference survey"),
    ), (
        ("LOAD-SMALL-MODEL", "Load a small Hugging Face model"),
        ("TRACE-KV-SHAPES", "Print KV cache shapes during generation"),
        ("SEQUENCE-TIMING", "Measure generation time across sequence lengths"),
    )),
    ("P2-1", "IC-03", "vLLM", (
        ("INSTALL-SERVE", "Install and serve a model with vLLM"),
        ("PAGED-ATTENTION", "PagedAttention"),
        ("BATCHING", "Continuous and static batching"),
        ("SCHEDULER", "vLLM request scheduling"),
        ("OPENAI-API", "OpenAI-compatible API server internals"),
        ("CORE-PARAMETERS", "max_model_len, gpu_memory_utilization, and tensor_parallel_size"),
        ("BUILTIN-BENCHMARKS", "vLLM built-in benchmarking"),
    ), (
        ("VLLM-DOCS", "vLLM documentation"),
        ("PAGED-ATTENTION-PAPER", "PagedAttention paper"),
        ("SCHEDULER-SOURCE", "vLLM scheduler source"),
    ), (
        ("SERVE-8B-DGX", "Serve an 8B model on DGX Spark"),
        ("SERVE-LARGE-QUANTIZED", "Serve a hardware-compatible larger quantized model"),
        ("CONCURRENCY-BENCHMARK", "Benchmark throughput and latency across concurrency"),
        ("COMPARE-HF-GENERATE", "Compare vLLM with Hugging Face generate"),
    )),
    ("P2-2", "IC-04", "Serving Framework Survey", (
        ("TENSORRT-LLM", "TensorRT-LLM"),
        ("SGLANG-RADIX", "SGLang and RadixAttention"),
        ("TGI", "Text Generation Inference"),
        ("TRITON-SERVER", "Triton Inference Server"),
        ("LLAMA-CPP-GGML", "llama.cpp and GGML"),
        ("DECISION-CRITERIA", "Serving framework decision criteria"),
    ), (), (
        ("MULTI-FRAMEWORK-SERVE", "Serve one model with vLLM, TGI, and llama.cpp"),
        ("FRAMEWORK-COMPARISON", "Build a framework throughput, latency, memory, and setup comparison"),
        ("TENSORRT-BLACKWELL", "Evaluate TensorRT-LLM on compatible Blackwell hardware"),
    )),
    ("P3-1", "IC-05", "Quantization Theory", (
        ("PRECISION-LADDER", "FP32 to FP16 to INT8 to INT4 quantization"),
        ("DATA-TYPES", "FP32, FP16, BF16, FP8, INT8, and INT4 data types"),
        ("PTQ-QAT", "Post-training and quantization-aware training"),
        ("WEIGHT-ACTIVATION", "Weight-only and weight-activation quantization"),
        ("CALIBRATION", "Calibration datasets"),
        ("PERPLEXITY", "Perplexity as a quality measure"),
    ), (
        ("QUANTIZATION-SURVEY", "Neural-network quantization survey"),
        ("DETTMERS-ARTICLES", "Tim Dettmers quantization articles"),
        ("HF-QUANTIZATION-DOCS", "Hugging Face quantization documentation"),
    ), ()),
    ("P3-2", "IC-05", "Quantization in Practice", (
        ("GPTQ", "GPTQ"),
        ("AWQ", "Activation-Aware Weight Quantization"),
        ("GGUF", "GGUF quantization levels"),
        ("FP8", "FP8 quantization"),
        ("BITSANDBYTES", "BitsAndBytes"),
        ("AUTOAWQ-AUTOGPTQ", "AutoAWQ and AutoGPTQ"),
    ), (), (
        ("PREPARE-VARIANTS", "Prepare FP16, INT8, GPTQ INT4, and AWQ INT4 variants"),
        ("MEASURE-VARIANTS", "Measure model size, memory, throughput, and perplexity"),
        ("CHART-TRADEOFFS", "Chart quality, speed, and memory trade-offs"),
    )),
    ("P3-3", "IC-06", "Other Optimization Techniques", (
        ("SPECULATIVE-DECODE", "Speculative decoding"),
        ("KV-QUANTIZATION", "KV cache quantization"),
        ("FLASH-ATTENTION", "FlashAttention and FlashAttention 2"),
        ("SLIDING-WINDOW", "Sliding-window attention"),
        ("GQA-MQA", "Grouped Query and Multi-Query Attention"),
        ("PRUNING", "Structured and unstructured pruning"),
        ("DISTILLATION", "Knowledge distillation"),
    ), (), (
        ("SPECULATIVE-BENCHMARK", "Benchmark speculative decoding with a draft model"),
        ("ATTENTION-COMPARISON", "Compare attention paths under one workload"),
        ("KV-QUANTIZATION-EXPERIMENT", "Experiment with KV cache quantization in vLLM"),
    )),
    ("P4-1", "IC-07", "GPU Architecture for Inference Engineers", (
        ("GPU-CPU", "GPU and CPU matrix-math differences"),
        ("GPU-CORES-SMS", "CUDA cores, Tensor cores, and Streaming Multiprocessors"),
        ("MEMORY-HIERARCHY", "Registers, shared memory, L2 cache, and HBM"),
        ("ROOFLINE", "Memory bandwidth and the roofline model"),
        ("BANDWIDTH-BOUND", "Memory-bandwidth-bound LLM inference"),
        ("GPU-GENERATIONS", "Ampere, Hopper, and Blackwell generations"),
        ("GPU-SPECS", "GPU capacity, bandwidth, and Tensor core throughput"),
    ), (
        ("GO-BRRR", "Making Deep Learning Go Brrrr From First Principles"),
        ("CUDA-GUIDE", "NVIDIA CUDA programming guide architecture sections"),
        ("FLASH-GPU-BACKGROUND", "FlashAttention GPU performance background"),
    ), (
        ("NVIDIA-SMI", "Monitor inference with nvidia-smi"),
        ("PYTORCH-MEMORY", "Inspect allocation with torch.cuda.memory_summary"),
        ("MODEL-FIT", "Calculate whether a model and KV cache fit a target GPU"),
    )),
    ("P4-2", "IC-08", "Multi-GPU and Distributed Inference", (
        ("TENSOR-PARALLEL", "Tensor parallelism"),
        ("PIPELINE-PARALLEL", "Pipeline parallelism"),
        ("DATA-PARALLEL", "Data parallelism"),
        ("INTERCONNECTS", "NVLink, NVSwitch, and InfiniBand"),
        ("PARALLEL-SELECTION", "Tensor versus pipeline parallel selection"),
        ("NCCL", "NCCL collectives"),
    ), (), (
        ("DGX-LARGE-MODEL", "Serve a large model using DGX Spark unified memory"),
        ("A100-PLAN", "Plan an optional multi-GPU A100 exercise"),
        ("SCALING-MEASUREMENT", "Measure scaling across parallelism strategies"),
    )),
    ("P5-1", "IC-09", "Serving Infrastructure", (
        ("LOAD-BALANCING", "Inference replica load balancing"),
        ("AUTOSCALING-SIGNALS", "Autoscaling from queue, latency, and GPU signals"),
        ("QUEUE-PRIORITY", "Request queuing and priority scheduling"),
        ("STREAMING", "SSE and chunked streaming"),
        ("SERVICE-LIFECYCLE", "Health checks, graceful shutdown, and model loading"),
        ("MODEL-ROUTING", "A/B testing and model routing"),
        ("RATE-QUOTA", "Rate limiting and quota management"),
    ), (), (
        ("MULTI-REPLICA-SERVICE", "Build a multi-replica service behind a load balancer"),
        ("WORKLOAD-ROUTING", "Route requests by workload needs"),
        ("LOAD-GENERATOR", "Exercise autoscaling with a load generator"),
    )),
    ("P5-2", "IC-10", "Kubernetes for GPU Workloads", (
        ("GPU-SCHEDULING", "Kubernetes GPU scheduling and device plugin"),
        ("RESOURCE-REQUESTS", "GPU, CPU, and memory requests and limits"),
        ("NODE-PLACEMENT", "GPU node pools, taints, and tolerations"),
        ("GPU-OPERATOR", "NVIDIA GPU Operator"),
        ("MODEL-STORAGE", "Object storage, model cache, and persistent volumes"),
        ("CUSTOM-HPA", "Horizontal autoscaling with custom metrics"),
    ), (), (
        ("DEPLOY-VLLM", "Deploy vLLM on Kubernetes with GPU support"),
        ("QUEUE-AUTOSCALE", "Autoscale from request queue length"),
        ("ROLLING-UPDATE", "Perform a rolling model update with rollback evidence"),
    )),
    ("P5-3", "IC-11", "Observability and Cost Optimization", (
        ("SERVICE-METRICS", "TTFT, TPOT, throughput, and queue depth"),
        ("PROMETHEUS-GRAFANA", "Prometheus and Grafana inference dashboards"),
        ("COST-PER-UNIT", "Cost per token and request"),
        ("GPU-UTILIZATION", "GPU utilization optimization"),
        ("BATCHING-TRADEOFFS", "Batching throughput and latency trade-offs"),
        ("SPOT-BATCH", "Spot and preemptible batch inference"),
        ("CACHING", "Semantic, prompt, and prefix caching"),
    ), (), (
        ("GRAFANA-DASHBOARD", "Build a Grafana dashboard for vLLM metrics"),
        ("SEMANTIC-CACHE", "Implement and measure a semantic cache"),
        ("COST-CALCULATION", "Calculate cost per token across quantization and batch settings"),
    )),
    ("P6-1", "IC-12", "Cutting Edge", (
        ("MOE", "Mixture-of-Experts inference"),
        ("PREFIX-RADIX", "Prefix caching and RadixAttention"),
        ("DISAGGREGATED", "Disaggregated prefill and decode"),
        ("LORA-ADAPTERS", "LoRA multi-adapter serving"),
        ("STRUCTURED-GENERATION", "Structured and constrained generation"),
        ("MULTIMODAL", "Multimodal inference"),
        ("EDGE", "Edge and on-device inference"),
        ("TRITON-KERNELS", "Custom kernels with the Triton language"),
    ), (), ()),
    ("P6-2", "IC-13", "Stay Current", (
        ("FOLLOW-RELEASES", "Track vLLM releases, NVIDIA material, and LocalLLaMA"),
        ("READ-PAPERS", "Read new papers monthly"),
        ("WATCH-CONFERENCES", "Watch MLSys, NeurIPS systems, and NVIDIA GTC"),
        ("FOLLOW-RESEARCHERS", "Follow key inference researchers"),
        ("JOIN-COMMUNITIES", "Join relevant inference communities"),
    ), (), ()),
)


_EXTRA_SOURCE_DATA = (
    ("SRC-WP-01", "workplace_project", "Self-hosted model serving workplace project", "IC-14"),
    ("SRC-WP-01-TASK-AUDIT-USAGE", "workplace_task", "Audit current LLM API usage by workload complexity", "IC-14"),
    ("SRC-WP-01-TASK-DEPLOY-OPEN-MODEL", "workplace_task", "Deploy an open model on internal infrastructure with vLLM", "IC-14"),
    ("SRC-WP-01-TASK-COMPARE-QUALITY", "workplace_task", "Compare hosted and self-hosted output quality", "IC-14"),
    ("SRC-WP-01-TASK-COMPARE-COST", "workplace_task", "Compare hosted and self-hosted cost per token", "IC-14"),
    ("SRC-WP-01-TASK-ROUTE-BY-COMPLEXITY", "workplace_task", "Route simple use cases locally and retain complex hosted use cases", "IC-14"),
    ("SRC-WP-01-TASK-DOCUMENT-OUTCOMES", "workplace_task", "Document before and after cost, latency, and quality outcomes", "IC-14"),
    ("SRC-WP-02", "workplace_project", "Internal LLM gateway workplace project", "IC-14"),
    ("SRC-WP-02-TASK-BUILD-PROXY", "workplace_task", "Build an API proxy across hosted and self-hosted backends", "IC-14"),
    ("SRC-WP-02-TASK-LOG-REQUESTS", "workplace_task", "Log tokens, latency, model, caller, and request cost", "IC-14"),
    ("SRC-WP-02-TASK-BUILD-DASHBOARD", "workplace_task", "Build team cost, latency percentile, throughput, and error dashboards", "IC-14"),
    ("SRC-WP-02-TASK-ENFORCE-QUOTAS", "workplace_task", "Enforce team rate limits and quotas", "IC-14"),
    ("SRC-WP-02-TASK-ADD-SEMANTIC-CACHE", "workplace_task", "Add semantic caching and measure hit rate and savings", "IC-14"),
    ("SRC-WP-02-TASK-ADD-SMART-ROUTING", "workplace_task", "Add workload-aware routing between economical and capable models", "IC-14"),
    ("SRC-WP-03", "workplace_project", "Private self-hosted RAG workplace project", "IC-14"),
    ("SRC-WP-03-TASK-SETUP-VECTOR-STORE", "workplace_task", "Set up a vector store for internal documents", "IC-14"),
    ("SRC-WP-03-TASK-BUILD-RETRIEVAL", "workplace_task", "Build chunking, embedding, and similarity retrieval", "IC-14"),
    ("SRC-WP-03-TASK-SERVE-LOCAL-MODEL", "workplace_task", "Serve the generation model locally with vLLM", "IC-14"),
    ("SRC-WP-03-TASK-BUILD-END-TO-END", "workplace_task", "Build the private query, retrieval, and generation path", "IC-14"),
    ("SRC-WP-03-TASK-OPTIMIZE-PIPELINE", "workplace_task", "Optimize embedding precision, generation precision, and response latency", "IC-14"),
    ("SRC-WP-03-TASK-EVALUATE-RAG", "workplace_task", "Evaluate retrieval accuracy, generation quality, and hallucination behavior", "IC-14"),
    ("SRC-WP-04", "workplace_project", "Inference optimization sprint workplace project", "IC-14"),
    ("SRC-WP-04-TASK-PROFILE-BASELINE", "workplace_task", "Profile GPU utilization, memory, and batching efficiency", "IC-14"),
    ("SRC-WP-04-TASK-APPLY-QUANTIZATION", "workplace_task", "Apply reduced precision and measure quality and speed changes", "IC-14"),
    ("SRC-WP-04-TASK-TUNE-BATCHING", "workplace_task", "Tune continuous batching for the latency and throughput objective", "IC-14"),
    ("SRC-WP-04-TASK-ADD-PROMPT-CACHING", "workplace_task", "Add prompt or prefix caching for repeated patterns", "IC-14"),
    ("SRC-WP-04-TASK-OPTIMIZE-KV-CACHE", "workplace_task", "Apply a supported KV cache optimization", "IC-14"),
    ("SRC-WP-04-TASK-DOCUMENT-DELTAS", "workplace_task", "Document before and after measurements and decision rationale", "IC-14"),
    ("SRC-PP-01", "personal_project", "Inference benchmark suite personal project", "IC-15"),
    ("SRC-PP-02", "personal_project", "Optimized large-model pipeline personal project", "IC-15"),
    ("SRC-PP-03", "personal_project", "Speculative decoding benchmark personal project", "IC-15"),
    ("SRC-PP-04", "personal_project", "Cross-platform inference comparison personal project", "IC-15"),
    ("SRC-PAPER-01", "paper", "Attention Is All You Need", "IC-01"),
    ("SRC-PAPER-02", "paper", "FlashAttention paper", "IC-06"),
    ("SRC-PAPER-03", "paper", "PagedAttention paper", "IC-03"),
    ("SRC-PAPER-04", "paper", "GPTQ paper", "IC-05"),
    ("SRC-PAPER-05", "paper", "AWQ paper", "IC-05"),
    ("SRC-PAPER-06", "paper", "Speculative Decoding paper", "IC-06"),
    ("SRC-PAPER-07", "paper", "Efficiently Scaling Transformer Inference paper", "IC-08"),
    ("SRC-PAPER-08", "paper", "SGLang paper", "IC-04"),
    ("SRC-PAPER-09", "paper", "Efficient LLM Inference survey", "IC-13"),
    ("SRC-HW-DGX-01", "hardware", "DGX Spark Blackwell GPU", "IC-00"),
    ("SRC-HW-DGX-02", "hardware", "DGX Spark unified memory capacity", "IC-00"),
    ("SRC-HW-DGX-03", "hardware", "DGX Spark model-size envelope", "IC-00"),
    ("SRC-HW-DGX-04", "hardware", "DGX Spark ConnectX networking", "IC-00"),
    ("SRC-HW-DGX-05", "hardware", "Run a quantized large model locally", "IC-00"),
    ("SRC-HW-DGX-06", "hardware", "Run an 8B model at full precision", "IC-00"),
    ("SRC-HW-DGX-07", "hardware", "Compare quantization variants with memory headroom", "IC-00"),
    ("SRC-HW-DGX-08", "hardware", "Serve draft and target models together", "IC-00"),
    ("SRC-HW-DGX-09", "hardware", "Build portfolio experiments locally", "IC-00"),
    ("SRC-HW-DGX-10", "hardware", "Explore LoRA multi-adapter serving", "IC-12"),
    ("SRC-HW-DGX-11", "hardware", "Verify NVIDIA AI Enterprise stack", "IC-00"),
    ("SRC-HW-DGX-12", "hardware", "Configure NVIDIA Container Toolkit", "IC-00"),
    ("SRC-HW-DGX-13", "hardware", "Install a Blackwell-compatible vLLM build", "IC-00"),
    ("SRC-HW-DGX-14", "hardware", "Verify CUDA version and driver compatibility", "IC-00"),
    ("SRC-HW-DGX-15", "hardware", "Inspect nvidia-smi output", "IC-00"),
    ("SRC-HW-DGX-16", "hardware", "Set up Jupyter Lab", "IC-00"),
    ("SRC-HW-MAC-01", "hardware", "Mac mini M4 chip", "IC-00"),
    ("SRC-HW-MAC-02", "hardware", "Mac mini unified-memory envelope", "IC-00"),
    ("SRC-HW-MAC-03", "hardware", "Mac mini edge-inference role", "IC-00"),
    ("SRC-HW-MAC-04", "hardware", "Run llama.cpp and MLX on Apple Silicon", "IC-00"),
    ("SRC-HW-MAC-05", "hardware", "Compare CUDA and Metal inference", "IC-04"),
    ("SRC-HW-MAC-06", "hardware", "Exercise edge deployment on Mac", "IC-12"),
    ("SRC-HW-MAC-07", "hardware", "Use Mac as a DGX inference client", "IC-00"),
    ("SRC-HW-MAC-08", "hardware", "Install Metal-accelerated llama.cpp", "IC-00"),
    ("SRC-HW-MAC-09", "hardware", "Install MLX and mlx-lm", "IC-00"),
    ("SRC-HW-MAC-10", "hardware", "Run a quantized 7-8B Mac baseline", "IC-00"),
    ("SRC-HW-MAC-11", "hardware", "Use Mac as daily driver for reading, coding, and light experiments", "IC-00"),
    ("SRC-HW-CLOUD-01", "hardware", "Optional cloud multi-GPU practice", "IC-08"),
    ("SRC-HW-PLAN-01", "hardware", "Prefer DGX and Mac before paid cloud", "IC-00"),
    ("SRC-ROUTINE-01", "routine", "Weekday study and hands-on routine", "IC-16"),
    ("SRC-ROUTINE-02", "routine", "Saturday portfolio project session", "IC-16"),
    ("SRC-ROUTINE-03", "routine", "Sunday paper and community review", "IC-16"),
)


def _section_sources() -> Iterable[SourceItem]:
    for code, module_id, section, topics, resources, hands_on in _SECTION_DATA:
        yield SourceItem(f"SRC-{code}-SECTION", "section", section, module_id)
        for stable_id, label in topics:
            yield SourceItem(f"SRC-{code}-TOPIC-{stable_id}", "topic", label, module_id)
        for stable_id, label in resources:
            yield SourceItem(f"SRC-{code}-RESOURCE-{stable_id}", "resource", label, module_id)
        for stable_id, label in hands_on:
            yield SourceItem(f"SRC-{code}-HANDS-{stable_id}", "hands_on", label, module_id)


SOURCE_MANIFEST = tuple(_section_sources()) + tuple(SourceItem(*row) for row in _EXTRA_SOURCE_DATA)


def _completion_entries(source_ids: tuple[str, ...]) -> tuple[CompletionEntry, ...]:
    by_id = {source.id: source for source in SOURCE_MANIFEST}
    return tuple(CompletionEntry(source_id, by_id[source_id].label) for source_id in source_ids)


WORKPLACE_PROJECT_IDS = ("SRC-WP-01", "SRC-WP-02", "SRC-WP-03", "SRC-WP-04")
PAPER_SOURCE_IDS = tuple(f"SRC-PAPER-{index:02d}" for index in range(1, 10))

_COMPLETION_RULES = {
    "IC-14": ArtifactCompletionRule(
        id="COMPLETION-WORKPLACE-PROJECT-SELECTION",
        collection_field="project_scopes",
        entry_id_field="project_id",
        entry_value_field="scope",
        entries=_completion_entries(WORKPLACE_PROJECT_IDS),
        chosen_id_field="chosen_project_id",
        evidence_field="selected_proposal",
        evidence_id_field="project_id",
        evidence_value_field="evidence",
    ),
    "IC-16": ArtifactCompletionRule(
        id="COMPLETION-ORDERED-PAPER-NOTES",
        collection_field="paper_notes",
        entry_id_field="paper_id",
        entry_value_field="note",
        entries=_completion_entries(PAPER_SOURCE_IDS),
    ),
}


_ARTIFACT_OVERRIDES = {
    "IC-03": (("BENCHMARK-DATA", "benchmark-data", "csv", "Benchmark CSV and schema",
        ("run_id", "model", "framework", "concurrency", "input_tokens", "output_tokens", "ttft_ms", "tpot_ms", "throughput", "memory"), None),),
    "IC-04": (("FRAMEWORK-MATRIX", "framework-decision-matrix", "markdown", "Serving framework decision matrix",
        ("framework", "supported_platform", "workload_fit", "latency", "throughput", "memory", "operational_notes", "decision"), None),),
    "IC-05": (("QUANTIZATION-CHART", "quality-speed-memory-chart", "csv", "Quality, speed, and memory chart",
        ("variant", "format", "calibration", "memory", "throughput", "quality_measure", "decision"), None),),
    "IC-06": (("EXPERIMENT-MEMO", "experiment-memo", "markdown", "Optimization experiment memo",
        ("hypothesis", "control", "change", "measurements", "limitations", "decision"), None),),
    "IC-07": (("MODEL-FIT", "model-fit-worksheet", "markdown", "Model-fit and roofline worksheet",
        ("hardware", "parameter_bytes", "cache_assumptions", "capacity_result", "bottleneck", "evidence"), None),),
    "IC-08": (("SCALING-REPORT", "scaling-report", "markdown", "Topology and scaling report",
        ("topology", "strategy", "baseline", "scaled_result", "efficiency", "cost_boundary"), None),),
    "IC-09": (("GATEWAY-ADR", "gateway-adr", "markdown", "Inference gateway architecture decision record",
        ("context", "decision", "architecture", "routing_rules", "failure_drill", "consequences", "rollback"), None),),
    "IC-10": (("K8S-ROLLBACK", "kubernetes-rollback-record", "markdown", "Kubernetes rollout and rollback record",
        ("manifests_ref", "preflight", "rollout_steps", "observations", "rollback_trigger", "rollback_steps", "result"), None),),
    "IC-11": (
        ("GRAFANA-CHECKLIST", "grafana-dashboard-checklist", "markdown", "Grafana dashboard checklist",
            ("data_source", "ttft_panel", "tpot_panel", "throughput_panel", "queue_panel", "gpu_panel", "alerts", "validation"),
            ("SRC-P5-3-HANDS-GRAFANA-DASHBOARD",)),
        ("COST-MODEL", "cost-model", "csv", "Inference cost model",
            ("variant", "batch", "tokens", "runtime", "hardware_cost", "cache_hit_rate", "cost_per_token", "decision"),
            ("SRC-P5-3-HANDS-SEMANTIC-CACHE", "SRC-P5-3-HANDS-COST-CALCULATION")),
    ),
    "IC-14": (("WORKPLACE-PROPOSAL", "workplace-proposal", "markdown", "Workplace proposal",
        ("problem", "baseline", "proposal", "evaluation", "privacy", "operational_risk", "rollback"), None),),
    "IC-15": (("CAPSTONE-README", "capstone-readme", "markdown", "Capstone README",
        ("purpose", "setup", "dataset", "reproduction", "results", "charts", "limitations", "next_projects"), None),),
    "IC-16": (("PAPER-NOTES", "paper-notes", "markdown", "Paper notes and learning routine",
        ("citation", "claim", "mechanism", "evidence", "lab_connection", "open_question", "routine_update"), None),),
}


def _source_ids(module_id: str) -> tuple[str, ...]:
    return tuple(item.id for item in SOURCE_MANIFEST if item.module_id == module_id)


def _evidence_ids(module_id: str) -> tuple[str, ...]:
    return tuple(
        item.id for item in SOURCE_MANIFEST
        if item.module_id == module_id and item.kind in EVIDENCE_SOURCE_KINDS
    )


def _artifact_descriptors(
    module_id: str, fallback_title: str, fallback_fields: tuple[str, ...]
) -> tuple[ArtifactDescriptor, ...]:
    specs = _ARTIFACT_OVERRIDES.get(module_id, (
        ("ARTIFACT", f"{module_id.lower()}-artifact", "markdown", fallback_title, fallback_fields, None),
    ))
    return tuple(
        ArtifactDescriptor(
            id=f"{module_id}-ARTIFACT-{suffix}" if suffix != "ARTIFACT" else f"{module_id}-ARTIFACT",
            title=title,
            template_key=template_key,
            output_format=output_format,
            template_fields=fields,
            verification_rubric=(
                "Reproducible inputs are present.",
                "Observed results are separated from inference.",
                "A next decision is stated.",
            ),
            source_ids=source_ids if source_ids is not None else _evidence_ids(module_id),
            completion_rule=_COMPLETION_RULES.get(module_id),
        )
        for suffix, template_key, output_format, title, fields, source_ids in specs
    )


def _module(
    module_id: str,
    callsign: str,
    title: str,
    brief: str,
    objectives: tuple[str, ...],
    outline: tuple[str, ...],
    lab_title: str,
    platform: str,
    lab_steps: tuple[str, ...],
    artifact_title: str,
    artifact_fields: tuple[str, ...],
    prerequisites: tuple[str, ...] = (),
    selection_rule: SelectionRule | None = None,
) -> CourseModule:
    order = int(module_id.removeprefix("IC-"))
    return CourseModule(
        id=module_id, order=order, callsign=callsign, title=title, mission_brief=brief,
        prerequisites=prerequisites, learning_objectives=objectives, lesson_outline=outline,
        lab=LabDescriptor(
            title=lab_title, platform=platform, steps=lab_steps,
            verification="Record commands, versions, inputs, and observed output; explain anomalies.",
            safety=("Use non-production models and data.", "Review every command before running it outside PrepPilot."),
        ),
        checkpoint=CheckpointDescriptor(
            id=f"{module_id}-CHECKPOINT",
            prompts=("Explain the governing mechanism in your own words.", "Defend the key trade-off using lab evidence."),
            pass_condition="Every required check is supported by the saved artifact and a defensible explanation.",
        ),
        oral=OralDescriptor(
            id=f"{module_id}-ORAL",
            opening_prompt=f"Walk me through {title.lower()} as if you were diagnosing a production design.",
            rubric=("Names the mechanism accurately.", "Uses measured evidence.", "Explains trade-offs and failure modes."),
        ),
        artifacts=_artifact_descriptors(module_id, artifact_title, artifact_fields),
        source_ids=_source_ids(module_id),
        debrief_prompt="What changed in your mental model, and what evidence would change your decision next time?",
        selection_rule=selection_rule,
    )


COURSE_MODULES = (
    _module("IC-00", "HANGAR", "Hangar Check",
        "Prepare both machines as observable lab platforms before changing model behavior.",
        ("Identify each platform's useful limits.", "Capture a reproducible software and hardware baseline."),
        ("DGX Spark architecture and local safety", "Mac Metal and MLX baseline", "Optional cloud boundary"),
        "Bring both rigs online", "both",
        ("Inventory DGX drivers, CUDA, containers, vLLM, and monitoring.", "Inventory Mac hardware, llama.cpp, MLX, and a quantized baseline.", "Test the Mac as a client of a DGX endpoint."),
        "Hardware and software baseline", ("platform", "versions", "model", "command", "observed_result")),
    _module("IC-01", "BLACK BOX", "Open the Black Box",
        "Trace one token through a transformer so later optimization choices have a concrete target.",
        ("Explain each transformer stage.", "Relate attention tensors to autoregressive generation."),
        ("Tokens and embeddings", "Attention and residual blocks", "Decoder-only generation"),
        "Build and trace a tiny transformer", "both",
        ("Implement a minimal transformer in PyTorch.", "Capture tensor shapes through one forward pass.", "Trace logits through token sampling."),
        "Annotated transformer trace", ("implementation_ref", "tensor_trace", "explanation"), ("IC-00",)),
    _module("IC-02", "DECODE", "Race the Decode Loop",
        "Instrument prefill and decode to expose the cache and sampling work hidden by a generation API.",
        ("Distinguish prefill from decode.", "Explain cache growth, sampling controls, context limits, and RoPE."),
        ("Generation phases", "KV cache", "Sampling and stopping", "Context and rotation"),
        "Measure a small generation loop", "both",
        ("Load a small model.", "Log cache shapes at each step.", "Compare timings across sequence lengths and sampling settings."),
        "Decode timing notebook", ("model", "inputs", "cache_shapes", "timings", "interpretation"), ("IC-01",)),
    _module("IC-03", "TOWER", "Tower Control: vLLM",
        "Operate vLLM as a measured serving system rather than a black-box endpoint.",
        ("Explain PagedAttention and continuous batching.", "Tune core capacity and scheduling parameters."),
        ("PagedAttention", "Scheduler and batching", "API server", "Benchmark design"),
        "Benchmark vLLM on DGX", "dgx",
        ("Serve an 8B model.", "Serve a compatible larger quantized model.", "Sweep concurrency and compare with Hugging Face generation."),
        "vLLM benchmark report", ("model_config", "workload", "ttft", "tpot", "throughput", "memory", "comparison"), ("IC-02",)),
    _module("IC-04", "SHOOTOUT", "Engine Shootout",
        "Choose a serving framework from evidence gathered on DGX and Mac rather than brand familiarity.",
        ("Describe the major serving engines.", "Select an engine from workload and hardware constraints."),
        ("TensorRT-LLM", "SGLang and TGI", "Triton server", "llama.cpp and GGML"),
        "Run a cross-engine comparison", "both",
        ("Hold model and workload constant.", "Run each compatible engine.", "Document incompatibilities instead of hiding them."),
        "Serving framework decision matrix", ("framework", "platform", "latency", "throughput", "memory", "setup_notes", "decision"), ("IC-03",)),
    _module("IC-05", "PRECISION", "Precision Heist",
        "Reduce model precision under controlled quality, memory, and latency observations.",
        ("Explain quantization formats and calibration.", "Choose a practical quantizer from workload needs."),
        ("Numeric formats", "PTQ and QAT", "Calibration and perplexity", "GPTQ, AWQ, GGUF, and BitsAndBytes"),
        "Compare quantized variants", "dgx",
        ("Prepare full-precision and reduced-precision variants.", "Measure memory, throughput, and perplexity on one dataset.", "Chart the trade-offs."),
        "Quality, speed, and memory chart", ("variant", "format", "calibration", "memory", "throughput", "quality_measure", "decision"), ("IC-03",)),
    _module("IC-06", "FAST PATH", "The Fast Path",
        "Isolate advanced decoding and attention optimizations so their benefits are measured, not assumed.",
        ("Explain speculative decoding and attention kernels.", "Separate algorithmic benefit from workload noise."),
        ("Draft-model verification", "KV cache formats", "Attention kernels and windows", "GQA, MQA, pruning, and distillation"),
        "Run controlled optimization experiments", "dgx",
        ("Benchmark one draft and target pair.", "Compare attention paths under the same workload.", "Toggle KV cache format and record effects."),
        "Optimization experiment memo", ("hypothesis", "control", "change", "measurements", "limitations", "decision"), ("IC-05",)),
    _module("IC-07", "METAL", "Read the Metal",
        "Connect model behavior to GPU compute, memory hierarchy, and bandwidth limits.",
        ("Explain the GPU execution hierarchy.", "Estimate model and cache fit before loading."),
        ("Cores and multiprocessors", "Memory hierarchy", "Roofline reasoning", "GPU generation trade-offs"),
        "Profile memory and utilization", "dgx",
        ("Capture nvidia-smi during inference.", "Inspect PyTorch memory allocation.", "Calculate parameter and KV cache capacity."),
        "Model-fit and roofline worksheet", ("hardware", "parameter_bytes", "cache_assumptions", "capacity_result", "bottleneck", "evidence"), ("IC-03",)),
    _module("IC-08", "GIANT", "Split the Giant",
        "Design a distributed serving topology that respects model shape, interconnect, and scaling loss.",
        ("Compare tensor, pipeline, and data parallelism.", "Reason about topology and collectives."),
        ("Parallel strategies", "Interconnects", "NCCL", "Unified memory and optional multi-GPU cloud"),
        "Measure a parallel deployment plan", "optional_cloud",
        ("Characterize DGX unified-memory behavior.", "Design an optional A100 topology.", "Measure or model scaling efficiency."),
        "Topology and scaling report", ("topology", "strategy", "baseline", "scaled_result", "efficiency", "cost_boundary"), ("IC-07",)),
    _module("IC-09", "SERVICE", "Keep the Service Flying",
        "Turn a model endpoint into a resilient service with explicit traffic and failure behavior.",
        ("Design routing, queuing, and streaming.", "Exercise health, shutdown, capacity, and quota behavior."),
        ("Replica routing", "Queues and autoscaling", "Streaming lifecycle", "Health, model routing, and quotas"),
        "Load-test a multi-replica gateway", "both",
        ("Place replicas behind a load balancer.", "Route requests by workload needs.", "Generate load and trigger a controlled failure."),
        "Inference gateway architecture record", ("architecture", "routing_rules", "load_profile", "failure_drill", "observations", "rollback"), ("IC-03",)),
    _module("IC-10", "FLEET", "GPU Fleet Ops",
        "Deploy GPU inference with reversible Kubernetes scheduling and rollout controls.",
        ("Configure GPU resources and nodes.", "Design storage, autoscaling, and safe model swaps."),
        ("Device plugin and GPU Operator", "Resources and node placement", "Model storage", "Custom-metric autoscaling and rollout"),
        "Rehearse a GPU workload rollout", "optional_cloud",
        ("Validate manifests without touching production.", "Exercise queue-based autoscaling in a lab cluster.", "Perform rollout and rollback rehearsal."),
        "Kubernetes rollout record", ("manifests_ref", "validation", "autoscaling_evidence", "rollout", "rollback", "open_risks"), ("IC-09",)),
    _module("IC-11", "BOTTLENECK", "Find the Bottleneck",
        "Make latency, capacity, and cost visible enough to choose the next optimization.",
        ("Define inference service indicators.", "Connect cache and batching choices to cost."),
        ("Latency and throughput signals", "Prometheus and Grafana", "Cost model", "Caching and capacity trade-offs"),
        "Build an observability and cost view", "dgx",
        ("Export vLLM metrics to a dashboard.", "Measure a semantic cache.", "Compare cost across precision and batch settings."),
        "Dashboard and cost model", ("dashboard_ref", "metric_definitions", "cache_results", "cost_inputs", "cost_result", "decision"), ("IC-09",)),
    _module("IC-12", "FRONTIER", "Frontier Recon",
        "Investigate selected frontier techniques deeply while retaining a decision map for the full menu.",
        ("Explain the frontier option set.", "Design controlled experiments for selected options."),
        ("MoE and disaggregation", "Prefix and adapter serving", "Structured and multimodal generation", "Edge inference and custom kernels"),
        "Run selected frontier experiments", "both",
        ("Choose techniques from explicit constraints.", "Record one experiment memo per choice.", "Defend why the remaining options were deferred."),
        "Frontier experiment portfolio", ("option_map", "selected_experiments", "measurements", "deferred_rationale", "next_probe"),
        ("IC-06", "IC-08"),
        SelectionRule(
            minimum=2,
            maximum=3,
            options=(
                "SRC-P6-1-TOPIC-MOE", "SRC-P6-1-TOPIC-PREFIX-RADIX", "SRC-P6-1-TOPIC-DISAGGREGATED",
                "SRC-P6-1-TOPIC-LORA-ADAPTERS", "SRC-P6-1-TOPIC-STRUCTURED-GENERATION",
                "SRC-P6-1-TOPIC-MULTIMODAL", "SRC-P6-1-TOPIC-EDGE", "SRC-P6-1-TOPIC-TRITON-KERNELS",
            ),
        )),
    _module("IC-13", "SIGNAL", "Signal Watch",
        "Build a repeatable filter for releases, papers, talks, researchers, and communities.",
        ("Distinguish durable mechanisms from announcements.", "Capture a recurring evidence-review practice."),
        ("Release feeds", "Paper discovery", "Conference talks", "Researchers and communities"),
        "Produce a current-signal briefing", "both",
        ("Select one release and one paper.", "Summarize claims and primary evidence.", "Record a follow-up experiment."),
        "Inference watchlist", ("source", "claim", "primary_evidence", "relevance", "follow_up"), ("IC-03",)),
    _module("IC-14", "WORKPLACE", "Workplace Flight Plans",
        "Translate inference skills into four business-shaped proposals without assuming permission to deploy.",
        ("Frame cost, privacy, reliability, and evaluation outcomes.", "Bound an experiment before requesting organizational change."),
        ("Self-hosted serving", "Observable gateway", "Private RAG", "Optimization sprint"),
        "Draft an executable workplace proposal", "both",
        ("Scope all four options.", "Select one from available evidence.", "Write success, safety, and rollback criteria."),
        "Workplace proposal set", ("option", "problem", "baseline", "proposal", "evaluation", "privacy", "rollback"), ("IC-09", "IC-11")),
    _module("IC-15", "RUNWAY", "Portfolio Runway",
        "Convert measured work into a reproducible capstone and credible plans for the remaining portfolio options.",
        ("Package code, data, charts, and decisions.", "Write claims that are supported by reproducible evidence."),
        ("Benchmark suite", "Optimized large-model pipeline", "Speculative decode study", "Cross-platform comparison"),
        "Ship one evidence-backed capstone", "both",
        ("Select one capstone.", "Publish reproducible results and limitations.", "Outline the remaining projects."),
        "Capstone README and results package", ("repository_ref", "setup", "dataset", "results", "charts", "limitations", "next_projects"), ("IC-12",)),
    _module("IC-16", "PAPER TRAIL", "Paper Trail and Cadence",
        "Close the course with an ordered reading trail and a sustainable learner-owned routine.",
        ("Connect foundational papers to lab observations.", "Plan recurring study without artificial engagement mechanics."),
        ("Ordered paper trail", "Weekday study and lab practice", "Saturday project work", "Sunday paper and community review"),
        "Build the ongoing learning system", "both",
        ("Annotate the paper queue.", "Choose a repeatable weekly rhythm.", "Define how new evidence updates prior decisions."),
        "Reading notes and learning routine", ("paper_notes", "weekly_routine", "update_trigger", "next_experiment"), ("IC-13", "IC-15")),
)


# Closed by default: run_supplement.py generates slugs dynamically and the inspected
# repository database contains no supplement rows. Add only audited exact identities.
SUPPLEMENT_ALIASES: tuple[SupplementAlias, ...] = ()

# Closed by default: run_ingest.py proves only the course slug prefix and sequence
# base; its model-authored section titles do not prove an exact catalog identity.
LEGACY_IDENTITIES: tuple[LegacyIdentity, ...] = ()


COURSE = CourseCatalog(
    key=COURSE_KEY,
    version=COURSE_VERSION,
    title="Inference Flight School: Token to Traffic",
    audience="Experienced full-stack developer building practical inference systems",
    modules=COURSE_MODULES,
    source_manifest=SOURCE_MANIFEST,
    supplement_aliases=SUPPLEMENT_ALIASES,
    legacy_identities=LEGACY_IDENTITIES,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise CatalogValidationError(message)


def _validate_dependencies(modules: tuple[CourseModule, ...]) -> None:
    by_id = {module.id: module for module in modules}
    for module in modules:
        unknown = set(module.prerequisites) - set(by_id)
        _require(not unknown, f"{module.id} has unknown prerequisite: {sorted(unknown)}")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(module_id: str) -> None:
        if module_id in visiting:
            raise CatalogValidationError("dependency cycle detected")
        if module_id in visited:
            return
        visiting.add(module_id)
        for dependency in by_id[module_id].prerequisites:
            visit(dependency)
        visiting.remove(module_id)
        visited.add(module_id)

    for module in modules:
        visit(module.id)
    for module in modules:
        _require(
            all(by_id[item].order < module.order for item in module.prerequisites),
            f"{module.id} prerequisites must be earlier in the ordered course",
        )


def _learner_strings(module: CourseModule) -> Iterable[str]:
    yield from (module.callsign, module.title, module.mission_brief, module.debrief_prompt)
    yield from module.learning_objectives
    yield from module.lesson_outline
    yield from (module.lab.title, module.lab.verification)
    yield from module.lab.steps
    yield from module.lab.safety
    yield from module.checkpoint.prompts
    yield module.checkpoint.pass_condition
    yield module.oral.opening_prompt
    yield from module.oral.rubric
    for artifact in module.artifacts:
        yield artifact.title
        yield from artifact.template_fields
        yield from artifact.verification_rubric


def _validate_module_content(module: CourseModule) -> None:
    complete = all((
        module.callsign, module.title, module.mission_brief, module.learning_objectives,
        module.lesson_outline, module.lab.title, module.lab.steps, module.lab.verification,
        module.lab.safety, module.checkpoint.prompts, module.checkpoint.pass_condition,
        module.oral.opening_prompt, module.oral.rubric, module.artifacts, module.debrief_prompt,
    ))
    _require(complete, f"{module.id} has an incomplete mission loop")
    _require(module.lab.platform in VALID_PLATFORMS, f"{module.id} has unknown lab platform")
    _require(
        not any(_FORBIDDEN_COPY.search(text) for text in _learner_strings(module)),
        f"{module.id} contains learner-facing gamification copy",
    )
    for artifact in module.artifacts:
        complete_artifact = all((
            artifact.title, artifact.template_key, artifact.output_format,
            artifact.template_fields, artifact.verification_rubric,
        ))
        _require(complete_artifact, f"{artifact.id} is incomplete")


def _validate_artifact_templates(catalog: CourseCatalog) -> None:
    artifacts = [artifact for module in catalog.modules for artifact in module.artifacts]
    template_keys = [artifact.template_key for artifact in artifacts]
    _require(len(template_keys) == len(set(template_keys)), "duplicate artifact template keys")
    for artifact in artifacts:
        _require(
            artifact.output_format in VALID_ARTIFACT_FORMATS,
            f"{artifact.id} has unsupported output format",
        )


def _validate_ids(catalog: CourseCatalog) -> None:
    module_ids = tuple(module.id for module in catalog.modules)
    _require(len(module_ids) == len(set(module_ids)), "duplicate module ids")
    expected = tuple(f"IC-{index:02d}" for index in range(17))
    _require(set(module_ids) == set(expected), "catalog must contain IC-00 through IC-16")
    _require(module_ids == expected, "modules must be ordered IC-00 through IC-16")
    _require(tuple(module.order for module in catalog.modules) == tuple(range(17)), "module order is invalid")
    activity_ids = [
        activity_id
        for module in catalog.modules
        for activity_id in (module.checkpoint.id, module.oral.id, *(item.id for item in module.artifacts))
    ]
    _require(len(activity_ids) == len(set(activity_ids)), "duplicate activity ids")


def _validate_sources(catalog: CourseCatalog) -> None:
    source_ids = tuple(item.id for item in catalog.source_manifest)
    _require(len(source_ids) == len(set(source_ids)), "duplicate source ids")
    module_ids = {module.id for module in catalog.modules}
    _require(all(item.kind in SOURCE_KINDS for item in catalog.source_manifest), "unknown source kind")
    _require(all(item.module_id in module_ids for item in catalog.source_manifest), "unknown source module")
    _require(
        not any(_FORBIDDEN_COPY.search(item.label) for item in catalog.source_manifest),
        "source label contains learner-facing gamification copy",
    )
    mapped = {source_id for module in catalog.modules for source_id in module.source_ids}
    unknown = mapped - set(source_ids)
    _require(not unknown, f"modules contain unknown source ids: {sorted(unknown)}")
    unmapped = set(source_ids) - mapped
    _require(not unmapped, f"catalog has unmapped source ids: {sorted(unmapped)}")
    by_source = {item.id: item for item in catalog.source_manifest}
    evidence = {item.id for item in catalog.source_manifest if item.kind in EVIDENCE_SOURCE_KINDS}
    artifact_sources: set[str] = set()
    for module in catalog.modules:
        for artifact in module.artifacts:
            owned = all(
                source_id in by_source
                and by_source[source_id].module_id == module.id
                and by_source[source_id].kind in EVIDENCE_SOURCE_KINDS
                for source_id in artifact.source_ids
            )
            _require(owned, f"{artifact.id} violates artifact source ownership")
            artifact_sources.update(artifact.source_ids)
    _require(artifact_sources == evidence, "evidence sources must map to artifact descriptors")


def _validate_selection_rules(catalog: CourseCatalog) -> None:
    by_source = {item.id: item for item in catalog.source_manifest}
    frontier = next(module for module in catalog.modules if module.id == "IC-12")
    _require(frontier.selection_rule is not None, "IC-12 requires a selection rule")
    for module in catalog.modules:
        rule = module.selection_rule
        if rule is None:
            continue
        bounds_ok = 0 < rule.minimum <= rule.maximum <= len(rule.options)
        _require(bounds_ok, f"{module.id} has invalid selection bounds")
        _require(len(rule.options) == len(set(rule.options)), f"{module.id} has duplicate selection options")
        options_ok = all(
            source_id in by_source
            and by_source[source_id].module_id == module.id
            and by_source[source_id].kind == "topic"
            for source_id in rule.options
        )
        _require(options_ok, f"{module.id} has invalid selection options")


def _validate_completion_rules(catalog: CourseCatalog) -> None:
    by_source = {item.id: item for item in catalog.source_manifest}
    expected_ids = {"IC-14": WORKPLACE_PROJECT_IDS, "IC-16": PAPER_SOURCE_IDS}
    rules = [
        (module, artifact, artifact.completion_rule)
        for module in catalog.modules
        for artifact in module.artifacts
        if artifact.completion_rule is not None
    ]
    _require(
        {(module.id, artifact.id) for module, artifact, _ in rules} == {
            ("IC-14", "IC-14-ARTIFACT-WORKPLACE-PROPOSAL"),
            ("IC-16", "IC-16-ARTIFACT-PAPER-NOTES"),
        },
        "IC-14 and IC-16 require their catalog-owned completion contracts",
    )
    rule_ids = [rule.id for _, _, rule in rules]
    _require(len(rule_ids) == len(set(rule_ids)), "duplicate completion rule ids")
    for module, artifact, rule in rules:
        _require(_has_semantic_id(rule.id, "COMPLETION-"), f"{artifact.id} has a positional completion rule id")
        entry_ids = tuple(entry.source_id for entry in rule.entries)
        _require(entry_ids == expected_ids[module.id], f"{artifact.id} completion entries drifted")
        _require(len(entry_ids) == len(set(entry_ids)), f"{artifact.id} has duplicate completion entries")
        _require(
            all(source_id in by_source and by_source[source_id].label == entry.label
                for source_id, entry in zip(entry_ids, rule.entries)),
            f"{artifact.id} completion labels or sources drifted",
        )
        expected_kind = "workplace_project" if module.id == "IC-14" else "paper"
        _require(
            all(by_source[source_id].kind == expected_kind for source_id in entry_ids),
            f"{artifact.id} completion sources have the wrong kind",
        )
        if module.id == "IC-14":
            _require(
                all(by_source[source_id].module_id == module.id for source_id in entry_ids),
                f"{artifact.id} completion sources cross module ownership",
            )
        fields = tuple(filter(None, (
            rule.collection_field, rule.chosen_id_field, rule.evidence_field,
        )))
        _require(len(fields) == len(set(fields)), f"{artifact.id} completion fields collide")
        _require(
            all(re.fullmatch(r"[a-z][a-z0-9_]*", field) for field in (
                rule.collection_field, rule.entry_id_field, rule.entry_value_field,
            )),
            f"{artifact.id} has invalid completion field names",
        )
        evidence_fields = (
            rule.chosen_id_field, rule.evidence_field,
            rule.evidence_id_field, rule.evidence_value_field,
        )
        _require(
            all(evidence_fields) if module.id == "IC-14" else not any(evidence_fields),
            f"{artifact.id} has an invalid selection evidence shape",
        )
        _require(0 < rule.maximum_value_length <= 4000, f"{artifact.id} has invalid completion bounds")


def normalize_alias_identity(value: str) -> str:
    """Normalize an exact reconciliation identity without fuzzy matching."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    punctuation_collapsed = "".join(char if char.isalnum() else " " for char in normalized)
    return " ".join(punctuation_collapsed.split())


def _canonical_alias_identities(catalog: CourseCatalog) -> set[str]:
    identities = {catalog.key, catalog.title}
    for module in catalog.modules:
        identities.update((module.id, module.callsign, module.title, f"{module.id}-LESSON"))
    for source in catalog.source_manifest:
        identities.update((source.id, source.label))
    return {normalize_alias_identity(value) for value in identities}


def _has_semantic_id(identifier: str, prefix: str) -> bool:
    """Accept descriptive uppercase words, never ordinal/numeric segments."""
    pattern = rf"^{re.escape(prefix)}[A-Z]+(?:-[A-Z]+){{2,}}$"
    return re.fullmatch(pattern, identifier) is not None


def _validate_supplement_aliases(catalog: CourseCatalog) -> None:
    aliases = catalog.supplement_aliases
    ids = [alias.id for alias in aliases]
    _require(len(ids) == len(set(ids)), "duplicate supplement alias ids")
    _require(
        all(_has_semantic_id(item, "SUPPLEMENT-ALIAS-") for item in ids),
        "supplement alias requires a semantic id",
    )

    normalized_values = [value for alias in aliases for value in (alias.slug_alias, alias.title_alias)]
    exact_values = all(value and value == normalize_alias_identity(value) for value in normalized_values)
    _require(exact_values, "supplement aliases must be normalized exact identities without wildcards or fuzzy syntax")
    _require(
        len(normalized_values) == len(set(normalized_values)),
        "duplicate normalized supplement alias",
    )
    canonical = _canonical_alias_identities(catalog)
    _require(not (set(normalized_values) & canonical), "supplement alias collides with canonical identity")

    modules = {module.id: module for module in catalog.modules}
    sources = {source.id: source for source in catalog.source_manifest}
    for alias in aliases:
        _require(not alias.source_id.startswith("SUPPLEMENT-ALIAS-"), "supplement alias chaining is forbidden")
        _require(alias.module_id in modules, "supplement alias has unknown target module")
        _require(alias.source_id in sources, "supplement alias has unknown target source")
        module = modules[alias.module_id]
        _require(alias.lesson_id == f"{module.id}-LESSON", "supplement alias has invalid lesson identity")
        source_owned = sources[alias.source_id].module_id == module.id and alias.source_id in module.source_ids
        _require(source_owned, "supplement alias violates source ownership")


def _validate_legacy_identities(catalog: CourseCatalog) -> None:
    identities = catalog.legacy_identities
    ids = [identity.id for identity in identities]
    _require(len(ids) == len(set(ids)), "duplicate legacy identity ids")
    _require(
        all(_has_semantic_id(item, "LEGACY-IDENTITY-") for item in ids),
        "legacy identity requires a semantic id",
    )
    exact = all(
        value and value == normalize_alias_identity(value)
        for identity in identities
        for value in (identity.title_alias, identity.chapter_alias)
    )
    _require(exact, "legacy identity title and chapter must be normalized exact values")
    _require(
        all(identity.slug_prefix == f"{COURSE_KEY}-" for identity in identities),
        "legacy identity has invalid importer slug prefix",
    )
    _require(
        all(type(identity.sequence) is int and identity.sequence >= 1000 for identity in identities),
        "legacy identity has invalid exact sequence",
    )
    tuples = [
        (identity.slug_prefix, identity.title_alias, identity.chapter_alias, identity.sequence)
        for identity in identities
    ]
    _require(len(tuples) == len(set(tuples)), "duplicate normalized legacy identity")

    modules = {module.id: module for module in catalog.modules}
    sources = {source.id: source for source in catalog.source_manifest}
    for identity in identities:
        _require(identity.module_id in modules, "legacy identity has unknown target module")
        _require(identity.source_id in sources, "legacy identity has unknown target source")
        module = modules[identity.module_id]
        source = sources[identity.source_id]
        _require(identity.lesson_id == f"{module.id}-LESSON", "legacy identity has invalid lesson identity")
        owned = source.module_id == module.id and source.id in module.source_ids and source.kind == "section"
        _require(owned, "legacy identity violates source ownership")
        expected = normalize_alias_identity(source.label)
        _require(
            identity.title_alias == expected and identity.chapter_alias == expected,
            "legacy identity must use its approved source identity",
        )


def validate_catalog(catalog: CourseCatalog = COURSE) -> None:
    """Validate identity, graph, traceability, and learner-facing invariants."""
    _require(catalog.key == COURSE_KEY, "unexpected course key")
    _require(bool(catalog.version and catalog.title and catalog.audience), "course metadata is incomplete")
    _require(
        not _FORBIDDEN_COPY.search(catalog.title) and not _FORBIDDEN_COPY.search(catalog.audience),
        "course metadata contains learner-facing gamification copy",
    )
    _validate_ids(catalog)
    _validate_dependencies(catalog.modules)
    _validate_artifact_templates(catalog)
    _validate_sources(catalog)
    _validate_selection_rules(catalog)
    _validate_completion_rules(catalog)
    _validate_supplement_aliases(catalog)
    _validate_legacy_identities(catalog)
    for module in catalog.modules:
        _validate_module_content(module)


def supplement_alias_payload(aliases: tuple[SupplementAlias, ...]) -> list[dict[str, str]]:
    """Serialize aliases in stable semantic-ID order for consumers and snapshots."""
    return [asdict(alias) for alias in sorted(aliases, key=lambda item: item.id)]


def explicit_supplement_aliases(
    module_id: str, catalog: CourseCatalog | None = None,
) -> tuple[SupplementAlias, ...]:
    """Return the closed exact-alias set owned by one course module."""
    selected = COURSE if catalog is None else catalog
    return tuple(alias for alias in sorted(selected.supplement_aliases, key=lambda item: item.id)
                 if alias.module_id == module_id)


def legacy_identity_payload(identities: tuple[LegacyIdentity, ...]) -> list[dict[str, object]]:
    """Serialize exact legacy identities in stable semantic-ID order."""
    return [asdict(identity) for identity in sorted(identities, key=lambda item: item.id)]


def legacy_identities(
    module_id: str, catalog: CourseCatalog | None = None,
) -> tuple[LegacyIdentity, ...]:
    """Return the closed legacy-import identity set owned by one module."""
    selected = COURSE if catalog is None else catalog
    return tuple(identity for identity in sorted(selected.legacy_identities, key=lambda item: item.id)
                 if identity.module_id == module_id)


def legacy_identity_match(
    module_id: str, *, slug: str, title: str, chapter: str, sequence: int,
    catalog: CourseCatalog | None = None,
) -> LegacyIdentity | None:
    """Resolve only a complete exact importer identity; never infer a near match."""
    normalized_slug = unicodedata.normalize("NFKC", slug).casefold()
    normalized_title = normalize_alias_identity(title)
    normalized_chapter = normalize_alias_identity(chapter)
    return next((
        identity for identity in legacy_identities(module_id, catalog)
        if normalized_slug.startswith(identity.slug_prefix)
        and normalized_title == identity.title_alias
        and normalized_chapter == identity.chapter_alias
        and sequence == identity.sequence
    ), None)


def _bounded_completion_text(value: object, maximum: int) -> str:
    if not isinstance(value, str):
        raise CatalogValidationError("completion values must be text")
    clean = value.strip()
    has_control = any(ord(char) < 32 and char not in "\n\r\t" for char in clean)
    if not clean or len(clean) > maximum or has_control:
        raise CatalogValidationError("completion values must be nonblank bounded text")
    return clean


def canonical_completion_payload(artifact: ArtifactDescriptor, payload: object) -> dict[str, object]:
    """Validate one structured artifact completion and return catalog-ordered data."""
    rule = artifact.completion_rule
    if rule is None or not isinstance(payload, dict):
        raise CatalogValidationError("artifact has no structured completion contract")
    required_fields = {rule.collection_field}
    if rule.chosen_id_field:
        required_fields.update((rule.chosen_id_field, rule.evidence_field))
    if set(payload) != required_fields:
        raise CatalogValidationError("completion payload fields do not match the catalog contract")
    raw_entries = payload[rule.collection_field]
    if not isinstance(raw_entries, list):
        raise CatalogValidationError("completion collection must be a list")
    expected_ids = tuple(entry.source_id for entry in rule.entries)
    collected: dict[str, dict[str, str]] = {}
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict) or set(raw_entry) != {
            rule.entry_id_field, rule.entry_value_field,
        }:
            raise CatalogValidationError("completion entry shape is invalid")
        source_id = raw_entry[rule.entry_id_field]
        if not isinstance(source_id, str) or source_id in collected or source_id not in expected_ids:
            raise CatalogValidationError("completion entry identity is duplicate or unknown")
        collected[source_id] = {
            rule.entry_id_field: source_id,
            rule.entry_value_field: _bounded_completion_text(
                raw_entry[rule.entry_value_field], rule.maximum_value_length,
            ),
        }
    if set(collected) != set(expected_ids):
        raise CatalogValidationError("completion collection omits required catalog entries")
    canonical: dict[str, object] = {
        rule.collection_field: [collected[source_id] for source_id in expected_ids],
    }
    if rule.chosen_id_field:
        chosen_id = payload[rule.chosen_id_field]
        evidence = payload[rule.evidence_field]
        if not isinstance(chosen_id, str) or chosen_id not in expected_ids:
            raise CatalogValidationError("chosen completion identity is unknown")
        if not isinstance(evidence, dict) or set(evidence) != {
            rule.evidence_id_field, rule.evidence_value_field,
        }:
            raise CatalogValidationError("selected evidence shape is invalid")
        if evidence[rule.evidence_id_field] != chosen_id:
            raise CatalogValidationError("selected evidence is not tied to the chosen identity")
        canonical[rule.chosen_id_field] = chosen_id
        canonical[rule.evidence_field] = {
            rule.evidence_id_field: chosen_id,
            rule.evidence_value_field: _bounded_completion_text(
                evidence[rule.evidence_value_field], rule.maximum_value_length,
            ),
        }
    return canonical


def catalog_payload(catalog: CourseCatalog = COURSE) -> dict:
    """Return a detached, deterministic JSON-compatible representation."""
    validate_catalog(catalog)
    payload = asdict(catalog)
    payload["supplement_aliases"] = supplement_alias_payload(catalog.supplement_aliases)
    payload["legacy_identities"] = legacy_identity_payload(catalog.legacy_identities)
    return json.loads(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))


validate_catalog()


__all__ = [
    "ArtifactCompletionRule", "ArtifactDescriptor", "CatalogValidationError", "CheckpointDescriptor",
    "CompletionEntry", "COURSE", "COURSE_KEY", "COURSE_MODULES", "COURSE_VERSION",
    "CourseCatalog", "CourseModule",
    "LEGACY_IDENTITIES", "LabDescriptor", "LegacyIdentity", "OralDescriptor", "SOURCE_MANIFEST",
    "SUPPLEMENT_ALIASES", "SelectionRule", "SourceItem", "SupplementAlias", "WORKPLACE_PROJECT_IDS",
    "PAPER_SOURCE_IDS", "canonical_completion_payload", "catalog_payload",
    "explicit_supplement_aliases", "legacy_identities", "legacy_identity_match",
    "legacy_identity_payload", "normalize_alias_identity", "supplement_alias_payload",
    "validate_catalog",
]
