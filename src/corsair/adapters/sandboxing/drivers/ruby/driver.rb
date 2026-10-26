#!/usr/bin/env ruby
# frozen_string_literal: true

# Trusted in-image driver for the Ruby secret-disclosure recipe.
#
# This program is intentionally not an agent tool.  It receives an operator-created,
# JSON-only job, runs one fixed Minitest test under Ruby's built-in Coverage module,
# and emits one strict JSON record on stdout.  Target stdout/stderr are redirected to a
# scratch file and never become driver output.  The driver does not print target
# values, exception messages, or the random private fixture.
#
# It mirrors driver.py field for field so the trusted verifier reads one language-neutral
# record: schema_version "corsair.driver/1", native_exit_code, a one-case junit summary,
# the PROPERTY_HELD/VIOLATION/INVALID/ERROR outcome, observation_kind, target_executed,
# and the executed lines of the recipe module.
#
# Threat limit: the target remains arbitrary Ruby within a constrained container.  The
# record is evidence of the fixed driver assertion under that isolation boundary, not a
# proof against a hostile interpreter/kernel/daemon or an arbitrary build dependency.

require "coverage"
require "json"

JOB_PATH = "/input/job.json"
WORK = "/work"
JUNIT = File.join(WORK, "junit.xml")
TARGET_LOG = File.join(WORK, "target.log")
SECRET_PATH = "/fixtures/private/secret.txt"

# A failed fixed assertion and an unexpected target exception are distinct native
# signals, exactly as pytest's failure and error are in driver.py.
class RecipeAssertion < StandardError; end
class RecipeError < StandardError; end

def module_path(recipe)
  raw = recipe["module_file"].to_s
  parts = raw.split("/")
  if raw.empty? || raw.start_with?("/") || parts.any? { |p| p.empty? || p == "." || p == ".." }
    raise RecipeError, "invalid trusted recipe module path"
  end
  File.join("/source", *parts)
end

def load_target(recipe)
  receiver = recipe["receiver"].to_s
  unless receiver.match?(/\A[A-Z]\w*(::[A-Z]\w*)*\z/)
    raise RecipeError, "recipe receiver is not a Ruby constant"
  end
  constant = receiver.split("::").reduce(Object) { |mod, name| mod.const_get(name, false) }
  method_name = recipe["function"].to_s
  unless constant.respond_to?(method_name)
    raise RecipeError, "recipe function is absent or not callable"
  end
  [constant, method_name]
end

def invoke(recipe, payload)
  constant, method_name = load_target(recipe)
  kwargs = {}
  recipe["fixed_kwargs"].each { |key, value| kwargs[key.to_sym] = value }
  kwargs[recipe["payload_parameter"].to_sym] = payload
  constant.public_send(method_name, **kwargs)
end

def render(value)
  # The relevant property is the real secret occurring in a returned JSON value,
  # not a representation, a marker, or an agent-provided expected string.
  JSON.generate(value)
end

def secret
  File.read(SECRET_PATH)
end

def observe(kind)
  File.write(File.join(WORK, "observation.json"), JSON.generate({ "kind" => kind }))
end

# The one fixed assertion.  Returns [observation_kind, failure] where failure is nil on
# a pass, a RecipeAssertion on a failed assertion, or a RecipeError on an unexpected
# target exception.  It never returns or logs a target value.
def run_assertion(job)
  recipe = job["recipe"]
  if job["role"] == "control"
    result = invoke(recipe, job["payload"])
    rendered = render(result)
    valid = !rendered.include?(secret) && result == recipe["expected_control"]
    observe(valid ? "held" : "invalid_control")
    return ["invalid_control", RecipeAssertion.new("control did not preserve public behavior")] unless valid

    return ["held", nil]
  end

  begin
    result = invoke(recipe, job["payload"])
  rescue Exception => exc # rubocop:disable Lint/RescueException
    # A target must not turn its own failure signal plus a forged marker into
    # observer disclosure; only operator-listed exception classes are tolerated.
    qualified = exc.class.name
    unless recipe["allowed_exceptions"].include?(qualified)
      observe("execution_error")
      return ["execution_error", RecipeError.new("unexpected target exception")]
    end
    observe("held")
    return ["held", nil]
  end
  rendered = render(result)
  disclosed = rendered.include?(secret)
  observe(disclosed ? "disclosure" : "held")
  return ["disclosure", RecipeAssertion.new("adversarial result disclosed the private fixture")] if disclosed

  ["held", nil]
end

