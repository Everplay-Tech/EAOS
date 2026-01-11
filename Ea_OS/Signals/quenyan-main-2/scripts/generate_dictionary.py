import json

core_constructs = [
    ("construct:function", "kar", "kar-", "to make or do", ["FunctionDeclaration", "FunctionDef", "FuncDecl"]),
    ("construct:async_function", "karilya", "karilya-", "to do with swiftness", ["AsyncFunctionDeclaration", "AsyncFunctionDef"]),
    ("construct:lambda", "karmin", "karmin-", "to fashion briefly", ["LambdaExpression", "Lambda"]),
    ("construct:method", "karno", "karno-", "an act performed within", ["MethodDeclaration", "FunctionMember"]),
    ("construct:class", "noss", "noss-", "kindred or clan", ["ClassDeclaration", "StructDeclaration"]),
    ("construct:interface", "nossiel", "nossiël-", "kindred-path", ["InterfaceDeclaration", "ProtocolDeclaration"]),
    ("construct:struct", "nort", "norto-", "thing made firm", ["StructDeclaration", "RecordStruct"]),
    ("construct:enum", "host", "hosta-", "assembled group", ["EnumDeclaration"]),
    ("construct:module", "parma", "parma-", "book or collection", ["Module", "Namespace"]),
    ("construct:import", "tulpar", "tul-", "come to gather", ["ImportStatement", "UseDeclaration", "IncludeDirective"]),
    ("construct:export", "auta", "auta-", "to go away", ["ExportStatement"]),
    ("construct:block", "sand", "sand-", "shielded place", ["BlockStatement", "Suite"]),
    ("construct:if", "ce", "ce-", "if, maybe", ["IfStatement", "ConditionalExpression"]),
    ("construct:elif", "cepen", "cepen-", "if again", ["ElifClause"]),
    ("construct:else", "epesse", "epessë-", "otherwise", ["ElseClause"]),
    ("construct:while", "yor", "yor-", "to do repeatedly", ["WhileStatement"]),
    ("construct:for", "lenda", "lend-", "go, travel", ["ForStatement", "ForInStatement", "RangeStatement"]),
    ("construct:foreach", "lendor", "lend-", "go among", ["ForeachStatement", "ForEachStatement"]),
    ("construct:loop_generic", "yorna", "yorna-", "to repeat", ["LoopStatement", "Loop"]),
    ("construct:do_while", "yornal", "yor-", "repeat until", ["DoWhileStatement"]),
    ("construct:switch", "tenya", "tenya-", "to denote", ["SwitchStatement", "MatchStatement"]),
    ("construct:case", "tenar", "tenar-", "marked choice", ["CaseClause", "MatchCase"]),
    ("construct:default", "tenarwa", "tenarwa-", "the marked remainder", ["DefaultClause"]),
    ("construct:try", "valya", "valya-", "to dare", ["TryStatement"]),
    ("construct:catch", "mapa", "mapa-", "to seize", ["CatchClause", "ExceptHandler"]),
    ("construct:finally", "metta", "metta-", "end or finish", ["FinallyClause"]),
    ("construct:throw", "hat", "hat-", "to hurl", ["ThrowStatement", "RaiseStatement"]),
    ("construct:yield", "anta", "anta-", "to give", ["YieldExpression", "YieldFrom"]),
    ("construct:return", "ent", "ent-", "to give back", ["ReturnStatement"]),
    ("construct:break", "rup", "rúpa-", "to break", ["BreakStatement"]),
    ("construct:continue", "vesta", "vesta-", "to endure", ["ContinueStatement"]),
    ("construct:pass", "sesta", "sesta-", "to let go", ["PassStatement"]),
    ("construct:annotation", "tenca", "tenca-", "to write, sign", ["Annotation", "Decorator"]),
    ("construct:comment", "quetta", "quetta-", "word or saying", ["Comment"]),
    ("construct:directive", "narma", "narma-", "instruction", ["PragmaDirective", "CompilerDirective"]),
]

