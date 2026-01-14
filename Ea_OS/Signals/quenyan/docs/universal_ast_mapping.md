# Universal AST Schema Documentation

This document describes the universal abstract syntax tree (AST) schema located at
`docs/universal_ast.schema.json`. The schema provides a deterministic, language-agnostic
intermediate representation that can encode programs written in Python, JavaScript/TypeScript,
Go, Rust, and C++.

## Canonical Node Types

The schema defines the following top-level categories:

- **Program** – Root node containing ordered module-level statements and an optional `language` tag.
- **Statement** – Includes `BlockStatement`, `ExpressionStatement`, `ReturnStatement`,
  `IfStatement`, `WhileStatement`, `ForStatement`, `BreakStatement`, `ContinueStatement`,
  `VariableDeclaration`, `FunctionDeclaration`, and `ClassDeclaration`.
- **Expression** – Covers identifiers, literals, calls, member access, binary/unary operations,
  assignments, and lambda/literal function expressions.
- **ClassMember** – Provides `MethodDeclaration` and `FieldDeclaration` nodes shared by all
  supported languages.
- **Shared Utility Nodes** – `Parameter`, `TypeAnnotation`, `TypeParameter`, `VariableDeclarator`,
  and comment/location metadata.

Each node inherits from `Node`, which introduces deterministic metadata fields (`leadingComments`,
`trailingComments`, and `loc`). These fields MUST always be present in serialized form using `null`
when no data exists.

## Deterministic Optional Fields

Optional semantic fields (for example, `returnType`, `decorators`, or `defaultValue`) are encoded as
`null` instead of being omitted. This ensures canonical JSON serialization regardless of language
features used by the source program. Producers MUST emit `null` for:

- Missing type annotations or generic parameter constraints
- Absent initializer expressions
- Empty decorator/type argument lists
- Loops that do not require `init`, `test`, `update`, or `iterable` components

Boolean feature toggles (such as `async`, `generator`, `isStatic`, or `variadic`) are always
included, preventing ambiguity when a language does not provide the feature.

## Ordering Rules

- `Program.body` preserves source order of declarations.
- `BlockStatement.body`, `FunctionDeclaration.parameters`, and `CallExpression.arguments` retain the
  textual order of the source program.
- `ClassDeclaration.body` preserves the order of members as they appear in the class definition.
- `TypeAnnotation.typeArguments` and `TypeParameter` arrays maintain declared ordering to keep type
  relationships unambiguous.

## Language Feature Mapping

### Python

- Module-level `def` statements map to `FunctionDeclaration` with `async`/`decorators` populated when
  present. `returnType` carries annotations from function definitions.
- `class` statements produce `ClassDeclaration` nodes. Decorated methods and `@property` accessors map
  to `MethodDeclaration` with `kind` set to `Getter`/`Setter` as appropriate.
- `for`/`while` loops map to `ForStatement` (with `forKind="ForOf"` for `for target in iterable`) or
  `WhileStatement`. Python comprehensions can be represented as `LambdaExpression` bodies or expanded
  loops in downstream tooling.

### JavaScript / TypeScript

- Function and arrow declarations use `FunctionDeclaration` and `LambdaExpression`. `typeParameters`
  and `typeArguments` capture TypeScript generics; plain JavaScript sets these arrays to `null`.
- `class` syntax maps directly to `ClassDeclaration`; `static`/`async` modifiers fill boolean fields.
- `let`/`const`/`var` map to `VariableDeclaration` with `declarationKind` of `Let`, `Const`, or `Var`.
- Property access and optional chaining use `MemberExpression` with `computed=false` for dot syntax.

### Go

- Top-level functions map to `FunctionDeclaration` with `visibility="Public"` or `"Private"`
  inferred from identifier casing. Receivers are encoded as the first `Parameter` entry.
- Methods on types produce `MethodDeclaration` within the owning `ClassDeclaration`. Go interfaces are
  represented using `ClassDeclaration` with `implements=null` and empty bodies to preserve structure.
- `for` loops map to `ForStatement` with `forKind="CStyle"`, `"Range"`, or `"ForOf"` depending on syntax.

### Rust

