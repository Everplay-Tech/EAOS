use std::env;
use std::fs;

fn main() {
    let mut args = env::args().skip(1);
    let path = match args.next() {
        Some(path) => path,
        None => {
            eprintln!("Usage: hash-blob <file>");
            std::process::exit(1);
        }
    };

    let data = fs::read(&path).unwrap_or_else(|err| {
        eprintln!("Failed to read {}: {}", path, err);
        std::process::exit(1);
    });

    let hash = blake3::hash(&data);
    println!("{}", hash.to_hex());
}