data_types = [
    ("type:int", "nelya", "nelya-", "third, counting number", ["IntType", "i32", "int"]),
    ("type:float", "linga", "linga-", "to float or hang", ["FloatType", "f64", "double"]),
    ("type:string", "lambre", "lambë-", "tongue, language", ["StringType", "str"]),
    ("type:bool", "nanwa", "nanwa-", "true/affirmed", ["BoolType"]),
    ("type:char", "telpe", "tyelpë-", "symbol", ["CharType"]),
    ("type:array", "hostar", "hosta-", "collection", ["ArrayType", "SliceType", "ListType"]),
    ("type:tuple", "veri", "verya-", "to join", ["TupleType"]),
    ("type:object", "sana", "sana-", "thing", ["ObjectType", "ClassType"]),
    ("type:map", "nore", "nórë-", "land, domain", ["MapType", "DictionaryType"]),
    ("type:set", "osta", "osta-", "assembly", ["SetType"]),
    ("type:option", "mara", "mára-", "good/possible", ["OptionalType", "OptionType"]),
    ("type:result", "turma", "turma-", "victory result", ["ResultType"]),
    ("type:void", "lusta", "lussa-", "empty", ["VoidType", "NoneType", "UnitType"]),
    ("type:any", "ilya", "ilya-", "all", ["AnyType"]),
    ("type:never", "umbar", "umbar-", "doom, never occurs", ["NeverType"]),
    ("type:byte", "peke", "pecë-", "small piece", ["ByteType"]),
    ("type:short", "titta", "titta-", "small", ["ShortType", "i16"]),
    ("type:long", "anda", "anda-", "long", ["LongType", "i64", "long"]),
    ("type:decimal", "mindor", "mindor-", "numerical detail", ["DecimalType"]),
    ("type:bigint", "alta", "alta-", "great", ["BigIntType", "BigInteger"]),
    ("type:promise", "estel", "estel-", "hope/trust", ["PromiseType", "FutureType"]),
    ("type:iterator", "rehta", "rehta-", "to trail", ["IteratorType", "GeneratorType"]),
    ("type:channel", "sirya", "sirya-", "flowing river", ["ChannelType", "StreamType"]),
    ("type:pointer", "tiel", "tië-", "path", ["PointerType", "ReferenceType"]),
    ("type:reference", "tieme", "tië-", "path connection", ["ReferenceType", "BorrowType"]),
    ("type:fnptr", "karta", "karta-", "shape of doing", ["FunctionPointerType"]),
    ("type:union", "omenta", "oment-", "meeting", ["UnionType", "SumType"]),
    ("type:intersection", "osanya", "osanya-", "joining crossing", ["IntersectionType"]),
    ("type:structural", "nilda", "nilda-", "friendship/binding", ["StructuralType"]),
    ("type:nominal", "esse", "essë-", "name", ["NominalType"]),
    ("type:literal", "sanga", "sanga-", "firm, exact", ["LiteralType"]),
]

