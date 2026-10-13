require "test_helper"

module Widget
  class CorsairTest < Minitest::Test
    def test_control
      assert_equal "a", Widget.escape("a")
    end

    def test_security
      assert_equal "&lt;b&gt;", Widget.escape("<b>")
    end

    def test_fixed
      assert_equal "&lt;b", Widget.escape("<b")
    end

    def test_error
      raise ArgumentError, "boom"
    end

    def test_skipped
      skip "not here"
    end

    def test_unselected
      flunk "must not run"
    end
  end
end

class OtherTest < Minitest::Test
  def test_control
    flunk "other class must not run"
  end
end
