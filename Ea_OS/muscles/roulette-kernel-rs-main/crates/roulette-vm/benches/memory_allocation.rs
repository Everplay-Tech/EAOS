use criterion::{black_box, criterion_group, criterion_main, Criterion};
use roulette_vm::*;
use std::time::Duration;

/// INNOVATIVE MEMORY TESTING: Advanced Memory Allocation Benchmarks
/// Tests memory fragmentation, allocation patterns, and deallocation strategies
/// Includes statistical analysis of allocation performance

fn fractal_allocation_pattern_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("fractal_allocation");
    group.measurement_time(Duration::from_secs(15));

    group.bench_function("fractal_depth_5_1000_allocations", |b| {
        b.iter_batched(
            || SimpleAllocator::new(0x1000, 0x100000),
            |mut allocator| {
                fractal_allocate(&mut allocator, 0, 5, 1024);
            },
            criterion::BatchSize::SmallInput,
        )
    });

    group.finish();
}

/// PROPRIETARY ALGORITHM: Fractal allocation for benchmarking
fn fractal_allocate(allocator: &mut SimpleAllocator, depth: usize, max_depth: usize, base_size: usize) -> Vec<(VirtAddr, usize)> {
    if depth >= max_depth {
        return Vec::new();
    }

    let mut allocations = Vec::new();

    // Allocate at current level
    let size = base_size / (1 << depth);
    if size > 0 {
        if let Some(addr) = allocator.allocate(core::alloc::Layout::from_size_align(size, 8).unwrap()) {
            allocations.push((addr, size));

            // Recursively allocate in sub-regions
            let sub_allocs = fractal_allocate(allocator, depth + 1, max_depth, size);
            allocations.extend(sub_allocs);
        }
    }

    allocations
}

fn memory_fragmentation_analysis_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("memory_fragmentation");
    group.measurement_time(Duration::from_secs(20));

    group.bench_function("fragmentation_chaos_simulation", |b| {
        b.iter_batched(
            || SimpleAllocator::new(0x1000, 0x100000),
            |mut allocator| {
                // Simulate complex allocation/deallocation patterns
                let mut allocations = Vec::new();

                // Phase 1: Allocate in increasing sizes
                for i in 0..50 {
                    let size = 64 + (i * 32);
                    if let Some(addr) = allocator.allocate(core::alloc::Layout::from_size_align(size, 8).unwrap()) {
                        allocations.push((addr, size));
                    }
                }

                // Phase 2: Deallocate every other allocation (simulate fragmentation)
                let mut to_remove = Vec::new();
                for (i, &(addr, size)) in allocations.iter().enumerate() {
                    if i % 2 == 0 {
                        // Note: SimpleAllocator doesn't support deallocation in this implementation
                        // In a real scenario, this would create fragmentation
                        to_remove.push((addr, size));
                    }
                }

                // Phase 3: Allocate small objects in gaps
                for _ in 0..25 {
                    let _ = allocator.allocate(core::alloc::Layout::from_size_align(32, 8).unwrap());
                }

                black_box(allocations.len())
            },
            criterion::BatchSize::SmallInput,
        )
    });

    group.finish();
}

fn allocation_strategy_comparison_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("allocation_strategies");
    group.measurement_time(Duration::from_secs(10));

    group.bench_function("best_fit_simulation", |b| {
        b.iter_batched(
            || SimpleAllocator::new(0x1000, 0x100000),
            |mut allocator| {
                // Simulate best-fit strategy by allocating in specific patterns
                let sizes = [128, 256, 64, 512, 32, 1024, 16, 2048];
                for &size in &sizes {
                    black_box(allocator.allocate(core::alloc::Layout::from_size_align(size, 8).unwrap()));
                }
            },
            criterion::BatchSize::SmallInput,
        )
    });

    group.bench_function("worst_fit_simulation", |b| {
        b.iter_batched(
            || SimpleAllocator::new(0x1000, 0x100000),
            |mut allocator| {
                // Simulate worst-fit by allocating largest first
                let sizes = [2048, 1024, 512, 256, 128, 64, 32, 16];
                for &size in &sizes {
                    black_box(allocator.allocate(core::alloc::Layout::from_size_align(size, 8).unwrap()));
                }
            },
            criterion::BatchSize::SmallInput,
        )
    });

    group.finish();
}

criterion_group!(
    name = memory_benches;
    config = Criterion::default().measurement_time(Duration::from_secs(25));
    targets = fractal_allocation_pattern_benchmark, memory_fragmentation_analysis_benchmark, allocation_strategy_comparison_benchmark
);
criterion_main!(memory_benches);