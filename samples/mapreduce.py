import threading
import queue
import random
import re
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# 配置参数
NUM_PRODUCERS = 3
NUM_CONSUMERS = 4
LINES_PER_PRODUCER = 500
WORDS_PER_LINE = (10, 30)
TOP_N = 15

# 模拟词汇库：生成一些具有偏斜分布的词汇
VOCAB_BASE = [
    "python", "algorithm", "data", "structure", "function", "class", "object",
    "inheritance", "polymorphism", "encapsulation", "threading", "concurrency",
    "parallel", "synchronization", "mutex", "semaphore", "queue", "pipeline",
    "mapreduce", "filter", "lambda", "generator", "iterator", "decorator",
    "recursion", "dynamic", "programming", "greedy", "backtracking", "branch",
    "neural", "network", "deep", "learning", "gradient", "descent", "optimization",
    "vector", "matrix", "tensor", "computation", "graph", "tree", "heap", "stack"
]

# 为 Zipf 分布准备加权词汇
VOCAB_WEIGHTED = []
for i, word in enumerate(VOCAB_BASE):
    weight = max(1, 50 // (i + 1))  # Zipf-like 权重
    VOCAB_WEIGHTED.extend([word] * weight)

# 线程安全的共享队列和结果收集器
task_queue = queue.Queue(maxsize=100)
result_queue = queue.Queue()
lock = threading.Lock()
producers_done = threading.Event()

# 统计指标
stats = {
    "total_lines": 0,
    "total_words": 0,
    "producer_times": [],
    "consumer_times": []
}

def generate_text_line():
    """生成一条模拟的随机文本行"""
    n_words = random.randint(*WORDS_PER_LINE)
    words = [random.choice(VOCAB_WEIGHTED) for _ in range(n_words)]
    # 添加一些噪声：标点、数字、大小写变化
    line = " ".join(words)
    line = re.sub(r'(\w+)', lambda m: m.group(1).upper() if random.random() < 0.1 else m.group(1), line)
    line = re.sub(r'(\w{4,})', lambda m: m.group(1) + random.choice([",", ";", ".", "!"]) if random.random() < 0.15 else m.group(1), line)
    return line

def producer(pid):
    """生产者：生成文本行并放入队列"""
    start = time.perf_counter()
    local_lines = 0
    for _ in range(LINES_PER_PRODUCER):
        line = generate_text_line()
        task_queue.put(line)
        local_lines += 1
    elapsed = time.perf_counter() - start
    with lock:
        stats["producer_times"].append((pid, elapsed))
        stats["total_lines"] += local_lines
    print(f"[Producer-{pid}] 完成，生成 {local_lines} 行，耗时 {elapsed:.4f}s")

def consumer(cid):
    """消费者：从队列取出行，进行词频统计"""
    start = time.perf_counter()
    local_counter = Counter()
    local_words = 0
    while True:
        try:
            line = task_queue.get(timeout=2)
        except queue.Empty:
            if producers_done.is_set() and task_queue.empty():
                break
            continue

        # 复杂的文本处理：清洗、分词、标准化
        line = line.lower()
        tokens = re.findall(r'\b[a-z]{3,}\b', line)  # 只保留3字母以上单词
        local_counter.update(tokens)
        local_words += len(tokens)
        task_queue.task_done()

    elapsed = time.perf_counter() - start
    with lock:
        stats["consumer_times"].append((cid, elapsed))
        stats["total_words"] += local_words
    result_queue.put(local_counter)
    print(f"[Consumer-{cid}] 完成，处理 {local_words} 词，耗时 {elapsed:.4f}s")

def parallel_mapreduce():
    """主调度器：协调生产者和消费者"""
    print("=" * 60)
    print("启动复杂并发 MapReduce 模拟系统")
    print("=" * 60)

    # 启动消费者
    consumers = []
    for cid in range(NUM_CONSUMERS):
        t = threading.Thread(target=consumer, args=(cid,))
        t.start()
        consumers.append(t)

    # 启动生产者（使用线程池）
    producer_threads = []
    for pid in range(NUM_PRODUCERS):
        t = threading.Thread(target=producer, args=(pid,))
        t.start()
        producer_threads.append(t)

    # 等待所有生产者完成
    for t in producer_threads:
        t.join()
    producers_done.set()
    print("\n[Main] 所有生产者已完成，通知消费者结束...")

    # 等待所有消费者完成
    for t in consumers:
        t.join()

    # Reduce 阶段：合并所有局部 Counter
    final_counter = Counter()
    while not result_queue.empty():
        final_counter.update(result_queue.get())

    return final_counter

# 运行主程序
overall_start = time.perf_counter()
final_counts = parallel_mapreduce()
overall_elapsed = time.perf_counter() - overall_start

# 输出详细报告
print("\n" + "=" * 60)
print("RESULT REPORT")
print("=" * 60)
print(f"总耗时: {overall_elapsed:.4f} 秒")
print(f"生产者数量: {NUM_PRODUCERS}, 消费者数量: {NUM_CONSUMERS}")
print(f"总生成行数: {stats['total_lines']}")
print(f"总处理词数: {stats['total_words']}")
print(f"唯一词汇数: {len(final_counts)}")
print(f"平均词频: {stats['total_words'] / max(len(final_counts), 1):.2f}")

print(f"\n生产者耗时详情:")
for pid, t in stats["producer_times"]:
    print(f"  Producer-{pid}: {t:.4f}s")

print(f"\n消费者耗时详情:")
for cid, t in stats["consumer_times"]:
    print(f"  Consumer-{cid}: {t:.4f}s")

print(f"\nTop {TOP_N} 高频词汇 (Zipf 分布验证):")
print("-" * 40)
print(f"{'Rank':<6} {'Word':<20} {'Count':<10} {'Percentage':<12}")
print("-" * 40)

total_valid = sum(final_counts.values())
for rank, (word, count) in enumerate(final_counts.most_common(TOP_N), 1):
    pct = (count / total_valid) * 100 if total_valid > 0 else 0
    print(f"{rank:<6} {word:<20} {count:<10} {pct:<11.2f}%")

# 附加：计算 Gini 系数衡量分布不均匀度
def gini_coefficient(counter):
    counts = sorted(counter.values())
    n = len(counts)
    if n == 0:
        return 0.0
    cumsum = 0
    for i, c in enumerate(counts, 1):
        cumsum += (2 * i - n - 1) * c
    return cumsum / (n * sum(counts))

gini = gini_coefficient(final_counts)
print("-" * 40)
print(f"\n词汇分布 Gini 系数: {gini:.4f} (越接近1越不均匀)")
print("=" * 60)