- `fn` items become `FunctionDeclaration`. Generics populate `typeParameters`; lifetimes are rendered
  as `TypeParameter` with `typeName` prefixes (`'a`).
- `impl` blocks produce `ClassDeclaration` with `name` set to the implementing type and `implements`
  referencing trait bounds via `TypeAnnotation` nodes.
- `let`/`mut` statements become `VariableDeclaration` with `declarationKind` `Let` or `Mutable`.
- Match expressions should be lowered into nested `IfStatement` trees or represented using domain-
  specific extensions if consumers support them.

### C++

- Functions map to `FunctionDeclaration` with `typeParameters` for template parameters and
  `visibility` derived from access specifiers.
- Classes, structs, and namespaces correspond to `ClassDeclaration`. `FieldDeclaration.isMutable`
  distinguishes `mutable` fields; `isStatic` mirrors the `static` keyword.
- Loops map to `ForStatement` (`forKind="CStyle"`) or `WhileStatement`; `do-while` uses
  `WhileStatement` with a trailing `conditional=true` flag encoded via `leadingComments` metadata or a
  custom extension if needed.
- Operator overloads are `MethodDeclaration` nodes with `kind="Operator"` and an identifier of `null`.

## Cross-Language Notes

- `Literal.literalType` distinguishes strings, numbers, booleans, bytes, and explicit `null`/`None`/`nullptr`.
- `BinaryExpression.operator` provides a normalized enumeration shared across languages.
- `ForStatement.forKind` differentiates C-style for loops, iterator loops (`ForOf`), associative
  iterations (`ForIn`), and Go-style range loops (`Range`).
- `TypeAnnotation.typeName` always stores the fully qualified canonical name for deterministic
  serialization (`std::vector`, `List`, `Option`, etc.).

## Worked Examples

### Python Example

Source:

```python
def add(a: int, b: int) -> int:
    return a + b
```

Excerpt:

```json
{
  "type": "Program",
  "language": "python",
  "body": [
    {
      "type": "FunctionDeclaration",
      "name": {"type": "Identifier", "name": "add"},
      "parameters": [
        {"type": "Parameter", "name": {"type": "Identifier", "name": "a"}, "typeAnnotation": {"type": "TypeAnnotation", "typeName": "int", "typeArguments": null, "optional": false}, "defaultValue": null, "variadic": false},
        {"type": "Parameter", "name": {"type": "Identifier", "name": "b"}, "typeAnnotation": {"type": "TypeAnnotation", "typeName": "int", "typeArguments": null, "optional": false}, "defaultValue": null, "variadic": false}
      ],
      "returnType": {"type": "TypeAnnotation", "typeName": "int", "typeArguments": null, "optional": false},
      "typeParameters": null,
      "body": {
        "type": "BlockStatement",
        "body": [
          {
            "type": "ReturnStatement",
            "argument": {
              "type": "BinaryExpression",
              "operator": "Add",
              "left": {"type": "Identifier", "name": "a"},
              "right": {"type": "Identifier", "name": "b"}
            }
          }
        ]
      },
      "decorators": null,
      "async": false,
      "generator": false,
      "visibility": null
    }
  ]
}
```

### JavaScript Example

Source:

```javascript
export class Counter {
  constructor() {
    this.count = 0;
  }
  increment() {
    this.count += 1;
  }
}
```

Excerpt:

