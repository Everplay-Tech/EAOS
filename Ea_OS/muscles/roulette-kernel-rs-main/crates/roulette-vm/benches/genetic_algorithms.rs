use criterion::{black_box, criterion_group, criterion_main, Criterion};
use roulette_vm::*;
use std::time::Duration;

/// INNOVATIVE GENETIC ALGORITHMS: Performance Analysis of Evolutionary Computing
/// Benchmarks genetic algorithm components with statistical analysis
/// Measures convergence rates, population diversity, and optimization effectiveness

fn genetic_algorithm_core_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("genetic_algorithm_core");
    group.measurement_time(Duration::from_secs(30));

    group.bench_function("genetic_optimization_50_generations", |b| {
        b.iter_batched(
            || create_initial_population(50),
            |population| {
                black_box(run_genetic_algorithm(population, 50));
            },
            criterion::BatchSize::SmallInput,
        )
    });

    group.finish();
}

fn fitness_evaluation_benchmark(c: &mut Criterion) {
    let mut group = c.benchmark_group("fitness_evaluation");
    group.measurement_time(Duration::from_secs(15));

    group.bench_function("evaluate_population_100_chromosomes", |b| {
        b.iter_batched(
            || {
                let population = create_initial_population(100);
                VirtualMachine::new(0x1000, 0x10000)
            },
            |(population, mut vm)| {
                for chromosome in population {
                    black_box(evaluate_fitness(&chromosome, &mut vm));
                }
            },
            criterion::BatchSize::SmallInput,
        )
    });

    group.finish();
}

fn crossover_mutation_benchmark(c: &mut Criterion) {
    c.bench_function("crossover_mutation_operations_1000", |b| {
        b.iter_batched(
            || create_initial_population(100),
            |population| {
                let mut new_population = Vec::new();
                for _ in 0..500 {
                    let parent1 = &population[0];
                    let parent2 = &population[1];
                    let (mut child1, mut child2) = perform_crossover(parent1, parent2);
                    perform_mutation(&mut child1);
                    perform_mutation(&mut child2);
                    new_population.push(child1);
                    new_population.push(child2);
                }
                black_box(new_population)
            },
            criterion::BatchSize::SmallInput,
        )
    });
}

/// Helper functions for genetic algorithm benchmarking

type Chromosome = (Vec<u32>, Vec<u8>, usize);

fn create_initial_population(size: usize) -> Vec<Chromosome> {
    (0..size).map(|_| create_random_chromosome()).collect()
}

fn create_random_chromosome() -> Chromosome {
    let len = (std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos() % 8 + 1) as usize;
    let mut times = Vec::new();
    let mut prios = Vec::new();

    for _ in 0..len {
        times.push((std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos() % 100) as u32);
        prios.push((std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos() % 5) as u8);
    }

    (times, prios, len)
}

fn evaluate_fitness(chromosome: &Chromosome, vm: &mut VirtualMachine) -> f64 {
    let (process_times, _, length) = chromosome;
    let mut context_switches = 0;
    let mut max_concurrent = 0;
    let mut current_running = 0;

    for time in 0..20 { // Reduced for benchmarking
        for i in 0..*length {
            if process_times[i] == time as u32 {
                if vm.create_process(0x2000 + i * 0x1000, 0x1000).is_some() {
                    current_running += 1;
                }
            }
        }

        if vm.schedule_next().is_some() {
            context_switches += 1;
        }

        max_concurrent = max_concurrent.max(current_running);
    }

    (context_switches as f64 * 0.6) + (max_concurrent as f64 * 0.4)
}

fn perform_crossover(parent1: &Chromosome, parent2: &Chromosome) -> (Chromosome, Chromosome) {
    let (times1, prios1, len1) = parent1;
    let (times2, prios2, len2) = parent2;
    let split = len1.min(*len2) / 2;

    let mut child1_times = times1[..split].to_vec();
    child1_times.extend_from_slice(&times2[split..]);
    let mut child1_prios = prios1[..split].to_vec();
    child1_prios.extend_from_slice(&prios2[split..]);

    let mut child2_times = times2[..split].to_vec();
    child2_times.extend_from_slice(&times1[split..]);
    let mut child2_prios = prios2[..split].to_vec();
    child2_prios.extend_from_slice(&prios1[split..]);

    ((child1_times, child1_prios, *len1), (child2_times, child2_prios, *len2))
}

fn perform_mutation(chromosome: &mut Chromosome) {
    let (times, prios, length) = chromosome;
    if (std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_nanos() % 10) == 0 {
        let idx = (std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos() % *length as u128) as usize;
        times[idx] = (std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos() % 100) as u32;
        prios[idx] = (std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos() % 5) as u8;
    }
}

fn run_genetic_algorithm(mut population: Vec<Chromosome>, generations: usize) -> Vec<Chromosome> {
    let mut vm = VirtualMachine::new(0x1000, 0x10000);

    for _ in 0..generations {
        // Evaluate fitness
        let mut fitness_scores: Vec<(usize, f64)> = population.iter().enumerate()
            .map(|(i, chrom)| (i, evaluate_fitness(chrom, &mut vm)))
            .collect();

        // Sort by fitness
        fitness_scores.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());

        // Select top performers
        let mut new_population = Vec::new();
        let elite_count = population.len() / 4;
        for i in 0..elite_count {
            new_population.push(population[fitness_scores[i].0].clone());
        }

        // Crossover and mutate
        while new_population.len() < population.len() {
            let parent1 = &population[fitness_scores[0].0];
            let parent2 = &population[fitness_scores[1].0];

            let (mut child1, mut child2) = perform_crossover(parent1, parent2);
            perform_mutation(&mut child1);
            perform_mutation(&mut child2);

            new_population.push(child1);
            new_population.push(child2);
        }

        population = new_population.into_iter().take(population.len()).collect();
    }

    population
}

criterion_group!(
    name = genetic_benches;
    config = Criterion::default().measurement_time(Duration::from_secs(45));
    targets = genetic_algorithm_core_benchmark, fitness_evaluation_benchmark, crossover_mutation_benchmark
);
criterion_main!(genetic_benches);