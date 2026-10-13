package corsair.sample;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.nio.file.Path;
import org.junit.jupiter.api.Test;

class DocumentsTest {
    private static final Path ROOT = Path.of("/srv/documents");

    @Test void readsOrdinaryDocument() {
        Path resolved = Documents.resolve(ROOT, "report.txt");
        System.out.println("CONTROL_RESOLVED=" + resolved);
        assertEquals(ROOT.resolve("report.txt"), resolved);
    }

    @Test void refusesTraversalOutsideRoot() {
        Path resolved = Documents.resolve(ROOT, "../secret.txt");
        System.out.println("SECURITY_RESOLVED=" + resolved);
        assertTrue(resolved.startsWith(ROOT), () -> "resolved outside the root: " + resolved);
    }

    @Test void unrelatedThirdTest() {
        assertTrue(true);
    }
}
