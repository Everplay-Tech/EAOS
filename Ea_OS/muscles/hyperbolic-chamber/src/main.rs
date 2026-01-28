fn main() {
    let code = hyperbolic_chamber::run_cli();
    if code != 0 {
        std::process::exit(code);
    }
}