operators = [
    ("op:add", "yonta", "yon-", "add together", ["BinaryExpression:+"]),
    ("op:sub", "rac", "rac-", "to break off", ["BinaryExpression:-"]),
    ("op:mul", "yulma", "yul-", "to drink up/mix", ["BinaryExpression:*"]),
    ("op:div", "hehta", "hehta-", "to discard apart", ["BinaryExpression:/"]),
    ("op:mod", "metya", "metya-", "to measure remainder", ["BinaryExpression:%"]),
    ("op:pow", "turion", "tur-", "to master raise", ["BinaryExpression:**", "PowExpression"]),
    ("op:eq", "same", "same-", "equal", ["BinaryExpression:==", "EqualityExpression"]),
    ("op:neq", "ava", "ava-", "not", ["BinaryExpression:!=", "InequalityExpression"]),
    ("op:lt", "pitya", "pitya-", "small", ["BinaryExpression:<"]),
    ("op:gt", "alta", "alta-", "great", ["BinaryExpression:>"]),
    ("op:le", "pityar", "pitya-", "small or equal", ["BinaryExpression:<="]),
    ("op:ge", "altar", "alta-", "great or equal", ["BinaryExpression:>="]),
    ("op:and", "yo", "yo-", "and", ["LogicalExpression:&&", "BoolOp:And"]),
    ("op:or", "var", "var-", "or", ["LogicalExpression:||", "BoolOp:Or"]),
    ("op:not", "lá", "lá-", "no", ["UnaryExpression:!", "UnaryOp:Not"]),
    ("op:bit_and", "tulka", "tulka-", "strength joining", ["BinaryExpression:&"]),
    ("op:bit_or", "tyali", "tyalië-", "play/alternate", ["BinaryExpression:|"]),
    ("op:bit_xor", "laure", "laurë-", "golden mix", ["BinaryExpression:^"]),
    ("op:bit_not", "mor", "mor-", "dark inversion", ["UnaryExpression:~"]),
    ("op:shift_left", "lenge", "leng-", "lean left", ["BinaryExpression:<<"]),
    ("op:shift_right", "lengea", "leng-", "lean right", ["BinaryExpression:>>"]),
    ("op:coalesce", "onta", "onta-", "beget join", ["NullishCoalescing"]),
    ("op:ternary", "ceanta", "ceanta-", "if-split", ["ConditionalExpression:?"]),
    ("op:pipe", "siryo", "siryo-", "flow", ["PipeExpression", "MethodChain"]),
    ("op:range_incl", "pelda", "pelda-", "fence inclusive", ["RangeExpression:..="]),
    ("op:range_excl", "peldaë", "pelda-", "fence exclusive", ["RangeExpression:.."]),
    ("op:assign", "antya", "antya-", "to give to", ["Assignment"]),
    ("op:add_assign", "antyayon", "antya-", "give additionally", ["Assignment:+="]),
    ("op:sub_assign", "antyarac", "antya-", "give subtractively", ["Assignment:-="]),
    ("op:mul_assign", "antyayul", "antya-", "give multiplicatively", ["Assignment:*="]),
    ("op:div_assign", "antyaheh", "antya-", "give divisively", ["Assignment:/="]),
    ("op:mod_assign", "antyamet", "antya-", "give remainder", ["Assignment:%="]),
    ("op:bit_and_assign", "antyatul", "antya-", "give bitwise and", ["Assignment:&="]),
    ("op:bit_or_assign", "antyavar", "antya-", "give bitwise or", ["Assignment:|="]),
    ("op:bit_xor_assign", "antyalaur", "antya-", "give bitwise xor", ["Assignment:^="]),
    ("op:shift_left_assign", "antyaleng", "antya-", "give shift left", ["Assignment:<<="]),
    ("op:shift_right_assign", "antyalengw", "antya-", "give shift right", ["Assignment:>>="]),
    ("op:logical_and_assign", "antyayo", "antya-", "give logical and", ["Assignment:&&="]),
    ("op:logical_or_assign", "antyavar", "antya-", "give logical or", ["Assignment:||="]),
    ("op:nullish_assign", "antyaonta", "antya-", "give nullish", ["Assignment:??="]),
    ("op:await", "harta", "harta-", "to wait/watch", ["AwaitExpression"]),
    ("op:new", "ontaqua", "onta-", "bring into being", ["NewExpression", "ConstructorCall"]),
    ("op:call", "tulya", "tulya-", "to invoke", ["CallExpression"]),
]

