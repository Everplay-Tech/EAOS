"""
FILE: src/grok_ppo_enterprise/telemetry.py
================================================================================
Telemetry and Metrics Collection for Grok PPO Enterprise
"""
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)

class MetricType(Enum):
    COUNTER = "counter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"
    SUMMARY = "summary"

@dataclass
class Metric:
    """Base metric class."""
    name: str
    metric_type: MetricType
    description: str
    labels: Dict[str, str]
    value: Any
    timestamp: float
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "type": self.metric_type.value,
            "description": self.description,
            "labels": self.labels,
            "value": self.value,
            "timestamp": self.timestamp
        }

class TelemetryMeter:
    """
    Simple telemetry meter for collecting and emitting metrics.
    In production, this would integrate with Prometheus, Datadog, etc.
    """
    
    def __init__(self):
        self.metrics: List[Metric] = []
        self.start_time = time.time()
        
        # Initialize default metrics
        self.init_default_metrics()
    
    def init_default_metrics(self):
        """Initialize default metrics."""
        self.create_counter(
            "grok.api.calls.total",
            description="Total number of Grok API calls made"
        )
        self.create_counter(
            "grok.api.errors.total", 
            description="Total number of Grok API errors"
        )
        self.create_histogram(
            "grok.api.latency.ms",
            description="Latency of Grok API calls in milliseconds"
        )
        self.create_counter(
            "grok.api.overloads.total",
            description="Total number of channel overload errors"
        )
        self.create_gauge(
            "grok.agent.success_rate",
            description="Current success rate of the agent"
        )
        self.create_histogram(
            "grok.dpo.loss",
            description="DPO preference alignment loss"
        )
        self.create_counter(
            "grok.dpo.preference_accuracy",
            description="How often policy prefers YGI-chosen trajectory"
        )
    
    def create_counter(self, name: str, description: str = "", initial_value: int = 0) -> 'Counter':
        """Create a counter metric."""
        counter = Counter(name, description, initial_value)
        self.metrics.append(counter.to_metric())
        return counter
    
    def create_histogram(self, name: str, description: str = "") -> 'Histogram':
        """Create a histogram metric."""
        histogram = Histogram(name, description)
        self.metrics.append(histogram.to_metric())
        return histogram
    
    def create_gauge(self, name: str, description: str = "", initial_value: float = 0.0) -> 'Gauge':
        """Create a gauge metric."""
        gauge = Gauge(name, description, initial_value)
        self.metrics.append(gauge.to_metric())
        return gauge
    
    def record(self, metric: Metric):
        """Record a metric."""
        self.metrics.append(metric)
        # Also log for now (in production, emit to monitoring system)
        logger.info("Metric recorded", 
                   name=metric.name, 
                   value=metric.value,
                   labels=metric.labels)
    
    def get_metrics(self) -> List[Dict]:
        """Get all metrics as dictionaries."""
        return [metric.to_dict() for metric in self.metrics]
    
    def get_metric_by_name(self, name: str) -> Optional[Metric]:
        """Get a specific metric by name."""
        for metric in reversed(self.metrics):
            if metric.name == name:
                return metric
        return None
    
    def clear_metrics(self):
        """Clear all metrics (use with caution)."""
        self.metrics.clear()
        self.init_default_metrics()

class Counter:
    """Counter metric that only increases."""
    
    def __init__(self, name: str, description: str = "", initial_value: int = 0):
        self.name = name
        self.description = description
        self.value = initial_value
        self.labels: Dict[str, str] = {}
    
    def add(self, amount: int = 1, labels: Optional[Dict[str, str]] = None):
        """Add to the counter."""
        self.value += amount
        if labels:
            self.labels.update(labels)
        
        # Create metric and emit
        metric = Metric(
            name=self.name,
            metric_type=MetricType.COUNTER,
            description=self.description,
            labels=self.labels.copy(),
            value=self.value,
            timestamp=time.time()
        )
        meter.record(metric)
    
    def to_metric(self) -> Metric:
        return Metric(
            name=self.name,
            metric_type=MetricType.COUNTER,
            description=self.description,
            labels=self.labels,
            value=self.value,
            timestamp=time.time()
        )

class Histogram:
    """Histogram metric for distributions."""
    
    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.values: List[float] = []
        self.labels: Dict[str, str] = {}
    
    def record(self, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a value in the histogram."""
        self.values.append(value)
        if len(self.values) > 1000:  # Keep last 1000 values
            self.values = self.values[-1000:]
        
        if labels:
            self.labels.update(labels)
        
        # Create summary metric
        if self.values:
            metric = Metric(
                name=self.name,
                metric_type=MetricType.HISTOGRAM,
                description=self.description,
                labels=self.labels.copy(),
                value={
                    "count": len(self.values),
                    "sum": sum(self.values),
                    "min": min(self.values),
                    "max": max(self.values),
                    "avg": sum(self.values) / len(self.values),
                    "p95": self._percentile(95),
                    "p99": self._percentile(99)
                },
                timestamp=time.time()
            )
            meter.record(metric)
    
    def _percentile(self, p: float) -> float:
        """Calculate percentile."""
        if not self.values:
            return 0.0
        sorted_vals = sorted(self.values)
        k = (len(sorted_vals) - 1) * (p / 100.0)
        f = int(k)
        c = k - f
        
        if f + 1 < len(sorted_vals):
            return sorted_vals[f] + c * (sorted_vals[f + 1] - sorted_vals[f])
        return sorted_vals[f]
    
    def to_metric(self) -> Metric:
        value = {
            "count": len(self.values),
            "sum": sum(self.values) if self.values else 0,
            "min": min(self.values) if self.values else 0,
            "max": max(self.values) if self.values else 0,
            "avg": sum(self.values) / len(self.values) if self.values else 0
        }
        return Metric(
            name=self.name,
            metric_type=MetricType.HISTOGRAM,
            description=self.description,
            labels=self.labels,
            value=value,
            timestamp=time.time()
        )

class Gauge:
    """Gauge metric that can go up and down."""
    
    def __init__(self, name: str, description: str = "", initial_value: float = 0.0):
        self.name = name
        self.description = description
        self.value = initial_value
        self.labels: Dict[str, str] = {}
    
    def set(self, value: float, labels: Optional[Dict[str, str]] = None):
        """Set the gauge value."""
        self.value = value
        if labels:
            self.labels.update(labels)
        
        metric = Metric(
            name=self.name,
            metric_type=MetricType.GAUGE,
            description=self.description,
            labels=self.labels.copy(),
            value=self.value,
            timestamp=time.time()
        )
        meter.record(metric)
    
    def inc(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Increase the gauge."""
        self.set(self.value + amount, labels)
    
    def dec(self, amount: float = 1.0, labels: Optional[Dict[str, str]] = None):
        """Decrease the gauge."""
        self.set(self.value - amount, labels)
    
    def to_metric(self) -> Metric:
        return Metric(
            name=self.name,
            metric_type=MetricType.GAUGE,
            description=self.description,
            labels=self.labels,
            value=self.value,
            timestamp=time.time()
        )

# Global telemetry meter
meter = TelemetryMeter()
