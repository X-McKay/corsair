require 'minitest/autorun'

class CanaryTest < Minitest::Test
  def test_canary
    File.write(File.join(ENV.fetch('CORSAIR_MARKER_DIR'), 'start'), '')
    total = 1 + 1
    holds = total == 3
    File.write(File.join(ENV.fetch('CORSAIR_MARKER_DIR'), 'check'), holds ? 'holds' : 'violated')
    assert holds, ENV.fetch('CORSAIR_TOKEN')
    File.write(File.join(ENV.fetch('CORSAIR_MARKER_DIR'), 'end'), '')
  end
end