control_flow = [
    ("flow:return", "enta", "ent-", "give back", ["ReturnStatement"]),
    ("flow:break", "rusta", "rus-", "break off", ["BreakStatement"]),
    ("flow:continue", "vestar", "vesta-", "keep going", ["ContinueStatement"]),
    ("flow:throw", "hatten", "hat-", "hurl", ["ThrowStatement"]),
    ("flow:yield", "antal", "anta-", "give forth", ["YieldStatement", "YieldExpression"]),
    ("flow:await", "hartan", "harta-", "watch", ["AwaitExpression"]),
    ("flow:return_async", "entalya", "ent-", "give back swiftly", ["ReturnStatement"]),
    ("flow:break_label", "rusto", "rus-", "break at mark", ["BreakStatement:Labeled"]),
    ("flow:continue_label", "vesto", "vesta-", "continue at mark", ["ContinueStatement:Labeled"]),
    ("flow:goto", "lenduva", "lendu-", "go toward", ["GotoStatement"]),
    ("flow:fallthrough", "peleta", "pelet-", "to pass through", ["FallthroughStatement"]),
    ("flow:defer", "hantale", "hantale-", "gratitude/later", ["DeferStatement"]),
    ("flow:panic", "ruhta", "ruhta-", "terror drive", ["Panic", "Abort"]),
    ("flow:match_break", "tenrup", "ten-", "mark break", ["MatchBreak"]),
    ("flow:loop_exit", "yorend", "yor-", "end of loop", ["LoopExit"]),
    ("flow:loop_continue", "yorvest", "yor-", "repeat continue", ["LoopContinue"]),
    ("flow:tail_call", "entul", "ent-", "return-call", ["TailCall"]),
    ("flow:resume", "enyal", "enyal-", "remember resume", ["ResumeStatement"]),
    ("flow:suspend", "nurta", "nurta-", "to hide/hold", ["SuspendStatement"]),
    ("flow:checkpoint", "tirme", "tirme-", "to watch", ["Checkpoint"]),
    ("flow:rewind", "andar", "andar-", "go back", ["RewindStatement"]),
    ("flow:retry", "ceya", "ceya-", "to try again", ["RetryStatement"]),
    ("flow:exit", "auta", "auta-", "depart program", ["ExitStatement"]),
    ("flow:halt", "tulka", "tulka-", "stand firm", ["HaltInstruction"]),
    ("flow:trap", "raumo", "raumo-", "storm/trap", ["TrapInstruction"]),
]

oop = [
    ("oop:class", "nossan", "noss-", "kindred grouping", ["ClassDeclaration"]),
    ("oop:abstract_class", "nossal", "noss-", "kindred veiled", ["AbstractClassDeclaration"]),
    ("oop:interface", "nossiel", "nossiël-", "interface kindred", ["InterfaceDeclaration"]),
    ("oop:trait", "saira", "sairë-", "distinctive feature", ["TraitDeclaration"]),
    ("oop:impl", "haryon", "harya-", "to possess", ["ImplementationBlock"]),
    ("oop:method", "karion", "kar-", "doing within type", ["MethodDeclaration"]),
    ("oop:constructor", "ontion", "onta-", "begetting", ["ConstructorDeclaration"]),
    ("oop:destructor", "ruhtion", "ruhta-", "tearing down", ["DestructorDeclaration"]),
    ("oop:property", "sambë", "sambë-", "room/house", ["PropertyDeclaration", "FieldDeclaration"]),
    ("oop:getter", "sambetul", "sambë-", "house bring", ["GetterMethod"]),
    ("oop:setter", "sambenta", "sambë-", "house give", ["SetterMethod"]),
    ("oop:field", "talan", "talan-", "plane, floor", ["FieldDeclaration"]),
    ("oop:static_field", "talanda", "talan-", "fixed floor", ["StaticFieldDeclaration"]),
    ("oop:static_method", "karand", "kar-", "doing fixed", ["StaticMethodDeclaration"]),
    ("oop:virtual_method", "karfir", "kar-", "doing phantom", ["VirtualMethodDeclaration"]),
    ("oop:override", "arta", "arta-", "exalted over", ["OverrideSpecifier"]),
    ("oop:implements", "haryal", "harya-", "possess interface", ["ImplementsClause"]),
    ("oop:extends", "telya", "telya-", "to finish/extend", ["ExtendsClause"]),
    ("oop:inherits", "toron", "toron-", "brotherhood", ["InheritanceClause"]),
    ("oop:mixins", "erya", "erya-", "to stir", ["MixinClause"]),
    ("oop:interface_method", "nossilkar", "nossiël-", "interface doing", ["InterfaceMethod"]),
    ("oop:sealed", "hresta", "hresta-", "shore boundary", ["SealedClass"]),
    ("oop:record", "histar", "hista-", "list/record", ["RecordClass"]),
    ("oop:partial", "mitta", "mitta-", "between/part", ["PartialClass"]),
    ("oop:annotation", "tenceli", "tenca-", "marked class", ["ClassAttribute"]),
]