```json
{
  "type": "ClassDeclaration",
  "name": {"type": "Identifier", "name": "Counter"},
  "typeParameters": null,
  "superClass": null,
  "implements": null,
  "body": [
    {
      "type": "MethodDeclaration",
      "name": {"type": "Identifier", "name": "constructor"},
      "parameters": [],
      "returnType": null,
      "body": {
        "type": "BlockStatement",
        "body": [
          {
            "type": "ExpressionStatement",
            "expression": {
              "type": "AssignmentExpression",
              "operator": "Assign",
              "target": {
                "type": "MemberExpression",
                "object": {"type": "Identifier", "name": "this"},
                "property": {"type": "Identifier", "name": "count"},
                "computed": false
              },
              "value": {"type": "Literal", "literalType": "Number", "value": 0}
            }
          }
        ]
      },
      "kind": "Method",
      "isStatic": false,
      "isAsync": false,
      "visibility": "Public"
    },
    {
      "type": "MethodDeclaration",
      "name": {"type": "Identifier", "name": "increment"},
      "parameters": [],
      "returnType": null,
      "body": {
        "type": "BlockStatement",
        "body": [
          {
            "type": "ExpressionStatement",
            "expression": {
              "type": "AssignmentExpression",
              "operator": "AddAssign",
              "target": {
                "type": "MemberExpression",
                "object": {"type": "Identifier", "name": "this"},
                "property": {"type": "Identifier", "name": "count"},
                "computed": false
              },
              "value": {"type": "Literal", "literalType": "Number", "value": 1}
            }
          }
        ]
      },
      "kind": "Method",
      "isStatic": false,
      "isAsync": false,
      "visibility": "Public"
    }
  ]
}
```

### Go Example

Source:

```go
func Sum(vals []int) int {
    total := 0
    for _, v := range vals {
        total += v
    }
    return total
}
```

Excerpt:

```json
{
  "type": "FunctionDeclaration",
  "name": {"type": "Identifier", "name": "Sum"},
  "parameters": [
    {"type": "Parameter", "name": {"type": "Identifier", "name": "vals"}, "typeAnnotation": {"type": "TypeAnnotation", "typeName": "[]int", "typeArguments": null, "optional": false}, "defaultValue": null, "variadic": false}
  ],
  "returnType": {"type": "TypeAnnotation", "typeName": "int", "typeArguments": null, "optional": false},
  "typeParameters": null,
  "body": {
    "type": "BlockStatement",
    "body": [
      {
        "type": "VariableDeclaration",
        "declarationKind": "Mutable",
        "declarators": [
          {
            "type": "VariableDeclarator",
            "id": {"type": "Identifier", "name": "total"},
            "typeAnnotation": null,
            "init": {"type": "Literal", "literalType": "Number", "value": 0}
          }
        ]
      },
      {
        "type": "ForStatement",
        "forKind": "Range",
        "init": null,
        "test": null,
        "update": null,
        "iterable": {"type": "Identifier", "name": "vals"},
        "body": {
          "type": "BlockStatement",
          "body": [
            {
              "type": "ExpressionStatement",
              "expression": {
                "type": "AssignmentExpression",
                "operator": "AddAssign",
                "target": {"type": "Identifier", "name": "total"},
                "value": {"type": "Identifier", "name": "v"}
              }
            }
          ]
        }
      },
      {"type": "ReturnStatement", "argument": {"type": "Identifier", "name": "total"}}
    ]
  },
  "decorators": null,
  "async": false,
  "generator": false,
  "visibility": "Public"
}
```

### Rust Example

Source:

```rust
pub fn max(a: i32, b: i32) -> i32 {
    if a > b { a } else { b }
}
```

Excerpt:

```json
{
  "type": "FunctionDeclaration",
  "name": {"type": "Identifier", "name": "max"},
  "parameters": [
    {"type": "Parameter", "name": {"type": "Identifier", "name": "a"}, "typeAnnotation": {"type": "TypeAnnotation", "typeName": "i32", "typeArguments": null, "optional": false}, "defaultValue": null, "variadic": false},
    {"type": "Parameter", "name": {"type": "Identifier", "name": "b"}, "typeAnnotation": {"type": "TypeAnnotation", "typeName": "i32", "typeArguments": null, "optional": false}, "defaultValue": null, "variadic": false}
  ],
  "returnType": {"type": "TypeAnnotation", "typeName": "i32", "typeArguments": null, "optional": false},
  "typeParameters": null,
  "body": {
    "type": "BlockStatement",
    "body": [
      {
        "type": "IfStatement",
        "test": {
          "type": "BinaryExpression",
          "operator": "Greater",
          "left": {"type": "Identifier", "name": "a"},
          "right": {"type": "Identifier", "name": "b"}
        },
        "consequent": {"type": "BlockStatement", "body": [{"type": "ReturnStatement", "argument": {"type": "Identifier", "name": "a"}}]},
        "alternate": {"type": "BlockStatement", "body": [{"type": "ReturnStatement", "argument": {"type": "Identifier", "name": "b"}}]}
      }
    ]
  },
  "decorators": null,
  "async": false,
  "generator": false,
  "visibility": "Public"
}
```

