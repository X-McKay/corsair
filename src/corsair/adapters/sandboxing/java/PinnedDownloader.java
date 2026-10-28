import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;

/** Downloads one build-time observer dependency and verifies its immutable publisher hash. */
public final class PinnedDownloader {
  private PinnedDownloader() {}

  public static void main(String[] arguments) throws Exception {
    if (arguments.length != 4) {
      System.exit(2);
    }
    String algorithm = arguments[0];
    URI source = URI.create(arguments[1]);
    byte[] expected = hex(arguments[2]);
    Path destination = Path.of(arguments[3]);
    MessageDigest digest = MessageDigest.getInstance(algorithm);
    HttpClient client = HttpClient.newBuilder().followRedirects(HttpClient.Redirect.NORMAL).build();
    HttpResponse<InputStream> response =
        client.send(HttpRequest.newBuilder(source).GET().build(), HttpResponse.BodyHandlers.ofInputStream());
    if (response.statusCode() != 200) {
      System.exit(2);
    }
    Files.createDirectories(destination.getParent());
    Path temporary = Files.createTempFile(destination.getParent(), ".download-", ".part");
    try (InputStream input = response.body(); var output = Files.newOutputStream(temporary)) {
      byte[] buffer = new byte[8192];
      for (int read; (read = input.read(buffer)) >= 0; ) {
        if (read > 0) {
          digest.update(buffer, 0, read);
          output.write(buffer, 0, read);
        }
      }
    }
    if (!MessageDigest.isEqual(expected, digest.digest())) {
      Files.deleteIfExists(temporary);
      System.exit(2);
    }
    Files.move(temporary, destination, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
  }

  private static byte[] hex(String value) {
    if ((value.length() & 1) != 0 || !value.matches("[0-9a-f]+")) {
      throw new IllegalArgumentException("invalid digest");
    }
    byte[] decoded = new byte[value.length() / 2];
    for (int index = 0; index < decoded.length; index++) {
      decoded[index] = (byte) Integer.parseInt(value.substring(index * 2, index * 2 + 2), 16);
    }
    return decoded;
  }
}