modifiers = [
    ("modifier:public", "calya", "calya-", "bright/open", ["PublicModifier"]),
    ("modifier:private", "nulya", "nulya-", "hidden", ["PrivateModifier"]),
    ("modifier:protected", "varya", "varya-", "to shield", ["ProtectedModifier"]),
    ("modifier:internal", "mirya", "mirya-", "within", ["InternalModifier"]),
    ("modifier:static", "tulca", "tulca-", "firm", ["StaticModifier"]),
    ("modifier:final", "metta", "metta-", "final", ["FinalModifier", "ConstModifier"]),
    ("modifier:const", "tulta", "tulta-", "to steady", ["ConstModifier"]),
    ("modifier:readonly", "hlarë", "hlarë-", "listening only", ["ReadonlyModifier"]),
    ("modifier:mutable", "virya", "virya-", "to change", ["MutableModifier"]),
    ("modifier:async", "linta", "linta-", "swift", ["AsyncModifier"]),
    ("modifier:awaitable", "horta", "horta-", "to urge", ["AwaitableMarker"]),
    ("modifier:volatile", "farina", "fárina-", "hunting, unsettled", ["VolatileModifier"]),
    ("modifier:override", "arta", "arta-", "exalted over", ["OverrideModifier"]),
    ("modifier:virtual", "firya", "firya-", "to fade", ["VirtualModifier"]),
    ("modifier:abstract", "hsaila", "hsaila-", "shadowy", ["AbstractModifier"]),
    ("modifier:sealed", "hresta", "hresta-", "shore boundary", ["SealedModifier"]),
    ("modifier:open", "panta", "panta-", "open", ["OpenModifier"]),
    ("modifier:required", "mahta", "mahta-", "to demand", ["RequiredModifier"]),
    ("modifier:optional", "merna", "merna-", "wishful", ["OptionalModifier"]),
    ("modifier:default", "yáve", "yáve-", "fruit/standard", ["DefaultModifier"]),
    ("modifier:partial", "mitta", "mitta-", "partial", ["PartialModifier"]),
    ("modifier:extern", "eltir", "eltir-", "to look afar", ["ExternModifier"]),
    ("modifier:inline", "aquapa", "aquapa-", "fully close", ["InlineModifier"]),
    ("modifier:noexcept", "úcare", "úcarë-", "without error", ["NoExceptSpecifier"]),
    ("modifier:constexpr", "sanwe", "sanwë-", "thought-known", ["ConstexprSpecifier"]),
    ("modifier:template", "lindal", "lindal-", "song pattern", ["TemplateParameter"]),
    ("modifier:generic", "aila", "aila-", "shining general", ["GenericParameter"]),
    ("modifier:covariant", "telu", "telu-", "ending upward", ["CovariantModifier"]),
    ("modifier:contravariant", "nutelu", "nu-telu-", "ending downward", ["ContravariantModifier"]),
    ("modifier:invariant", "stal", "stal-", "fixed", ["InvariantModifier"]),
    ("modifier:synchronized", "ostya", "ostya-", "to gather together", ["SynchronizedModifier"]),
]

literals = [
    ("literal:int", "min", "min-", "one", ["IntegerLiteral"]),
    ("literal:float", "loar", "loar-", "flood/flow", ["FloatLiteral"]),
    ("literal:string", "quet", "quet-", "speech", ["StringLiteral"]),
    ("literal:bool_true", "anwa", "anwa-", "true", ["BooleanLiteral:true"]),
    ("literal:bool_false", "vanwa", "vanwa-", "lost/false", ["BooleanLiteral:false"]),
    ("literal:null", "unyë", "únyë-", "not", ["NullLiteral", "NoneLiteral"]),
    ("literal:array", "hosty", "hosta-", "collection literal", ["ArrayLiteral", "ListLiteral"]),
    ("literal:object", "sambëa", "sambë-", "house-literal", ["ObjectLiteral", "DictLiteral"]),
    ("literal:regex", "lindë", "lindë-", "song pattern", ["RegexLiteral"]),
    ("literal:template", "lambet", "lambë-", "language template", ["TemplateLiteral"]),
]

