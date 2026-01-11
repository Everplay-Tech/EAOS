import Lake
open Lake DSL

package braid_t9_godel_verification {
  -- add package configuration options here
}

lean_lib BraidT9GodelVerification {
  -- add library configuration options here
}

@[default_target]
lean_exe braid_t9_godel_verification {
  root := `Main
}