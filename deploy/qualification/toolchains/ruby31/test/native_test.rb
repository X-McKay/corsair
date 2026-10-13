require "digest"
require "json"
require "minitest/autorun"
require "tmpdir"

class NativeTest < Minitest::Test
  def test_native_roundtrip
    value = { "message" => "native Ruby fixture", "numbers" => [1, 2, 3] }
    payload = JSON.generate(value)
    Dir.mktmpdir do |directory|
      path = File.join(directory, "roundtrip.json")
      File.binwrite(path, payload)
      assert_equal value, JSON.parse(File.binread(path))
      assert_equal Digest::SHA256.digest(payload), Digest::SHA256.digest(File.binread(path))
    end
  end

  def test_native_runtime
    assert_equal "3.1", RUBY_VERSION[/\A\d+\.\d+/]
    assert_equal "5.15.0", Minitest::VERSION
  end
end
