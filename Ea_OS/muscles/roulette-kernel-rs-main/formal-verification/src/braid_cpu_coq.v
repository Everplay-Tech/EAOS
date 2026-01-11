(* Coq Skeleton for Verified Braid CPU Operations *)
(* Generated for MetaCoq extraction to Rust *)

Require Import List.
Require Import Arith.
Require Import Nat.

(* Braid generator: Left or Right crossing *)
Inductive Generator : Type :=
| Left : nat -> Generator
| Right : nat -> Generator.

(* Braid word as list of generators *)
Definition BraidWord := list Generator.

(* CPU state: registers as strand values, current braid word *)
Record CPUState (n : nat) : Type := {
  registers : list nat;  (* strand values, length n *)
  braid_word : BraidWord;
  strand_count : registers = n  (* invariant: exactly n strands *)
}.

(* Strand index type (0 to n-1) *)
Definition strand_index (n : nat) := {i : nat | i < n}.

(* Read register: get strand value *)
Definition read_register {n : nat} (state : CPUState n) (i : strand_index n) : nat :=
  nth (proj1_sig i) (registers n state) 0.

(* Write register: update strand and append generator to braid *)
Definition write_register {n : nat} (state : CPUState n) 
  (i : strand_index n) (value : nat) (gen : Generator) : CPUState n :=
  let new_registers := replace_nth (proj1_sig i) value (registers n state) in
  {| registers := new_registers;
     braid_word := gen :: (braid_word n state);
     strand_count := eq_refl |}.

(* Proof: write_register preserves strand count *)
Theorem write_preserves_strand_count : forall n state i v g,
  strand_count n (write_register state i v g) = strand_count n state.
Proof.
  intros. simpl. reflexivity.
Qed.

(* Braid validity: generators operate on valid strands *)
Definition valid_generator (n : nat) (g : Generator) : Prop :=
  match g with
  | Left i => i < n - 1
  | Right i => i < n - 1
  end.

(* Valid braid word *)
Definition valid_braid_word (n : nat) (w : BraidWord) : Prop :=
  Forall (valid_generator n) w.

(* Proof: write_register with valid generator preserves validity *)
Theorem write_preserves_validity : forall n state i v g,
  valid_generator n g ->
  valid_braid_word n (braid_word n state) ->
  valid_braid_word n (braid_word n (write_register state i v g)).
Proof.
  intros n state i v g Hg Hw.
  simpl. constructor; assumption.
Qed.

(* Theorem: Identity braid preserves validity *)
Theorem identity_preserves_validity : forall n,
  valid_braid_word n nil.
Proof.
  intros. simpl. constructor.
Qed.

(* Theorem: Braid composition preserves validity *)
Theorem compose_preserves_validity : forall n w1 w2,
  valid_braid_word n w1 ->
  valid_braid_word n w2 ->
  valid_braid_word n (w1 ++ w2).
Proof.
  intros n w1 w2 H1 H2.
  apply Forall_app; assumption.
Qed.

(* Theorem: Strand count invariant preservation *)
Theorem operations_preserve_strand_count : forall n state i v g,
  strand_count n (write_register state i v g) = n.
Proof.
  intros. reflexivity.
Qed.

(* MetaCoq extraction hints *)
From MetaCoq.Template Require Import All.

(* Quote the definitions for extraction *)
MetaCoq Run (tmQuote CPUState >>= tmPrint).
MetaCoq Run (tmQuote read_register >>= tmPrint).
MetaCoq Run (tmQuote write_register >>= tmPrint).
MetaCoq Run (tmQuote valid_braid_word >>= tmPrint).