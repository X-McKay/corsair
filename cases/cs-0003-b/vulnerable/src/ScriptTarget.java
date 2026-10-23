// SPDX-License-Identifier: Apache-2.0
package fixture;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ScriptTarget {
    public static void main(String[] args) throws Exception {
        Path root = Path.of("allowed").toAbsolutePath().normalize();
        Path candidate = root.resolve(args[0]).normalize();
        System.out.print(Files.readString(candidate));
    }
}
