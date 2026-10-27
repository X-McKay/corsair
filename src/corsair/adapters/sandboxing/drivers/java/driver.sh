#!/usr/bin/env bash
# Trusted in-image driver for the Java secret-disclosure recipe.
#
# Like the Python driver, this is NOT an agent tool. It receives an operator-created,
# JSON-only job at /input/job.json, writes a fixed JUnit 5 test, compiles the admitted
# source with `javac` alone (no build tool, no dependency resolution), runs the test
# under the JaCoCo agent, converts the exec file to XML with the JaCoCo CLI, and emits
# exactly one strict JSON record on stdout. The target's own stdout/stderr and the
# compiler/launcher output go to work files, never to this script's stdout. The driver
# never prints target return values, exception messages, or the random private fixture.
#
# Threat limit: the target remains arbitrary Java inside a constrained container. The
# record is evidence of the fixed driver assertion under that isolation boundary, not a
# defence against a hostile JVM/kernel/daemon or an arbitrary build dependency.
set -u

JUNIT_JAR=/opt/corsair/junit-standalone.jar
JACOCO_AGENT=/opt/corsair/jacocoagent.jar
JACOCO_CLI=/opt/corsair/jacococli.jar
JOB=/input/job.json
WORK=/work
REPORTS="$WORK/reports"
CLASSES="$WORK/classes"
# The container's own cgroup v2 CPU accounting (Docker's private cgroup namespace).
CPU_STAT=/sys/fs/cgroup/cpu.stat

