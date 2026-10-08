#!/usr/bin/env bats
load helpers

setup() {
  setup_sandbox
  SCRIPT="$TEST_REPO/scripts/task-env.sh"
  unset MISE_ENV usage_profile
}

# Sources the script the way a task does and prints the environment it chose.
resolve() {
  run env "$@" sh -c '. "$1" && printf %s "$mise_env"' sh "$SCRIPT"
}

@test "--profile alone selects the environment" {
  resolve usage_profile=work
  [ "$status" -eq 0 ]
  [ "$output" = "work" ]
}

@test "DEVSETUP_PROFILE alone selects the environment" {
  resolve DEVSETUP_PROFILE=work
  [ "$status" -eq 0 ]
  [ "$output" = "work" ]
}

@test "--profile and DEVSETUP_PROFILE may agree" {
  resolve usage_profile=personal DEVSETUP_PROFILE=personal
  [ "$status" -eq 0 ]
  [ "$output" = "personal" ]
}

@test "--profile and DEVSETUP_PROFILE must not disagree" {
  resolve usage_profile=work DEVSETUP_PROFILE=personal
  [ "$status" -eq 64 ]
  [[ "$output" == *"--profile work conflicts with DEVSETUP_PROFILE=personal"* ]]
}

@test "an unknown profile is refused from either source" {
  resolve usage_profile=guest
  [ "$status" -eq 64 ]
  [[ "$output" == *"must be personal or work, not 'guest'"* ]]
  resolve DEVSETUP_PROFILE=staging
  [ "$status" -eq 64 ]
  [[ "$output" == *"must be personal or work, not 'staging'"* ]]
}

@test "the recorded MISE_ENV applies when nothing is passed and a flag overrides it" {
  resolve MISE_ENV=work
  [ "$status" -eq 0 ]
  [ "$output" = "work" ]
  resolve MISE_ENV=work usage_profile=personal
  [ "$status" -eq 0 ]
  [ "$output" = "personal" ]
}

@test "personal is the last resort" {
  resolve
  [ "$status" -eq 0 ]
  [ "$output" = "personal" ]
}
