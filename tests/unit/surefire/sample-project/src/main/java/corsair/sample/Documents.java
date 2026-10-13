package corsair.sample;

import java.nio.file.Path;

public final class Documents {
    private Documents() {}

    public static Path resolve(Path root, String name) {
        return root.resolve(name).normalize();
    }
}