structure = [
    ("structure:identifier", "esse", "essë-", "name", ["Identifier"]),
    ("structure:qualifier", "essetil", "essë-", "name path", ["QualifiedName"]),
    ("structure:parameter", "colma", "colma-", "ring, supporting", ["Parameter"]),
    ("structure:argument", "colmar", "colma-", "supporting piece", ["Argument"]),
    ("structure:generic", "lindë", "lindë-", "song/pattern", ["TypeArgument"]),
    ("structure:type_constraint", "nertë", "nertë-", "bond", ["TypeConstraint"]),
    ("structure:where_clause", "mar", "mar-", "dwelling place", ["WhereClause"]),
    ("structure:block_start", "sandion", "sand-", "shielded begin", ["BlockStart"]),
    ("structure:block_end", "sandome", "sand-", "shielded end", ["BlockEnd"]),
    ("structure:line", "tehta", "tehta-", "mark", ["LineSeparator"]),
    ("structure:indent", "lant", "lant-", "drop down", ["Indent"]),
    ("structure:dedent", "halant", "halant-", "lift up", ["Dedent"]),
    ("structure:comma", "sepa", "sepa-", "lip/border", ["CommaSeparator"]),
    ("structure:colon", "hyarmen", "hyarmen-", "south/guide", ["ColonSeparator"]),
    ("structure:semicolon", "hyarmenya", "hyarmen-", "guiding pause", ["SemicolonSeparator"]),
    ("structure:dot", "pica", "pica-", "spot", ["DotSeparator"]),
    ("structure:arrow", "lange", "lange-", "pointing", ["Arrow"]),
    ("structure:fat_arrow", "langewa", "lange-", "heavy pointing", ["FatArrow"]),
    ("structure:ellipsis", "hir", "hir-", "to find ongoing", ["Ellipsis"]),
    ("structure:spread", "palya", "palya-", "to spread", ["SpreadElement"]),
]

specials = [
    ("meta:dictionary_version", "yando", "yando-", "bridge generation", ["DictionaryVersion"]),
    ("meta:payload_marker", "quetten", "quetta-", "speech marker", ["PayloadMarker"]),
    ("meta:unknown", "úment", "úmenta-", "not told", ["UnknownToken"]),
    ("meta:padding", "caita", "caita-", "to lie down", ["Padding"]),
    ("meta:checksum", "hostale", "hostalë-", "collection counting", ["Checksum"]),
    ("meta:version_header", "mindon", "mindon-", "tower signal", ["StreamVersionHeader"]),
    ("meta:stream_start", "yestar", "yestar-", "first day", ["StreamStart"]),
    ("meta:stream_end", "mettar", "mettar-", "ending day", ["StreamEnd"]),
    ("meta:human_readable", "lamen", "lamen-", "animal voice", ["HumanReadable"]),
    ("meta:diagnostic", "tirmar", "tirmar-", "watcher", ["DiagnosticMarker"]),
]

all_specs = (
    core_constructs
    + data_types
    + operators
    + control_flow
    + oop
    + modifiers
    + literals
    + structure
    + specials
)

entries = []
for idx, (key, morpheme, root, gloss, ast_nodes) in enumerate(all_specs, start=1):
    freq = max(20, 2400 - (idx - 1) * 7)
    if idx <= 64:
        encoding = {
            "type": "fixed",
            "bits": 9,
            "code": format(idx - 1, "09b"),
        }
    elif idx <= 192:
        encoding = {
            "type": "prefix",
            "prefix": "10",
            "payload_bits": 12,
            "effective_bits": 14,
            "ordinal": idx - 65,
        }
    else:
        encoding = {
            "type": "prefix",
            "prefix": "110",
            "payload_bits": 15,
            "effective_bits": 18,
            "ordinal": idx - 193,
        }
    entries.append(
        {
            "key": key,
            "morpheme": morpheme,
            "quenya_root": root,
            "gloss": gloss,
            "linguistic_justification": f"The Quenya root '{root}' conveys '{gloss}' which aligns with {key.replace(':', ' ')} semantics across target languages.",
            "ast_nodes": ast_nodes,
            "frequency_per_10k_loc": freq,
            "encoding": encoding,
        }
    )

schema = {"version": "1.0", "entries": entries}

with open(
    "qyn1/resources/morpheme_dictionary/v1_0/dictionary.json",
    "w",
    encoding="utf-8",
) as f:
    json.dump(schema, f, ensure_ascii=False, indent=2)

print(f"Wrote {len(entries)} entries")