### C++ Example

Source:

```cpp
class Point {
public:
    Point(double x, double y) : x_(x), y_(y) {}
    double length() const {
        return std::sqrt(x_ * x_ + y_ * y_);
    }
private:
    double x_;
    double y_;
};
```

Excerpt:

```json
{
  "type": "ClassDeclaration",
  "name": {"type": "Identifier", "name": "Point"},
  "typeParameters": null,
  "superClass": null,
  "implements": null,
  "body": [
    {
      "type": "MethodDeclaration",
      "name": null,
      "parameters": [
        {"type": "Parameter", "name": {"type": "Identifier", "name": "x"}, "typeAnnotation": {"type": "TypeAnnotation", "typeName": "double", "typeArguments": null, "optional": false}, "defaultValue": null, "variadic": false},
        {"type": "Parameter", "name": {"type": "Identifier", "name": "y"}, "typeAnnotation": {"type": "TypeAnnotation", "typeName": "double", "typeArguments": null, "optional": false}, "defaultValue": null, "variadic": false}
      ],
      "returnType": null,
      "body": {
        "type": "BlockStatement",
        "body": [
          {
            "type": "ExpressionStatement",
            "expression": {
              "type": "AssignmentExpression",
              "operator": "Assign",
              "target": {"type": "Identifier", "name": "x_"},
              "value": {"type": "Identifier", "name": "x"}
            }
          },
          {
            "type": "ExpressionStatement",
            "expression": {
              "type": "AssignmentExpression",
              "operator": "Assign",
              "target": {"type": "Identifier", "name": "y_"},
              "value": {"type": "Identifier", "name": "y"}
            }
          }
        ]
      },
      "kind": "Constructor",
      "isStatic": false,
      "isAsync": false,
      "visibility": "Public"
    },
    {
      "type": "MethodDeclaration",
      "name": {"type": "Identifier", "name": "length"},
      "parameters": [],
      "returnType": {"type": "TypeAnnotation", "typeName": "double", "typeArguments": null, "optional": false},
      "body": {
        "type": "BlockStatement",
        "body": [
          {
            "type": "ReturnStatement",
            "argument": {
              "type": "CallExpression",
              "callee": {"type": "Identifier", "name": "std::sqrt"},
              "arguments": [
                {
                  "type": "BinaryExpression",
                  "operator": "Add",
                  "left": {
                    "type": "BinaryExpression",
                    "operator": "Mul",
                    "left": {"type": "Identifier", "name": "x_"},
                    "right": {"type": "Identifier", "name": "x_"}
                  },
                  "right": {
                    "type": "BinaryExpression",
                    "operator": "Mul",
                    "left": {"type": "Identifier", "name": "y_"},
                    "right": {"type": "Identifier", "name": "y_"}
                  }
                }
              ],
              "typeArguments": null
            }
          }
        ]
      },
      "kind": "Method",
      "isStatic": false,
      "isAsync": false,
      "visibility": "Public"
    },
    {
      "type": "FieldDeclaration",
      "name": {"type": "Identifier", "name": "x_"},
      "typeAnnotation": {"type": "TypeAnnotation", "typeName": "double", "typeArguments": null, "optional": false},
      "initializer": null,
      "isStatic": false,
      "isMutable": false,
      "visibility": "Private"
    },
    {
      "type": "FieldDeclaration",
      "name": {"type": "Identifier", "name": "y_"},
      "typeAnnotation": {"type": "TypeAnnotation", "typeName": "double", "typeArguments": null, "optional": false},
      "initializer": null,
      "isStatic": false,
      "isMutable": false,
      "visibility": "Private"
    }
  ]
}
```

## Extensibility

Languages may introduce constructs beyond this core. Producers SHOULD encode custom metadata using
`leadingComments`/`trailingComments` or out-of-band channels while proposing additions to the schema.
Consumers MUST ignore unknown properties to maintain forward compatibility.
