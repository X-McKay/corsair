require 'erb'

module Greeting
  TEMPLATE = ERB.new('<p>Hello, <%= name %>!</p>')

  # Render the greeting banner for a visitor.
  def self.render(name)
    TEMPLATE.result_with_hash(name: name)
  end
end