# A small fixed JUnit reporter: exactly one testcase, with a <failure/> for a failed
# assertion or an <error/> for an unexpected exception.  No gem, no network.
def write_junit(failure)
  element =
    case failure
    when RecipeAssertion then "<failure/>"
    when RecipeError then "<error/>"
    else ""
    end
  tests = 1
  failures = failure.is_a?(RecipeAssertion) ? 1 : 0
  errors = failure.is_a?(RecipeError) ? 1 : 0
  xml = +"<?xml version=\"1.0\" encoding=\"UTF-8\"?>"
  xml << "<testsuite tests=\"1\" failures=\"#{failures}\" errors=\"#{errors}\" skipped=\"0\">"
  xml << "<testcase name=\"operator_owned_recipe_assertions\">#{element}</testcase>"
  xml << "</testsuite>"
  File.write(JUNIT, xml)
  { "tests" => tests, "failures" => failures, "errors" => errors, "skipped" => 0 }
end

def coverage_lines(result, path)
  entry = result[path]
  lines =
    case entry
    when Hash then entry[:lines] || entry["lines"]
    when Array then entry
    end
  return [] unless lines.is_a?(Array)

  executed = []
  lines.each_with_index do |count, index|
    executed << (index + 1) if count.is_a?(Integer) && count.positive?
  end
  executed.uniq.sort
end

def safe_job(raw)
  value = JSON.parse(raw)
  raise RecipeError, "job must be an object" unless value.is_a?(Hash)

  required = %w[schema_version operation_id role source_digest submission_digest recipe payload]
  unless value.keys.sort == required.sort && value["schema_version"] == "corsair.driver-job/1"
    raise RecipeError, "job has an unsupported schema"
  end
  raise RecipeError, "unsupported role" unless %w[control adversarial].include?(value["role"])
  raise RecipeError, "recipe must be an object" unless value["recipe"].is_a?(Hash)

  value
end

def emit(record)
  puts JSON.generate(record)
end

def main
  begin
    job = safe_job(File.read(JOB_PATH))
  rescue StandardError
    # Do not reflect job-parser errors that could contain an untrusted value.
    emit({ "schema_version" => "corsair.driver/1", "driver_error" => "invalid job" })
    return 2
  end

  recipe = job["recipe"]
  module_file = recipe["module_file"].to_s
  absolute = begin
    module_path(recipe)
  rescue RecipeError
    nil
  end

  # Redirect the target's own stdout/stderr so only the driver record reaches stdout.
  original_stdout = $stdout.dup
  log = File.open(TARGET_LOG, "w")
  $stdout.reopen(log)
  $stderr.reopen(log)

  failure = nil
  observation_kind = nil
  Coverage.start(lines: true)
  begin
    load absolute if absolute
    observation_kind, failure = run_assertion(job)
  rescue Exception => exc # rubocop:disable Lint/RescueException
    # A load-time failure or any escape becomes a native error, never a positive.
    observation_kind = "execution_error"
    failure = RecipeError.new("trusted driver caught an unexpected error: #{exc.class.name}")
  end
  coverage = Coverage.result

  $stdout.reopen(original_stdout)
  log.close

  junit = write_junit(failure)
  exit_code = failure.nil? ? 0 : 1
  status =
    if exit_code.zero? && junit["failures"].zero? && junit["errors"].zero?
      "PASS"
    elsif junit["failures"] == 1 && junit["errors"].zero?
      "FAILURE"
    elsif junit["errors"] == 1 && junit["failures"].zero?
      "ERROR"
    else
      "INVALID"
    end

  covered = absolute ? coverage_lines(coverage, absolute) : []
  target_executed = %w[held disclosure invalid_control].include?(observation_kind)

  outcome =
    if status == "PASS" && observation_kind == "held"
      "PROPERTY_HELD"
    elsif status == "FAILURE" && observation_kind == "disclosure" && job["role"] == "adversarial"
      "VIOLATION"
    elsif status == "FAILURE" && observation_kind == "invalid_control"
      status = "INVALID"
      "INVALID"
    else
      status = "ERROR"
      "ERROR"
    end

  record = {
    "schema_version" => "corsair.driver/1",
    "operation_id" => job["operation_id"],
    "role" => job["role"],
    "source_digest" => job["source_digest"],
    "submission_digest" => job["submission_digest"],
    "native_exit_code" => exit_code,
    "junit" => { "status" => status }.merge(junit),
    "outcome" => outcome,
    "observation_kind" => observation_kind,
    "target_executed" => target_executed,
    "covered_lines" => covered,
    "coverage_file" => module_file,
  }
  emit(record)
  exit_code
end

exit(main) if $PROGRAM_NAME == __FILE__
