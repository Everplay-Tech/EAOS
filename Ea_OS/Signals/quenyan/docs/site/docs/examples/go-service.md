# Example: Go Microservice

Use a `go generate` target to run the CLI before compiling the service:

```go
//go:generate quenyan encode main.go --key .quenyan/keys/master.key
```

The generated `.qyn1` files can be bundled into Docker images while the
plaintext source stays encrypted at rest.
