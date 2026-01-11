% QUENYAN(1) Quenyan User Manuals
% Quenyan Project Team
% July 2024

# NAME

quenyan \- morphemic encoding toolkit for encrypted source packages

# SYNOPSIS

**quenyan** [*command*] [*options*]

# DESCRIPTION

The **quenyan** command line interface exposes the full QYN-1 encoding
pipeline. It resembles common developer tooling such as Git by
providing composable sub-commands. The most frequently used commands
are:

* **encode** \- convert a source file into an encrypted morpheme stream
* **decode** \- restore canonical source code from a package
* **verify** \- authenticate a package without producing source output
* **inspect** \- display wrapper metadata without decryption
* **diff** \- compare two encrypted packages semantically
* **init** \- scaffold local configuration and key material

All commands accept **--help** to display detailed usage information.

# OPTIONS

Global options are provided per sub-command. Common flags include:

* **--key** *FILE* \- read the encryption passphrase from *FILE*
* **--passphrase** *TEXT* \- supply the passphrase directly (interactive use only)
* **--compression-mode** *MODE* \- select balanced, maximum, or
  security presets for the encoder
* **--compression-backend** *BACKEND* \- override the compression backend

# COMMANDS

## encode

```
quenyan encode source.py [-o output.qyn1] [--key keyfile]
```

Encodes *source.py* using the configured morpheme dictionary. Progress
bars are shown for files larger than 256 KiB.

## decode

```
quenyan decode package.qyn1 [-o source.py] [--key keyfile]
```

Decrypts and canonicalises a package. The command writes the restored
source to *source.py* and prints timing information unless **--quiet**
was provided.

## verify

```
quenyan verify package.qyn1 [--key keyfile] [--check-signature]
```

Verifies authenticated encryption. When **--check-signature** is
specified, the recorded source hash must match the decrypted payload.

## inspect

```
quenyan inspect package.qyn1 [--show-metadata]
```

Displays wrapper metadata without requiring a passphrase.

## diff

```
quenyan diff package_a.qyn1 package_b.qyn1 [--key keyfile]
```

Produces a semantic diff between two encrypted packages.

## init

```
quenyan init [directory] [--generate-keys]
```

Creates a *.quenyan* configuration directory beneath *directory*,
optionally generating a master key. Existing keys are preserved unless
**--force** is supplied.

## completion

```
quenyan completion (bash|zsh|fish)
```

Outputs shell completion code that can be sourced into the running
shell.

## man

```
quenyan man
```

Prints this manual page to standard output.

# FILES

~/.quenyan/config.json
: Default user-wide configuration emitted by **quenyan init**.

# EXAMPLES

```
# Encode using a key file and emit a human readable trace
quenyan encode app.py --key .quenyan/keys/master.key --human-readable app.trace

# Verify a package inside CI without decoding the source
quenyan verify build/app.qyn1 --key $CI_KEY --check-signature --json
```

# SEE ALSO

**quenyan completion**, **quenyan inspect**, the project documentation
in *docs/* within the source tree.