# Integer microseconds of the realtime clock (bash 5 EPOCHREALTIME, "s.us").
now_usec() {
    local seconds=${EPOCHREALTIME%.*} micros=${EPOCHREALTIME#*.}
    echo $((seconds * 1000000 + 10#$micros))
}

# The cgroup v2 usage_usec CPU total, or "null" when the file or field is absent.
cgroup_cpu_usec() {
    local key value
    if [ -r "$CPU_STAT" ]; then
        while read -r key value; do
            if [ "$key" = "usage_usec" ] && [[ "$value" =~ ^[0-9]+$ ]]; then
                echo "$value"
                return
            fi
        done <"$CPU_STAT"
    fi
    echo null
}

emit_driver_error() {
    # No secret-bearing field is reflected: only a fixed reason string.
    printf '{"schema_version":"corsair.driver/1","driver_error":"%s"}\n' "$1"
}

# --- Validate the job (shape only; never reflect untrusted values) -----------------
if ! jq -e . "$JOB" >/dev/null 2>&1; then
    emit_driver_error "invalid job"
    exit 2
fi
schema=$(jq -r '.schema_version // empty' "$JOB")
role=$(jq -r '.role // empty' "$JOB")
if [ "$schema" != "corsair.driver-job/1" ]; then
    emit_driver_error "invalid job"
    exit 2
fi
if [ "$role" != "control" ] && [ "$role" != "adversarial" ]; then
    emit_driver_error "invalid job"
    exit 2
fi
for key in operation_id source_digest submission_digest recipe payload; do
    if ! jq -e "has(\"$key\")" "$JOB" >/dev/null 2>&1; then
        emit_driver_error "invalid job"
        exit 2
    fi
done

operation_id=$(jq -r '.operation_id' "$JOB")
source_digest=$(jq -r '.source_digest' "$JOB")
submission_digest=$(jq -r '.submission_digest' "$JOB")
module_file=$(jq -r '.recipe.module_file' "$JOB")
entry_class=$(jq -r '.recipe.entry_class' "$JOB")
method=$(jq -r '.recipe.method' "$JOB")

mkdir -p "$CLASSES" "$REPORTS"
# The model-controlled payload and operator-fixed scalars are written as raw bytes so
# the fixed Java test consumes them without a JSON parser in the target JVM.
printf '%s' "$role" >"$WORK/role.txt"
printf '%s' "$entry_class" >"$WORK/entry_class.txt"
printf '%s' "$method" >"$WORK/method.txt"
jq -rj '.payload' "$JOB" >"$WORK/payload.bin"
jq -rj '.recipe.expected_control' "$JOB" >"$WORK/expected.bin"
jq -r '.recipe.allowed_exceptions[]?' "$JOB" >"$WORK/allowed.txt"

cat >"$WORK/RecipeTest.java" <<'JAVA'
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class RecipeTest {
    private static String read(String path) throws Exception {
        return Files.readString(Path.of(path));
    }

    private static String secret() throws Exception {
        return Files.readString(Path.of("/fixtures/private/secret.txt"));
    }

    private static void observe(String kind) throws Exception {
        // Only the fixed observation kind is written; never a target value.
        Files.writeString(Path.of("/work/observation.json"), "{\"kind\":\"" + kind + "\"}");
    }

    private static String render(Object value) {
        // The relevant property is the real secret occurring in the returned value's
        // text, not a representation, marker, or agent-provided expected string.
        return String.valueOf(value);
    }

    @Test
    void operatorOwnedRecipeAssertions() throws Exception {
        String role = read("/work/role.txt").trim();
        String entryClass = read("/work/entry_class.txt").trim();
        String methodName = read("/work/method.txt").trim();
        String payload = read("/work/payload.bin");
        String expected = read("/work/expected.bin");
        List<String> allowed = Files.readAllLines(Path.of("/work/allowed.txt"));

        Class<?> target = Class.forName(entryClass);
        Method method = target.getMethod(methodName, String.class);
        Object instance =
                Modifier.isStatic(method.getModifiers())
                        ? null
                        : target.getDeclaredConstructor().newInstance();

        if (role.equals("control")) {
            Object result = render(method.invoke(instance, payload));
            boolean valid = !((String) result).contains(secret()) && result.equals(expected);
            observe(valid ? "held" : "invalid_control");
            assertTrue(valid, "control did not preserve expected public behavior");
            return;
        }

        Object result;
        try {
            result = method.invoke(instance, payload);
        } catch (InvocationTargetException invocation) {
            // A target must not turn its own failure signal plus a forged marker into
            // observer disclosure: only operator-whitelisted exceptions are "held".
            Throwable cause = invocation.getCause();
            String qualified = cause.getClass().getName();
            if (!allowed.contains(qualified)) {
                observe("execution_error");
                throw new RuntimeException("unexpected target exception");
            }
            observe("held");
            return;
        }
        boolean disclosed = render(result).contains(secret());
        observe(disclosed ? "disclosure" : "held");
        assertFalse(disclosed, "adversarial result disclosed the private fixture");
    }
}
JAVA

# --- Compile the admitted source with javac alone ----------------------------------
# Wall time covers compiling the admitted source with the fixed test and running it.
started_usec=$(now_usec)
mapfile -t source_files < <(
    jq -r '.recipe.source_roots[]' "$JOB" | while read -r root; do
        [ -d "/source/$root" ] && find "/source/$root" -name '*.java'
    done
)
compile_ok=1
if [ "${#source_files[@]}" -eq 0 ]; then
    compile_ok=0
elif ! javac -encoding UTF-8 -d "$CLASSES" -cp "$JUNIT_JAR" \
    "${source_files[@]}" "$WORK/RecipeTest.java" >"$WORK/javac.log" 2>&1; then
    compile_ok=0
fi

native_exit_code=2
wall_usec=$(($(now_usec) - started_usec))
if [ "$compile_ok" -eq 1 ]; then
    java "-javaagent:${JACOCO_AGENT}=destfile=$WORK/jacoco.exec" \
        -jar "$JUNIT_JAR" execute -cp "$CLASSES" --select-class=RecipeTest \
        --reports-dir="$REPORTS" --disable-banner --disable-ansi-colors \
        >"$WORK/junit.log" 2>&1
    native_exit_code=$?
    wall_usec=$(($(now_usec) - started_usec))
    # Coverage conversion runs only after the launcher exits; the container deadline
    # continues to govern the whole driver process. A missing report stays invalid.
    java -jar "$JACOCO_CLI" report "$WORK/jacoco.exec" \
        --classfiles "$CLASSES" --xml "$WORK/jacoco.xml" \
        >"$WORK/jacoco.log" 2>&1
fi

# --- Project the native reports into the strict record -----------------------------
# The console launcher writes one report per registered engine (jupiter, vintage,
# platform-suite); only jupiter carries this JUnit 5 test. Aggregate across all so the
# empty engine reports contribute zero rather than masking the real testcase.
count_nodes() {
    local total=0 file count
    for file in "$REPORTS"/*.xml; do
        [ -f "$file" ] || continue
        count=$(xmllint --xpath "count($1)" "$file" 2>/dev/null)
        total=$((total + ${count:-0}))
    done
    echo "$total"
}
tests=0
failures=0
errors=0
skipped=0
status="MISSING"
if ls "$REPORTS"/*.xml >/dev/null 2>&1; then
    tests=$(count_nodes '//testcase')
    if [ "$tests" = "1" ]; then
        failures=$(count_nodes '//testcase/failure')
        errors=$(count_nodes '//testcase/error')
        skipped=$(count_nodes '//testcase/skipped')
        if [ "$native_exit_code" = "0" ] && [ "$failures" = "0" ] && [ "$errors" = "0" ] \
            && [ "$skipped" = "0" ]; then
            status="PASS"
        elif [ "$native_exit_code" != "0" ] && [ "$failures" = "1" ] && [ "$errors" = "0" ] \
            && [ "$skipped" = "0" ]; then
            status="FAILURE"
        elif [ "$native_exit_code" != "0" ] && [ "$errors" = "1" ] && [ "$failures" = "0" ] \
            && [ "$skipped" = "0" ]; then
            status="ERROR"
        else
            status="INVALID"
        fi
    else
        status="INVALID"
    fi
fi

# Covered lines (ci>0) for exactly the recipe module's source file.
covered="[]"
if [ -f "$WORK/jacoco.xml" ]; then
    rel="$module_file"
    while read -r root; do
        case "$module_file" in
            "$root"/*) rel="${module_file#"$root"/}" ;;
        esac
    done < <(jq -r '.recipe.source_roots[]' "$JOB")
    # JaCoCo names packages by their "/"-separated path under the source root (e.g.
    # "com/example") and the default package "", whereas dirname yields "." for a
    # top-level source file. Querying "." would find nothing and void all coverage.
    pkg=$(dirname "$rel")
    if [ "$pkg" = "." ]; then
        pkg=""
    fi
    src=$(basename "$rel")
    lines=$(xmllint --xpath \
        "//package[@name=\"$pkg\"]/sourcefile[@name=\"$src\"]/line[number(@ci)>0]/@nr" \
        "$WORK/jacoco.xml" 2>/dev/null \
        | grep -oE 'nr="[0-9]+"' | grep -oE '[0-9]+')
    if [ -n "$lines" ]; then
        covered=$(printf '%s\n' "$lines" | jq -s 'unique')
    fi
fi

observation_kind=$(jq -r '.kind // empty' "$WORK/observation.json" 2>/dev/null)
if [ -z "$observation_kind" ]; then
    observation_kind="null"
fi

# Outcome mapping, identical in spirit to the Python driver.
outcome="ERROR"
if [ "$status" = "PASS" ] && [ "$observation_kind" = "held" ]; then
    outcome="PROPERTY_HELD"
elif [ "$status" = "FAILURE" ] && [ "$observation_kind" = "disclosure" ] \
    && [ "$role" = "adversarial" ]; then
    outcome="VIOLATION"
elif [ "$status" = "FAILURE" ] && [ "$observation_kind" = "invalid_control" ]; then
    outcome="INVALID"
    status="INVALID"
else
    outcome="ERROR"
    status="ERROR"
fi

target_executed=false
case "$observation_kind" in
    held | disclosure | invalid_control) target_executed=true ;;
esac

jq -cn \
    --arg op "$operation_id" \
    --arg role "$role" \
    --arg sd "$source_digest" \
    --arg subd "$submission_digest" \
    --argjson exit "$native_exit_code" \
    --arg status "$status" \
    --argjson tests "$tests" \
    --argjson failures "$failures" \
    --argjson errors "$errors" \
    --argjson skipped "$skipped" \
    --arg outcome "$outcome" \
    --arg kind "$observation_kind" \
    --argjson executed "$target_executed" \
    --argjson covered "$covered" \
    --arg coverage_file "$module_file" \
    --argjson wall_usec "$wall_usec" \
    --argjson cpu_usec "$(cgroup_cpu_usec)" \
    '{schema_version:"corsair.driver/1",operation_id:$op,role:$role,source_digest:$sd,
      submission_digest:$subd,native_exit_code:$exit,
      junit:{status:$status,tests:$tests,failures:$failures,errors:$errors,skipped:$skipped},
      outcome:$outcome,observation_kind:($kind|if .=="null" then null else . end),
      target_executed:$executed,covered_lines:$covered,coverage_file:$coverage_file,
      wall_usec:$wall_usec}
      + (if $cpu_usec == null then {} else {cpu_usec:$cpu_usec} end)'

# Deliberately the launcher's native status (or compile failure), not a success inversion.
exit "$native_exit_code"
