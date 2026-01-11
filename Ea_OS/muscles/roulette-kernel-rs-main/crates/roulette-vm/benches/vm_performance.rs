use criterion::{black_box, criterion_group, criterion_main, Criterion};
use roulette_vm::*;
use std::time::Duration;

/// INNOVATIVE PERFORMANCE TESTING: VM Performance Benchmarks
/// Measures critical path performance with statistical analysis
/// Includes regression detection and performance profiling

fn vm_creation_benchmark(c: &mut Criterion) {
    c.bench_function("vm_creation_1mb", |b| {
        b.iter(|| {
            black_box(VirtualMachine::new(0x1000, 0x100000));
        })
    });

    c.bench_function("vm_creation_10mb", |b| {
        b.iter(|| {
            black_box(VirtualMachine::new(0x1000, 0xA00000));
        })
    });
}

fn process_scheduling_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("process_scheduling");
    group.measurement_time(Duration::from_secs(10));
    group.sample_size(100);

    group.bench_function("schedule_10_processes", |b| {
        b.iter_batched(
            || {
                let mut vm = VirtualMachine::new(0x1000, 0x100000);
                for i in 0..10 {
                    vm.create_process(0x2000 + i * 0x1000, 0x1000).unwrap();
                }
                vm
            },
            |mut vm| {
                for _ in 0..100 {
                    black_box(vm.schedule_next());
                }
            },
            criterion::BatchSize::SmallInput,
        )
    });

    group.finish();
}

fn memory_allocation_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("memory_allocation");
    group.measurement_time(Duration::from_secs(15));

    group.bench_function("allocator_stress_1000", |b| {
        b.iter_batched(
            || SimpleAllocator::new(0x1000, 0x100000),
            |mut allocator| {
                for i in 0..1000 {
                    let size = (i % 100 + 1) * 64;
                    black_box(allocator.allocate(
                        core::alloc::Layout::from_size_align(size, 8).unwrap()
                    ));
                }
            },
            criterion::BatchSize::SmallInput,
        )
    });

    group.finish();
}

fn braid_cpu_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("braid_cpu_operations");
    group.measurement_time(Duration::from_secs(10));

    group.bench_function("braid_execution_1000_steps", |b| {
        b.iter_batched(
            || {
                let mut cpu = BraidCPU::new();
                let program = BraidWord {
                    generators: [BraidGenerator::Left(1); 16],
                    length: 4,
                };
                cpu.load_program(program);
                cpu
            },
            |mut cpu| {
                for _ in 0..1000 {
                    black_box(cpu.step());
                }
            },
            criterion::BatchSize::SmallInput,
        )
    });

    group.finish();
}

criterion_group!(
    name = vm_benches;
    config = Criterion::default()
        .with_profiler(criterion::profiler::PProfProfiler::new(100, criterion::profiler::Output::Flamegraph(None)))
        .measurement_time(Duration::from_secs(20))
        .sample_size(50);
    targets = vm_creation_benchmark, process_scheduling_benchmark, memory_allocation_benchmark, braid_cpu_benchmark
);
criterion_main!(vm_benches);