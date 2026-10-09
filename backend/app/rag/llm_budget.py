"""A per-ingestion request budget shared by both normalization stages."""
from collections.abc import Callable
from time import monotonic

LIMIT_MESSAGES = {
    'call_limit': '达到单文档 LLM 请求上限，剩余内容保留原文',
    'time_limit': '达到单文档 LLM 整理时间预算，剩余内容保留原文',
    'configuration': 'LLM 配置不可用，剩余内容保留原文',
    'api_failures': 'LLM 连续请求失败，已停止后续调用并保留原文',
}


class LLMLimitReached(RuntimeError):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(LIMIT_MESSAGES[reason])


class IngestionLlmBudget:
    def __init__(self, settings, *, clock=monotonic):
        self.max_calls = max(0, int(getattr(settings, 'INGESTION_LLM_MAX_CALLS', 120)))
        self.max_seconds = max(0.0, float(getattr(settings, 'INGESTION_LLM_MAX_SECONDS', 600)))
        self.max_retries = max(0, int(getattr(settings, 'INGESTION_LLM_MAX_RETRIES', 1)))
        self.clock = clock
        self.started = None
        self.attempts = self.successes = self.failures = self.retries = 0
        self.stop_reason = None
        self.on_event: Callable[[str], None] | None = None

    @property
    def elapsed(self):
        return max(0.0, self.clock() - self.started) if self.started is not None else 0.0

    def reserve(self, *, retry=False):
        if self.stop_reason:
            raise LLMLimitReached(self.stop_reason)
        if self.started is None:
            self.started = self.clock()
        reason = ('call_limit' if self.attempts >= self.max_calls else
                  'time_limit' if self.elapsed >= self.max_seconds else None)
        if reason:
            self.stop_reason = reason
            self.emit(LIMIT_MESSAGES[reason])
            raise LLMLimitReached(reason)
        self.attempts += 1
        if retry:
            self.retries += 1
        self.emit('API 重试请求中' if retry else 'API 请求中')
        return max(0.001, self.max_seconds - self.elapsed)

    def emit(self, message):
        if self.on_event:
            self.on_event(message)

    def snapshot(self):
        return dict(request_attempted_count=self.attempts,
                    request_succeeded_count=self.successes, request_failed_count=self.failures,
                    retry_count=self.retries, request_max_calls=self.max_calls,
                    max_seconds=self.max_seconds, elapsed_seconds=round(self.elapsed, 2),
                    limit_reason=self.stop_reason)
