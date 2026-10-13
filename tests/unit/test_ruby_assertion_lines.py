"""The Minitest assertion-line reader on authored-test shapes; checked against Prism over 7,377 gem test methods."""
from pathlib import Path

import pytest

from corsair.agents.test_authoring.ruby import ruby_assertion_lines
from corsair.agents.test_authoring.static import assertion_lines

RACK = (Path(__file__).resolve().parents[2] / 'benchmarks/cases/rack-static/test/corsair_static_test.rb').read_text()


def test_rack_reference_test():
    assert ruby_assertion_lines(RACK, 'CorsairStaticTest', 'test_serves_files_under_urls') == (20, 21)
    assert assertion_lines(RACK, 'test/corsair_static_test.rb::CorsairStaticTest#test_does_not_serve_files_outside_urls') == (26, 27)


SHAPES = '''\
module Outer
  class ShapesTest < Minitest::Test
    WORDS = %w[end if do]
    OPTIONS = { if: 1, end: 2, class: :end }

    def helper
      assert false
    end

    def test_shapes
      body = <<~HTML
        <p>end</p>
        if do class
      HTML
      assert_match /end/, body
      assert_equal "if #{"end"} do", body unless body.empty?
      return if body.nil?
      [1].each do |item|
        refute_nil item
      end
      _(body).must_include "p"
      e = assert_raises(ArgumentError) { Integer("x") }
      assert_msg = :assert_equal
      send assert_msg, 1, 1
      def nested
        assert true
      end
      while false do
        flunk
      end
      char = ?e
      assert_equal 1,
        1
    end
  end
end
'''


def test_literals_modifiers_blocks_and_nested_defs():
    assert ruby_assertion_lines(SHAPES, 'Outer::ShapesTest', 'test_shapes') == (15, 16, 19, 21, 22, 29, 32)


@pytest.mark.parametrize('content, message', [
    (SHAPES, 'not defined'),
    (SHAPES + 'class Outer::ShapesTest\n  def test_shapes\n  end\nend\n', 'more than once'),
    ('class T\n  def test_a = assert(true)\nend\n', 'endless method'),
    ('class T\n  def test_a\n    assert "x\n  end\nend\n', 'unterminated'),
    ('class T\n  def test_a\n    assert true\nend\n', 'unclosed'),
    ('=begin\n=end\nclass T\n  def test_a\n  end\nend\n', '=begin'),
])
def test_refusals(content, message):
    method = 'test_missing' if message == 'not defined' else 'test_shapes' if content.startswith('module') else 'test_a'
    cls = 'Outer::ShapesTest' if content.startswith('module') else 'T'
    with pytest.raises(ValueError, match=message):
        ruby_assertion_lines(content, cls, method)


def test_a_method_without_assertions_is_refused_by_the_authoring_check():
    with pytest.raises(ValueError, match='has no assertion'):
        assertion_lines('class T < Minitest::Test\n  def test_a\n    1\n  end\nend\n', 't.rb::T#test_a')
