//! Nucleus CLI - Command Loop for EAOS Office Suite
//!
//! This binary provides a simple command-line interface to the Nucleus Director,
//! allowing users to interact with the BIOwerk Office Suite via Osteon and Myocyte.

use nucleus_director::{DirectorResponse, NucleusDirector};
use std::io::{self, BufRead, Write};

fn main() {
    println!("EAOS Nucleus Director v0.2.0");
    println!("Office Suite Command Interface");
    println!("Type 'help' for available commands, 'quit' to exit.\n");

    let mut director = NucleusDirector::new();
    let stdin = io::stdin();
    let mut stdout = io::stdout();

    loop {
        // Print prompt
        print!("nucleus> ");
        stdout.flush().unwrap();

        // Read input
        let mut input = String::new();
        match stdin.lock().read_line(&mut input) {
            Ok(0) => break, // EOF
            Ok(_) => {}
            Err(e) => {
                eprintln!("Error reading input: {}", e);
                continue;
            }
        }

        let input = input.trim();

        // Check for quit
        if input == "quit" || input == "exit" || input == "q" {
            println!("Goodbye.");
            break;
        }

        // Skip empty lines
        if input.is_empty() {
            continue;
        }

        // Parse and execute command
        match NucleusDirector::parse_command(input) {
            Some(request) => {
                let response = director.process(request);
                print_response(&response);
            }
            None => {
                println!("Unknown command: '{}'. Type 'help' for usage.", input);
            }
        }
    }
}

/// Print a DirectorResponse in a user-friendly format
fn print_response(response: &DirectorResponse) {
    match response {
        DirectorResponse::DocumentSaved { filename, block_offset, size } => {
            println!("Document saved: {}", filename);
            println!("  Block: {}", block_offset);
            println!("  Size: {} bytes", size);
        }
        DirectorResponse::LogicProcessed { name, block_offset, bytecode_size } => {
            println!("Logic processed: {}", name);
            println!("  Block: {}", block_offset);
            println!("  Bytecode: {} bytes", bytecode_size);
        }
        DirectorResponse::Status { biowerk_ready, document_count, logic_count } => {
            println!("System Status:");
            println!("  BIOwerk: {}", if *biowerk_ready { "Ready" } else { "Not Ready" });
            println!("  Documents: {}", document_count);
            println!("  Logic units: {}", logic_count);
        }
        DirectorResponse::DocumentList { count, documents } => {
            println!("Documents ({}):", count);
            for doc in documents {
                println!("  - {}", doc);
            }
        }
        DirectorResponse::HelpText(text) => {
            println!("{}", text);
        }
        DirectorResponse::Error(e) => {
            println!("Error: {}", e);
        }
    }
}
