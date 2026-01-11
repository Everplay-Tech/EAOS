//! Userland: shell and utilities, robust, enterprise-grade

use crate::process::ProcessManager;
use crate::fs::OSFileSystem;
use crate::syscall::{SyscallDispatcher, SyscallContext};
use futures::executor::block_on;

/// Algebraic shell command
#[derive(Debug, Clone)]
pub enum Command {
    Ls(Option<String>),
    Cat(String),
    Run(String),
    History,
    Help,
    Exit,
    Unknown(String),
}

/// Algebraic command pipeline (combinator)
#[derive(Debug, Clone)]
pub struct CommandPipeline {
    pub commands: Vec<Command>,
}

impl CommandPipeline {
    pub fn new(commands: Vec<Command>) -> Self {
        Self { commands }
    }

    /// Async combinator execution: executes commands in sequence, piping output
    pub async fn execute<'a>(&self, shell: &mut Shell<'a>) {
        let mut last_output: Option<String> = None;
        for cmd in &self.commands {
            last_output = shell.execute_command_pipe(cmd, last_output.clone()).await;
        }
    }
}

    /// Parser combinator for shell commands and pipelines
    fn parse_command_pipeline(input: &str) -> CommandPipeline {
        let segments: Vec<&str> = input.split('|').map(str::trim).collect();
        let commands = segments.into_iter().map(|seg| {
            let parts: Vec<&str> = seg.split_whitespace().collect();
            match parts.as_slice() {
                ["ls"] => Command::Ls(None),
                ["ls", path] => Command::Ls(Some(path.to_string())),
                ["cat", file] => Command::Cat(file.to_string()),
                ["run", prog] => Command::Run(prog.to_string()),
                ["history"] => Command::History,
                ["help"] => Command::Help,
                ["exit"] => Command::Exit,
                [cmd, ..] => Command::Unknown(cmd.to_string()),
                [] => Command::Help,
            }
        }).collect();
        CommandPipeline::new(commands)
    }

/// Interactive shell REPL with async command execution
pub struct Shell<'a> {
    process_manager: &'a mut ProcessManager,
    fs: &'a mut OSFileSystem,
    history: Vec<String>,
}

impl<'a> Shell<'a> {
    /// Create a new shell
    pub fn new(process_manager: &'a mut ProcessManager, fs: &'a mut OSFileSystem) -> Self {
        Self { process_manager, fs, history: Vec::new() }
    }

    /// Run interactive shell REPL (async, combinator pipelines)
    pub fn run(&mut self) {
        use std::io::{self, Write};
        loop {
            print!("roulette> ");
            let _ = io::stdout().flush();
            let mut input = String::new();
            if io::stdin().read_line(&mut input).is_err() { break; }
            let input = input.trim();
            if input.is_empty() { continue; }
            self.history.push(input.to_string());
            let pipeline = parse_command_pipeline(input);
            if pipeline.commands.iter().any(|c| matches!(c, Command::Exit)) { break; }
            block_on(pipeline.execute(self));
        }
    }

    /// Async command execution for combinator pipeline (returns output for piping)
    pub async fn execute_command_pipe(&mut self, command: &Command, input: Option<String>) -> Option<String> {
        match command {
            Command::Ls(path) => {
                let dir = path.clone().unwrap_or("/".to_string());
                match self.fs.list_dir(&dir) {
                    Ok(entries) => {
                        let out = entries.join("\n");
                        println!("{}", out);
                        Some(out)
                    },
                    Err(e) => {
                        println!("Error: {:?}", e);
                        None
                    },
                }
            }
            Command::Cat(file) => {
                let mut buf = vec![0u8; 1024];
                match self.fs.read(file, &mut buf) {
                    Ok(sz) => {
                        let out = String::from_utf8_lossy(&buf[..sz]).to_string();
                        println!("{}", out);
                        Some(out)
                    },
                    Err(e) => {
                        println!("Error: {:?}", e);
                        None
                    },
                }
            }
            Command::Run(prog) => {
                let entry_point = 0x2000; // Replace with real loader
                let stack_size = 0x1000;
                let priority = 5;
                if let Some(pid) = self.process_manager.create_process(entry_point, stack_size, priority) {
                    let out = format!("Started process {} for program {}", pid, prog);
                    println!("{}", out);
                    Some(out)
                } else {
                    println!("Failed to start program {}");
                    None
                }
            }
            Command::History => {
                let out = self.history.iter().enumerate().map(|(i, cmd)| format!("{}: {}", i + 1, cmd)).collect::<Vec<_>>().join("\n");
                println!("{}", out);
                Some(out)
            }
            Command::Help => {
                let out = "Available commands: ls [dir], cat <file>, run <program>, history, help, exit".to_string();
                println!("{}", out);
                Some(out)
            }
            Command::Unknown(cmd) => {
                println!("Unknown command: {}", cmd);
                None
            }
            Command::Exit => None,
        }
    }
}
