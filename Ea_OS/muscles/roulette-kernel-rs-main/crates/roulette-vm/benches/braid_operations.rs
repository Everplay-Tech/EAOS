use criterion::{black_box, criterion_group, criterion_main, Criterion};
use roulette_vm::*;
use std::time::Duration;

/// INNOVATIVE ALGORITHMIC TESTING: Braid Operations Benchmarks
/// Performance analysis of proprietary braid group algorithms
/// Includes complexity analysis and optimization validation

fn braid_word_construction_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("braid_construction");
    group.measurement_time(Duration::from_secs(10));

    group.bench_function("braid_word_16_generators", |b| {
        b.iter(|| {
            black_box(BraidWord {
                generators: [
                    BraidGenerator::Left(1), BraidGenerator::Right(1),
                    BraidGenerator::Left(2), BraidGenerator::Right(2),
                    BraidGenerator::Left(3), BraidGenerator::Right(3),
                    BraidGenerator::Left(4), BraidGenerator::Right(4),
                    BraidGenerator::Left(5), BraidGenerator::Right(5),
                    BraidGenerator::Left(6), BraidGenerator::Right(6),
                    BraidGenerator::Left(7), BraidGenerator::Right(7),
                    BraidGenerator::Left(8), BraidGenerator::Right(8),
                ],
                length: 16,
            });
        })
    });

    group.finish();
}

fn braid_cpu_state_transition_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("braid_state_transitions");
    group.measurement_time(Duration::from_secs(15));

    group.bench_function("cpu_state_10000_transitions", |b| {
        b.iter_batched(
            || {
                let mut cpu = BraidCPU::new();
                // Create a complex braid program
                let mut generators = [BraidGenerator::Left(0); 16];
                for i in 0..16 {
                    generators[i] = if i % 2 == 0 {
                        BraidGenerator::Left((i / 2 + 1) as u8)
                    } else {
                        BraidGenerator::Right((i / 2 + 1) as u8)
                    };
                }
                let program = BraidWord { generators, length: 16 };
                cpu.load_program(program);
                cpu
            },
            |mut cpu| {
                for _ in 0..10000 {
                    black_box(cpu.step());
                }
            },
            criterion::BatchSize::SmallInput,
        )
    });

    group.finish();
}

fn permutation_invariant_computation_benchmark(c: &mut Criterion) {
    c.bench_function("permutation_invariant_16_elements", |b| {
        b.iter_batched(
            || {
                // Create a random permutation for testing
                let mut perm = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15];
                // Fisher-Yates shuffle simulation
                for i in (1..16).rev() {
                    let j = (std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .unwrap()
                        .as_nanos() % (i + 1) as u128) as usize;
                    perm.swap(i, j);
                }
                perm
            },
            |perm| {
                // Compute cycle decomposition invariant
                black_box(compute_permutation_invariant(&perm));
            },
            criterion::BatchSize::SmallInput,
        )
    });
}

/// PROPRIETARY ALGORITHM: Compute permutation invariant
/// Used for benchmarking braid group invariant computation
fn compute_permutation_invariant(perm: &[usize; 16]) -> u64 {
    let mut visited = [false; 16];
    let mut invariant = 0u64;
    let mut cycle_count = 0;

    for start in 0..16 {
        if !visited[start] {
            let mut cycle_length = 0;
            let mut current = start;

            while !visited[current] {
                visited[current] = true;
                current = perm[current];
                cycle_length += 1;
            }

            invariant = invariant.wrapping_mul(31).wrapping_add(cycle_length as u64);
            cycle_count += 1;
        }
    }

    invariant.wrapping_mul(31).wrapping_add(cycle_count as u64)
}

criterion_group!(
    name = braid_benches;
    config = Criterion::default().measurement_time(Duration::from_secs(20));
    targets = braid_word_construction_benchmark, braid_cpu_state_transition_benchmark, permutation_invariant_computation_benchmark
);
criterion_main!(braid_benches);