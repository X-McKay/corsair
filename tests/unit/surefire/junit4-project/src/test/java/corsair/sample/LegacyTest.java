package corsair.sample;

import static org.junit.Assert.assertEquals;
import org.junit.Test;

public class LegacyTest {
    @Test public void control() { System.out.println("CONTROL_RAN"); assertEquals(1, 1); }
    @Test public void security() { System.out.println("SECURITY_RAN"); assertEquals("x", "y"); }
}
