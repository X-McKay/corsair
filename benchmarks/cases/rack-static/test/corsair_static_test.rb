# frozen_string_literal: true

# Classic-Minitest form of two rack test/spec_static.rb examples (MIT, see LICENSE): "serves files" (unchanged
# behavior, the control) and "does not serve files outside :urls", added by the CVE-2025-27610 fix 50caab7.
require_relative 'helper'
require_relative '../lib/rack/static'
require_relative '../lib/rack/lint'
require_relative '../lib/rack/mock_request'

class CorsairStaticTest < Minitest::Test
  ROOT = File.expand_path(__dir__)

  def request
    app = lambda { |_env| [200, { "content-type" => "text/plain" }, ["Hello World"]] }
    Rack::MockRequest.new(Rack::Lint.new(Rack::Static.new(app, urls: ["/cgi"], root: ROOT)))
  end

  def test_serves_files_under_urls
    res = request.get("/cgi/test")
    assert res.ok?
    assert_match(/ruby/, res.body)
  end

  def test_does_not_serve_files_outside_urls
    res = request.get("/cgi/../#{File.basename(__FILE__)}")
    assert res.ok?
    assert_equal "Hello World", res.body
  end
end
